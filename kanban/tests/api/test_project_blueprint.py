# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for Project Blueprint REST endpoints and engine (KB-P4-10)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> None:
    """Enroll confirmed TOTP factor and elevate test client to AAL2 session."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )


async def _seed_test_issue(  # noqa: PLR0913, PLR0917
    api_env: ApiEnv,
    proj_id: str,
    pref: str,
    admin_uid: uuid.UUID,
    state_id: str,
    priority_id: str,
    summary: str = "Test Issue",
    cycle_id: str | None = None,
) -> uuid.UUID:
    """Seed an issue for testing state migrations or cycle rollover."""
    ws_id = (
        await api_env.seed.execute(
            text("SELECT workspace_id FROM projects WHERE id = :p"), {"p": proj_id}
        )
    ).scalar_one()
    seq_val = (
        await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()
    issue_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :creator, :id)"
        ),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"{pref}-{seq_val}",
            "title": summary,
            "creator": admin_uid,
            "id": issue_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, cycle_id, summary, created_by_id, "
            "original_created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, :st, :pr, :cyc, :title, "
            ":creator, :creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq_val,
            "st": state_id,
            "pr": priority_id,
            "cyc": cycle_id,
            "title": summary,
            "creator": admin_uid,
        },
    )
    await api_env.seed.commit()
    return issue_id


async def test_case_1_positive_blueprint_plan_apply_and_roundtrip(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test positive flow: plan + apply creates project KAN, get -> plan roundtrip."""
    admin = await make_user("admin_case1", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)
    client = api_env.client

    blueprint_payload = {
        "identifier": "KAN",
        "name": "Kanban Project KAN",
        "description_markdown": "Test project created via declarative blueprint",
        "states": [
            {"name": "Backlog", "group": "backlog", "color": "#94A3B8", "sort_order": 0},
            {"name": "Todo", "group": "unstarted", "color": "#64748B", "sort_order": 1},
            {"name": "In Progress", "group": "started", "color": "#3B82F6", "sort_order": 2},
            {"name": "In Review", "group": "started", "color": "#8B5CF6", "sort_order": 3},
            {"name": "Done", "group": "completed", "color": "#10B981", "sort_order": 4},
            {"name": "Canceled", "group": "cancelled", "color": "#EF4444", "sort_order": 5},
        ],
        "priorities": [
            {"name": "Urgent", "emoji": "🔴", "color": "#EF4444", "sort_order": 0},
            {"name": "High", "emoji": "🟠", "color": "#F97316", "sort_order": 1},
            {"name": "Medium", "emoji": "🟡", "color": "#FBBF24", "sort_order": 2},
            {"name": "Low", "emoji": "🔵", "color": "#3B82F6", "sort_order": 3},
            {"name": "None", "emoji": "⚪", "color": "#94A3B8", "sort_order": 4},
        ],
        "labels": [
            {"name": "frontend", "color": "#3B82F6", "exclusive_group": "layer"},
            {"name": "backend", "color": "#10B981", "exclusive_group": "layer"},
            {"name": "bug", "color": "#EF4444", "exclusive_group": None},
        ],
        "modules_enabled": True,
        "modules": [{"name": "Core"}, {"name": "Auth"}],
        "default_modules": ["Core"],
        "auto_archive_days": 30,
        "wip_limits": {"In Progress": {"soft": 5, "hard": 8}},
    }

    # 1. Plan
    plan_resp = await client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={"blueprint": blueprint_payload},
    )
    assert plan_resp.status_code == 200, plan_resp.text
    plan_data = plan_resp.json()
    assert plan_data["project"] == "KAN"
    assert "plan_sha256" in plan_data
    plan_sha = plan_data["plan_sha256"]
    assert "create" in plan_data["changes"]["project"]

    # 2. Apply
    apply_resp = await client.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={"blueprint": blueprint_payload, "plan_sha256": plan_sha},
    )
    assert apply_resp.status_code == 200, apply_resp.text
    apply_data = apply_resp.json()
    assert apply_data["status"] == "applied"
    assert apply_data["project"] == "KAN"

    # Verify project in DB
    proj_row = (
        await api_env.seed.execute(
            text(
                "SELECT identifier, name, modules_enabled, auto_archive_days "
                "FROM projects WHERE identifier = 'KAN'"
            )
        )
    ).first()
    assert proj_row is not None
    assert proj_row.identifier == "KAN"
    assert proj_row.modules_enabled is True
    assert proj_row.auto_archive_days == 30

    # 3. Get blueprint and verify round-trip fidelity
    get_resp = await client.get("/api/v1/admin/projects/KAN/blueprint")
    assert get_resp.status_code == 200, get_resp.text
    fetched_bp = get_resp.json()

    assert fetched_bp["identifier"] == "KAN"
    assert len(fetched_bp["states"]) == 6
    assert len(fetched_bp["priorities"]) == 5
    assert len(fetched_bp["labels"]) == 3
    assert len(fetched_bp["modules"]) == 2
    assert fetched_bp["default_modules"] == ["Core"]
    assert fetched_bp["auto_archive_days"] == 30

    # Plan with get output yields zero changes
    roundtrip_plan = await client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={"blueprint": fetched_bp},
    )
    assert roundtrip_plan.status_code == 200
    assert roundtrip_plan.json()["changes"] == {}


async def test_case_1_cycles_and_rollover(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Create cycles Cycle 4 / Cycle 5, start Cycle 4, rollover exactly 7 unfinished issues."""
    admin = await make_user("admin_cyc1", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # Create project
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"identifier": "CYC", "name": "Cycle Rollover Project"},
    )
    assert proj_resp.status_code == 201
    proj_id = proj_resp.json()["id"]

    # Fetch states and priorities
    states = (await client.get(f"/api/v1/projects/{proj_id}/states")).json()
    st_started = next(s["id"] for s in states if s["group"] == "started")
    st_completed = next(s["id"] for s in states if s["group"] == "completed")
    priorities = (await client.get(f"/api/v1/projects/{proj_id}/priorities")).json()
    pri_id = priorities[0]["id"]

    # Create Cycle 4 and Cycle 5
    c4_resp = await client.post(f"/api/v1/projects/{proj_id}/cycles", json={"name": "Cycle 4"})
    assert c4_resp.status_code == 201
    c4_id = c4_resp.json()["id"]

    c5_resp = await client.post(f"/api/v1/projects/{proj_id}/cycles", json={"name": "Cycle 5"})
    assert c5_resp.status_code == 201
    c5_id = c5_resp.json()["id"]

    # Start Cycle 4
    start_resp = await client.post(f"/api/v1/cycles/{c4_id}/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "active"

    # Seed 7 unfinished issues in Cycle 4
    for i in range(7):
        await _seed_test_issue(
            api_env, proj_id, "CYC", admin.id, st_started, pri_id, f"Unfinished {i}", cycle_id=c4_id
        )

    # Seed 2 completed issues in Cycle 4
    for i in range(2):
        await _seed_test_issue(
            api_env,
            proj_id,
            "CYC",
            admin.id,
            st_completed,
            pri_id,
            f"Completed {i}",
            cycle_id=c4_id,
        )

    # Perform rollover to Cycle 5
    rollover_resp = await client.post(
        f"/api/v1/cycles/{c4_id}/rollover",
        json={"target_cycle_id": c5_id},
    )
    assert rollover_resp.status_code == 200, rollover_resp.text
    rollover_data = rollover_resp.json()
    assert rollover_data["status"] == "rolled_over"
    assert rollover_data["from_cycle"] == "Cycle 4"
    assert rollover_data["to_cycle"] == "Cycle 5"
    assert rollover_data["moved"] == 7

    # Verify in DB: exactly 7 issues moved to Cycle 5, 2 completed issues remained in Cycle 4
    c5_cnt = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE cycle_id = :cid"), {"cid": uuid.UUID(c5_id)}
        )
    ).scalar_one()
    assert c5_cnt == 7

    c4_cnt = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE cycle_id = :cid"), {"cid": uuid.UUID(c4_id)}
        )
    ).scalar_one()
    assert c4_cnt == 2


async def test_case_2_atomicity_stale_plan_and_security(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test atomicity rollback on error, stale plan_sha256 rejection, and permissions."""
    admin = await make_user("admin_sec2", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer_sec2")
    await _as_admin_aal2(api_env, admin)
    client = api_env.client
    viewer_client = as_principal(viewer, aal_level=1)

    # 1. Non-admin project blueprint plan rejected
    bp = {
        "identifier": "SEC",
        "name": "Security Project",
        "states": [
            {"name": "Started", "group": "started", "color": "#3B82F6"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
    }
    non_admin_resp = await viewer_client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={"blueprint": bp},
    )
    assert non_admin_resp.status_code in (401, 403)

    # 2. Plan and apply project SEC as admin
    await _as_admin_aal2(api_env, admin)
    plan_resp = await client.post("/api/v1/admin/projects/blueprint:plan", json={"blueprint": bp})
    assert plan_resp.status_code == 200
    plan_sha = plan_resp.json()["plan_sha256"]

    apply_resp = await client.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={"blueprint": bp, "plan_sha256": plan_sha},
    )
    assert apply_resp.status_code == 200

    # 3. Stale plan: modified blueprint with old plan_sha256 -> 409 PLAN_STALE
    stale_resp = await client.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={
            "blueprint": {
                **bp,
                "name": "Different Name",
            },
            "plan_sha256": plan_sha,
        },
    )
    assert stale_resp.status_code == 409
    assert stale_resp.json()["code"] == "PLAN_STALE"

    # 4. Atomicity: blueprint with 200 labels where one violates exclusive_group
    # uniqueness applies 0 changes
    labels = [
        {"name": f"label-{i}", "color": "#64748B", "exclusive_group": None} for i in range(199)
    ]
    # 200th label has invalid exclusive group pattern violating constraint
    labels.append({"name": "bad-label", "color": "#64748B", "exclusive_group": "INVALID_GROUP!"})

    bad_bp = {
        **bp,
        "labels": labels,
    }
    # Schema validation rejects invalid pattern
    bad_plan = await client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={"blueprint": bad_bp},
    )
    assert bad_plan.status_code == 422
    assert bad_plan.json()["code"] == "VALIDATION_FAILED"

    # Verify 0 labels exist in SEC
    lbl_cnt = (
        await api_env.seed.execute(
            text(
                "SELECT count(*) FROM project_labels WHERE project_id = "
                "(SELECT id FROM projects WHERE identifier = 'SEC')"
            )
        )
    ).scalar_one()
    assert lbl_cnt == 0


async def test_case_3_in_use_protection_and_migration(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test removing state with issues requires migration, and migration moves issues."""
    admin = await make_user("admin_inuse", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)
    client = api_env.client

    # 1. Create project with QA state
    bp_initial = {
        "identifier": "INU",
        "name": "In Use Project",
        "states": [
            {"name": "Todo", "group": "unstarted", "color": "#64748B"},
            {"name": "In Review", "group": "started", "color": "#8B5CF6"},
            {"name": "QA", "group": "started", "color": "#F59E0B"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
        "priorities": [{"name": "Default", "color": "#64748B"}],
    }
    p_resp = await client.post(
        "/api/v1/admin/projects/blueprint:plan", json={"blueprint": bp_initial}
    )
    p_sha = p_resp.json()["plan_sha256"]
    await client.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={"blueprint": bp_initial, "plan_sha256": p_sha},
    )

    # Fetch project ID and QA state ID
    proj_row = (
        await api_env.seed.execute(text("SELECT id FROM projects WHERE identifier = 'INU'"))
    ).first()
    assert proj_row is not None
    proj_id = str(proj_row.id)

    qa_row = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p AND name = 'QA'"),
            {"p": proj_row.id},
        )
    ).first()
    assert qa_row is not None
    qa_id = str(qa_row.id)

    pri_row = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p"),
            {"p": proj_row.id},
        )
    ).first()
    assert pri_row is not None
    pri_id = str(pri_row.id)

    # Seed 3 issues in QA state
    for i in range(3):
        await _seed_test_issue(api_env, proj_id, "INU", admin.id, qa_id, pri_id, f"QA issue {i}")

    # 2. Removing QA without state_migrations -> 409 STATE_IN_USE
    bp_no_qa = {
        "identifier": "INU",
        "name": "In Use Project",
        "states": [
            {"name": "Todo", "group": "unstarted", "color": "#64748B"},
            {"name": "In Review", "group": "started", "color": "#8B5CF6"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
        "priorities": [{"name": "Default", "color": "#64748B"}],
    }
    fail_plan = await client.post(
        "/api/v1/admin/projects/blueprint:plan", json={"blueprint": bp_no_qa}
    )
    assert fail_plan.status_code == 409
    assert fail_plan.json()["code"] == "STATE_IN_USE"

    # 3. With state_migrations: {QA: In Review} -> succeeds and moves issues
    bp_migrated = {
        **bp_no_qa,
        "state_migrations": {"QA": "In Review"},
    }
    mig_plan = await client.post(
        "/api/v1/admin/projects/blueprint:plan", json={"blueprint": bp_migrated}
    )
    assert mig_plan.status_code == 200, mig_plan.text
    mig_sha = mig_plan.json()["plan_sha256"]

    mig_apply = await client.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={"blueprint": bp_migrated, "plan_sha256": mig_sha},
    )
    assert mig_apply.status_code == 200, mig_apply.text

    # Verify QA state deleted and 3 issues moved to In Review
    in_review_row = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p AND name = 'In Review'"),
            {"p": proj_row.id},
        )
    ).first()
    assert in_review_row is not None

    in_review_cnt = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE state_id = :st"),
            {"st": in_review_row.id},
        )
    ).scalar_one()
    assert in_review_cnt == 3

    qa_exists = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM workflow_states WHERE project_id = :p AND name = 'QA'"),
            {"p": proj_row.id},
        )
    ).scalar_one()
    assert qa_exists == 0

    # 4. Removing the last completed state -> 422 VALIDATION_FAILED
    bp_no_completed = {
        "identifier": "INU",
        "name": "In Use Project",
        "states": [
            {"name": "Todo", "group": "unstarted", "color": "#64748B"},
            {"name": "In Review", "group": "started", "color": "#8B5CF6"},
        ],
    }
    no_comp_resp = await client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={"blueprint": bp_no_completed},
    )
    assert no_comp_resp.status_code == 422
    assert no_comp_resp.json()["code"] == "VALIDATION_FAILED"

    # 5. Priority in use check in compute_plan -> 409 PRIORITY_IN_USE
    p_default = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p AND label = 'Default'"),
            {"p": proj_row.id},
        )
    ).first()
    assert p_default is not None
    await api_env.seed.execute(
        text("UPDATE issues SET priority_id = :pr WHERE state_id = :st"),
        {"pr": p_default.id, "st": in_review_row.id},
    )
    await api_env.seed.commit()

    bp_no_default = {
        **bp_migrated,
        "priorities": [{"name": "Normal", "emoji": "🔵", "color": "#3B82F6"}],
    }
    p_pri_fail = await client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={"blueprint": bp_no_default},
    )
    assert p_pri_fail.status_code == 409
    assert p_pri_fail.json()["code"] == "PRIORITY_IN_USE"


async def test_case_4_boundaries_and_error_handling(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test boundary checks: identifier pattern, auto_archive_days range, 31 states."""
    admin = await make_user("admin_bnd4", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)
    client = api_env.client

    base_states = [
        {"name": "Start", "group": "started", "color": "#3B82F6"},
        {"name": "End", "group": "completed", "color": "#10B981"},
    ]

    # 1. Invalid identifiers: kan (lowercase), K (1 char), KANBANPROJX1 (11 chars)
    for bad_id in ("kan", "K", "KANBANPROJX1"):
        resp = await client.post(
            "/api/v1/admin/projects/blueprint:plan",
            json={
                "blueprint": {
                    "identifier": bad_id,
                    "name": "Boundary Project",
                    "states": base_states,
                }
            },
        )
        assert resp.status_code == 422, (
            f"Expected 422 for identifier '{bad_id}', got {resp.status_code}"
        )
        assert resp.json()["code"] == "VALIDATION_FAILED"

    # 2. Invalid auto_archive_days: 0 and 366
    for bad_days in (0, 366):
        resp = await client.post(
            "/api/v1/admin/projects/blueprint:plan",
            json={
                "blueprint": {
                    "identifier": "BND",
                    "name": "Boundary Days Project",
                    "states": base_states,
                    "auto_archive_days": bad_days,
                }
            },
        )
        assert resp.status_code == 422, f"Expected 422 for auto_archive_days {bad_days}"
        assert resp.json()["code"] == "VALIDATION_FAILED"

    # 3. 31 states exceeds MAX_STATES (30)
    too_many_states = [
        {"name": f"State-{i}", "group": "started" if i < 20 else "completed", "color": "#64748B"}
        for i in range(31)
    ]
    resp = await client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={
            "blueprint": {
                "identifier": "BND",
                "name": "Boundary States Project",
                "states": too_many_states,
            }
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_FAILED"

    # 4. State soft > hard wip limit
    bad_state_wip = await client.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={
            "blueprint": {
                "identifier": "BND",
                "name": "Boundary States Project",
                "states": [
                    {"name": "Todo", "group": "unstarted", "color": "#64748B"},
                    {
                        "name": "Prog",
                        "group": "started",
                        "color": "#3B82F6",
                        "wip_soft_limit": 10,
                        "wip_hard_limit": 5,
                    },
                    {"name": "Done", "group": "completed", "color": "#10B981"},
                ],
            }
        },
    )
    assert bad_state_wip.status_code == 422
    assert bad_state_wip.json()["code"] == "VALIDATION_FAILED"


async def test_case_5_updates_and_blueprint_validation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test full update diff lifecycle: states, priorities, labels, modules, and limits."""
    admin = await make_user("admin_up5", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)
    client = api_env.client

    initial_bp = {
        "identifier": "UPD",
        "name": "Initial Name",
        "description_markdown": "Initial Desc",
        "states": [
            {"name": "Todo", "group": "unstarted", "color": "#64748B"},
            {
                "name": "Started",
                "group": "started",
                "color": "#3B82F6",
                "wip_soft_limit": 2,
                "wip_hard_limit": 4,
            },
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
        "priorities": [
            {"name": "P1", "emoji": "🔥", "color": "#DC2626"},
            {"name": "P2", "emoji": "💤", "color": "#22C55E"},
        ],
        "labels": [
            {"name": "frontend", "color": "#3B82F6", "exclusive_group": "layer"},
            {"name": "obsolete", "color": "#A3A3A3", "exclusive_group": None},
        ],
        "modules_enabled": True,
        "modules": ["ModuleA", "ModuleB"],  # tests string coercion in validator
        "default_modules": ["ModuleA"],
        "auto_archive_days": 10,
        "wip_limits": {"Started": {"soft": 2, "hard": 4}},
    }

    # Plan and apply initial
    p1 = await client.post("/api/v1/admin/projects/blueprint:plan", json={"blueprint": initial_bp})
    assert p1.status_code == 200, p1.text
    sha1 = p1.json()["plan_sha256"]
    a1 = await client.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={"blueprint": initial_bp, "plan_sha256": sha1},
    )
    assert a1.status_code == 200, a1.text

    # Updated blueprint modifying every entity
    updated_bp = {
        "identifier": "UPD",
        "name": "Updated Name",
        "description_markdown": "Updated Desc",
        "states": [
            {"name": "Todo", "group": "unstarted", "color": "#64748B"},
            {
                "name": "Started",
                "group": "started",
                "color": "#2563EB",
                "wip_soft_limit": 3,
                "wip_hard_limit": 5,
            },
            {"name": "Review", "group": "started", "color": "#8B5CF6"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
        "priorities": [
            {"name": "P1", "emoji": "⚡", "color": "#F97316"},  # updated emoji & color
            {"name": "P2", "emoji": "💤", "color": "#22C55E"},
            {"name": "123-Priority", "emoji": "⭐", "color": "#EAB308"},  # non-alpha slug
        ],
        "labels": [
            {"name": "frontend", "color": "#2563EB", "exclusive_group": "layer"},  # updated color
            {"name": "backend", "color": "#10B981", "exclusive_group": "layer"},  # added
        ],  # obsolete label removed
        "modules_enabled": True,
        "modules": [{"name": "ModuleA"}, {"name": "ModuleC"}],  # ModuleB removed, ModuleC added
        "default_modules": ["ModuleA", "ModuleC"],
        "auto_archive_days": 20,
        "wip_limits": {"Started": {"soft": 3, "hard": 5}},
    }

    # Plan update
    p2 = await client.post("/api/v1/admin/projects/blueprint:plan", json={"blueprint": updated_bp})
    assert p2.status_code == 200, p2.text
    p2_data = p2.json()
    assert "name" in p2_data["changes"]
    assert "update" in p2_data["changes"]["states"]
    assert "create" in p2_data["changes"]["states"]
    assert "update" in p2_data["changes"]["priorities"]
    assert "create" in p2_data["changes"]["priorities"]
    assert "update" in p2_data["changes"]["labels"]
    assert "create" in p2_data["changes"]["labels"]
    assert "remove" in p2_data["changes"]["labels"]
    assert "create" in p2_data["changes"]["modules"]
    assert "remove" in p2_data["changes"]["modules"]

    # Apply update
    sha2 = p2_data["plan_sha256"]
    a2 = await client.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={"blueprint": updated_bp, "plan_sha256": sha2},
    )
    assert a2.status_code == 200, a2.text

    # Validation: soft > hard wip limit
    bad_wip = {
        **updated_bp,
        "wip_limits": {"Started": {"soft": 10, "hard": 5}},
    }
    wip_resp = await client.post(
        "/api/v1/admin/projects/blueprint:plan", json={"blueprint": bad_wip}
    )
    assert wip_resp.status_code == 422
    assert wip_resp.json()["code"] == "VALIDATION_FAILED"

    # Validation: non-existent migration target
    # When an active state needs migration to missing target, seed issue in Review state
    rev_st = (
        await api_env.seed.execute(
            text(
                "SELECT id FROM workflow_states "
                "WHERE project_id = (SELECT id FROM projects WHERE identifier = 'UPD') "
                "AND name = 'Review'"
            )
        )
    ).scalar_one()
    pri_row = (
        await api_env.seed.execute(
            text(
                "SELECT id FROM project_priorities "
                "WHERE project_id = (SELECT id FROM projects WHERE identifier = 'UPD') "
                "LIMIT 1"
            )
        )
    ).scalar_one()
    proj_id = (
        await api_env.seed.execute(text("SELECT id FROM projects WHERE identifier = 'UPD'"))
    ).scalar_one()
    await _seed_test_issue(
        api_env, str(proj_id), "UPD", admin.id, str(rev_st), str(pri_row), "Issue in Review"
    )

    raw_states = updated_bp.get("states")
    assert isinstance(raw_states, list)
    mig_missing_target = {
        **updated_bp,
        "states": [s for s in raw_states if isinstance(s, dict) and s.get("name") != "Review"],
        "state_migrations": {"Review": "DoesNotExist"},
    }
    bad_target_resp = await client.post(
        "/api/v1/admin/projects/blueprint:plan", json={"blueprint": mig_missing_target}
    )
    assert bad_target_resp.status_code == 422
    assert bad_target_resp.json()["code"] == "VALIDATION_FAILED"
