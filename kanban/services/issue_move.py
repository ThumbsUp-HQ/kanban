"""Issue move service: fractional rank computation and WIP limit enforcement (KB-P3-12, S6.4)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from sqlalchemy import func, select, text

from database.models import Issue, ObjectRecord, Project, WorkflowState
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issue_move import IssueMoveRequest, IssueMoveResponse, WipWarning
from kanban.content.normalize import normalize_plain_text
from kanban.security.granular_permissions import GranularPermission, require_permissions
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.board_rank import REBALANCE_THRESHOLD_LEN, midpoint_rank
from kanban.services.issue_keys import resolve_issue_ref
from kanban.workflows.engine import TransitionEngine

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.responses import Response

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

MIN_OVERRIDE_REASON_LEN: Final[int] = 10
_HTTP_ACCEPTED: Final[int] = 202
MAX_OVERRIDE_REASON_LEN: Final[int] = 500
REQUIRED_AAL2_LEVEL: Final[int] = 2


async def _verify_move_permissions(  # noqa: PLR0913
    session: AsyncSession,
    caller: PrincipalContext,
    issue_id: uuid.UUID,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    is_cross_column: bool,
) -> None:
    """Verify caller holds required capabilities for intra-column or cross-column move."""
    await require_capability(session, caller, issue_id, Capability.EDIT)
    if is_cross_column:
        await require_capability(session, caller, issue_id, Capability.TRANSITION)
        await require_permissions(
            session,
            caller,
            workspace_id,
            {
                GranularPermission.FIELD_MODIFY_STATE.value,
                GranularPermission.ISSUE_TRANSITION.value,
            },
            project_id=project_id,
            object_readable=True,
            object_id=issue_id,
        )
    else:
        await require_permissions(
            session,
            caller,
            workspace_id,
            {GranularPermission.ISSUE_MOVE_RANK.value},
            project_id=project_id,
            object_readable=True,
            object_id=issue_id,
        )


async def _lock_and_validate_target_state(
    session: AsyncSession,
    project_id: uuid.UUID,
    target_state_id: uuid.UUID,
) -> WorkflowState:
    """Lock target column under transaction advisory lock and verify project ownership."""
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock(  hashtext('kanban.state.' || CAST(:state_id AS text)))"
        ),
        {"state_id": str(target_state_id)},
    )
    state_stmt = select(WorkflowState).where(
        WorkflowState.id == target_state_id,
        WorkflowState.project_id == project_id,
    )
    target_state = (await session.execute(state_stmt)).scalar_one_or_none()
    if target_state is None:
        raise ProblemException(
            status=422,
            code="INVALID_REFERENCE",
            title="Unprocessable Entity",
            detail="Target workflow state does not belong to the issue's project",
        )
    return target_state


async def _resolve_anchor(
    session: AsyncSession,
    caller: PrincipalContext,
    moved_issue: Issue,
    target_state_id: uuid.UUID,
    anchor_ref: str,
) -> Issue:
    """Resolve an anchor issue under caller VIEW and verify state and project alignment."""
    try:
        anchor = await resolve_issue_ref(session, caller, anchor_ref)
    except ProblemException as exc:
        raise ProblemException(
            status=422,
            code="INVALID_ANCHOR",
            title="Unprocessable Entity",
            detail=f"Anchor issue '{anchor_ref}' not found or unreadable",
        ) from exc

    archived_stmt = select(ObjectRecord.archived_at).where(ObjectRecord.id == anchor.id)
    is_archived = (await session.execute(archived_stmt)).scalar_one_or_none() is not None

    if (
        anchor.id == moved_issue.id
        or anchor.project_id != moved_issue.project_id
        or anchor.state_id != target_state_id
        or is_archived
    ):
        raise ProblemException(
            status=422,
            code="INVALID_ANCHOR",
            title="Unprocessable Entity",
            detail=f"Anchor issue '{anchor_ref}' does not belong to target column",
        )
    return anchor


async def _resolve_neighbor_ranks(
    session: AsyncSession,
    caller: PrincipalContext,
    issue: Issue,
    target_state_id: uuid.UUID,
    req: IssueMoveRequest,
) -> tuple[str | None, str | None]:
    """Resolve prev_rank and next_rank bounds from after_issue and before_issue."""
    prev_rank: str | None = None
    next_rank: str | None = None

    if req.after_issue:
        after_obj = await _resolve_anchor(session, caller, issue, target_state_id, req.after_issue)
        prev_rank = after_obj.board_rank

    if req.before_issue:
        before_obj = await _resolve_anchor(
            session, caller, issue, target_state_id, req.before_issue
        )
        next_rank = before_obj.board_rank

    if prev_rank is not None and next_rank is not None and prev_rank >= next_rank:
        raise ProblemException(
            status=409,
            code="ANCHOR_ORDER_CONFLICT",
            title="Conflict",
            detail="Neighbor anchors are out of order; card may have been moved concurrently",
        )

    if req.after_issue is None and req.before_issue is None:
        # Neither anchor provided -> place at the bottom of the target column
        max_stmt = (
            select(func.max(Issue.board_rank))
            .join(ObjectRecord, ObjectRecord.id == Issue.id)
            .where(
                Issue.project_id == issue.project_id,
                Issue.state_id == target_state_id,
                Issue.id != issue.id,
                ObjectRecord.deleted_at.is_(None),
                ObjectRecord.archived_at.is_(None),
            )
        )
        prev_rank = (await session.execute(max_stmt)).scalar_one_or_none()
        next_rank = None

    return prev_rank, next_rank


async def _enforce_wip_limits(
    session: AsyncSession,
    caller: PrincipalContext,
    moved_issue: Issue,
    target_state: WorkflowState,
    req: IssueMoveRequest,
) -> tuple[WipWarning | None, bool, str | None, int]:
    """Enforce Soft and Hard WIP limits when entering target_state_id."""
    count_stmt = (
        select(func.count(Issue.id))
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.project_id == moved_issue.project_id,
            Issue.state_id == target_state.id,
            Issue.id != moved_issue.id,
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
        )
    )
    current_count = int((await session.execute(count_stmt)).scalar_one())
    resulting_count = current_count + 1

    wip_overridden = False
    clean_override_reason: str | None = None

    # 1. Hard WIP Limit Check
    if target_state.wip_hard_limit is not None and resulting_count > target_state.wip_hard_limit:
        has_admin_role = (
            await session.execute(
                text(
                    "SELECT app_principal_has_role(:project_id, "
                    "ARRAY['PROJECT_ADMIN','SERVER_ADMIN'])"
                ),
                {"project_id": moved_issue.project_id},
            )
        ).scalar_one()

        if not has_admin_role:
            raise ProblemException(
                status=409,
                code="WIP_HARD_LIMIT_EXCEEDED",
                title="Conflict",
                detail=f"Column hard WIP limit of {target_state.wip_hard_limit} exceeded",
                extra={
                    "hard_limit": target_state.wip_hard_limit,
                    "current_count": current_count,
                },
            )

        if caller.aal_level < REQUIRED_AAL2_LEVEL:
            raise ProblemException(
                status=403,
                code="AAL2_REQUIRED",
                title="Forbidden",
                detail="AAL2 verification required to override column hard WIP limit",
            )

        raw_reason = req.wip_override_reason or ""
        clean_reason = normalize_plain_text(raw_reason).strip()
        if (
            len(clean_reason) < MIN_OVERRIDE_REASON_LEN
            or len(clean_reason) > MAX_OVERRIDE_REASON_LEN
        ):
            raise ProblemException(
                status=409,
                code="WIP_HARD_LIMIT_OVERRIDE_REQUIRED",
                title="Conflict",
                detail="A valid override justification between 10 and 500 characters is required",
                extra={
                    "hard_limit": target_state.wip_hard_limit,
                    "current_count": current_count,
                },
            )

        wip_overridden = True
        clean_override_reason = clean_reason

    # 2. Soft WIP Limit Check
    wip_warning: WipWarning | None = None
    if target_state.wip_soft_limit is not None and resulting_count > target_state.wip_soft_limit:
        wip_warning = WipWarning(
            soft_limit=target_state.wip_soft_limit,
            resulting_count=resulting_count,
        )

    return wip_warning, wip_overridden, clean_override_reason, resulting_count


async def move_issue(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    req: IssueMoveRequest,
    *,
    response: Response | None = None,
) -> IssueMoveResponse:
    """Move an issue to a new board position or column in a single-row mutation."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    archived_stmt = select(ObjectRecord.archived_at).where(ObjectRecord.id == issue.id)
    is_archived = (await session.execute(archived_stmt)).scalar_one_or_none() is not None
    if is_archived:
        raise ProblemException(
            status=409,
            code="ISSUE_ARCHIVED",
            title="Conflict",
            detail="Cannot move an archived issue",
        )

    target_state_id = req.target_state_id if req.target_state_id is not None else issue.state_id
    is_cross_column = target_state_id != issue.state_id

    # 1. Authorization checks
    await _verify_move_permissions(
        session,
        caller,
        issue.id,
        issue.workspace_id,
        issue.project_id,
        is_cross_column=is_cross_column,
    )

    # 2. State validation and locking
    target_state = await _lock_and_validate_target_state(session, issue.project_id, target_state_id)

    # 3. Lock moved issue row
    await session.execute(
        text("SELECT id FROM issues WHERE id = :id FOR UPDATE"),
        {"id": issue.id},
    )

    # 4. Resolve neighbor ranks
    prev_rank, next_rank = await _resolve_neighbor_ranks(
        session, caller, issue, target_state_id, req
    )

    # 5. Compute new board rank
    new_rank = midpoint_rank(prev_rank, next_rank)

    # Guard against exact slot collision under concurrency
    col_stmt = select(Issue.id).where(
        Issue.project_id == issue.project_id,
        Issue.state_id == target_state_id,
        Issue.board_rank == new_rank,
        Issue.id != issue.id,
    )
    if (await session.execute(col_stmt)).scalar_one_or_none() is not None:
        new_rank = midpoint_rank(prev_rank, new_rank)

    # 6. Soft & Hard WIP Limit Enforcement
    wip_warning: WipWarning | None = None
    wip_overridden = False
    clean_override_reason: str | None = None
    resulting_count = 0

    if is_cross_column:
        (
            wip_warning,
            wip_overridden,
            clean_override_reason,
            resulting_count,
        ) = await _enforce_wip_limits(session, caller, issue, target_state, req)

    # 7. Execute single-row mutation
    old_rank = issue.board_rank
    old_state_id = issue.state_id

    if is_cross_column:
        outcome = await TransitionEngine.request_transition(
            session=session,
            issue_key=str(issue.id),
            to_state=target_state_id,
            actor=caller,
        )
        if outcome.status_code == _HTTP_ACCEPTED or outcome.status == "pending_agent_gate":
            if response is not None:
                response.status_code = _HTTP_ACCEPTED
            proj_ident = (
                await session.execute(
                    select(Project.identifier).where(Project.id == issue.project_id)
                )
            ).scalar_one()
            issue_key = f"{proj_ident}-{issue.sequence_id}"
            return IssueMoveResponse(
                issue_key=issue_key,
                state_id=old_state_id,
                board_rank=old_rank,
                rebalance_scheduled=False,
                wip_warning=wip_warning,
                hard_limit=target_state.wip_hard_limit if wip_overridden else None,
                resulting_count=resulting_count if (wip_overridden or wip_warning) else None,
            )
        await session.execute(
            text("UPDATE issues SET board_rank = :r WHERE id = :id"),
            {"r": new_rank, "id": issue.id},
        )
    else:
        await session.execute(
            text("UPDATE issues SET board_rank = :r WHERE id = :id"),
            {"r": new_rank, "id": issue.id},
        )
    await session.flush()
    await session.refresh(issue)

    # 8. Activity Ledger emission (category HISTORY)
    if old_rank != new_rank:
        await record_activity(
            session,
            workspace_id=issue.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_RANK_MOVED,
            payload={"old_rank": old_rank, "new_rank": new_rank},
        )

    if wip_overridden and clean_override_reason is not None:
        await record_activity(
            session,
            workspace_id=issue.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.WIP_HARD_LIMIT_OVERRIDDEN,
            payload={
                "issue_id": str(issue.id),
                "from_state_id": str(old_state_id),
                "to_state_id": str(target_state_id),
                "hard_limit": target_state.wip_hard_limit,
                "resulting_count": resulting_count,
                "reason": clean_override_reason,
            },
        )

    rebalance_scheduled = bool(len(new_rank) > REBALANCE_THRESHOLD_LEN)

    # 9. Format response issue key
    proj_ident = (
        await session.execute(select(Project.identifier).where(Project.id == issue.project_id))
    ).scalar_one()
    issue_key = f"{proj_ident}-{issue.sequence_id}"

    return IssueMoveResponse(
        issue_key=issue_key,
        state_id=target_state_id,
        board_rank=new_rank,
        rebalance_scheduled=rebalance_scheduled,
        wip_warning=wip_warning,
        hard_limit=target_state.wip_hard_limit if wip_overridden else None,
        resulting_count=resulting_count if (wip_overridden or wip_warning) else None,
    )
