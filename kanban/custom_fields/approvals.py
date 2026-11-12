# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Cryptographic manifest escalation approvals and tamper auto-revocation.

KB-P5-12, S13.2, S4.2, S3.2.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import select, text

from database.models.custom_field import CustomFieldDefinition
from database.models.custom_field_approval import CustomFieldApproval
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.custom_fields import (
    CustomFieldApprovalApproveRequest,
    CustomFieldApprovalRequestCreate,
    CustomFieldApprovalResponse,
)
from kanban.security import load_key_material
from kanban.security.keys import derive_subkey
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.projects import get_project_or_404

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

AAL2_MIN_LEVEL: Final[int] = 2
AAL2_FRESHNESS_SECONDS: Final[int] = 900
HMAC_PURPOSE: Final[str] = "custom-field-approval/v1"
SHA256_BYTE_LEN: Final[int] = 32

# S13.2 Scope x Principal Matrix
REQUIRED_APPROVER_TIERS: Final[dict[tuple[str, str], str | None]] = {
    ("PROJECT", "INVOKING_USER"): None,
    ("PROJECT", "PROJECT_ADMIN_SP"): "PROJECT_ADMIN",
    ("WORKSPACE", "INVOKING_USER"): "WORKSPACE_ADMIN",
    ("WORKSPACE", "PROJECT_ADMIN_SP"): "WORKSPACE_ADMIN",
    ("SERVER", "INVOKING_USER"): "SERVER_ADMIN_DUAL",
    ("SERVER", "SERVER_ADMIN_SP"): "SERVER_ADMIN_DUAL",
}


class ApprovalRevokedError(Exception):
    """Raised when custom field execution authorization fails closed."""

    def __init__(self, message: str, code: str = "APPROVAL_REVOKED") -> None:
        """Initialize fail-closed authorization error."""
        super().__init__(message)
        self.code = code


def validate_escalation_tuple(target_scope: str, credential_mode: str) -> str | None:
    """Validate (target_scope, credential_mode) against the S13.2 matrix."""
    key = (target_scope, credential_mode)
    if key not in REQUIRED_APPROVER_TIERS:
        msg = (
            f"The combination of scope '{target_scope}' and credential mode "
            f"'{credential_mode}' is not permitted"
        )
        raise ProblemException(
            code="ESCALATION_COMBO_INVALID",
            status=422,
            title="Escalation Combo Invalid",
            detail=msg,
        )
    return REQUIRED_APPROVER_TIERS[key]


def required_approver_tier(target_scope: str, credential_mode: str) -> str | None:
    """Return required approver tier for given tuple, or None if no escalation needed."""
    return validate_escalation_tuple(target_scope, credential_mode)


def compute_approval_signature_hmac(  # noqa: PLR0913, PLR0917
    field_id: uuid.UUID,
    manifest_sha256: bytes,
    target_scope: str,
    credential_mode: str,
    primary_approver_id: uuid.UUID,
    secondary_approver_id: uuid.UUID | None,
    auth_pepper: bytes,
) -> bytes:
    """Compute 32-byte HMAC-SHA256 signature for an APPROVED escalation record."""
    subkey = derive_subkey(auth_pepper, HMAC_PURPOSE)
    sec_bytes = secondary_approver_id.bytes if secondary_approver_id else (b"\x00" * 16)
    msg = (
        field_id.bytes
        + bytes(manifest_sha256)
        + target_scope.encode("utf-8")
        + credential_mode.encode("utf-8")
        + primary_approver_id.bytes
        + sec_bytes
    )
    return hmac.new(subkey, msg, hashlib.sha256).digest()


def compute_cache_partition_key(  # noqa: PLR0913, PLR0917
    target_scope: str,
    credential_mode: str,
    issue_id: uuid.UUID,
    field_id: uuid.UUID,
    script_version: int,
    caller_user_access_hash: bytes,
) -> tuple[bool, bytes]:
    """Compute cache authorization flag and partitioned user_access_hash."""
    del issue_id, field_id, script_version  # Used in outer query/key construction
    validate_escalation_tuple(target_scope, credential_mode)
    if target_scope == "SERVER":
        return (False, b"")
    if credential_mode in ("PROJECT_ADMIN_SP", "SERVER_ADMIN_SP"):
        return (True, b"")
    return (True, caller_user_access_hash)


async def assert_execution_authorized(
    session: AsyncSession,
    definition: CustomFieldDefinition,
    auth_pepper: bytes | None = None,
) -> CustomFieldApproval | None:
    """Fail-closed check verifying an escalated custom field has a valid, untampered approval."""
    if definition.target_scope == "PROJECT" and definition.credential_mode == "INVOKING_USER":
        return None

    stmt = select(CustomFieldApproval).where(
        CustomFieldApproval.field_id == definition.id,
        CustomFieldApproval.manifest_sha256 == definition.manifest_sha256,
        CustomFieldApproval.status == "APPROVED",
    )
    approval = (await session.execute(stmt)).scalar_one_or_none()
    if approval is None:
        msg = "Execution not authorized: no approved escalation record matching manifest"
        raise ApprovalRevokedError(msg, code="APPROVAL_REVOKED")

    if (
        approval.approval_signature_hmac is None
        or len(approval.approval_signature_hmac) != SHA256_BYTE_LEN
        or approval.primary_approver_id is None
    ):
        msg = "Execution not authorized: invalid or missing approval signature"
        raise ApprovalRevokedError(msg, code="APPROVAL_REVOKED")

    if auth_pepper is None:
        auth_pepper = load_key_material().auth_pepper

    expected = compute_approval_signature_hmac(
        approval.field_id,
        approval.manifest_sha256,
        approval.target_scope,
        approval.credential_mode,
        approval.primary_approver_id,
        approval.secondary_approver_id,
        auth_pepper,
    )
    if not hmac.compare_digest(bytes(approval.approval_signature_hmac), expected):
        msg = "Execution not authorized: approval signature tamper detected"
        raise ApprovalRevokedError(msg, code="APPROVAL_REVOKED")

    return approval


class CustomFieldApprovalService:
    """Encapsulates escalation request creation, dual-control approval, and audit recording."""

    @classmethod
    def serialize(cls, row: CustomFieldApproval) -> CustomFieldApprovalResponse:
        """Serialize custom field approval model to Pydantic schema."""
        created_ts: datetime | None = getattr(row, "created_at", None)
        created_at_val = created_ts if isinstance(created_ts, datetime) else datetime.now(UTC)
        return CustomFieldApprovalResponse(
            id=row.id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            field_id=row.field_id,
            manifest_sha256=row.manifest_sha256.hex(),
            target_scope=row.target_scope,
            credential_mode=row.credential_mode,
            required_tier=row.required_tier,
            status=row.status,
            requested_by_id=row.requested_by_id,
            justification=row.justification,
            primary_approver_id=row.primary_approver_id,
            primary_approver_aal=row.primary_approver_aal,
            primary_approved_at=row.primary_approved_at,
            secondary_approver_id=row.secondary_approver_id,
            secondary_approver_aal=row.secondary_approver_aal,
            secondary_approved_at=row.secondary_approved_at,
            sp_warning_acknowledged=row.sp_warning_acknowledged,
            revoked_at=row.revoked_at,
            revoked_reason=row.revoked_reason,
            created_at=created_at_val,
        )

    @classmethod
    async def request_approval(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        field_id_str: str,
        payload: CustomFieldApprovalRequestCreate,
    ) -> CustomFieldApprovalResponse:
        """Create a new pending escalation approval request for a custom field."""
        if caller.aal_level < AAL2_MIN_LEVEL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Authentication Required",
                detail="Requesting escalation approval requires AAL2 authentication",
            )

        definition = await cls._find_definition_by_ref(session, caller.workspace_id, field_id_str)
        if definition is None:
            not_found()

        # Caller must hold PROJECT_ADMIN or SERVER_ADMIN on the field's project
        stmt_adm = text(
            "SELECT app_principal_has_role(:proj_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])"
        )
        is_admin = bool(
            (await session.execute(stmt_adm, {"proj_id": definition.project_id})).scalar_one()
        )
        if not is_admin:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Caller lacks PROJECT_ADMIN role to request escalation approval",
            )

        if payload.manifest_sha256.lower() != definition.manifest_sha256.hex().lower():
            msg = (
                "Submitted manifest_sha256 does not match current custom field definition manifest"
            )
            raise ProblemException(
                code="MANIFEST_MISMATCH",
                status=409,
                title="Manifest Mismatch",
                detail=msg,
            )

        tier = required_approver_tier(definition.target_scope, definition.credential_mode)
        if tier is None:
            msg = "Default (PROJECT, INVOKING_USER) scope does not require escalation approval"
            raise ProblemException(
                code="NO_ESCALATION_REQUIRED",
                status=422,
                title="No Escalation Required",
                detail=msg,
            )

        row = CustomFieldApproval(
            workspace_id=definition.workspace_id,
            project_id=definition.project_id,
            field_id=definition.id,
            manifest_sha256=definition.manifest_sha256,
            target_scope=definition.target_scope,
            credential_mode=definition.credential_mode,
            required_tier=tier,
            status="PENDING",
            requested_by_id=caller.principal_id,
            justification=payload.justification,
        )
        session.add(row)
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=definition.project_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.CUSTOM_FIELD_APPROVAL_REQUESTED,
            payload={
                "approval_id": str(row.id),
                "field_id": str(definition.id),
                "target_scope": row.target_scope,
                "credential_mode": row.credential_mode,
                "required_tier": row.required_tier,
                "manifest_sha256": row.manifest_sha256.hex(),
            },
        )

        return cls.serialize(row)

    @classmethod
    async def approve(  # noqa: C901, PLR0912, PLR0915
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        approval_id: uuid.UUID,
        payload: CustomFieldApprovalApproveRequest,
        auth_pepper: bytes | None = None,
    ) -> CustomFieldApprovalResponse:
        """Approve an escalation request with AAL2 verification and dual-control checks."""
        # 1. AAL2 freshness gate
        if caller.aal_level < AAL2_MIN_LEVEL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Authentication Required",
                detail="Approving escalation requires AAL2 authentication",
            )
        if caller.aal2_verified_at is not None:
            elapsed = (datetime.now(UTC) - caller.aal2_verified_at).total_seconds()
            if elapsed > AAL2_FRESHNESS_SECONDS:
                raise ProblemException(
                    code="AAL2_REQUIRED",
                    status=403,
                    title="AAL2 Authentication Required",
                    detail="AAL2 verification has expired (>900s). Re-authentication required.",
                )

        row = await session.get(CustomFieldApproval, approval_id)
        if row is None:
            not_found()

        # Check visibility
        await get_project_or_404(session, caller, str(row.project_id))

        definition = await session.get(CustomFieldDefinition, row.field_id)
        if definition is None:
            not_found()

        # 2. TOCTOU & revocation checks
        if (
            row.status == "REVOKED"
            or row.manifest_sha256 != definition.manifest_sha256
            or payload.manifest_sha256.lower() != definition.manifest_sha256.hex().lower()
        ):
            msg = (
                "Approval request manifest differs from active definition manifest "
                "or has been revoked"
            )
            raise ProblemException(
                code="MANIFEST_MISMATCH",
                status=409,
                title="Manifest Mismatch",
                detail=msg,
            )

        # 3. Approver tier role checks
        has_role = await cls._check_approver_tier(session, caller, row)
        if not has_role:
            msg = f"Caller lacks required approver tier: {row.required_tier}"
            raise ProblemException(
                code="INSUFFICIENT_APPROVER_TIER",
                status=403,
                title="Insufficient Approver Tier",
                detail=msg,
            )

        # 4. Service Principal warning check
        if row.credential_mode in ("PROJECT_ADMIN_SP", "SERVER_ADMIN_SP") and not (
            payload.sp_warning_acknowledged or row.sp_warning_acknowledged
        ):
            msg = (
                "Approval of elevated Service Principal requires explicit acknowledgement "
                "of sp_warning_acknowledged"
            )
            raise ProblemException(
                code="SP_WARNING_ACK_REQUIRED",
                status=422,
                title="Service Principal Warning Required",
                detail=msg,
            )

        if auth_pepper is None:
            auth_pepper = load_key_material().auth_pepper

        now = datetime.now(UTC)

        # 5. Dual-control vs single approval transition
        if row.required_tier == "SERVER_ADMIN_DUAL":
            if row.status == "PENDING":
                row.status = "PENDING_SECOND_APPROVER"
                row.primary_approver_id = caller.principal_id
                row.primary_approver_aal = caller.aal_level
                row.primary_approved_at = now
                if payload.sp_warning_acknowledged:
                    row.sp_warning_acknowledged = True
                await session.flush()

                await record_activity(
                    session,
                    workspace_id=caller.workspace_id,
                    object_id=row.project_id,
                    actor_principal_id=caller.principal_id,
                    event_type=ActivityEventType.CUSTOM_FIELD_APPROVED_PRIMARY,
                    payload={"approval_id": str(row.id), "field_id": str(row.field_id)},
                )
                return cls.serialize(row)

            if row.status == "PENDING_SECOND_APPROVER":
                if caller.principal_id == row.primary_approver_id:
                    msg = "Dual control requires a second distinct Server Administrator"
                    raise ProblemException(
                        code="DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED",
                        status=409,
                        title="Dual Control Distinct Approver Required",
                        detail=msg,
                    )
                row.status = "APPROVED"
                row.secondary_approver_id = caller.principal_id
                row.secondary_approver_aal = caller.aal_level
                row.secondary_approved_at = now
                if payload.sp_warning_acknowledged:
                    row.sp_warning_acknowledged = True

                row.approval_signature_hmac = compute_approval_signature_hmac(
                    field_id=row.field_id,
                    manifest_sha256=row.manifest_sha256,
                    target_scope=row.target_scope,
                    credential_mode=row.credential_mode,
                    primary_approver_id=row.primary_approver_id,  # type: ignore[arg-type]
                    secondary_approver_id=row.secondary_approver_id,
                    auth_pepper=auth_pepper,
                )
                await session.flush()

                await record_activity(
                    session,
                    workspace_id=caller.workspace_id,
                    object_id=row.project_id,
                    actor_principal_id=caller.principal_id,
                    event_type=ActivityEventType.CUSTOM_FIELD_APPROVED,
                    payload={"approval_id": str(row.id), "field_id": str(row.field_id)},
                )
                return cls.serialize(row)

            msg = f"Approval is already in status {row.status}"
            raise ProblemException(
                code="APPROVAL_ALREADY_RESOLVED",
                status=409,
                title="Approval Already Resolved",
                detail=msg,
            )

        # Single-approver tiers (PROJECT_ADMIN, WORKSPACE_ADMIN)
        if row.status != "PENDING":
            msg = f"Approval is already in status {row.status}"
            raise ProblemException(
                code="APPROVAL_ALREADY_RESOLVED",
                status=409,
                title="Approval Already Resolved",
                detail=msg,
            )

        row.status = "APPROVED"
        row.primary_approver_id = caller.principal_id
        row.primary_approver_aal = caller.aal_level
        row.primary_approved_at = now
        if payload.sp_warning_acknowledged:
            row.sp_warning_acknowledged = True

        row.approval_signature_hmac = compute_approval_signature_hmac(
            field_id=row.field_id,
            manifest_sha256=row.manifest_sha256,
            target_scope=row.target_scope,
            credential_mode=row.credential_mode,
            primary_approver_id=row.primary_approver_id,
            secondary_approver_id=None,
            auth_pepper=auth_pepper,
        )
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=row.project_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.CUSTOM_FIELD_APPROVED,
            payload={"approval_id": str(row.id), "field_id": str(row.field_id)},
        )
        return cls.serialize(row)

    @classmethod
    async def list_approvals(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        field_id_str: str,
    ) -> list[CustomFieldApprovalResponse]:
        """List approval history for a custom field."""
        definition = await cls._find_definition_by_ref(session, caller.workspace_id, field_id_str)
        if definition is None:
            not_found()

        await get_project_or_404(session, caller, str(definition.project_id))

        stmt = (
            select(CustomFieldApproval)
            .where(
                CustomFieldApproval.workspace_id == caller.workspace_id,
                CustomFieldApproval.field_id == definition.id,
            )
            .order_by(CustomFieldApproval.created_at.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [cls.serialize(r) for r in rows]

    @classmethod
    async def get_active_approval_summary(
        cls,
        session: AsyncSession,
        definition: CustomFieldDefinition,
    ) -> tuple[str, str | None]:
        """Return (approval_status, required_tier) for a definition."""
        tier = required_approver_tier(definition.target_scope, definition.credential_mode)
        if tier is None:
            return ("default_no_escalation", None)

        stmt = (
            select(CustomFieldApproval.status)
            .where(
                CustomFieldApproval.field_id == definition.id,
                CustomFieldApproval.manifest_sha256 == definition.manifest_sha256,
            )
            .order_by(CustomFieldApproval.created_at.desc())
            .limit(1)
        )
        latest_status = (await session.execute(stmt)).scalar_one_or_none()
        if latest_status is None:
            return ("UNAPPROVED", tier)
        return (latest_status, tier)

    @classmethod
    async def _check_approver_tier(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        row: CustomFieldApproval,
    ) -> bool:
        """Verify caller possesses required administrative role for target tier."""
        del caller
        if row.required_tier == "PROJECT_ADMIN":
            stmt = text(
                "SELECT app_principal_has_role(:proj_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])"
            )
            return bool((await session.execute(stmt, {"proj_id": row.project_id})).scalar_one())
        if row.required_tier == "WORKSPACE_ADMIN":
            stmt = text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM role_bindings rb "
                "  WHERE rb.principal_id = ANY (app_effective_principal_set()) "
                "    AND rb.workspace_id = :ws "
                "    AND rb.role::text IN ('WORKSPACE_ADMIN', 'SERVER_ADMIN')"
                ")"
            )
            return bool((await session.execute(stmt, {"ws": row.workspace_id})).scalar_one())
        if row.required_tier == "SERVER_ADMIN_DUAL":
            stmt = text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM role_bindings rb "
                "  WHERE rb.principal_id = ANY (app_effective_principal_set()) "
                "    AND rb.role::text = 'SERVER_ADMIN'"
                ")"
            )
            return bool((await session.execute(stmt)).scalar_one())
        return False

    @staticmethod
    async def _find_definition_by_ref(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        field_ref: str,
    ) -> CustomFieldDefinition | None:
        """Find custom field definition by UUID or slug within caller workspace."""
        stmt = select(CustomFieldDefinition).where(
            CustomFieldDefinition.workspace_id == workspace_id
        )
        try:
            uid = uuid.UUID(field_ref)
            stmt = stmt.where(CustomFieldDefinition.id == uid)
        except ValueError:
            stmt = stmt.where(CustomFieldDefinition.slug == field_ref)
        return (await session.execute(stmt)).scalar_one_or_none()
