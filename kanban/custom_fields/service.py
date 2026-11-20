# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Business logic and service operations for custom field definitions (KB-P5-11, S13.1, S13.2)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import select, text

from database.models.custom_field import CustomFieldDefinition
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.custom_fields import (
    CustomFieldCreateRequest,
    CustomFieldResponse,
    CustomFieldUpdateRequest,
)
from kanban.custom_fields.approvals import required_approver_tier
from kanban.custom_fields.manifest import (
    compute_field_manifest_sha256,
    validate_egress_allowlist,
)
from kanban.custom_fields.output_formats import parse_output_format_metadata
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.projects import get_project_or_404

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models.projects import Project
    from kanban.api.deps import PrincipalContext

AAL2_MIN_LEVEL: Final[int] = 2
SHA256_BYTE_LEN: Final[int] = 32


def _parse_wasm_sha256(hex_str: str) -> bytes:
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError as exc:
        msg = f"Invalid hex for wasm_module_sha256: {exc}"
        raise ProblemException(
            code="INVALID_WASM_SHA256",
            status=422,
            title="Invalid WASM SHA256",
            detail=msg,
        ) from exc
    if len(raw) != SHA256_BYTE_LEN:
        msg = "WASM SHA256 must be 32 bytes (64 hex characters)"
        raise ProblemException(
            code="INVALID_WASM_SHA256",
            status=422,
            title="Invalid WASM SHA256",
            detail=msg,
        )
    return raw


class CustomFieldDefinitionService:
    """Service encapsulating custom field definition lifecycle, RLS gates, and auditing."""

    @staticmethod
    async def is_admin(
        session: AsyncSession,
        caller: PrincipalContext,
        project_id: uuid.UUID,
    ) -> bool:
        """Return True if caller holds PROJECT_ADMIN on project or SERVER_ADMIN."""
        del caller  # Session binds caller RLS/GUC context
        stmt = text(
            "SELECT app_principal_has_role(:project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])"
        )
        return bool((await session.execute(stmt, {"project_id": project_id})).scalar_one())

    @classmethod
    async def require_admin_and_aal2(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project: Project,
    ) -> None:
        """Enforce PROJECT_ADMIN / SERVER_ADMIN role and AAL2 session level."""
        is_adm = await cls.is_admin(session, caller, project.id)
        if not is_adm:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Caller lacks required admin role to manage custom field definitions",
            )
        if caller.aal_level < AAL2_MIN_LEVEL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Authentication Required",
                detail="This operation requires multi-factor authentication (AAL2).",
            )

    @classmethod
    def serialize(
        cls,
        row: CustomFieldDefinition,
        *,
        is_admin: bool,
        approval_status: str | None = None,
        required_approver_tier_override: str | None = None,
    ) -> CustomFieldResponse:
        """Serialize custom field definition, redacting script_source for non-admins."""
        tier = required_approver_tier(row.target_scope, row.credential_mode)
        default_status = "default_no_escalation" if tier is None else "UNAPPROVED"
        final_status = approval_status or default_status
        final_tier = required_approver_tier_override or tier

        wasm_hex = row.wasm_module_sha256.hex() if row.wasm_module_sha256 else None
        return CustomFieldResponse(
            id=row.id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            slug=row.slug,
            name=row.name,
            tier=row.tier if is_admin else None,
            output_format=row.output_format,
            output_format_metadata=dict(row.output_format_metadata),
            script_source=row.script_source if is_admin else None,
            wasm_module_sha256=wasm_hex,
            script_version=row.script_version,
            target_scope=row.target_scope if is_admin else None,
            credential_mode=row.credential_mode if is_admin else None,
            egress_allowlist=list(row.egress_allowlist),
            manifest_sha256=row.manifest_sha256.hex() if is_admin else None,
            is_enabled=row.is_enabled,
            approval_status=final_status,
            required_approver_tier=final_tier,
            created_by_id=row.created_by_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @classmethod
    async def list_definitions(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_ref: str,
    ) -> list[CustomFieldResponse]:
        """List custom field definitions for project visible to caller."""
        project = await get_project_or_404(session, caller, project_ref)
        await require_capability(session, caller, project.id, Capability.VIEW)

        is_adm = await cls.is_admin(session, caller, project.id)
        stmt = (
            select(CustomFieldDefinition)
            .where(
                CustomFieldDefinition.workspace_id == caller.workspace_id,
                CustomFieldDefinition.project_id == project.id,
            )
            .order_by(CustomFieldDefinition.created_at)
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [cls.serialize(row, is_admin=is_adm) for row in rows]

    @classmethod
    async def create_definition(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_ref: str,
        payload: CustomFieldCreateRequest,
    ) -> CustomFieldResponse:
        """Create a new custom field definition with validation and activity recording."""
        project = await get_project_or_404(session, caller, project_ref)
        await cls.require_admin_and_aal2(session, caller, project)

        existing = (
            await session.execute(
                select(CustomFieldDefinition.id).where(
                    CustomFieldDefinition.project_id == project.id,
                    CustomFieldDefinition.slug == payload.slug,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            msg = f"A custom field with slug '{payload.slug}' already exists in this project"
            raise ProblemException(
                code="SLUG_ALREADY_EXISTS",
                status=409,
                title="Slug Already Exists",
                detail=msg,
            )

        try:
            parse_output_format_metadata(payload.output_format, payload.output_format_metadata)
        except Exception as exc:
            raise ProblemException(
                code="OUTPUT_FORMAT_INVALID",
                status=422,
                title="Output Format Invalid",
                detail=str(exc),
            ) from exc

        try:
            cleaned_egress = validate_egress_allowlist(payload.egress_allowlist)
        except Exception as exc:
            raise ProblemException(
                code="EGRESS_ALLOWLIST_INVALID",
                status=422,
                title="Egress Allowlist Invalid",
                detail=str(exc),
            ) from exc

        wasm_bytes = (
            _parse_wasm_sha256(payload.wasm_module_sha256) if payload.wasm_module_sha256 else None
        )

        manifest_bytes = compute_field_manifest_sha256(
            script_source=payload.script_source,
            output_format=payload.output_format,
            output_format_metadata=payload.output_format_metadata,
            tier=payload.tier,
            target_scope=payload.target_scope,
            credential_mode=payload.credential_mode,
            egress_allowlist=cleaned_egress,
            wasm_module_sha256=wasm_bytes,
        )

        row = CustomFieldDefinition(
            workspace_id=project.workspace_id,
            project_id=project.id,
            slug=payload.slug,
            name=payload.name,
            tier=payload.tier,
            output_format=payload.output_format,
            output_format_metadata=payload.output_format_metadata,
            script_source=payload.script_source,
            wasm_module_sha256=wasm_bytes,
            script_version=1,
            target_scope=payload.target_scope,
            credential_mode=payload.credential_mode,
            egress_allowlist=cleaned_egress,
            manifest_sha256=manifest_bytes,
            is_enabled=payload.is_enabled,
            created_by_id=caller.principal_id,
        )
        session.add(row)
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.CUSTOM_FIELD_CREATED,
            payload={
                "field_id": str(row.id),
                "slug": row.slug,
                "name": row.name,
                "output_format": row.output_format,
                "tier": row.tier,
                "script_version": row.script_version,
                "manifest_sha256": row.manifest_sha256.hex(),
            },
        )

        return cls.serialize(row, is_admin=True)

    @classmethod
    def _apply_patch(
        cls,
        row: CustomFieldDefinition,
        payload: CustomFieldUpdateRequest,
    ) -> bool:
        """Apply patch values to definition row, returning True if manifest must update."""
        if payload.name is not None:
            row.name = payload.name

        if payload.is_enabled is not None:
            row.is_enabled = payload.is_enabled

        spec_changed = False
        spec_fields = (
            ("tier", payload.tier),
            ("output_format", payload.output_format),
            ("output_format_metadata", payload.output_format_metadata),
            ("script_source", payload.script_source),
            ("target_scope", payload.target_scope),
            ("credential_mode", payload.credential_mode),
        )
        for attr, val in spec_fields:
            if val is not None and val != getattr(row, attr):
                setattr(row, attr, val)
                spec_changed = True

        if payload.egress_allowlist is not None:
            try:
                new_egress = validate_egress_allowlist(payload.egress_allowlist)
            except Exception as exc:
                raise ProblemException(
                    code="EGRESS_ALLOWLIST_INVALID",
                    status=422,
                    title="Egress Allowlist Invalid",
                    detail=str(exc),
                ) from exc
            if new_egress != row.egress_allowlist:
                row.egress_allowlist = new_egress
                spec_changed = True

        if payload.wasm_module_sha256 is not None:
            new_wasm = _parse_wasm_sha256(payload.wasm_module_sha256)
            if new_wasm != row.wasm_module_sha256:
                row.wasm_module_sha256 = new_wasm
                spec_changed = True

        return spec_changed

    @classmethod
    async def update_definition(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_ref: str,
        field_id: str,
        payload: CustomFieldUpdateRequest,
    ) -> CustomFieldResponse:
        """Update an existing custom field definition."""
        project = await get_project_or_404(session, caller, project_ref)
        await cls.require_admin_and_aal2(session, caller, project)

        row = await cls._find_definition(session, caller.workspace_id, project.id, field_id)
        if row is None:
            not_found()

        # Validate format metadata if updating format or metadata
        if payload.output_format is not None or payload.output_format_metadata is not None:
            fmt = payload.output_format if payload.output_format is not None else row.output_format
            meta = (
                payload.output_format_metadata
                if payload.output_format_metadata is not None
                else row.output_format_metadata
            )
            try:
                parse_output_format_metadata(fmt, meta)
            except Exception as exc:
                raise ProblemException(
                    code="OUTPUT_FORMAT_INVALID",
                    status=422,
                    title="Output Format Invalid",
                    detail=str(exc),
                ) from exc

        spec_changed = cls._apply_patch(row, payload)
        if spec_changed:
            row.script_version += 1
            row.manifest_sha256 = compute_field_manifest_sha256(
                script_source=row.script_source,
                output_format=row.output_format,
                output_format_metadata=row.output_format_metadata,
                tier=row.tier,
                target_scope=row.target_scope,
                credential_mode=row.credential_mode,
                egress_allowlist=row.egress_allowlist,
                wasm_module_sha256=row.wasm_module_sha256,
            )

        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.CUSTOM_FIELD_UPDATED,
            payload={
                "field_id": str(row.id),
                "slug": row.slug,
                "script_version": row.script_version,
                "manifest_sha256": row.manifest_sha256.hex(),
            },
        )

        return cls.serialize(row, is_admin=True)

    @classmethod
    async def delete_definition(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_ref: str,
        field_id: str,
    ) -> None:
        """Delete an existing custom field definition."""
        project = await get_project_or_404(session, caller, project_ref)
        await cls.require_admin_and_aal2(session, caller, project)

        row = await cls._find_definition(session, caller.workspace_id, project.id, field_id)
        if row is None:
            not_found()

        deleted_id = str(row.id)
        deleted_slug = row.slug

        await session.delete(row)
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.CUSTOM_FIELD_DELETED,
            payload={
                "field_id": deleted_id,
                "slug": deleted_slug,
            },
        )

    @staticmethod
    async def _find_definition(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        field_ref: str,
    ) -> CustomFieldDefinition | None:
        stmt = select(CustomFieldDefinition).where(
            CustomFieldDefinition.workspace_id == workspace_id,
            CustomFieldDefinition.project_id == project_id,
        )
        try:
            uid = uuid.UUID(field_ref)
            stmt = stmt.where(CustomFieldDefinition.id == uid)
        except ValueError:
            stmt = stmt.where(CustomFieldDefinition.slug == field_ref)

        return (await session.execute(stmt)).scalar_one_or_none()
