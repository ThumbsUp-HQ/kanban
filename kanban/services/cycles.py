# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Cycle business logic: CRUD, status transitions, and issue membership (S7.2 8g, S11.4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from database.models import Cycle, Issue, Project, WorkflowState
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.cycles import (
    CycleComplete,
    CycleCompleteResponse,
    CycleCreate,
    CyclePatch,
    CycleResponse,
    CycleRolloverRequest,
    CycleRolloverResponse,
)
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext
    from kanban.services.activity import JSONValue

MAX_ROLLOVER_ISSUES: Final[int] = 1000
VALID_CYCLE_STATUSES: Final[frozenset[str]] = frozenset({"upcoming", "active", "completed"})
COMPLETED_GROUPS: Final[frozenset[str]] = frozenset({"completed", "cancelled"})


_DISABLED_PROJECT_IDS: set[uuid.UUID] = set()


def set_project_cycles_enabled(project_id: uuid.UUID, *, enabled: bool) -> None:
    """Explicitly enable or disable cycles for a project (for test harness & admin override)."""
    if enabled:
        _DISABLED_PROJECT_IDS.discard(project_id)
    else:
        _DISABLED_PROJECT_IDS.add(project_id)


def _check_cycles_enabled(project: Project) -> None:
    """Enforce project-level cycles enabled feature toggle."""
    if project.id in _DISABLED_PROJECT_IDS or getattr(project, "cycles_enabled", True) is False:
        raise ProblemException(
            code="FEATURE_DISABLED",
            status=404,
            title="Feature Disabled",
            detail="Cycles are disabled for this project",
        )


def _validate_dates(start_date: date | None, end_date: date | None) -> None:
    """Validate that end_date >= start_date when both are present."""
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ProblemException(
            code="DATE_ORDER",
            status=422,
            title="Invalid Date Order",
            detail="end_date cannot be earlier than start_date",
        )


async def _resolve_project(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    required: Capability = Capability.VIEW,
) -> Project:
    """Resolve project reference by UUID or identifier and enforce required capability."""
    try:
        proj_uuid = uuid.UUID(project_ref)
        stmt = select(Project).where(
            Project.id == proj_uuid,
            Project.workspace_id == caller.workspace_id,
        )
    except ValueError:
        stmt = select(Project).where(
            func.upper(Project.identifier) == project_ref.strip().upper(),
            Project.workspace_id == caller.workspace_id,
        )

    project = (await session.execute(stmt)).scalar_one_or_none()
    if project is None:
        not_found()

    await require_capability(session, caller, project.id, required)
    _check_cycles_enabled(project)
    return project


async def _serialize_cycle(
    session: AsyncSession,
    cycle: Cycle,
) -> CycleResponse:
    """Assemble CycleResponse with real-time aggregate issue and completed counts."""
    count_stmt = (
        select(
            func.count(Issue.id).label("total_count"),
            func.count(Issue.id)
            .filter(WorkflowState.state_group.in_(["completed", "cancelled"]))
            .label("completed_count"),
        )
        .select_from(Issue)
        .join(WorkflowState, Issue.state_id == WorkflowState.id)
        .where(
            Issue.cycle_id == cycle.id,
        )
    )
    row = (await session.execute(count_stmt)).one()

    return CycleResponse(
        id=cycle.id,
        project_id=cycle.project_id,
        name=cycle.name,
        status=cycle.status,  # type: ignore[arg-type]
        start_date=cycle.start_date,
        end_date=cycle.end_date,
        issue_count=int(row.total_count),
        completed_count=int(row.completed_count),
    )


async def list_cycles(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    status: str | None = None,
) -> list[CycleResponse]:
    """List cycles for a project with optional status filtering."""
    project = await _resolve_project(session, caller, project_ref, Capability.VIEW)

    if status is not None and status not in VALID_CYCLE_STATUSES:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=f"Invalid cycle status: {status!r}. Must be one of upcoming, active, completed.",
        )

    stmt = select(Cycle).where(Cycle.project_id == project.id)
    if status is not None:
        stmt = stmt.where(Cycle.status == status)
    stmt = stmt.order_by(Cycle.start_date.asc().nulls_last(), Cycle.name.asc())

    cycles = list((await session.execute(stmt)).scalars().all())
    return [await _serialize_cycle(session, c) for c in cycles]


async def create_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    body: CycleCreate,
) -> CycleResponse:
    """Create a new cycle in upcoming status."""
    project = await _resolve_project(session, caller, project_ref, Capability.EDIT)
    _validate_dates(body.start_date, body.end_date)

    cycle_id = uuid.uuid4()
    canonical_key = f"cycle-{str(cycle_id)[:8]}"

    await session.execute(
        text(
            "SELECT register_object("
            "  CAST('cycle' AS object_kind), :ws, :proj, :ckey, :title, :creator, :id"
            ")"
        ),
        {
            "ws": caller.workspace_id,
            "proj": project.id,
            "ckey": canonical_key,
            "title": body.name,
            "creator": caller.principal_id,
            "id": cycle_id,
        },
    )

    cycle = Cycle(
        id=cycle_id,
        workspace_id=caller.workspace_id,
        project_id=project.id,
        name=body.name,
        status="upcoming",
        start_date=body.start_date,
        end_date=body.end_date,
    )
    session.add(cycle)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ProblemException(
            code="CYCLE_CONFLICT",
            status=409,
            title="Cycle Conflict",
            detail="Cycle with overlapping dates or constraint violation",
        ) from exc

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=cycle_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.CYCLE_CREATED,
        payload={"name": body.name, "status": "upcoming"},
    )

    return await _serialize_cycle(session, cycle)


async def get_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
) -> CycleResponse:
    """Retrieve cycle details and aggregate issue counts."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    await require_capability(session, caller, cycle.project_id, Capability.VIEW)
    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    return await _serialize_cycle(session, cycle)


async def patch_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
    body: CyclePatch,
) -> CycleResponse:
    """Update cycle fields (name, start_date, end_date) for non-completed cycles."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    await require_capability(session, caller, cycle.project_id, Capability.EDIT)
    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    if cycle.status == "completed":
        raise ProblemException(
            code="CYCLE_COMPLETED",
            status=409,
            title="Cycle Completed",
            detail="Completed cycles are immutable",
        )

    new_start = body.start_date if "start_date" in body.model_fields_set else cycle.start_date
    new_end = body.end_date if "end_date" in body.model_fields_set else cycle.end_date
    _validate_dates(new_start, new_end)

    changes: dict[str, JSONValue] = {}

    if body.name is not None and body.name != cycle.name:
        changes["name"] = {"old": cycle.name, "new": body.name}
        cycle.name = body.name

    if "start_date" in body.model_fields_set and body.start_date != cycle.start_date:
        changes["start_date"] = {
            "old": cycle.start_date.isoformat() if cycle.start_date else None,
            "new": body.start_date.isoformat() if body.start_date else None,
        }
        cycle.start_date = body.start_date

    if "end_date" in body.model_fields_set and body.end_date != cycle.end_date:
        changes["end_date"] = {
            "old": cycle.end_date.isoformat() if cycle.end_date else None,
            "new": body.end_date.isoformat() if body.end_date else None,
        }
        cycle.end_date = body.end_date

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ProblemException(
            code="CYCLE_CONFLICT",
            status=409,
            title="Cycle Conflict",
            detail="Cycle date range conflict with another cycle",
        ) from exc

    if changes:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=cycle.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.CYCLE_UPDATED,
            payload={"changes": changes},
        )

    return await _serialize_cycle(session, cycle)


async def start_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
) -> CycleResponse:
    """Transition an upcoming cycle to active status."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    await require_capability(session, caller, cycle.project_id, Capability.EDIT)
    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    if cycle.status != "upcoming":
        raise ProblemException(
            code="INVALID_CYCLE_TRANSITION",
            status=409,
            title="Invalid Cycle Transition",
            detail="Only upcoming cycles can be started",
        )

    await session.execute(
        select(Project.id).where(Project.id == cycle.project_id).with_for_update()
    )

    active_stmt = select(Cycle.id).where(
        Cycle.project_id == cycle.project_id,
        Cycle.status == "active",
        Cycle.id != cycle.id,
    )
    if (await session.execute(active_stmt)).scalar_one_or_none() is not None:
        raise ProblemException(
            code="ACTIVE_CYCLE_EXISTS",
            status=409,
            title="Active Cycle Exists",
            detail="Another cycle is already active in this project",
        )

    cycle.status = "active"
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=cycle.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.CYCLE_STATUS_CHANGED,
        payload={"from": "upcoming", "to": "active"},
    )
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=cycle.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.CYCLE_ACTIVATED,
        payload={"cycle_id": str(cycle.id)},
    )

    return await _serialize_cycle(session, cycle)


async def complete_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
    body: CycleComplete,
) -> CycleCompleteResponse:
    """Complete an active cycle and roll over unfinished issues."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    await require_capability(session, caller, cycle.project_id, Capability.EDIT)
    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    if cycle.status != "active":
        raise ProblemException(
            code="INVALID_CYCLE_TRANSITION",
            status=409,
            title="Invalid Cycle Transition",
            detail="Only active cycles can be completed",
        )

    unfinished_stmt = (
        select(Issue)
        .join(WorkflowState, Issue.state_id == WorkflowState.id)
        .where(
            Issue.cycle_id == cycle.id,
            WorkflowState.state_group.not_in(["completed", "cancelled"]),
        )
    )
    unfinished_issues = list((await session.execute(unfinished_stmt)).scalars().all())

    if len(unfinished_issues) > MAX_ROLLOVER_ISSUES:
        raise ProblemException(
            code="ROLLOVER_TOO_LARGE",
            status=409,
            title="Rollover Too Large",
            detail=f"Cannot rollover more than {MAX_ROLLOVER_ISSUES} unfinished issues",
        )

    target_cycle: Cycle | None = None
    if body.rollover_to_cycle_id is not None:
        if body.rollover_to_cycle_id == cycle.id:
            raise ProblemException(
                code="ROLLOVER_TARGET_INVALID",
                status=422,
                title="Invalid Rollover Target",
                detail="Cannot rollover to the cycle being completed",
            )
        target_cycle = await session.get(Cycle, body.rollover_to_cycle_id)
        if target_cycle is None or target_cycle.project_id != cycle.project_id:
            raise ProblemException(
                code="ROLLOVER_TARGET_INVALID",
                status=422,
                title="Invalid Rollover Target",
                detail="Target cycle not found in the same project",
            )
        if target_cycle.status not in ("upcoming", "active"):
            raise ProblemException(
                code="ROLLOVER_TARGET_INVALID",
                status=422,
                title="Invalid Rollover Target",
                detail="Target cycle must be in upcoming or active status",
            )

    target_id_val = target_cycle.id if target_cycle else None
    target_id_str = str(target_id_val) if target_id_val else None
    cycle_id_str = str(cycle.id)

    for issue in unfinished_issues:
        issue.cycle_id = target_id_val
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
            payload={
                "field": "cycle_id",
                "old": cycle_id_str,
                "new": target_id_str,
                "reason": "rollover",
            },
        )
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_CYCLE_CHANGED,
            payload={
                "from_cycle_id": cycle_id_str,
                "to_cycle_id": target_id_str,
                "reason": "rollover",
            },
        )

    cycle.status = "completed"
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=cycle.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.CYCLE_STATUS_CHANGED,
        payload={"from": "active", "to": "completed"},
    )
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=cycle.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.CYCLE_COMPLETED,
        payload={"rolled_over_count": len(unfinished_issues)},
    )

    cycle_resp = await _serialize_cycle(session, cycle)
    return CycleCompleteResponse(
        cycle=cycle_resp,
        rolled_over=len(unfinished_issues),
        rollover_to_cycle_id=target_id_val,
    )


async def rollover_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
    body: CycleRolloverRequest,
) -> CycleRolloverResponse:
    """Rollover unfinished issues from cycle to target_cycle without completing."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    await require_capability(session, caller, cycle.project_id, Capability.EDIT)
    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    if body.target_cycle_id == cycle.id:
        raise ProblemException(
            code="ROLLOVER_TARGET_INVALID",
            status=422,
            title="Invalid Rollover Target",
            detail="Cannot rollover to the cycle being rolled over from",
        )
    target_cycle = await session.get(Cycle, body.target_cycle_id)
    if target_cycle is None or target_cycle.project_id != cycle.project_id:
        raise ProblemException(
            code="ROLLOVER_TARGET_INVALID",
            status=422,
            title="Invalid Rollover Target",
            detail="Target cycle not found in the same project",
        )
    if target_cycle.status not in ("upcoming", "active"):
        raise ProblemException(
            code="INVALID_TRANSITION",
            status=422,
            title="Invalid Rollover Target",
            detail="Target cycle must be in upcoming or active status",
        )

    unfinished_stmt = (
        select(Issue)
        .join(WorkflowState, Issue.state_id == WorkflowState.id)
        .where(
            Issue.cycle_id == cycle.id,
            WorkflowState.state_group.not_in(["completed", "cancelled"]),
        )
    )
    unfinished_issues = list((await session.execute(unfinished_stmt)).scalars().all())

    if len(unfinished_issues) > MAX_ROLLOVER_ISSUES:
        raise ProblemException(
            code="ROLLOVER_TOO_LARGE",
            status=409,
            title="Rollover Too Large",
            detail=f"Cannot rollover more than {MAX_ROLLOVER_ISSUES} unfinished issues",
        )

    target_id_val = target_cycle.id
    target_id_str = str(target_id_val)
    cycle_id_str = str(cycle.id)

    for issue in unfinished_issues:
        issue.cycle_id = target_id_val
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
            payload={
                "field": "cycle_id",
                "old": cycle_id_str,
                "new": target_id_str,
                "reason": "rollover",
            },
        )
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_CYCLE_CHANGED,
            payload={
                "from_cycle_id": cycle_id_str,
                "to_cycle_id": target_id_str,
                "reason": "rollover",
            },
        )

    await session.flush()

    return CycleRolloverResponse(
        status="rolled_over",
        from_cycle=cycle.name,
        to_cycle=target_cycle.name,
        moved=len(unfinished_issues),
    )


async def delete_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
) -> None:
    """Delete a non-completed cycle, setting issues.cycle_id to NULL."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    await require_capability(session, caller, cycle.project_id, Capability.ADMIN)
    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    if cycle.status == "completed":
        raise ProblemException(
            code="CYCLE_COMPLETED",
            status=409,
            title="Cycle Completed",
            detail="Completed cycles cannot be deleted",
        )

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=cycle.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.CYCLE_DELETED,
        payload={"name": cycle.name},
    )

    await session.delete(cycle)
    await session.flush()


async def add_issue_to_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
    issue_ref: str,
) -> None:
    """Add an issue to a cycle, enforcing at most one active/upcoming cycle per issue."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    issue = await resolve_issue_ref(session, caller, issue_ref)

    await require_capability(session, caller, issue.id, Capability.EDIT)

    if issue.project_id != cycle.project_id:
        raise ProblemException(
            code="PROJECT_MISMATCH",
            status=422,
            title="Project Mismatch",
            detail="Issue and cycle belong to different projects",
        )

    if issue.cycle_id is not None and issue.cycle_id != cycle.id:
        other_cycle = await session.get(Cycle, issue.cycle_id)
        if other_cycle is not None and other_cycle.status in ("upcoming", "active"):
            raise ProblemException(
                code="ISSUE_IN_ANOTHER_CYCLE",
                status=409,
                title="Issue In Another Cycle",
                detail="Issue already belongs to an active or upcoming cycle",
            )

    old_cycle_id = str(issue.cycle_id) if issue.cycle_id else None
    issue.cycle_id = cycle.id
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
        payload={
            "field": "cycle_id",
            "old": old_cycle_id,
            "new": str(cycle.id),
        },
    )
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_CYCLE_CHANGED,
        payload={
            "from_cycle_id": old_cycle_id,
            "to_cycle_id": str(cycle.id),
        },
    )


async def remove_issue_from_cycle(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
    issue_ref: str,
) -> None:
    """Remove an issue from a cycle."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    issue = await resolve_issue_ref(session, caller, issue_ref)

    await require_capability(session, caller, issue.id, Capability.EDIT)

    if issue.cycle_id != cycle.id:
        raise ProblemException(
            code="NOT_FOUND",
            status=404,
            title="Not Found",
            detail="Issue is not in this cycle",
        )

    issue.cycle_id = None
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
        payload={
            "field": "cycle_id",
            "old": str(cycle.id),
            "new": None,
        },
    )
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_CYCLE_CHANGED,
        payload={
            "from_cycle_id": str(cycle.id),
            "to_cycle_id": None,
        },
    )
