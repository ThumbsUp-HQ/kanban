"""Issue provenance service and administrative creator override logic (KB-P3-04)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.models.activity import ActivityRecord
from database.models.base import ObjectKind
from database.models.spine import ObjectRecord
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issue_provenance import (
    CreatorPrincipalSummary,
    CreatorSummary,
    IssueOverrideCreatorRequest,
    IssueProvenance,
    RedactedCreatorSummary,
)
from kanban.content.normalize import normalize_plain_text
from kanban.services.activity import ActivityEventType
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models.issues import Issue
    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.schemas.issues import IssueResponse

MIN_REASON_LEN: Final = 10
MAX_REASON_LEN: Final = 500
REQUIRED_AAL_LEVEL: Final = 2


async def resolve_creator_summary(
    session: AsyncSession,
    principal_id: uuid.UUID | None,
) -> CreatorSummary | None:
    """Resolve a principal UUID to a CreatorSummary or RedactedCreatorSummary under RLS."""
    if principal_id is None:
        return None

    stmt = select(ObjectRecord.canonical_key).where(
        ObjectRecord.id == principal_id,
        ObjectRecord.object_type == ObjectKind.USER,
    )
    row = (await session.execute(stmt)).first()
    if row is None or not row[0]:
        return RedactedCreatorSummary(redacted=True, label="1 External Collaborator")

    handle = row[0].lstrip("@")
    return CreatorPrincipalSummary(id=str(principal_id), handle=handle)


async def build_issue_provenance(
    session: AsyncSession,
    issue: Issue,
) -> IssueProvenance:
    """Build canonical IssueProvenance for an issue response."""
    created_by_summary = await resolve_creator_summary(
        session, issue.created_by_id
    ) or RedactedCreatorSummary(redacted=True, label="1 External Collaborator")

    orig_created_by_id = issue.original_created_by_id
    orig_summary = await resolve_creator_summary(
        session, orig_created_by_id
    ) or RedactedCreatorSummary(redacted=True, label="1 External Collaborator")

    overridden = bool(
        issue.created_by_id != orig_created_by_id or issue.creator_modified_at is not None
    )

    creator_modified_by: CreatorSummary | None = None
    creator_modified_at: str | None = None
    reason: str | None = None

    if overridden:
        creator_modified_by = await resolve_creator_summary(session, issue.creator_modified_by_id)
        if issue.creator_modified_at is not None:
            creator_modified_at = issue.creator_modified_at.isoformat()

        # Query latest CREATOR_OVERRIDDEN activity row
        act_stmt = (
            select(ActivityRecord.payload)
            .where(
                ActivityRecord.object_id == issue.id,
                ActivityRecord.event_type == ActivityEventType.CREATOR_OVERRIDDEN.value,
            )
            .order_by(ActivityRecord.recorded_at.desc(), ActivityRecord.chain_seq.desc())
            .limit(1)
        )
        act_row = (await session.execute(act_stmt)).first()
        if act_row and isinstance(act_row[0], dict):
            reason = act_row[0].get("reason")

    return IssueProvenance(
        created_by=created_by_summary,
        original_created_by=orig_summary,
        overridden=overridden,
        creator_modified_by=creator_modified_by,
        creator_modified_at=creator_modified_at,
        reason=reason,
    )


async def _verify_admin_override_auth(
    session: AsyncSession,
    caller: PrincipalContext,
    project_id: uuid.UUID,
) -> None:
    """Verify PROJECT_ADMIN/SERVER_ADMIN and AAL2 requirements."""
    has_admin_role = (
        await session.execute(
            text(
                "SELECT app_principal_has_role(:project_id, ARRAY['PROJECT_ADMIN','SERVER_ADMIN'])"
            ),
            {"project_id": project_id},
        )
    ).scalar_one()
    if not has_admin_role:
        raise ProblemException(
            status=403,
            code="INSUFFICIENT_CAPABILITY",
            title="Forbidden",
            detail="Caller lacks PROJECT_ADMIN or SERVER_ADMIN role",
        )

    if caller.aal_level < REQUIRED_AAL_LEVEL:
        raise ProblemException(
            status=403,
            code="AAL2_REQUIRED",
            title="Forbidden",
            detail="AAL2 verification required for administrative actions",
        )


def _validate_override_reason(raw_reason: str | None) -> str:
    """Validate that reason is plain text and between MIN_REASON_LEN and MAX_REASON_LEN."""
    reason_str = raw_reason or ""
    clean_reason = normalize_plain_text(reason_str).strip()
    if len(clean_reason) < MIN_REASON_LEN or len(clean_reason) > MAX_REASON_LEN:
        raise ProblemException(
            status=422,
            code="REASON_REQUIRED",
            title="Unprocessable Entity",
            detail="Reason must be between 10 and 500 characters",
            field="reason",
        )
    return clean_reason


async def _resolve_target_creator_id(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    target_str: str,
) -> uuid.UUID:
    """Resolve target creator handle or UUID string to a valid user principal ID."""
    clean_target = target_str.strip()
    try:
        return uuid.UUID(clean_target)
    except ValueError:
        clean_handle = clean_target.lstrip("@").lower()
        obj_stmt = select(ObjectRecord.id).where(
            ObjectRecord.workspace_id == workspace_id,
            ObjectRecord.object_type == ObjectKind.USER,
            func.lower(ObjectRecord.canonical_key) == clean_handle,
        )
        resolved_id = (await session.execute(obj_stmt)).scalar_one_or_none()
        if resolved_id is not None:
            return resolved_id

    raise ProblemException(
        status=422,
        code="CREATOR_NOT_ELIGIBLE",
        title="Unprocessable Entity",
        detail="Target creator must be an active user eligible to view the project",
        field="created_by",
    )


async def _validate_target_creator_eligibility(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    target_user_id: uuid.UUID,
    current_created_by_id: uuid.UUID | None,
) -> None:
    """Validate that target creator is an active user, has project VIEW, and is different."""
    valid_user = (
        await session.execute(
            text(
                "SELECT 1 FROM principals p "
                "JOIN users u ON u.id = p.id "
                "WHERE p.id = :uid "
                "  AND p.workspace_id = :ws "
                "  AND p.principal_type = 'USER' "
                "  AND p.status = 'ACTIVE'"
            ),
            {"uid": target_user_id, "ws": workspace_id},
        )
    ).scalar_one_or_none()
    if not valid_user:
        raise ProblemException(
            status=422,
            code="CREATOR_NOT_ELIGIBLE",
            title="Unprocessable Entity",
            detail="Target creator must be an active user eligible to view the project",
            field="created_by",
        )

    has_view = (
        await session.execute(
            text(
                "SELECT 1 FROM effective_resource_access era "
                "WHERE era.object_id = :proj_id "
                "  AND era.principal_id = :uid "
                "  AND era.workspace_id = :ws "
                "  AND (era.allow_mask & 1) = 1 "
                "  AND (era.deny_mask & 1) = 0"
            ),
            {"proj_id": project_id, "uid": target_user_id, "ws": workspace_id},
        )
    ).scalar_one_or_none()
    if not has_view:
        raise ProblemException(
            status=422,
            code="CREATOR_NOT_ELIGIBLE",
            title="Unprocessable Entity",
            detail="Target creator must be an active user eligible to view the project",
            field="created_by",
        )

    if target_user_id == current_created_by_id:
        raise ProblemException(
            status=422,
            code="CREATOR_UNCHANGED",
            title="Unprocessable Entity",
            detail="Target creator is already the issue creator",
            field="created_by",
        )


async def override_issue_created_by(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    body: IssueOverrideCreatorRequest,
) -> tuple[IssueResponse, str]:
    """Execute administrative creator override under strict authorization and DB trigger."""
    # (a) caller lacks VIEW -> 404 NOT_FOUND (equalized)
    issue = await resolve_issue_ref(session, caller, issue_ref)

    # (b) caller lacks PROJECT_ADMIN on issue's project and SERVER_ADMIN -> 403
    # (c) session app.aal_level < 2 -> 403 AAL2_REQUIRED
    await _verify_admin_override_auth(session, caller, issue.project_id)

    # Validation: reason plain text, length 10..500 else 422 REASON_REQUIRED
    clean_reason = _validate_override_reason(body.reason)

    # Validation: target creator exists, active user, project VIEW, not unchanged
    target_user_id = await _resolve_target_creator_id(session, caller.workspace_id, body.created_by)
    await _validate_target_creator_eligibility(
        session,
        caller.workspace_id,
        issue.project_id,
        target_user_id,
        issue.created_by_id,
    )

    # In the RLS transaction run:
    # SELECT set_config('app.override_reason', :reason, true)
    # UPDATE issues SET created_by_id = :new WHERE id = :id
    await session.execute(
        text("SELECT set_config('app.override_reason', :reason, true)"),
        {"reason": clean_reason},
    )
    try:
        await session.execute(
            text("UPDATE issues SET created_by_id = :new WHERE id = :id"),
            {"new": target_user_id, "id": issue.id},
        )
        await session.flush()
    except (IntegrityError, DBAPIError) as exc:
        err_msg = str(exc)
        if "CREATOR_OVERRIDE_FORBIDDEN" in err_msg or "RLS_CONTEXT_REQUIRED" in err_msg:
            raise ProblemException(
                status=403,
                code="INSUFFICIENT_CAPABILITY",
                title="Forbidden",
                detail="Caller lacks permission to override creator",
            ) from exc
        if "CREATOR_OVERRIDE_WORKSPACE_MISMATCH" in err_msg:
            raise ProblemException(
                status=422,
                code="CREATOR_NOT_ELIGIBLE",
                title="Unprocessable Entity",
                detail="Target creator must belong to the same workspace",
                field="created_by",
            ) from exc
        raise

    # Re-fetch updated issue
    await session.refresh(issue)

    from kanban.services.issues import (  # noqa: PLC0415  # Break circular dependency
        serialize_issue,
    )

    resp = await serialize_issue(session, caller, issue)
    sha256_hex = issue.description_sha256.hex() if issue.description_sha256 else ""
    return resp, f'"{sha256_hex}"'
