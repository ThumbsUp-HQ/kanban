# ruff: noqa: E501, PLR0913, PLR0915, PLR0917
"""Views API unit and integration tests (S6.4, S3.4).

Covers all 5 mandatory feature test cases:
    1. Positive: create shared board/timeline views, 2D query with WIP & timeline links,
       view CRUD (GET, PATCH, DELETE, list).
    2. Filter DSL matrix: state_groups, assignee_ids ('me', 'unassigned'), label_match,
       cycle_ids, overdue_only, blocked, gate_status.
    3. Security & RLS: private view returns 404 to other members, omitted from list;
       unreadable cross-project blocker does not mark issue blocked; VIEWER gets 403 on shared view.
    4. Modules gate: group_by='module' or filters.module_ids when modules_enabled=False returns 422 MODULES_DISABLED.
    5. Boundary: duplicate group axis 422, limit=201 422, state_ids=51 422, cursor mismatch 422,
       clean pagination across 55 issues (25 + 25 + 5).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import text

from database.models import View as DbView
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.views import FilterSpec
from kanban.content import ContentNormalizeError
from kanban.services.views import (
    _extract_db_filters,
    _normalize_view_description,
    _reconstruct_filters,
)
from kanban.tests.security.helpers import rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _seed_issues_batch(
    api_env: ApiEnv,
    proj_id: uuid.UUID,
    identifier: str,
    count: int,
    user_id: uuid.UUID,
    state_id: uuid.UUID,
    priority_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Fast batch issue seeder with sequence allocation and ERA refresh."""
    issue_ids: list[uuid.UUID] = []
    ws_id = api_env.workspace_id

    for i in range(1, count + 1):
        seq = (
            await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
        ).scalar_one()
        iss_id = uuid.uuid4()
        issue_ids.append(iss_id)
        await api_env.seed.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"
            ),
            {
                "ws": ws_id,
                "proj": proj_id,
                "ckey": f"{identifier}-{seq}",
                "title": f"Issue {seq}",
                "cr": user_id,
                "id": iss_id,
            },
        )
        await api_env.seed.execute(
            text(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
                "state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
                "VALUES (:id, 'issue', :ws, :proj, :seq, :title, :st, :pri, :cr, :cr, :rnk, 'top')"
            ),
            {
                "id": iss_id,
                "ws": ws_id,
                "proj": proj_id,
                "seq": seq,
                "title": f"Issue {seq}",
                "st": state_id,
                "pri": priority_id,
                "cr": user_id,
                "rnk": f"a{i:06d}",
            },
        )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()
    return issue_ids


async def test_case_1_positive_crud_and_2d_query(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive create shared board/timeline view, 2D query with WIP, links, and CRUD."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("VPRJ", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Fetch states and priorities
    states = (
        await api_env.seed.execute(
            text("SELECT id, name FROM workflow_states WHERE project_id = :p ORDER BY sort_order"),
            {"p": proj_id},
        )
    ).all()
    todo_state_id = states[0][0]
    in_prog_state_id = states[1][0]

    priorities = (
        await api_env.seed.execute(
            text(
                "SELECT id, label FROM project_priorities WHERE project_id = :p ORDER BY sort_order"
            ),
            {"p": proj_id},
        )
    ).all()
    urgent_pri_id = priorities[0][0]

    # Create shared board view with WIP limit override
    create_payload = {
        "name": "Sprint Board",
        "description_markdown": "Board view for active sprint",
        "layout": "board",
        "group_by": "state",
        "sub_group_by": "priority",
        "is_shared": True,
        "wip_limits_override": {
            str(todo_state_id): {"soft": 2, "hard": 5},
        },
    }
    resp = await client.post("/api/v1/projects/VPRJ/views", json=create_payload)
    contract_recorder.record("create_view_shared_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    view_data = resp.json()
    view_id = view_data["id"]
    assert view_data["name"] == "Sprint Board"
    assert view_data["layout"] == "board"
    assert view_data["is_shared"] is True
    assert view_data["visibility"] == "project"
    assert "access_manifest" in view_data
    assert "VIEW" in view_data["capabilities"]

    # Create timeline view
    resp_tl = await client.post(
        "/api/v1/projects/VPRJ/views",
        json={"name": "Timeline", "layout": "timeline", "is_shared": True},
    )
    assert resp_tl.status_code == 201
    tl_view_id = resp_tl.json()["id"]

    # Seed issues
    iss1_id = uuid.uuid4()
    iss2_id = uuid.uuid4()
    seq1 = (
        await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()
    seq2 = (
        await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()

    for iss_id, seq, st_id, pri_id, rnk in [
        (iss1_id, seq1, todo_state_id, urgent_pri_id, "a000001"),
        (iss2_id, seq2, in_prog_state_id, urgent_pri_id, "a000002"),
    ]:
        await api_env.seed.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"
            ),
            {
                "ws": admin.workspace_id,
                "proj": proj_id,
                "ckey": f"VPRJ-{seq}",
                "title": f"Issue {seq}",
                "cr": admin.id,
                "id": iss_id,
            },
        )
        await api_env.seed.execute(
            text(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
                "state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
                "VALUES (:id, 'issue', :ws, :proj, :seq, :title, :st, :pri, :cr, :cr, :rnk, 'top')"
            ),
            {
                "id": iss_id,
                "ws": admin.workspace_id,
                "proj": proj_id,
                "seq": seq,
                "title": f"Issue {seq}",
                "st": st_id,
                "pri": pri_id,
                "cr": admin.id,
                "rnk": rnk,
            },
        )

    # Link iss1 BLOCKS iss2
    await api_env.seed.execute(
        text(
            "INSERT INTO object_links (id, workspace_id, source_id, target_id, link_type, link_state, source_type, target_type, created_by_id) "
            "VALUES (:id, :ws, :src, :tgt, 'BLOCKS', 'ACTIVE', 'issue', 'issue', :cr)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": admin.workspace_id,
            "src": iss1_id,
            "tgt": iss2_id,
            "cr": admin.id,
        },
    )
    await rebuild_era(api_env.seed, admin.workspace_id)
    await api_env.seed.commit()

    # Query view issues
    q_resp = await client.get(f"/api/v1/views/{view_id}/issues")
    assert q_resp.status_code == 200, q_resp.text
    q_body = q_resp.json()
    assert q_body["total_matching"] == 2
    assert len(q_body["items"]) == 2
    assert len(q_body["groups"]) > 0

    # Ad-hoc query (2D swimlane with timeline layout)
    adhoc_resp = await client.post(
        "/api/v1/projects/VPRJ/issues:query",
        json={
            "layout": "timeline",
            "group_by": "state",
            "sub_group_by": "priority",
        },
    )
    contract_recorder.record("query_issues_2d_swimlane_200", adhoc_resp.request, adhoc_resp)
    assert adhoc_resp.status_code == 200, adhoc_resp.text
    adhoc_body = adhoc_resp.json()
    assert adhoc_body["total_matching"] == 2
    assert len(adhoc_body["timeline_links"]) == 1
    assert adhoc_body["timeline_links"][0]["link_type"] == "BLOCKS"

    # GET view
    get_v = await client.get(f"/api/v1/views/{view_id}")
    assert get_v.status_code == 200
    assert get_v.json()["id"] == view_id

    # PATCH view
    patch_v = await client.patch(
        f"/api/v1/views/{view_id}",
        json={"name": "Renamed Board", "description_markdown": "New description"},
    )
    assert patch_v.status_code == 200
    assert patch_v.json()["name"] == "Renamed Board"

    # List project views
    list_v = await client.get("/api/v1/projects/VPRJ/views")
    assert list_v.status_code == 200
    assert len(list_v.json()["items"]) == 2

    # DELETE view
    del_v = await client.delete(f"/api/v1/views/{tl_view_id}")
    assert del_v.status_code == 204

    # Verify deleted view is 404
    del_check = await client.get(f"/api/v1/views/{tl_view_id}")
    assert del_check.status_code == 404


async def test_case_2_filter_dsl_matrix(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 2: Filter DSL matrix (state_groups, assignees, label_match, overdue, blocked, gate)."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("FLTR", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Get workflow states
    states = (
        await api_env.seed.execute(
            text(
                "SELECT id, name, state_group FROM workflow_states WHERE project_id = :p ORDER BY sort_order"
            ),
            {"p": proj_id},
        )
    ).all()
    todo_st = next(s[0] for s in states if s[2] == "unstarted")
    in_prog_st = next(s[0] for s in states if s[2] == "started")
    done_st = next(s[0] for s in states if s[2] == "completed")

    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).scalar_one()

    # Labels
    lbl_bug = uuid.uuid4()
    lbl_feat = uuid.uuid4()
    for lid, name in [(lbl_bug, "bug"), (lbl_feat, "feature")]:
        await api_env.seed.execute(
            text(
                "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) "
                "VALUES (:id, :ws, :proj, :name, '#ff0000')"
            ),
            {"id": lid, "ws": admin.workspace_id, "proj": proj_id, "name": name},
        )

    # Seed 5 issues:
    # A: in_progress (started), assignee=admin, label=bug, overdue (due yesterday)
    # B: todo (unstarted), unassigned, labels=bug+feature, due next week
    # C: done (completed), overdue date (but completed, so overdue_only MUST exclude!)
    # D: todo, blocked by B
    # E: todo, pending_transition_exec_id set
    yesterday = dt.datetime.now(tz=dt.UTC).date() - dt.timedelta(days=1)
    next_week = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=7)

    iss_a = uuid.uuid4()
    iss_b = uuid.uuid4()
    iss_c = uuid.uuid4()
    iss_d = uuid.uuid4()
    iss_e = uuid.uuid4()

    seqs = [
        (
            await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
        ).scalar_one()
        for _ in range(5)
    ]

    items_data = [
        (iss_a, seqs[0], in_prog_st, yesterday, None),
        (iss_b, seqs[1], todo_st, next_week, None),
        (iss_c, seqs[2], done_st, yesterday, None),
        (iss_d, seqs[3], todo_st, next_week, None),
        (iss_e, seqs[4], todo_st, next_week, uuid.uuid4()),
    ]

    for iid, sq, st, dd, ptei in items_data:
        await api_env.seed.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"
            ),
            {
                "ws": admin.workspace_id,
                "proj": proj_id,
                "ckey": f"FLTR-{sq}",
                "title": f"Issue {sq}",
                "cr": admin.id,
                "id": iid,
            },
        )
        await api_env.seed.execute(
            text(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
                "state_id, priority_id, due_date, pending_transition_exec_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
                "VALUES (:id, 'issue', :ws, :proj, :seq, :title, :st, :pri, :due, :ptei, :cr, :cr, :rnk, 'top')"
            ),
            {
                "id": iid,
                "ws": admin.workspace_id,
                "proj": proj_id,
                "seq": sq,
                "title": f"Issue {sq}",
                "st": st,
                "pri": pri_id,
                "due": dd,
                "ptei": ptei,
                "cr": admin.id,
                "rnk": f"a{sq:06d}",
            },
        )

    # Assignee on A
    await api_env.seed.execute(
        text("INSERT INTO issue_assignees (issue_id, principal_id) VALUES (:iid, :pid)"),
        {"iid": iss_a, "pid": admin.id},
    )

    # Labels on A (bug), B (bug + feature)
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:iid, :lid)"),
        {"iid": iss_a, "lid": lbl_bug},
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:iid, :lid)"),
        {"iid": iss_b, "lid": lbl_bug},
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:iid, :lid)"),
        {"iid": iss_b, "lid": lbl_feat},
    )

    # Link: B BLOCKS D
    await api_env.seed.execute(
        text(
            "INSERT INTO object_links (id, workspace_id, source_id, target_id, link_type, link_state, source_type, target_type, created_by_id) "
            "VALUES (:id, :ws, :src, :tgt, 'BLOCKS', 'ACTIVE', 'issue', 'issue', :cr)"
        ),
        {"id": uuid.uuid4(), "ws": admin.workspace_id, "src": iss_b, "tgt": iss_d, "cr": admin.id},
    )

    await rebuild_era(api_env.seed, admin.workspace_id)
    await api_env.seed.commit()

    # Query 1: state_groups=["started"] -> only iss_a
    r1 = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"state_groups": ["started"]}},
    )
    assert r1.status_code == 200
    assert [i["id"] for i in r1.json()["items"]] == [str(iss_a)]

    # Query 2: assignee_ids=["me"] -> only iss_a
    r2 = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"assignee_ids": ["me"]}},
    )
    assert r2.status_code == 200
    assert [i["id"] for i in r2.json()["items"]] == [str(iss_a)]

    # Query 3: assignee_ids=["unassigned"] -> excludes iss_a
    r3 = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"assignee_ids": ["unassigned"]}},
    )
    assert r3.status_code == 200
    r3_ids = [i["id"] for i in r3.json()["items"]]
    assert str(iss_a) not in r3_ids
    assert str(iss_b) in r3_ids

    # Query 4: label_match="all" [bug, feat] -> only iss_b
    r4_all = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"label_ids": [str(lbl_bug), str(lbl_feat)], "label_match": "all"}},
    )
    assert r4_all.status_code == 200
    assert [i["id"] for i in r4_all.json()["items"]] == [str(iss_b)]

    # Query 5: label_match="any" [bug, feat] -> iss_a and iss_b
    r4_any = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"label_ids": [str(lbl_bug), str(lbl_feat)], "label_match": "any"}},
    )
    assert r4_any.status_code == 200
    any_ids = {i["id"] for i in r4_any.json()["items"]}
    assert str(iss_a) in any_ids
    assert str(iss_b) in any_ids

    # Query 6: overdue_only=True -> iss_a (due yesterday, started), excludes iss_c (done!)
    r6 = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"overdue_only": True}},
    )
    assert r6.status_code == 200
    assert [i["id"] for i in r6.json()["items"]] == [str(iss_a)]

    # Query 7: blocked=True -> only iss_d
    r7 = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"blocked": True}},
    )
    assert r7.status_code == 200
    assert [i["id"] for i in r7.json()["items"]] == [str(iss_d)]

    # Query 8: gate_status="pending" -> only iss_e
    r8 = await client.post(
        "/api/v1/projects/FLTR/issues:query",
        json={"filters": {"gate_status": "pending"}},
    )
    assert r8.status_code == 200
    assert [i["id"] for i in r8.json()["items"]] == [str(iss_e)]


async def test_case_3_security_and_rls(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Private view 404 to non-owner, unreadable blocker masking, viewer 403 on shared."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    user_a = await make_user("usera")
    user_b = await make_user("userb")

    proj_pub_id = await make_project(
        "PUB",
        created_by=admin,
        roles={user_a: "MEMBER", user_b: "VIEWER"},
    )
    proj_sec_id = await make_project(
        "SEC",
        created_by=admin,
        roles={user_a: "PROJECT_ADMIN"},  # user_b has NO access to SEC
    )

    # User A creates a private view in PUB
    priv_resp = await as_principal(user_a).post(
        "/api/v1/projects/PUB/views",
        json={"name": "User A Private", "is_shared": False, "layout": "board"},
    )
    assert priv_resp.status_code == 201, priv_resp.text
    priv_view_id = priv_resp.json()["id"]

    # User B accesses User A's private view -> 404
    b_resp = await as_principal(user_b).get(f"/api/v1/views/{priv_view_id}")
    contract_recorder.record("get_view_private_unreadable_404", b_resp.request, b_resp)
    assert b_resp.status_code == 404

    # User B lists views in PUB -> User A's private view is omitted
    b_list = await as_principal(user_b).get("/api/v1/projects/PUB/views")
    assert b_list.status_code == 200
    assert all(v["id"] != priv_view_id for v in b_list.json()["items"])

    # Unreadable cross-project blocker test:
    # Issue in PUB is blocked by Issue in SEC
    st_pub = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_pub_id},
        )
    ).scalar_one()
    pri_pub = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_pub_id},
        )
    ).scalar_one()

    st_sec = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_sec_id},
        )
    ).scalar_one()
    pri_sec = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_sec_id},
        )
    ).scalar_one()

    pub_iss_id = uuid.uuid4()
    sec_iss_id = uuid.uuid4()
    seq_pub = (
        await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_pub_id})
    ).scalar_one()
    seq_sec = (
        await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_sec_id})
    ).scalar_one()

    await api_env.seed.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, 'Pub Issue', :cr, :id)"
        ),
        {
            "ws": admin.workspace_id,
            "proj": proj_pub_id,
            "ckey": f"PUB-{seq_pub}",
            "cr": user_a.id,
            "id": pub_iss_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, 'Pub Issue', :st, :pri, :cr, :cr, 'a000001', 'top')"
        ),
        {
            "id": pub_iss_id,
            "ws": admin.workspace_id,
            "proj": proj_pub_id,
            "seq": seq_pub,
            "st": st_pub,
            "pri": pri_pub,
            "cr": user_a.id,
        },
    )

    await api_env.seed.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, 'Sec Issue', :cr, :id)"
        ),
        {
            "ws": admin.workspace_id,
            "proj": proj_sec_id,
            "ckey": f"SEC-{seq_sec}",
            "cr": user_a.id,
            "id": sec_iss_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, 'Sec Issue', :st, :pri, :cr, :cr, 'a000001', 'top')"
        ),
        {
            "id": sec_iss_id,
            "ws": admin.workspace_id,
            "proj": proj_sec_id,
            "seq": seq_sec,
            "st": st_sec,
            "pri": pri_sec,
            "cr": user_a.id,
        },
    )

    # SEC issue BLOCKS PUB issue
    await api_env.seed.execute(
        text(
            "INSERT INTO object_links (id, workspace_id, source_id, target_id, link_type, link_state, source_type, target_type, created_by_id) "
            "VALUES (:id, :ws, :src, :tgt, 'BLOCKS', 'ACTIVE', 'issue', 'issue', :cr)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": admin.workspace_id,
            "src": sec_iss_id,
            "tgt": pub_iss_id,
            "cr": user_a.id,
        },
    )
    await rebuild_era(api_env.seed, admin.workspace_id)
    await api_env.seed.commit()

    # User A (who CAN read SEC) queries PUB with blocked=True -> finds pub_iss_id
    a_q = await as_principal(user_a).post(
        "/api/v1/projects/PUB/issues:query", json={"filters": {"blocked": True}}
    )
    assert a_q.status_code == 200
    assert str(pub_iss_id) in [i["id"] for i in a_q.json()["items"]]

    # User B (who CANNOT read SEC) queries PUB with blocked=True -> returns 0 issues (zero side-channel leakage!)
    b_q = await as_principal(user_b).post(
        "/api/v1/projects/PUB/issues:query", json={"filters": {"blocked": True}}
    )
    assert b_q.status_code == 200
    assert len(b_q.json()["items"]) == 0

    # User B (VIEWER on PUB) attempts to create a shared view -> 403 INSUFFICIENT_CAPABILITY
    b_shared = await as_principal(user_b).post(
        "/api/v1/projects/PUB/views",
        json={"name": "B Shared View", "is_shared": True},
    )
    assert b_shared.status_code == 403


async def test_case_4_modules_gate(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 4: Modules gate returns 422 MODULES_DISABLED when modules_enabled = False."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("NOMOD", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Explicitly ensure modules_enabled = false
    await api_env.seed.execute(
        text("UPDATE projects SET modules_enabled = false WHERE id = :p"),
        {"p": proj_id},
    )
    await api_env.seed.commit()

    # Attempt to create view with group_by="module"
    resp = await client.post(
        "/api/v1/projects/NOMOD/views",
        json={"name": "Module View", "group_by": "module"},
    )
    contract_recorder.record("modules_disabled_422", resp.request, resp)
    assert resp.status_code == 422
    assert resp.json()["code"] == "MODULES_DISABLED"

    # Attempt ad-hoc query with filters.module_ids
    adhoc_resp = await client.post(
        "/api/v1/projects/NOMOD/issues:query",
        json={"filters": {"module_ids": [str(uuid.uuid4())]}},
    )
    assert adhoc_resp.status_code == 422
    assert adhoc_resp.json()["code"] == "MODULES_DISABLED"


async def test_case_5_boundaries_and_pagination(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 5: Boundary checks and 55-issue pagination (25 + 25 + 5)."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BND", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Duplicate group axis 422
    dup_resp = await client.post(
        "/api/v1/projects/BND/views",
        json={"name": "Dup View", "group_by": "state", "sub_group_by": "state"},
    )
    contract_recorder.record("duplicate_group_axis_422", dup_resp.request, dup_resp)
    assert dup_resp.status_code == 422
    assert dup_resp.json()["code"] == "DUPLICATE_GROUP_AXIS"

    # 2. limit=201 -> 422
    lim_resp = await client.post(
        "/api/v1/projects/BND/issues:query",
        json={"limit": 201},
    )
    assert lim_resp.status_code == 422

    # 3. state_ids with 51 items -> 422
    arr_resp = await client.post(
        "/api/v1/projects/BND/issues:query",
        json={"filters": {"state_ids": [str(uuid.uuid4()) for _ in range(51)]}},
    )
    assert arr_resp.status_code == 422

    # Seed 55 issues
    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).scalar_one()

    all_seeded_ids = await _seed_issues_batch(api_env, proj_id, "BND", 55, admin.id, st_id, pri_id)
    assert len(all_seeded_ids) == 55

    # 4. Cursor mismatch: obtain cursor under limit=5, replay with modified filter -> 422 INVALID_CURSOR
    q1 = await client.post(
        "/api/v1/projects/BND/issues:query",
        json={"limit": 5, "sort_by": "sequence_id", "sort_dir": "asc"},
    )
    assert q1.status_code == 200
    cursor_q1 = q1.json()["next_cursor"]
    assert cursor_q1 is not None

    mismatch_resp = await client.post(
        "/api/v1/projects/BND/issues:query",
        json={"cursor": cursor_q1, "filters": {"search_query": "beta"}},
    )
    contract_recorder.record("invalid_cursor_422", mismatch_resp.request, mismatch_resp)
    assert mismatch_resp.status_code == 422
    assert mismatch_resp.json()["code"] == "INVALID_CURSOR"

    # 5. Pagination across 55 issues: limit=25 -> 25 + 25 + 5
    page1 = await client.post(
        "/api/v1/projects/BND/issues:query",
        json={"limit": 25, "sort_by": "sequence_id", "sort_dir": "asc"},
    )
    assert page1.status_code == 200
    p1_data = page1.json()
    assert len(p1_data["items"]) == 25
    c1 = p1_data["next_cursor"]
    assert c1 is not None

    page2 = await client.post(
        "/api/v1/projects/BND/issues:query",
        json={"limit": 25, "cursor": c1, "sort_by": "sequence_id", "sort_dir": "asc"},
    )
    assert page2.status_code == 200
    p2_data = page2.json()
    assert len(p2_data["items"]) == 25
    c2 = p2_data["next_cursor"]
    assert c2 is not None

    page3 = await client.post(
        "/api/v1/projects/BND/issues:query",
        json={"limit": 25, "cursor": c2, "sort_by": "sequence_id", "sort_dir": "asc"},
    )
    assert page3.status_code == 200
    p3_data = page3.json()
    assert len(p3_data["items"]) == 5
    assert p3_data["next_cursor"] is None

    collected_ids = (
        [i["id"] for i in p1_data["items"]]
        + [i["id"] for i in p2_data["items"]]
        + [i["id"] for i in p3_data["items"]]
    )
    assert len(collected_ids) == 55
    assert len(set(collected_ids)) == 55


async def test_views_crud_edge_cases_and_coverage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Cover update_view permutations, description caps, slug collision, and route aliases."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member")
    other = await make_user("other")

    proj_id = await make_project(
        "COV",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER", other: "MEMBER"},
    )

    # 1. Description UTF-8 byte overflow (> 16384 bytes with <= 16384 chars)
    big_desc = "\u20ac" * 6000  # 6000 chars <= 16384, but 18000 UTF-8 bytes > 16384
    r_big = await as_principal(admin).post(
        "/api/v1/projects/COV/views",
        json={"name": "Big Desc", "description_markdown": big_desc},
    )
    assert r_big.status_code == 422
    assert r_big.json()["code"] == "DESCRIPTION_TOO_LARGE"

    # 2. Slug collision: create two views with same name
    r_v1 = await as_principal(admin).post(
        "/api/v1/projects/COV/views",
        json={"name": "Duplicate Slug", "is_shared": True},
    )
    assert r_v1.status_code == 201
    v1_id = r_v1.json()["id"]

    r_v2 = await as_principal(admin).post(
        "/api/v1/projects/COV/views",
        json={"name": "Duplicate Slug", "is_shared": True},
    )
    assert r_v2.status_code == 201

    # 3. Create personal view via explicit visibility="personal"
    r_pers = await as_principal(member).post(
        "/api/v1/projects/COV/views",
        json={"name": "Member Personal", "visibility": "personal", "layout": "list"},
    )
    assert r_pers.status_code == 201
    pers_id = r_pers.json()["id"]
    assert r_pers.json()["visibility"] == "personal"
    assert r_pers.json()["is_shared"] is False

    # 4. Anti-enumeration: other user attempts to update/delete member's personal view -> 404
    r_unauth_patch_priv = await as_principal(other).patch(
        f"/api/v1/views/{pers_id}",
        json={"name": "Hacked Name"},
    )
    assert r_unauth_patch_priv.status_code == 404

    r_unauth_del_priv = await as_principal(other).delete(f"/api/v1/views/{pers_id}")
    assert r_unauth_del_priv.status_code == 404

    # 5. Unauthorized update/delete of shared view: other user can view v1_id, but cannot edit/delete -> 403
    r_unauth_patch_shared = await as_principal(other).patch(
        f"/api/v1/views/{v1_id}",
        json={"name": "Hacked Name"},
    )
    assert r_unauth_patch_shared.status_code == 403

    r_unauth_del_shared = await as_principal(other).delete(f"/api/v1/views/{v1_id}")
    assert r_unauth_del_shared.status_code == 403

    # 6. Update view: comprehensive field changes (name, description, layout, group_by, filters, wip_limits)
    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).scalar_one()

    r_patch = await as_principal(member).patch(
        f"/api/v1/views/{pers_id}",
        json={
            "name": "Updated Member View",
            "description_markdown": "Now with markdown",
            "layout": "table",
            "group_by": "priority",
            "sub_group_by": "none",
            "filters": {"state_groups": ["started"]},
            "wip_limits_override": {str(st_id): {"soft": 3}},
        },
    )
    assert r_patch.status_code == 200
    p_body = r_patch.json()
    assert p_body["name"] == "Updated Member View"
    assert p_body["layout"] == "table"
    assert p_body["group_by"] == "priority"

    # 7. Toggle visibility: personal -> shared (flip is_shared to True)
    r_share = await as_principal(member).patch(
        f"/api/v1/views/{pers_id}",
        json={"visibility": "project"},
    )
    assert r_share.status_code == 200
    assert r_share.json()["is_shared"] is True
    assert r_share.json()["visibility"] == "project"

    # Toggle visibility back: shared -> personal
    r_priv = await as_principal(member).patch(
        f"/api/v1/views/{pers_id}",
        json={"is_shared": False},
    )
    assert r_priv.status_code == 200
    assert r_priv.json()["is_shared"] is False

    # 8. Query view issues via POST alias
    r_q_post = await as_principal(member).post(f"/api/v1/views/{pers_id}/issues")
    assert r_q_post.status_code == 200

    # 9. Query issues via slash alias /projects/{project_ref}/issues/query
    r_slash = await as_principal(admin).post(
        "/api/v1/projects/COV/issues/query",
        json={"layout": "list", "limit": 10},
    )
    assert r_slash.status_code == 200

    # 10. Delete view by admin (even if created by member)
    r_adm_del = await as_principal(admin).delete(f"/api/v1/views/{pers_id}")
    assert r_adm_del.status_code == 204


def test_views_service_helpers_unit() -> None:
    """Cover unit branches of _reconstruct_filters, _normalize_view_description, and _extract_db_filters."""
    # 1. Fallback to filters_json
    v1 = DbView(display_props_json={}, filters_json={"state_groups": ["started"]})
    assert _reconstruct_filters(v1).state_groups == ["started"]

    # 2. Corrupt filters in display_props_json falls back to empty FilterSpec
    v2 = DbView(display_props_json={"full_filters": "invalid-not-dict"})
    assert _reconstruct_filters(v2) == FilterSpec()

    # 3. Empty description
    assert _normalize_view_description("") == ""

    # 4. ContentNormalizeError raises INVALID_CONTENT
    with patch(
        "kanban.services.views.normalize_to_markdown",
        side_effect=ContentNormalizeError("TEST", "err"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_view_description("bad content")
        assert exc.value.code == "INVALID_CONTENT"

    # 5. _extract_db_filters empty list omitted
    spec = FilterSpec(state_ids=[], state_groups=["started"])
    extracted = _extract_db_filters(spec)
    assert "state_ids" not in extracted
    assert extracted["state_groups"] == ["started"]
