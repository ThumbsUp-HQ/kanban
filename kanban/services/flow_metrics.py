# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Statistical flow telemetry service (KAN-79, KB-FLOW-METRICS-01).

Computes:
1. Daily Cumulative Flow Diagram (CFD) series per WorkflowState / state_group.
2. Cycle Time (first_started_at -> latest_completed_at) & Lead Time
   (created_at -> latest_completed_at) scatterplot points + p50, p85, p95 percentiles.
3. Aging WIP for active (started) issues with age_in_current_state_hours, total_wip_hours,
   and column p50/p85/p95 thresholds.
4. 10,000-trial pure Python Monte Carlo throughput forecasting (<30ms) for 'How Many?'
   and 'When?' at p50/p85/p95 confidence with deterministic optional seed.
"""

from __future__ import annotations

import datetime as dt
import math
import random
import time
import uuid
from collections import Counter
from itertools import batched
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select, text

from database.models import Issue, ObjectRecord, Project, WorkflowState
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.flow_metrics import (
    STATE_GROUPS,
    AgingWipIssue,
    AgingWipMetrics,
    CfdPoint,
    CfdSeries,
    CfdStateMeta,
    ColumnAgingThresholds,
    CycleLeadTimeMetrics,
    CycleLeadTimePoint,
    MonteCarloForecast,
    MonteCarloHowMany,
    MonteCarloWhen,
    PercentileValues,
    ProjectFlowMetricsResponse,
)
from kanban.services.activity import ActivityEventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MIN_WINDOW_DAYS: Final[int] = 1
MAX_WINDOW_DAYS: Final[int] = 366
MIN_TARGET_ITEMS: Final[int] = 1
MAX_TARGET_ITEMS: Final[int] = 10000
MIN_HORIZON_DAYS: Final[int] = 1
MAX_HORIZON_DAYS: Final[int] = 366
MIN_TRIALS: Final[int] = 10
MAX_TRIALS: Final[int] = 50000
MONTE_CARLO_TRIALS: Final[int] = 10000
DEFAULT_MONTE_CARLO_TIMEOUT_SECONDS: Final[float] = 2.0
_MAX_FORECAST_DAYS: Final[int] = 3650


def _calculate_percentile(data: list[float], p: float) -> float:
    """Calculate the p-th percentile of numeric data with linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 1:
        return round(float(sorted_data[0]), 2)
    k = (n - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(float(sorted_data[int(k)]), 2)
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return round(float(d0 + d1), 2)


def _simulate_monte_carlo(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    history: list[int],
    horizon_days: int,
    target_items: int,
    today: dt.date,
    trials: int = MONTE_CARLO_TRIALS,
    seed: int | None = None,
    timeout_seconds: float = DEFAULT_MONTE_CARLO_TIMEOUT_SECONDS,
) -> MonteCarloForecast:
    """Execute high-speed pure Python Monte Carlo simulation with bounds and timeout clamping."""
    if not (MIN_TRIALS <= trials <= MAX_TRIALS):
        msg = f"trials must be between {MIN_TRIALS} and {MAX_TRIALS} (got {trials})"
        raise ValueError(msg)
    if not (MIN_HORIZON_DAYS <= horizon_days <= MAX_HORIZON_DAYS):
        msg = (
            f"horizon_days must be between {MIN_HORIZON_DAYS} and {MAX_HORIZON_DAYS} "
            f"(got {horizon_days})"
        )
        raise ValueError(msg)
    if not (MIN_TARGET_ITEMS <= target_items <= MAX_TARGET_ITEMS):
        msg = (
            f"target_items must be between {MIN_TARGET_ITEMS} and {MAX_TARGET_ITEMS} "
            f"(got {target_items})"
        )
        raise ValueError(msg)

    start_time = time.monotonic()
    rng = random.Random(seed)  # noqa: S311
    total_history = len(history)
    avg_throughput = round(sum(history) / total_history, 2) if total_history > 0 else 0.0

    # 1. 'How Many?' Simulation (horizon_days)
    if history:
        how_many_samples = rng.choices(history, k=trials * horizon_days)
    else:
        how_many_samples = [0] * (trials * horizon_days)
    how_many_totals = [sum(b) for b in batched(how_many_samples, horizon_days)]
    sorted_how_many = sorted(how_many_totals)

    # In throughput forecasting, confidence C% means completing >= X items in C% of trials:
    # 50% confidence -> index 5000 (median)
    # 85% confidence -> index 1500 (85% of trials >= sorted_how_many[1500])
    # 95% confidence -> index 500  (95% of trials >= sorted_how_many[500])
    hm_p50 = sorted_how_many[int(trials * 0.50)]
    hm_p85 = sorted_how_many[int(trials * 0.15)]
    hm_p95 = sorted_how_many[int(trials * 0.05)]
    hm_dist: dict[int, int] = dict(sorted(Counter(how_many_totals).items()))

    how_many = MonteCarloHowMany(
        horizon_days=horizon_days,
        p50=hm_p50,
        p85=hm_p85,
        p95=hm_p95,
        distribution=hm_dist,
    )

    # 2. 'When?' Simulation (target_items)
    if sum(history) > 0:
        mean_rate = sum(history) / total_history
        chunk_size = max(20, min(150, int(target_items / mean_rate * 2.2)))
        pool_samples = rng.choices(history, k=trials * chunk_size)
        when_days: list[int] = []
        append_when = when_days.append

        for b in batched(pool_samples, chunk_size):
            if time.monotonic() - start_time > timeout_seconds:
                while len(when_days) < trials:
                    append_when(_MAX_FORECAST_DAYS)
                break
            cum = 0
            day = 0
            for x in b:
                cum += x
                day += 1
                if cum >= target_items:
                    break
            else:
                # Fallback for rare extreme tails with timeout clamping
                rem = target_items - cum
                while rem > 0 and day < _MAX_FORECAST_DAYS:
                    if time.monotonic() - start_time > timeout_seconds:
                        day = _MAX_FORECAST_DAYS
                        break
                    day += 1
                    rem -= rng.choice(history)
            append_when(day)

        sorted_when = sorted(when_days)
        # For 'When?', confidence C% means finishing within X days in C% of trials:
        w_p50 = sorted_when[int(trials * 0.50)]
        w_p85 = sorted_when[int(trials * 0.85)]
        w_p95 = sorted_when[int(trials * 0.95)]

        w_p50_date = (today + dt.timedelta(days=w_p50)).isoformat()
        w_p85_date = (today + dt.timedelta(days=w_p85)).isoformat()
        w_p95_date = (today + dt.timedelta(days=w_p95)).isoformat()
        w_dist: dict[int, int] = dict(sorted(Counter(when_days).items()))

        when = MonteCarloWhen(
            target_items=target_items,
            p50_days=w_p50,
            p85_days=w_p85,
            p95_days=w_p95,
            p50_date=w_p50_date,
            p85_date=w_p85_date,
            p95_date=w_p95_date,
            distribution=w_dist,
        )
    else:
        when = MonteCarloWhen(
            target_items=target_items,
            p50_days=None,
            p85_days=None,
            p95_days=None,
            p50_date=None,
            p85_date=None,
            p95_date=None,
            distribution={},
        )

    return MonteCarloForecast(
        trials=trials,
        historical_daily_throughput=history,
        average_daily_throughput=avg_throughput,
        how_many=how_many,
        when=when,
    )


async def compute_project_flow_metrics(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    session: AsyncSession,
    project_id: uuid.UUID,
    window_days: int = 90,
    horizon_days: int = 14,
    target_items: int = 20,
    seed: int | None = None,
    trials: int = MONTE_CARLO_TRIALS,
) -> ProjectFlowMetricsResponse:
    """Compute native statistical flow telemetry metrics under caller RLS session."""
    if not (MIN_WINDOW_DAYS <= window_days <= MAX_WINDOW_DAYS):
        raise ProblemException(
            code="INVALID_PARAMETER",
            status=422,
            title="Invalid Parameter",
            detail=f"window_days must be between {MIN_WINDOW_DAYS} and {MAX_WINDOW_DAYS}",
        )
    if not (MIN_TARGET_ITEMS <= target_items <= MAX_TARGET_ITEMS):
        raise ProblemException(
            code="INVALID_PARAMETER",
            status=422,
            title="Invalid Parameter",
            detail=f"target_items must be between {MIN_TARGET_ITEMS} and {MAX_TARGET_ITEMS}",
        )
    if not (MIN_HORIZON_DAYS <= horizon_days <= MAX_HORIZON_DAYS):
        raise ProblemException(
            code="INVALID_PARAMETER",
            status=422,
            title="Invalid Parameter",
            detail=f"horizon_days must be between {MIN_HORIZON_DAYS} and {MAX_HORIZON_DAYS}",
        )
    if not (MIN_TRIALS <= trials <= MAX_TRIALS):
        raise ProblemException(
            code="INVALID_PARAMETER",
            status=422,
            title="Invalid Parameter",
            detail=f"trials must be between {MIN_TRIALS} and {MAX_TRIALS}",
        )

    # RLS Project Check
    project = await session.get(Project, project_id)
    if project is None:
        not_found()

    # Load project workflow states
    states_stmt = (
        select(WorkflowState)
        .where(WorkflowState.project_id == project_id)
        .order_by(WorkflowState.sort_order.asc())
    )
    states_res = await session.execute(states_stmt)
    states = list(states_res.scalars().all())

    state_by_id: dict[uuid.UUID, WorkflowState] = {s.id: s for s in states}
    state_meta_list = [
        CfdStateMeta(
            id=s.id,
            name=s.name,
            state_group=s.state_group,
            color_hex=s.color_hex,
            sort_order=s.sort_order,
        )
        for s in states
    ]

    # Load project issues with creation timestamps
    issues_stmt = (
        select(Issue, ObjectRecord.created_at, ObjectRecord.canonical_key)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(Issue.project_id == project_id)
    )
    issues_rows = (await session.execute(issues_stmt)).all()

    issue_map: dict[uuid.UUID, Issue] = {}
    issue_created_at: dict[uuid.UUID, dt.datetime] = {}
    issue_canonical_keys: dict[uuid.UUID, str] = {}

    for row in issues_rows:
        iss: Issue = row[0]
        c_at: dt.datetime = row[1]
        c_key: str = row[2]
        issue_map[iss.id] = iss
        issue_created_at[iss.id] = c_at
        issue_canonical_keys[iss.id] = c_key

    issue_ids = list(issue_map.keys())
    events_by_issue: dict[uuid.UUID, list[dict[str, Any]]] = {iid: [] for iid in issue_ids}

    if issue_ids:
        act_stmt = text(
            "SELECT object_id, event_type, payload, recorded_at "
            "FROM activity_records "
            "WHERE object_id = ANY(:issue_ids) "
            "  AND event_type IN (:ev_created, :ev_state) "
            "ORDER BY recorded_at ASC"
        )
        act_rows = (
            await session.execute(
                act_stmt,
                {
                    "issue_ids": issue_ids,
                    "ev_created": ActivityEventType.ISSUE_CREATED.value,
                    "ev_state": ActivityEventType.ISSUE_STATE_CHANGED.value,
                },
            )
        ).all()

        for r in act_rows:
            events_by_issue[r[0]].append(
                {
                    "event_type": r[1],
                    "payload": r[2] if isinstance(r[2], dict) else {},
                    "recorded_at": r[3],
                }
            )

        # Allow ISSUE_CREATED recorded_at to override ObjectRecord.created_at for historical replays
        for iid, evs in events_by_issue.items():
            c_ev = next(
                (e for e in evs if e["event_type"] == ActivityEventType.ISSUE_CREATED.value),
                None,
            )
            if c_ev and isinstance(c_ev["recorded_at"], dt.datetime):
                issue_created_at[iid] = c_ev["recorded_at"]

    now = dt.datetime.now(dt.UTC)
    today = now.date()
    start_date = today - dt.timedelta(days=window_days - 1)
    date_list = [start_date + dt.timedelta(days=d) for d in range(window_days)]
    window_start_dt = dt.datetime.combine(start_date, dt.time.min, tzinfo=dt.UTC)

    # 1. Daily CFD Series
    cfd_points: list[CfdPoint] = []
    for day in date_list:
        day_str = day.isoformat()
        day_cutoff = dt.datetime.combine(day, dt.time.max, tzinfo=dt.UTC)
        group_counts: dict[str, int] = dict.fromkeys(STATE_GROUPS, 0)
        by_state_counts: dict[str, int] = {str(s.id): 0 for s in states}
        total_for_day = 0

        for issue_id, issue in issue_map.items():
            c_at = issue_created_at.get(issue_id, issue_created_at.get(issue_id, now))
            if c_at > day_cutoff:
                continue

            events = events_by_issue.get(issue_id, [])
            state_changes = [
                e
                for e in events
                if e["event_type"] == ActivityEventType.ISSUE_STATE_CHANGED.value
                and isinstance(e["recorded_at"], dt.datetime)
            ]
            past_changes = [e for e in state_changes if e["recorded_at"] <= day_cutoff]

            resolved_state_id: uuid.UUID = issue.state_id
            if past_changes:
                last_ch = past_changes[-1]
                to_str = last_ch["payload"].get("to_state_id")
                if to_str:
                    try:
                        resolved_state_id = uuid.UUID(str(to_str))
                    except (ValueError, TypeError):
                        resolved_state_id = issue.state_id
            elif state_changes:
                first_ch = state_changes[0]
                from_str = first_ch["payload"].get("from_state_id")
                if from_str:
                    try:
                        resolved_state_id = uuid.UUID(str(from_str))
                    except (ValueError, TypeError):
                        resolved_state_id = issue.state_id

            wf_state = state_by_id.get(resolved_state_id)
            group_name = wf_state.state_group if wf_state else "unstarted"
            if group_name in group_counts:
                group_counts[group_name] += 1
            else:
                group_counts["unstarted"] += 1

            st_id_str = str(resolved_state_id)
            by_state_counts[st_id_str] = by_state_counts.get(st_id_str, 0) + 1
            total_for_day += 1

        cfd_points.append(
            CfdPoint(
                date=day_str,
                backlog=group_counts.get("backlog", 0),
                unstarted=group_counts.get("unstarted", 0),
                started=group_counts.get("started", 0),
                completed=group_counts.get("completed", 0),
                cancelled=group_counts.get("cancelled", 0),
                total=total_for_day,
                counts_by_state=by_state_counts,
            )
        )

    # 2. Cycle Time & Lead Time Scatterplot
    cycle_lead_points: list[CycleLeadTimePoint] = []
    cycle_time_values: list[float] = []
    lead_time_values: list[float] = []

    # Track historical completion per day for Monte Carlo throughput
    daily_completions: Counter[dt.date] = Counter()
    # Historical state durations per column for Aging WIP thresholds
    state_durations_hours: dict[uuid.UUID, list[float]] = {s.id: [] for s in states}

    for issue_id, issue in issue_map.items():
        events = events_by_issue.get(issue_id, [])
        c_at = issue_created_at[issue_id]
        state_changes = [
            e
            for e in events
            if e["event_type"] == ActivityEventType.ISSUE_STATE_CHANGED.value
            and isinstance(e["recorded_at"], dt.datetime)
        ]

        first_started_at: dt.datetime | None = None
        latest_completed_at: dt.datetime | None = None

        # Replay transitions to determine first_started_at, latest_completed_at, and state durations
        curr_state_id: uuid.UUID | None = None
        curr_state_entered_at: dt.datetime = c_at

        # If created directly in a state
        if state_changes:
            first_from = state_changes[0]["payload"].get("from_state_id")
            if first_from:
                try:
                    curr_state_id = uuid.UUID(str(first_from))
                except (ValueError, TypeError):
                    curr_state_id = issue.state_id
            else:
                curr_state_id = issue.state_id
        else:
            curr_state_id = issue.state_id

        if curr_state_id is not None:
            st = state_by_id.get(curr_state_id)
            if st and st.state_group == "started":
                first_started_at = c_at
            elif st and st.state_group == "completed":
                latest_completed_at = c_at

        for ch in state_changes:
            rec_at: dt.datetime = ch["recorded_at"]
            to_id_raw = ch["payload"].get("to_state_id")
            if not to_id_raw:
                continue
            try:
                to_id = uuid.UUID(str(to_id_raw))
            except (ValueError, TypeError):
                continue

            # Record duration in curr_state_id
            if curr_state_id in state_durations_hours and rec_at >= curr_state_entered_at:
                dur_h = (rec_at - curr_state_entered_at).total_seconds() / 3600.0
                state_durations_hours[curr_state_id].append(dur_h)

            curr_state_id = to_id
            curr_state_entered_at = rec_at

            target_st = state_by_id.get(to_id)
            if target_st:
                if target_st.state_group == "started" and first_started_at is None:
                    first_started_at = rec_at
                elif target_st.state_group == "completed":
                    latest_completed_at = rec_at

        # Check completed status
        current_st = state_by_id.get(issue.state_id)
        is_currently_completed = current_st is not None and current_st.state_group == "completed"

        if is_currently_completed and latest_completed_at is None:
            latest_completed_at = now

        if latest_completed_at is not None and latest_completed_at >= window_start_dt:
            lead_days = round(
                max(0.0, (latest_completed_at - c_at).total_seconds() / 86400.0),
                2,
            )
            if first_started_at is not None and latest_completed_at >= first_started_at:
                cycle_days = round(
                    (latest_completed_at - first_started_at).total_seconds() / 86400.0,
                    2,
                )
            else:
                cycle_days = lead_days

            cycle_time_values.append(cycle_days)
            lead_time_values.append(lead_days)

            canonical_key = issue_canonical_keys.get(issue_id, f"ISSUE-{issue.sequence_id}")
            cycle_lead_points.append(
                CycleLeadTimePoint(
                    issue_id=issue_id,
                    issue_key=canonical_key,
                    title=issue.summary,
                    completed_at=latest_completed_at.isoformat(),
                    cycle_time_days=cycle_days,
                    lead_time_days=lead_days,
                )
            )

            comp_date = latest_completed_at.date()
            if start_date <= comp_date <= today:
                daily_completions[comp_date] += 1

    cycle_percentiles = PercentileValues(
        p50=_calculate_percentile(cycle_time_values, 50),
        p85=_calculate_percentile(cycle_time_values, 85),
        p95=_calculate_percentile(cycle_time_values, 95),
    )
    lead_percentiles = PercentileValues(
        p50=_calculate_percentile(lead_time_values, 50),
        p85=_calculate_percentile(lead_time_values, 85),
        p95=_calculate_percentile(lead_time_values, 95),
    )

    cycle_lead_metrics = CycleLeadTimeMetrics(
        points=cycle_lead_points,
        cycle_time_percentiles=cycle_percentiles,
        lead_time_percentiles=lead_percentiles,
        total_completed_in_window=len(cycle_lead_points),
    )

    # 3. Aging WIP for Active (Started) Issues
    active_issues: list[AgingWipIssue] = []
    for issue_id, issue in issue_map.items():
        st = state_by_id.get(issue.state_id)
        if not st or st.state_group != "started":
            continue

        c_at = issue_created_at[issue_id]
        events = events_by_issue.get(issue_id, [])
        state_changes = [
            e
            for e in events
            if e["event_type"] == ActivityEventType.ISSUE_STATE_CHANGED.value
            and isinstance(e["recorded_at"], dt.datetime)
        ]

        state_entered_at: dt.datetime = c_at
        first_started_at_issue: dt.datetime | None = None

        initial_wf = state_by_id.get(issue.state_id)
        if initial_wf and initial_wf.state_group == "started":
            first_started_at_issue = c_at

        for ch in state_changes:
            rec_at = ch["recorded_at"]
            to_id_raw = ch["payload"].get("to_state_id")
            if not to_id_raw:
                continue
            try:
                to_id = uuid.UUID(str(to_id_raw))
            except (ValueError, TypeError):
                continue

            target_st = state_by_id.get(to_id)
            if target_st and target_st.state_group == "started" and first_started_at_issue is None:
                first_started_at_issue = rec_at

            if to_id == issue.state_id:
                state_entered_at = rec_at

        if first_started_at_issue is None:
            first_started_at_issue = state_entered_at

        age_state_h = round(max(0.0, (now - state_entered_at).total_seconds() / 3600.0), 1)
        wip_total_h = round(max(0.0, (now - first_started_at_issue).total_seconds() / 3600.0), 1)
        canonical_key = issue_canonical_keys.get(issue_id, f"ISSUE-{issue.sequence_id}")

        active_issues.append(
            AgingWipIssue(
                issue_id=issue_id,
                issue_key=canonical_key,
                title=issue.summary,
                state_id=issue.state_id,
                state_name=st.name,
                state_color_hex=st.color_hex,
                age_in_current_state_hours=age_state_h,
                total_wip_hours=wip_total_h,
                state_entered_at=state_entered_at.isoformat(),
                first_started_at=first_started_at_issue.isoformat(),
            )
        )

    # Column thresholds for started states
    col_thresholds: dict[str, ColumnAgingThresholds] = {}
    for st in states:
        if st.state_group == "started":
            durs = state_durations_hours.get(st.id, [])
            if not durs:
                # Fallback to active issue ages in this column
                durs = [
                    ai.age_in_current_state_hours for ai in active_issues if ai.state_id == st.id
                ]
            col_thresholds[str(st.id)] = ColumnAgingThresholds(
                state_id=st.id,
                state_name=st.name,
                p50_hours=_calculate_percentile(durs, 50),
                p85_hours=_calculate_percentile(durs, 85),
                p95_hours=_calculate_percentile(durs, 95),
            )

    aging_wip_metrics = AgingWipMetrics(
        active_issues=active_issues,
        column_thresholds=col_thresholds,
        total_active_wip=len(active_issues),
    )

    # 4. Monte Carlo Throughput Forecasting
    history_samples = [daily_completions.get(d, 0) for d in date_list]
    monte_carlo_res = _simulate_monte_carlo(
        history=history_samples,
        horizon_days=horizon_days,
        target_items=target_items,
        today=today,
        trials=trials,
        seed=seed,
    )

    return ProjectFlowMetricsResponse(
        project_id=project_id,
        project_key=project.identifier,
        window_days=window_days,
        cfd=CfdSeries(points=cfd_points, states=state_meta_list),
        cycle_lead_time=cycle_lead_metrics,
        aging_wip=aging_wip_metrics,
        monte_carlo=monte_carlo_res,
    )
