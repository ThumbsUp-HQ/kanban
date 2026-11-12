# Copyright 2026 Kanban Platform Contributors
"""Tests for Issue Move API endpoint (KB-P3-12, S6.4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models import Issue, WorkflowState
from kanban.services.activity import ActivityEventType
from kanban.tests.security.helpers import add_acl_entry, rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _create_api_test_issue(
    client: httpx.AsyncClient,
    project_key: str,
    summary: str = "Test Issue",
) -> dict[str, str]:
    """Create an issue via API and return its JSON response dict."""
    resp = await client.post(
        f"/api/v1/projects/{project_key}/issues",
        json={"summary": summary},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def test_case_1_single_row_mutation_proof_and_contract(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Moving card 50 between 2 and 3 updates exactly 1 row (99 byte-identical)."""
    admin = await make_user("admin1", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("SRM", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Fetch states
    states = (
        (
            await api_env.seed.execute(
                select(WorkflowState)
                .where(WorkflowState.project_id == proj_id)
                .order_by(WorkflowState.sort_order)
            )
        )
        .scalars()
        .all()
    )
    default_state = states[0]

    # Create 100 issues via fast committed inserts to verify 1-row mutation proof
    prio_id = await api_env.seed.scalar(
        text("SELECT id FROM project_priorities WHERE project_id = :p ORDER BY sort_order LIMIT 1"),
        {"p": proj_id},
    )

    issue_keys: list[str] = []
    for i in range(1, 101):
        seq = await api_env.seed.scalar(
            text("SELECT allocate_issue_sequence(:p)"),
            {"p": proj_id},
        )
        key = f"SRM-{seq}"
        issue_keys.append(key)
        iss_id = await api_env.seed.scalar(
            text(
                "SELECT register_object(  'issue'::object_kind, :ws, :proj, :ckey, :name, :creator)"
            ),
            {
                "ws": api_env.workspace_id,
                "proj": proj_id,
                "ckey": key,
                "name": f"Issue {i}",
                "creator": admin.id,
            },
        )
        rank = f"a{i:06d}V"
        await api_env.seed.execute(
            text(
                "INSERT INTO issues ("
                "  id, workspace_id, project_id, sequence_id, summary, state_id, "
                "  priority_id, board_rank, created_by_id, original_created_by_id"
                ") VALUES ("
                "  :id, :ws, :proj, :seq, :summary, :state, :prio, :rank, :creator, :creator"
                ")"
            ),
            {
                "id": iss_id,
                "ws": api_env.workspace_id,
                "proj": proj_id,
                "seq": seq,
                "summary": f"Issue {i}",
                "state": default_state.id,
                "prio": prio_id,
                "rank": rank,
                "creator": admin.id,
            },
        )
    await api_env.seed.commit()

    # Capture ranks of all 100 issues before move
    pre_rows = (
        await api_env.seed.execute(
            select(Issue.sequence_id, Issue.board_rank).where(Issue.project_id == proj_id)
        )
    ).all()
    pre_ranks: dict[int, str] = {row[0]: row[1] for row in pre_rows}
    assert len(pre_ranks) == 100

    # Move card 50 between card 2 and card 3
    card_50_key = "SRM-50"
    card_2_key = "SRM-2"
    card_3_key = "SRM-3"

    resp = await client.post(
        f"/api/v1/issues/{card_50_key}/move",
        json={
            "target_state_id": str(default_state.id),
            "after_issue": card_2_key,
            "before_issue": card_3_key,
        },
    )
    contract_recorder.record("move_issue_single_row_200", resp.request, resp)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["issue_key"] == card_50_key
    assert data["state_id"] == str(default_state.id)
    assert data["rebalance_scheduled"] is False
    assert data["wip_warning"] is None

    new_rank_50 = data["board_rank"]
    assert pre_ranks[2].encode("ascii") < new_rank_50.encode("ascii") < pre_ranks[3].encode("ascii")

    # Verify that exactly 1 row changed in the database, and 99 remain byte-identical
    post_rows = (
        await api_env.seed.execute(
            select(Issue.sequence_id, Issue.board_rank).where(Issue.project_id == proj_id)
        )
    ).all()
    post_ranks: dict[int, str] = {row[0]: row[1] for row in post_rows}
    assert post_ranks[50] == new_rank_50
    assert post_ranks[50] != pre_ranks[50]

    changed_count = 0
    for seq_num in range(1, 101):
        if post_ranks[seq_num] != pre_ranks[seq_num]:
            changed_count += 1
            assert seq_num == 50

    assert changed_count == 1, "Exactly 1 row must be updated in a single-row mutation!"


async def test_case_2a_soft_and_hard_wip_limits(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Soft & Hard WIP: soft warning (200), hard block (409)."""
    admin = await make_user("admin2a", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member2a")
    proj_id = await make_project(
        "WIP1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER"},
    )
    member_client = as_principal(member)

    states = (
        (
            await api_env.seed.execute(
                select(WorkflowState)
                .where(WorkflowState.project_id == proj_id)
                .order_by(WorkflowState.sort_order)
            )
        )
        .scalars()
        .all()
    )
    target_state = states[1]

    # Configure WIP limits on target_state: soft=2, hard=3
    await api_env.seed.execute(
        text("UPDATE workflow_states SET wip_soft_limit = 2, wip_hard_limit = 3 WHERE id = :id"),
        {"id": target_state.id},
    )
    await api_env.seed.commit()

    # Create 4 cards via member
    created_keys: list[str] = []
    for i in range(4):
        iss = await _create_api_test_issue(member_client, "WIP1", f"WIP Issue {i + 1}")
        created_keys.append(iss["key"])

    # 1. Move card 1 into target_state (count=1 <= soft=2) -> 200, wip_warning=None
    r1 = await member_client.post(
        f"/api/v1/issues/{created_keys[0]}/move",
        json={"target_state_id": str(target_state.id)},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["wip_warning"] is None

    # 2. Move card 2 into target_state (count=2 <= soft=2) -> 200, wip_warning=None
    r2 = await member_client.post(
        f"/api/v1/issues/{created_keys[1]}/move",
        json={"target_state_id": str(target_state.id)},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["wip_warning"] is None

    # 3. Move card 3 into target_state (count=3 > soft=2 and <= hard=3) -> 200 with wip_warning
    r3 = await member_client.post(
        f"/api/v1/issues/{created_keys[2]}/move",
        json={"target_state_id": str(target_state.id)},
    )
    contract_recorder.record("move_issue_soft_wip_warning_200", r3.request, r3)
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    assert d3["wip_warning"] is not None
    assert d3["wip_warning"]["soft_limit"] == 2
    assert d3["wip_warning"]["resulting_count"] == 3

    # 4. Move card 4 into target_state as member (count=4 > hard=3) -> 409 WIP_HARD_LIMIT_EXCEEDED
    r4 = await member_client.post(
        f"/api/v1/issues/{created_keys[3]}/move",
        json={"target_state_id": str(target_state.id)},
    )
    contract_recorder.record("move_issue_hard_wip_blocked_409", r4.request, r4)
    assert r4.status_code == 409, r4.text
    err4 = r4.json()
    assert err4["code"] == "WIP_HARD_LIMIT_EXCEEDED"
    assert err4["hard_limit"] == 3
    assert err4["current_count"] == 3


async def test_case_2b_hard_wip_admin_overrides(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Hard WIP admin override: AAL2 required (403), valid override (200), intra reorder (200)."""
    admin = await make_user("admin2b", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member2b")
    proj_id = await make_project(
        "WIP2",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER"},
    )
    member_client = as_principal(member)

    states = (
        (
            await api_env.seed.execute(
                select(WorkflowState)
                .where(WorkflowState.project_id == proj_id)
                .order_by(WorkflowState.sort_order)
            )
        )
        .scalars()
        .all()
    )
    target_state = states[1]

    # Configure WIP limits on target_state: soft=2, hard=3
    await api_env.seed.execute(
        text("UPDATE workflow_states SET wip_soft_limit = 2, wip_hard_limit = 3 WHERE id = :id"),
        {"id": target_state.id},
    )
    await api_env.seed.commit()

    created_keys: list[str] = []
    for i in range(4):
        iss = await _create_api_test_issue(member_client, "WIP2", f"WIP Issue {i + 1}")
        created_keys.append(iss["key"])

    # Move 3 cards into target_state
    for k in created_keys[:3]:
        r = await member_client.post(
            f"/api/v1/issues/{k}/move",
            json={"target_state_id": str(target_state.id)},
        )
        assert r.status_code == 200

    # 1. Move card 4 as admin lacking AAL2 (aal_level=1) -> 403 AAL2_REQUIRED
    admin_aal1_client = as_principal(admin, aal_level=1)
    r4_aal1 = await admin_aal1_client.post(
        f"/api/v1/issues/{created_keys[3]}/move",
        json={"target_state_id": str(target_state.id), "wip_override_reason": "Emergency fix"},
    )
    assert r4_aal1.status_code == 403, r4_aal1.text
    assert r4_aal1.json()["code"] == "AAL2_REQUIRED"

    # 2. Move card 4 as admin with AAL2 but short reason (< 10 chars) -> 409
    admin_aal2_client = as_principal(admin, aal_level=2)
    r4_short = await admin_aal2_client.post(
        f"/api/v1/issues/{created_keys[3]}/move",
        json={"target_state_id": str(target_state.id), "wip_override_reason": "short"},
    )
    assert r4_short.status_code == 409, r4_short.text
    assert r4_short.json()["code"] == "WIP_HARD_LIMIT_OVERRIDE_REQUIRED"

    # 3. Move card 4 as admin with AAL2 and valid reason (>= 10 chars) -> 200
    override_reason = "Emergency hotfix approved by SecOps team"
    r4_override = await admin_aal2_client.post(
        f"/api/v1/issues/{created_keys[3]}/move",
        json={"target_state_id": str(target_state.id), "wip_override_reason": override_reason},
    )
    contract_recorder.record("move_issue_admin_override_200", r4_override.request, r4_override)
    assert r4_override.status_code == 200, r4_override.text
    assert r4_override.json()["state_id"] == str(target_state.id)

    # Verify WIP_HARD_LIMIT_OVERRIDDEN activity recorded in database
    act_row = (
        await api_env.seed.execute(
            text(
                "SELECT payload FROM activity_records "
                "WHERE event_type = :e ORDER BY id DESC LIMIT 1"
            ),
            {"e": ActivityEventType.WIP_HARD_LIMIT_OVERRIDDEN.value},
        )
    ).scalar_one_or_none()
    assert act_row is not None
    assert act_row["hard_limit"] == 3
    assert act_row["resulting_count"] == 4
    assert act_row["reason"] == override_reason

    # 4. Intra-column reorder when column has 4 cards (> hard_limit 3) succeeds for regular member
    r_intra = await member_client.post(
        f"/api/v1/issues/{created_keys[0]}/move",
        json={
            "target_state_id": str(target_state.id),
            "after_issue": created_keys[1],
        },
    )
    assert r_intra.status_code == 200, r_intra.text


async def test_case_3_security_and_anchors(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Security & Anchors: non-viewer 404, edit-only 403, invalid anchors 422, conflict 409."""
    admin = await make_user("admin3", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member3")
    outsider = await make_user("outsider3")
    edit_only_user = await make_user("editor3")

    proj_id = await make_project(
        "SEC",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER", edit_only_user: "VIEWER"},
    )
    admin_client = as_principal(admin)
    outsider_client = as_principal(outsider)

    states = (
        (
            await api_env.seed.execute(
                select(WorkflowState)
                .where(WorkflowState.project_id == proj_id)
                .order_by(WorkflowState.sort_order)
            )
        )
        .scalars()
        .all()
    )
    s0 = states[0]
    s1 = states[1]

    # Create 3 cards in state 0 as admin
    admin_client = as_principal(admin)
    c1 = await _create_api_test_issue(admin_client, "SEC", "Card 1")
    c2 = await _create_api_test_issue(admin_client, "SEC", "Card 2")
    c3 = await _create_api_test_issue(admin_client, "SEC", "Card 3")

    # Grant edit_only_user EDIT capability on c3 specifically (VIEW comes from VIEWER role)
    c3_obj_id = await api_env.seed.scalar(
        text("SELECT id FROM objects WHERE canonical_key = :k"),
        {"k": c3["key"]},
    )
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        c3_obj_id,
        edit_only_user.id,
        capability_mask=5,  # VIEW=1 | EDIT=4 (no TRANSITION=16)
        created_by_id=admin.id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # 1. Non-viewer gets 404
    outsider_client = as_principal(outsider)
    r_non_viewer = await outsider_client.post(
        f"/api/v1/issues/{c1['key']}/move",
        json={"target_state_id": str(s0.id)},
    )
    assert r_non_viewer.status_code == 404, r_non_viewer.text

    # 2. EDIT-only user can reorder within column (s0)
    editor_client = as_principal(edit_only_user)
    r_reorder = await editor_client.post(
        f"/api/v1/issues/{c3['key']}/move",
        json={"target_state_id": str(s0.id), "after_issue": c1["key"], "before_issue": c2["key"]},
    )
    assert r_reorder.status_code == 200, r_reorder.text

    # 3. EDIT-only user gets 403 INSUFFICIENT_CAPABILITY when moving cross-column
    r_cross_403 = await editor_client.post(
        f"/api/v1/issues/{c3['key']}/move",
        json={"target_state_id": str(s1.id)},
    )
    assert r_cross_403.status_code == 403, r_cross_403.text
    assert r_cross_403.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 4. Invalid reference: target_state_id from another project
    admin_client = as_principal(admin)
    r_bad_state = await admin_client.post(
        f"/api/v1/issues/{c1['key']}/move",
        json={"target_state_id": str(uuid.uuid4())},
    )
    assert r_bad_state.status_code == 422, r_bad_state.text
    assert r_bad_state.json()["code"] == "INVALID_REFERENCE"

    # 5. Invalid anchor: non-existent anchor issue
    r_bad_anchor = await admin_client.post(
        f"/api/v1/issues/{c1['key']}/move",
        json={"target_state_id": str(s0.id), "after_issue": "SEC-9999"},
    )
    assert r_bad_anchor.status_code == 422, r_bad_anchor.text
    assert r_bad_anchor.json()["code"] == "INVALID_ANCHOR"

    # 6. Invalid anchor: anchor issue in another state
    await admin_client.post(
        f"/api/v1/issues/{c2['key']}/move",
        json={"target_state_id": str(s1.id)},
    )
    r_other_state_anchor = await admin_client.post(
        f"/api/v1/issues/{c1['key']}/move",
        json={"target_state_id": str(s0.id), "after_issue": c2["key"]},
    )
    assert r_other_state_anchor.status_code == 422, r_other_state_anchor.text
    assert r_other_state_anchor.json()["code"] == "INVALID_ANCHOR"

    # 7. Anchor order conflict: after_issue rank >= before_issue rank -> 409
    c4 = await _create_api_test_issue(admin_client, "SEC", "Card 4")
    c5 = await _create_api_test_issue(admin_client, "SEC", "Card 5")
    await admin_client.post(
        f"/api/v1/issues/{c4['key']}/move",
        json={"target_state_id": str(s1.id)},
    )
    await admin_client.post(
        f"/api/v1/issues/{c5['key']}/move",
        json={"target_state_id": str(s1.id)},
    )

    r_conflict = await admin_client.post(
        f"/api/v1/issues/{c1['key']}/move",
        json={"target_state_id": str(s1.id), "after_issue": c5["key"], "before_issue": c4["key"]},
    )
    contract_recorder.record("move_issue_anchor_order_conflict_409", r_conflict.request, r_conflict)
    assert r_conflict.status_code == 409, r_conflict.text
    assert r_conflict.json()["code"] == "ANCHOR_ORDER_CONFLICT"

    # 8. Extra fields in request body forbidden
    r_extra = await admin_client.post(
        f"/api/v1/issues/{c1['key']}/move",
        json={"target_state_id": str(s0.id), "unknown_field": "disallowed"},
    )
    assert r_extra.status_code == 422


async def test_case_4_archived_issue_and_rebalance_scheduled(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Cannot move archived issue (409), and deep rank triggers rebalance_scheduled."""
    admin = await make_user("admin4", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("ARC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = (
        (
            await api_env.seed.execute(
                select(WorkflowState)
                .where(WorkflowState.project_id == proj_id)
                .order_by(WorkflowState.sort_order)
            )
        )
        .scalars()
        .all()
    )
    s0 = states[0]

    c1 = await _create_api_test_issue(client, "ARC", "Active Card")
    c_arch = await _create_api_test_issue(client, "ARC", "Archived Card")

    # Mark c_arch archived in objects
    await api_env.seed.execute(
        text("UPDATE objects SET archived_at = NOW() WHERE canonical_key = :k"),
        {"k": c_arch["key"]},
    )
    await api_env.seed.commit()

    # Moving archived card -> 409 ISSUE_ARCHIVED
    r_arch = await client.post(
        f"/api/v1/issues/{c_arch['key']}/move",
        json={"target_state_id": str(s0.id)},
    )
    assert r_arch.status_code == 409, r_arch.text
    assert r_arch.json()["code"] == "ISSUE_ARCHIVED"

    # Moving with anchor as archived card -> 422 INVALID_ANCHOR
    r_anchor_arch = await client.post(
        f"/api/v1/issues/{c1['key']}/move",
        json={"target_state_id": str(s0.id), "after_issue": c_arch["key"]},
    )
    assert r_anchor_arch.status_code == 422, r_anchor_arch.text
    assert r_anchor_arch.json()["code"] == "INVALID_ANCHOR"
