# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Cycle burndown metrics computation and activity history replay (S7.2 8g, S11.4)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import select, text

from database.models import Cycle, Issue, Project, WorkflowState
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.cycles import (
    BurndownIdealPoint,
    BurndownPoint,
    BurndownResponse,
)
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType
from kanban.services.cycles import _check_cycles_enabled

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MAX_BURNDOWN_RANGE_DAYS: Final[int] = 366
COMPLETED_GROUPS: Final[frozenset[str]] = frozenset({"completed", "cancelled"})


def _resolve_burndown_window(cycle: Cycle) -> tuple[dt.date, dt.date]:
    """Validate and return normalized start and end dates for burndown calculation."""
    if cycle.start_date is not None and cycle.end_date is not None:
        if cycle.end_date < cycle.start_date:
            raise ProblemException(
                code="DATE_ORDER",
                status=422,
                title="Invalid Date Order",
                detail="end_date cannot be earlier than start_date",
            )
        range_days = (cycle.end_date - cycle.start_date).days + 1
        if range_days > MAX_BURNDOWN_RANGE_DAYS:
            raise ProblemException(
                code="CYCLE_RANGE_TOO_LONG",
                status=422,
                title="Cycle Range Too Long",
                detail="Burndown range exceeds 366 days",
            )
        return cycle.start_date, cycle.end_date

    today = dt.datetime.now(dt.UTC).date()
    if cycle.start_date is not None:
        return cycle.start_date, cycle.start_date
    if cycle.end_date is not None:
        return cycle.end_date, cycle.end_date
    return today, today


async def _fetch_candidate_issues(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> dict[uuid.UUID, Issue]:
    """Fetch all issues currently or historically associated with this cycle."""
    current_issues_stmt = select(Issue).where(
        Issue.cycle_id == cycle_id,
    )
    current_issues = list((await session.execute(current_issues_stmt)).scalars().all())
    issues_by_id: dict[uuid.UUID, Issue] = {i.id: i for i in current_issues}

    cycle_id_str = str(cycle_id)
    hist_stmt = text(
        "SELECT DISTINCT object_id FROM activity_records "
        "WHERE event_type = :event_type "
        "  AND payload->>'field' = 'cycle_id' "
        "  AND (payload->>'new' = :cycle_id OR payload->>'old' = :cycle_id)"
    )
    hist_rows = (
        await session.execute(
            hist_stmt,
            {
                "event_type": ActivityEventType.ISSUE_FIELD_CHANGED.value,
                "cycle_id": cycle_id_str,
            },
        )
    ).all()

    missing_ids = [r[0] for r in hist_rows if r[0] not in issues_by_id]
    if missing_ids:
        additional_stmt = select(Issue).where(
            Issue.id.in_(missing_ids),
        )
        for issue in (await session.execute(additional_stmt)).scalars().all():
            issues_by_id[issue.id] = issue

    return issues_by_id


async def _fetch_issue_events(
    session: AsyncSession,
    issue_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[dict[str, object]]]:
    """Retrieve activity records for specified issues ordered chronologically."""
    events_by_issue: dict[uuid.UUID, list[dict[str, object]]] = {iid: [] for iid in issue_ids}
    if not issue_ids:
        return events_by_issue

    act_stmt = text(
        "SELECT object_id, event_type, payload, recorded_at "
        "FROM activity_records "
        "WHERE object_id = ANY(:issue_ids) "
        "  AND event_type IN (:ev_created, :ev_field, :ev_state) "
        "ORDER BY recorded_at ASC"
    )
    act_rows = (
        await session.execute(
            act_stmt,
            {
                "issue_ids": issue_ids,
                "ev_created": ActivityEventType.ISSUE_CREATED.value,
                "ev_field": ActivityEventType.ISSUE_FIELD_CHANGED.value,
                "ev_state": ActivityEventType.ISSUE_STATE_CHANGED.value,
            },
        )
    ).all()

    for r in act_rows:
        events_by_issue[r[0]].append(
            {
                "event_type": r[1],
                "payload": r[2],
                "recorded_at": r[3],
            }
        )
    return events_by_issue


def _evaluate_issue_at_cutoff(
    issue: Issue,
    events: list[dict[str, object]],
    cycle_id: uuid.UUID,
    cutoff: dt.datetime,
    state_groups: dict[uuid.UUID, str],
) -> tuple[bool, bool]:
    """Determine (in_cycle, is_unfinished) for an issue at a specific daily cutoff timestamp."""
    created_ev = next(
        (e for e in events if e["event_type"] == ActivityEventType.ISSUE_CREATED.value),
        None,
    )
    created_at = created_ev["recorded_at"] if created_ev else None
    if isinstance(created_at, dt.datetime) and created_at > cutoff:
        return False, False

    cycle_id_str = str(cycle_id)
    all_cycle_changes = [
        e
        for e in events
        if e["event_type"] == ActivityEventType.ISSUE_FIELD_CHANGED.value
        and isinstance(e["payload"], dict)
        and e["payload"].get("field") == "cycle_id"
        and isinstance(e["recorded_at"], dt.datetime)
    ]
    past_cycle_changes = [
        e
        for e in all_cycle_changes
        if isinstance(e["recorded_at"], dt.datetime) and e["recorded_at"] <= cutoff
    ]

    if past_cycle_changes:
        last_cycle = past_cycle_changes[-1]["payload"]
        in_cycle = isinstance(last_cycle, dict) and last_cycle.get("new") == cycle_id_str
    elif all_cycle_changes:
        first_cycle = all_cycle_changes[0]["payload"]
        in_cycle = isinstance(first_cycle, dict) and first_cycle.get("old") == cycle_id_str
    else:
        in_cycle = issue.cycle_id == cycle_id

    if not in_cycle:
        return False, False

    all_state_changes = [
        e
        for e in events
        if e["event_type"] == ActivityEventType.ISSUE_STATE_CHANGED.value
        and isinstance(e["payload"], dict)
        and isinstance(e["recorded_at"], dt.datetime)
    ]
    past_state_changes = [
        e
        for e in all_state_changes
        if isinstance(e["recorded_at"], dt.datetime) and e["recorded_at"] <= cutoff
    ]

    if past_state_changes:
        last_state = past_state_changes[-1]["payload"]
        to_state_str = (
            str(last_state.get("to_state_id", "")) if isinstance(last_state, dict) else ""
        )
        try:
            to_state_id = uuid.UUID(to_state_str)
            st_group = state_groups.get(to_state_id, "unstarted")
        except (ValueError, TypeError):
            st_group = "unstarted"
    elif all_state_changes:
        first_state = all_state_changes[0]["payload"]
        from_state_str = (
            str(first_state.get("from_state_id", "")) if isinstance(first_state, dict) else ""
        )
        try:
            from_state_id = uuid.UUID(from_state_str)
            st_group = state_groups.get(from_state_id, "unstarted")
        except (ValueError, TypeError):
            st_group = "unstarted"
    else:
        st_group = state_groups.get(issue.state_id, "unstarted")

    is_unfinished = st_group not in COMPLETED_GROUPS
    return True, is_unfinished


async def compute_burndown(
    session: AsyncSession,
    caller: PrincipalContext,
    cycle_id: uuid.UUID,
) -> BurndownResponse:
    """Compute scope and remaining burndown series by replaying activity events."""
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        not_found()

    await require_capability(session, caller, cycle.project_id, Capability.VIEW)

    project = await session.get(Project, cycle.project_id)
    if project is not None:
        _check_cycles_enabled(project)

    start, end = _resolve_burndown_window(cycle)
    today = dt.datetime.now(dt.UTC).date()
    series_end = min(end, today)

    issues_by_id = await _fetch_candidate_issues(session, cycle.id)

    states_stmt = select(WorkflowState).where(WorkflowState.project_id == cycle.project_id)
    states = (await session.execute(states_stmt)).scalars().all()
    state_groups: dict[uuid.UUID, str] = {s.id: s.state_group for s in states}

    events_by_issue = await _fetch_issue_events(session, list(issues_by_id.keys()))

    series: list[BurndownPoint] = []
    if start <= series_end:
        cur_date = start
        while cur_date <= series_end:
            cutoff = dt.datetime.combine(cur_date, dt.time.max, tzinfo=dt.UTC)
            day_scope = 0
            day_remaining = 0

            for issue_id, issue in issues_by_id.items():
                in_cycle, is_unfinished = _evaluate_issue_at_cutoff(
                    issue,
                    events_by_issue.get(issue_id, []),
                    cycle.id,
                    cutoff,
                    state_groups,
                )
                if in_cycle:
                    day_scope += 1
                    if is_unfinished:
                        day_remaining += 1

            series.append(
                BurndownPoint(
                    date=cur_date.isoformat(),
                    scope=day_scope,
                    remaining=day_remaining,
                )
            )
            cur_date += dt.timedelta(days=1)

    initial_scope = series[0].scope if series else len(issues_by_id)
    ideal = [
        BurndownIdealPoint(date=start.isoformat(), remaining=initial_scope),
        BurndownIdealPoint(date=end.isoformat(), remaining=0),
    ]

    return BurndownResponse(
        cycle_id=cycle.id,
        series=series,
        ideal=ideal,
    )
