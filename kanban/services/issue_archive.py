"""Archive and unarchive service operations for kanban issues (S7.2 8p)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models import Issue as IssueModel
from database.models import ObjectRecord, Project, WorkflowState
from kanban.api.problems import ProblemException, not_found
from kanban.security.permissions import Capability, evaluate_capabilities, require_capability
from kanban.services.activity import ActivityEventType, JSONValue, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.issues import serialize_issue

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.schemas.issues import IssueResponse

logger = logging.getLogger(__name__)

ARCHIVE_TERMINAL_GROUPS: Final[frozenset[str]] = frozenset({"completed", "cancelled"})
ARCHIVE_NOT_ALLOWED_DETAIL: Final[str] = "Only completed or canceled work items can be archived"


async def archive_issue(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
) -> IssueResponse:
    """Archive an issue enforcing Plane rule and checking for open sub-issues.

    Enforces:
    1. Issue resolution through RLS (404 on non-existent, cross-workspace, deleted, unreadable).
    2. Capability.EDIT required on the issue (403 on insufficient capability).
    3. Issue must not already be archived (409 ALREADY_ARCHIVED).
    4. Issue workflow state group must be 'completed' or 'cancelled' (409 ARCHIVE_NOT_ALLOWED).
    5. Issue must not have any open sub-issues (409 ARCHIVE_OPEN_SUBISSUES).
    6. Sets objects.archived_at = clock_timestamp().
    7. Emits ISSUE_ARCHIVED activity event with mode="manual".
    """
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.EDIT)

    obj = await session.get(ObjectRecord, issue.id)
    if obj is None:  # pragma: no cover
        not_found()

    if obj.archived_at is not None:
        raise ProblemException(
            code="ALREADY_ARCHIVED",
            status=409,
            title="Already Archived",
            detail="Issue is already archived",
        )

    state = await session.get(WorkflowState, issue.state_id)
    state_group = state.state_group if state else "unknown"
    if state is None or state_group not in ARCHIVE_TERMINAL_GROUPS:
        raise ProblemException(
            code="ARCHIVE_NOT_ALLOWED",
            status=409,
            title="Archive not allowed",
            detail=ARCHIVE_NOT_ALLOWED_DETAIL,
            state_group=state_group,
        )

    # Check for open sub-issues
    sub_stmt = (
        select(IssueModel.id, IssueModel.sequence_id, Project.identifier)
        .join(WorkflowState, WorkflowState.id == IssueModel.state_id)
        .join(ObjectRecord, ObjectRecord.id == IssueModel.id)
        .join(Project, Project.id == IssueModel.project_id)
        .where(
            IssueModel.parent_issue_id == issue.id,
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
            WorkflowState.state_group.notin_(ARCHIVE_TERMINAL_GROUPS),
        )
        .order_by(IssueModel.sequence_id)
    )
    open_subs = (await session.execute(sub_stmt)).all()
    if open_subs:
        open_subissue_keys: list[str] = []
        hidden_open_count = 0
        for sub_id, sub_seq, proj_ident in open_subs:
            caps = await evaluate_capabilities(session, caller, sub_id)
            if Capability.VIEW in caps:
                open_subissue_keys.append(f"{proj_ident}-{sub_seq}")
            else:
                hidden_open_count += 1
        raise ProblemException(
            code="ARCHIVE_OPEN_SUBISSUES",
            status=409,
            title="Open sub-issues exist",
            detail="Cannot archive issue with open sub-issues",
            open_subissue_keys=open_subissue_keys,
            hidden_open_count=hidden_open_count,
        )

    now_ts = datetime.now(UTC)
    obj.archived_at = now_ts
    await session.flush()

    await record_activity(
        session=session,
        workspace_id=issue.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_ARCHIVED,
        payload={"mode": "manual", "source": "manual"},
    )

    return await serialize_issue(session, caller, issue)


async def unarchive_issue(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    *,
    reason: str | None = None,
    admin_override: bool = False,
) -> IssueResponse:
    """Unarchive an issue.

    Enforces:
    1. Issue resolution through RLS (404 on non-existent, cross-workspace, deleted, unreadable).
    2. Capability.EDIT required on the issue (403 on insufficient capability).
    3. Issue must currently be archived (409 NOT_ARCHIVED).
    4. Sets objects.archived_at = NULL.
    5. Emits ISSUE_UNARCHIVED activity event.
    """
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.EDIT)

    obj = await session.get(ObjectRecord, issue.id)
    if obj is None or obj.archived_at is None:
        raise ProblemException(
            code="NOT_ARCHIVED",
            status=409,
            title="Not Archived",
            detail="Issue is not archived",
        )

    obj.archived_at = None
    await session.flush()

    payload: dict[str, JSONValue] = {}
    if reason is not None:
        payload["reason"] = reason
    if admin_override:
        payload["admin_override"] = True

    await record_activity(
        session=session,
        workspace_id=issue.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_UNARCHIVED,
        payload=payload,
    )

    return await serialize_issue(session, caller, issue)
