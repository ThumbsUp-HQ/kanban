# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Unit and integration tests for cycle burndown computation (S7.2 8g, S11.4).

Verifies:
    1. Validation: DATE_ORDER (422), CYCLE_RANGE_TOO_LONG (422 on >366 days)
    2. Seeded activity replay: exact scope and remaining series across daily intervals
    3. Ideal burndown line calculation from (start_date, initial_scope) to (end_date, 0)
    4. Empty cycle: zero metrics with valid ideal line
    5. Fallback dates: null start_date / end_date defaults
    6. RLS security isolation: issues in unreadable projects are excluded
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models import Cycle, Issue, WorkflowState
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.services.activity import ActivityEventType
from kanban.services.burndown import (
    _evaluate_issue_at_cutoff,
    _resolve_burndown_window,
    compute_burndown,
)

_INSERT_ACT_SQL = text(
    "INSERT INTO activity_records "
    "(workspace_id, object_id, object_type, actor_id, event_type, payload, recorded_at) "
    "VALUES (:ws, :obj, 'issue'::object_kind, :actor, :ev, CAST(:pl AS jsonb), :rec)"
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def test_burndown_date_order_and_range_too_long(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Validate 422 DATE_ORDER and 422 CYCLE_RANGE_TOO_LONG (>366 days)."""
    admin = await make_user("admin_bd1", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BD1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    caller = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
    )

    # 1. DATE_ORDER: end_date < start_date
    cycle_inv = Cycle(
        start_date=dt.date(2026, 11, 20),
        end_date=dt.date(2026, 11, 10),
    )
    with pytest.raises(ProblemException) as exc_info:
        _resolve_burndown_window(cycle_inv)
    assert exc_info.value.status == 422
    assert exc_info.value.code == "DATE_ORDER"

    # 2. CYCLE_RANGE_TOO_LONG: 367 days (2026-01-01 to 2027-01-02)
    c_long_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "SELECT register_object("
            "  CAST('cycle' AS object_kind), :ws, :proj, :ckey, 'Long', :creator, :id"
            ")"
        ),
        {
            "ws": admin.workspace_id,
            "proj": proj_id,
            "ckey": f"cycle-{c_long_id.hex[:8]}",
            "creator": admin.id,
            "id": c_long_id,
        },
    )
    cycle_long = Cycle(
        id=c_long_id,
        workspace_id=admin.workspace_id,
        project_id=proj_id,
        name="Too Long",
        status="upcoming",
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2027, 1, 2),  # 367 days inclusive
    )
    api_env.seed.add(cycle_long)
    await api_env.seed.commit()

    with pytest.raises(ProblemException) as exc_info2:
        await compute_burndown(api_env.seed, caller, c_long_id)
    assert exc_info2.value.status == 422
    assert exc_info2.value.code == "CYCLE_RANGE_TOO_LONG"


async def test_burndown_seeded_activity_progression(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Verify seeded activity replay produces exact daily scope and remaining counts."""
    admin = await make_user("admin_bd2", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BD2", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create cycle spanning 2026-11-10 to 2026-11-20
    cycle_resp = await client.post(
        "/api/v1/projects/BD2/cycles",
        json={"name": "Burndown Sprint", "start_date": "2026-11-10", "end_date": "2026-11-20"},
    )
    assert cycle_resp.status_code == 201
    cycle_id = uuid.UUID(cycle_resp.json()["id"])
    await client.post(f"/api/v1/cycles/{cycle_id}/start")

    # Find workflow states
    states = (
        (
            await api_env.seed.execute(
                select(WorkflowState).where(WorkflowState.project_id == proj_id)
            )
        )
        .scalars()
        .all()
    )
    state_map = {s.state_group: s.id for s in states}
    backlog_id = state_map["backlog"]
    done_id = state_map["completed"]

    # Create 2 issues
    iss1 = (await client.post("/api/v1/projects/BD2/issues", json={"summary": "Issue 1"})).json()
    iss2 = (await client.post("/api/v1/projects/BD2/issues", json={"summary": "Issue 2"})).json()
    iss1_id = uuid.UUID(iss1["id"])
    iss2_id = uuid.UUID(iss2["id"])

    # Setup historical events in activity_records:
    # Day 2026-11-08: Issue 1 created in cycle
    ts_created = dt.datetime(2026, 11, 8, 10, 0, tzinfo=dt.UTC)
    ts_added_i2 = dt.datetime(2026, 11, 10, 14, 0, tzinfo=dt.UTC)
    ts_done_i1 = dt.datetime(2026, 11, 11, 16, 0, tzinfo=dt.UTC)

    # Assign Issue 1 directly to cycle
    await api_env.seed.execute(
        text("UPDATE issues SET cycle_id = :cid, state_id = :st WHERE id = :id"),
        {"cid": cycle_id, "st": backlog_id, "id": iss1_id},
    )
    # Assign Issue 2 to cycle
    await api_env.seed.execute(
        text("UPDATE issues SET cycle_id = :cid, state_id = :st WHERE id = :id"),
        {"cid": cycle_id, "st": backlog_id, "id": iss2_id},
    )

    # Insert historical activity events
    # Issue 1 created before start
    await api_env.seed.execute(
        _INSERT_ACT_SQL,
        {
            "ws": admin.workspace_id,
            "obj": iss1_id,
            "actor": admin.id,
            "ev": ActivityEventType.ISSUE_CREATED.value,
            "pl": '{"summary": "Issue 1"}',
            "rec": ts_created,
        },
    )

    # Issue 2 created before start
    await api_env.seed.execute(
        _INSERT_ACT_SQL,
        {
            "ws": admin.workspace_id,
            "obj": iss2_id,
            "actor": admin.id,
            "ev": ActivityEventType.ISSUE_CREATED.value,
            "pl": '{"summary": "Issue 2"}',
            "rec": ts_created,
        },
    )

    # Issue 2 added to cycle on 2026-11-12
    await api_env.seed.execute(
        _INSERT_ACT_SQL,
        {
            "ws": admin.workspace_id,
            "obj": iss2_id,
            "actor": admin.id,
            "ev": ActivityEventType.ISSUE_FIELD_CHANGED.value,
            "pl": f'{{"field": "cycle_id", "old": null, "new": "{cycle_id}"}}',
            "rec": ts_added_i2,
        },
    )

    # Issue 1 transitioned to Done on 2026-11-15
    await api_env.seed.execute(
        _INSERT_ACT_SQL,
        {
            "ws": admin.workspace_id,
            "obj": iss1_id,
            "actor": admin.id,
            "ev": ActivityEventType.ISSUE_STATE_CHANGED.value,
            "pl": f'{{"from_state_id": "{backlog_id}", "to_state_id": "{done_id}"}}',
            "rec": ts_done_i1,
        },
    )
    await api_env.seed.commit()

    # GET burndown via HTTP endpoint
    resp = await client.get(f"/api/v1/cycles/{cycle_id}/burndown")
    contract_recorder.record("burndown_200", resp.request, resp)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cycle_id"] == str(cycle_id)

    # Ideal line
    ideal = data["ideal"]
    assert len(ideal) == 2
    assert ideal[0]["date"] == "2026-11-10"
    assert ideal[1]["date"] == "2026-11-20"
    assert ideal[1]["remaining"] == 0

    # Series verification
    series = {p["date"]: p for p in data["series"]}
    assert "2026-11-10" in series
    assert series["2026-11-10"]["scope"] == 2
    assert series["2026-11-10"]["remaining"] == 2

    assert "2026-11-11" in series
    assert series["2026-11-11"]["scope"] == 2
    assert series["2026-11-11"]["remaining"] == 1

    assert "2026-11-12" in series
    assert series["2026-11-12"]["scope"] == 2
    assert series["2026-11-12"]["remaining"] == 1


async def test_burndown_empty_cycle_and_fallbacks(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify empty cycle produces 0-count series and null dates fall back safely."""
    admin = await make_user("admin_bd3", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BD3", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Empty cycle
    c_empty = (
        await client.post(
            "/api/v1/projects/BD3/cycles",
            json={"name": "Empty Sprint", "start_date": "2026-11-01", "end_date": "2026-11-10"},
        )
    ).json()

    resp = await client.get(f"/api/v1/cycles/{c_empty['id']}/burndown")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ideal"][0]["remaining"] == 0
    assert data["ideal"][1]["remaining"] == 0
    for pt in data["series"]:
        assert pt["scope"] == 0
        assert pt["remaining"] == 0

    # 2. Cycle without dates (start_date=null, end_date=null)
    caller = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
    )
    c_nodates_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "SELECT register_object("
            "  CAST('cycle' AS object_kind), :ws, :proj, :ckey, 'NoDates', :creator, :id"
            ")"
        ),
        {
            "ws": admin.workspace_id,
            "proj": proj_id,
            "ckey": f"cycle-{c_nodates_id.hex[:8]}",
            "creator": admin.id,
            "id": c_nodates_id,
        },
    )
    c_nodates = Cycle(
        id=c_nodates_id,
        workspace_id=admin.workspace_id,
        project_id=proj_id,
        name="No Dates",
        status="upcoming",
        start_date=None,
        end_date=None,
    )
    api_env.seed.add(c_nodates)
    await api_env.seed.commit()

    bd_nodates = await compute_burndown(api_env.seed, caller, c_nodates_id)
    assert bd_nodates.cycle_id == c_nodates_id
    assert len(bd_nodates.ideal) == 2

    # 3. Window resolution with partial dates (start only, end only)
    c_start_only = Cycle(
        name="S", status="upcoming", start_date=dt.date(2026, 11, 5), end_date=None
    )
    assert _resolve_burndown_window(c_start_only) == (dt.date(2026, 11, 5), dt.date(2026, 11, 5))

    c_end_only = Cycle(name="E", status="upcoming", start_date=None, end_date=dt.date(2026, 11, 25))
    assert _resolve_burndown_window(c_end_only) == (dt.date(2026, 11, 25), dt.date(2026, 11, 25))

    # 4. Future cycle: start_date > today -> empty series
    c_future = (
        await client.post(
            "/api/v1/projects/BD3/cycles",
            json={"name": "Future Sprint", "start_date": "2099-01-01", "end_date": "2099-01-15"},
        )
    ).json()
    bd_future = await compute_burndown(api_env.seed, caller, uuid.UUID(c_future["id"]))
    assert bd_future.series == []
    assert bd_future.ideal[0].date == "2099-01-01"

    # 5. Nonexistent cycle -> 404
    with pytest.raises(ProblemException) as nf_exc:
        await compute_burndown(api_env.seed, caller, uuid.uuid4())
    assert nf_exc.value.status == 404

    # 6. Candidate issues with historical cycle membership (missing_ids branch)
    # Create issue, record it was in cycle, but current issue.cycle_id is None
    iss_hist = (
        await client.post("/api/v1/projects/BD3/issues", json={"summary": "Hist Issue"})
    ).json()
    iss_hist_id = uuid.UUID(iss_hist["id"])
    await api_env.seed.execute(
        _INSERT_ACT_SQL,
        {
            "ws": admin.workspace_id,
            "obj": iss_hist_id,
            "actor": admin.id,
            "ev": ActivityEventType.ISSUE_FIELD_CHANGED.value,
            "pl": f'{{"field": "cycle_id", "old": "{c_empty["id"]}", "new": null}}',
            "rec": dt.datetime.now(dt.UTC),
        },
    )
    # Also add a state change with malformed uuid to test fallback branch
    await api_env.seed.execute(
        _INSERT_ACT_SQL,
        {
            "ws": admin.workspace_id,
            "obj": iss_hist_id,
            "actor": admin.id,
            "ev": ActivityEventType.ISSUE_STATE_CHANGED.value,
            "pl": '{"to_state_id": "not-a-valid-uuid"}',
            "rec": dt.datetime.now(dt.UTC),
        },
    )
    await api_env.seed.commit()

    # Re-run burndown for c_empty: _fetch_candidate_issues executes missing_ids query
    bd_hist = await compute_burndown(api_env.seed, caller, uuid.UUID(c_empty["id"]))
    assert bd_hist.cycle_id == uuid.UUID(c_empty["id"])


async def test_burndown_rls_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify issues belonging to unreadable projects are excluded from burndown calculation."""
    admin = await make_user("admin_bd4", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member_bd4")
    await make_project(
        "VIS1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "VIEWER"},
    )
    await make_project(
        "HID1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN"},  # member has NO access to HID1
    )

    admin_client = as_principal(admin)
    # Create cycle in VIS1 starting today
    today = dt.datetime.now(dt.UTC).date()
    cycle = (
        await admin_client.post(
            "/api/v1/projects/VIS1/cycles",
            json={
                "name": "Visible Cycle",
                "start_date": today.isoformat(),
                "end_date": (today + dt.timedelta(days=10)).isoformat(),
            },
        )
    ).json()
    cycle_id = uuid.UUID(cycle["id"])

    # Create issue in VIS1 and assign to cycle
    iss1 = (
        await admin_client.post(
            "/api/v1/projects/VIS1/issues",
            json={"summary": "Vis Issue"},
        )
    ).json()
    await admin_client.put(f"/api/v1/cycles/{cycle_id}/issues/{iss1['key']}")

    # Create issue in HID1 and insert an activity record referencing cycle_id
    iss2 = (
        await admin_client.post(
            "/api/v1/projects/HID1/issues",
            json={"summary": "Hidden Issue"},
        )
    ).json()
    await api_env.seed.execute(
        text(
            "INSERT INTO activity_records (workspace_id, object_id, object_type, actor_id, "
            "event_type, payload, recorded_at) "
            "VALUES (:ws, :obj, 'issue'::object_kind, :actor, :ev, CAST(:pl AS jsonb), :rec)"
        ),
        {
            "ws": admin.workspace_id,
            "obj": uuid.UUID(iss2["id"]),
            "actor": admin.id,
            "ev": ActivityEventType.ISSUE_FIELD_CHANGED.value,
            "pl": f'{{"field": "cycle_id", "old": null, "new": "{cycle_id}"}}',
            "rec": dt.datetime.now(dt.UTC),
        },
    )
    await api_env.seed.commit()

    # Member fetches burndown: only the visible issue should be counted
    member_client = as_principal(member)
    resp = await member_client.get(f"/api/v1/cycles/{cycle_id}/burndown")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Initial scope and series should only count 1 issue (the visible one)
    assert data["ideal"][0]["remaining"] == 1
    for pt in data["series"]:
        assert pt["scope"] <= 1


def test_evaluate_issue_at_cutoff_edge_cases() -> None:
    """Direct unit tests for _evaluate_issue_at_cutoff branches."""
    cid = uuid.uuid4()
    iss_id = uuid.uuid4()
    st_id = uuid.uuid4()
    done_st_id = uuid.uuid4()
    mock_issue = Issue(id=iss_id, cycle_id=cid, state_id=st_id)
    cutoff = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)

    # 1. Created at > cutoff -> (False, False)
    events_future_created: list[dict[str, object]] = [
        {
            "event_type": ActivityEventType.ISSUE_CREATED.value,
            "recorded_at": dt.datetime(2026, 11, 15, tzinfo=dt.UTC),
            "payload": {},
        }
    ]
    res_future = _evaluate_issue_at_cutoff(mock_issue, events_future_created, cid, cutoff, {})
    assert res_future == (False, False)

    # 2. Future state change with invalid from_state_id UUID -> falls back to unstarted
    events_future_state: list[dict[str, object]] = [
        {
            "event_type": ActivityEventType.ISSUE_STATE_CHANGED.value,
            "recorded_at": dt.datetime(2026, 11, 15, tzinfo=dt.UTC),
            "payload": {"from_state_id": "invalid-uuid"},
        }
    ]
    in_c, is_unf = _evaluate_issue_at_cutoff(mock_issue, events_future_state, cid, cutoff, {})
    assert in_c is True
    assert is_unf is True

    # 3. Past state change with invalid to_state_id UUID -> falls back to unstarted
    events_past_invalid: list[dict[str, object]] = [
        {
            "event_type": ActivityEventType.ISSUE_STATE_CHANGED.value,
            "recorded_at": dt.datetime(2026, 11, 5, tzinfo=dt.UTC),
            "payload": {"to_state_id": "not-a-uuid"},
        }
    ]
    in_c3, is_unf3 = _evaluate_issue_at_cutoff(mock_issue, events_past_invalid, cid, cutoff, {})
    assert in_c3 is True
    assert is_unf3 is True

    # 4. Past state change with valid completed to_state_id -> is_unfinished is False
    events_past_valid: list[dict[str, object]] = [
        {
            "event_type": ActivityEventType.ISSUE_STATE_CHANGED.value,
            "recorded_at": dt.datetime(2026, 11, 5, tzinfo=dt.UTC),
            "payload": {"to_state_id": str(done_st_id)},
        }
    ]
    in_c4, is_unf4 = _evaluate_issue_at_cutoff(
        mock_issue, events_past_valid, cid, cutoff, {done_st_id: "completed"}
    )
    assert in_c4 is True
    assert is_unf4 is False
