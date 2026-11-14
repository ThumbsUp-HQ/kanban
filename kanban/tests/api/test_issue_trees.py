# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, PLC0415, ASYNC240, ANN401, ARG001, F841
"""Feature unit tests for issue trees API (KB-P4-05)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _count(env: ApiEnv, sql: str, **params: Any) -> int:
    """Return a scalar count from the committed seed session."""
    await env.seed.rollback()
    return int((await env.seed.execute(text(sql), params)).scalar_one())


@pytest.mark.asyncio
async def test_case_1_positive_tree_creation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 1: Positive create root + 2 children with consecutive IDs, assignees, and PARENT_OF links."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    adam = await make_user("adam", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "TRE",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", adam: "MEMBER"},
        modules_enabled=True,
    )
    client = as_principal(admin)

    payload = {
        "summary": "Root Epic Feature",
        "description_markdown": "High-level feature specification.",
        "priority": "high",
        "assignees": ["@adam", "Vendor QA"],
        "children": [
            {
                "summary": "Sub-task A",
                "description_markdown": "Sub-task A notes.",
                "priority": "medium",
                "assignees": ["@adam"],
            },
            {
                "summary": "Sub-task B",
                "description_markdown": "Sub-task B notes.",
                "priority": "low",
                "assignees": ["Vendor QA"],
            },
        ],
    }

    resp = await client.post("/api/v1/projects/TRE/issue-trees", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["created"] == 3
    root = data["root"]
    assert root["key"] == "TRE-1"
    assert root["summary"] == "Root Epic Feature"
    assert root["priority"] == "high"

    children = data["children"]
    assert len(children) == 2
    assert children[0]["key"] == "TRE-2"
    assert children[0]["parent"] == "TRE-1"
    assert children[1]["key"] == "TRE-3"
    assert children[1]["parent"] == "TRE-1"

    # Verify DB state
    issue_count = await _count(
        api_env, "SELECT count(*) FROM issues WHERE project_id = :p", p=proj_id
    )
    assert issue_count == 3

    # Check assignees for root
    root_assignees = (
        await api_env.seed.execute(
            text(
                "SELECT principal_id, free_text_assignee FROM issue_assignees "
                "JOIN issues ON issues.id = issue_assignees.issue_id "
                "WHERE issues.sequence_id = 1"
            )
        )
    ).all()
    assert len(root_assignees) == 2
    principal_ids = [row[0] for row in root_assignees if row[0] is not None]
    free_texts = [row[1] for row in root_assignees if row[1] is not None]
    assert adam.id in principal_ids
    assert "Vendor QA" in free_texts

    # Check PARENT_OF links
    parent_links = (
        await api_env.seed.execute(
            text(
                "SELECT source_key_snapshot, target_key_snapshot FROM object_links "
                "WHERE link_type = 'PARENT_OF' AND workspace_id = :ws"
            ),
            {"ws": admin.workspace_id},
        )
    ).all()
    assert len(parent_links) == 2
    link_pairs = {(row[0], row[1]) for row in parent_links}
    assert ("TRE-1", "TRE-2") in link_pairs
    assert ("TRE-1", "TRE-3") in link_pairs

    # Save sample contract artifact for verification packet
    contract_sample = {
        "request_201": payload,
        "response_201": data,
    }
    qa_dir = Path("/tmp/kb-wt-KANBA-130/docs/qa/KANBA-130")
    qa_dir.mkdir(parents=True, exist_ok=True)
    sample_file = qa_dir / "contract-sample.json"
    with sample_file.open("w", encoding="utf-8") as f:
        json.dump(contract_sample, f, indent=2)


@pytest.mark.asyncio
async def test_case_2_atomicity_and_security(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 2: 501-char summary on 3rd child creates 0 rows; @eve without access rejected."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    eve = await make_user("eve")  # Exists in workspace, NO project VIEW
    proj_id = await make_project(
        "ATO",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN"},  # Eve has NO role on ATO
    )
    client = as_principal(admin)

    count_before = await _count(
        api_env, "SELECT count(*) FROM issues WHERE project_id = :p", p=proj_id
    )
    objects_before = await _count(
        api_env, "SELECT count(*) FROM objects WHERE project_id = :p", p=proj_id
    )

    # 1. Tree whose 3rd child has 501 chars summary
    invalid_payload = {
        "summary": "Valid Root",
        "children": [
            {"summary": "Valid Child 1"},
            {"summary": "Valid Child 2"},
            {"summary": "x" * 501},
        ],
    }

    resp = await client.post("/api/v1/projects/ATO/issue-trees", json=invalid_payload)
    assert resp.status_code == 422, resp.text
    err_data = resp.json()
    assert err_data["code"] == "SUMMARY_LENGTH"

    count_after = await _count(
        api_env, "SELECT count(*) FROM issues WHERE project_id = :p", p=proj_id
    )
    objects_after = await _count(
        api_env, "SELECT count(*) FROM objects WHERE project_id = :p", p=proj_id
    )
    assert count_before == count_after == 0
    assert objects_before == objects_after

    # Append 422 rollback to contract-sample.json
    qa_dir = Path("/tmp/kb-wt-KANBA-130/docs/qa/KANBA-130")
    qa_dir.mkdir(parents=True, exist_ok=True)
    sample_file = qa_dir / "contract-sample.json"
    if sample_file.exists():
        with sample_file.open("r", encoding="utf-8") as f:
            data_contract = json.load(f)
    else:
        data_contract = {}
    data_contract["request_422_rollback"] = invalid_payload
    data_contract["response_422_rollback"] = err_data
    with sample_file.open("w", encoding="utf-8") as f:
        json.dump(data_contract, f, indent=2)

    # 2. @eve without project access
    eve_payload = {
        "summary": "Attempt with Eve",
        "assignees": ["@eve"],
    }
    resp_eve = await client.post("/api/v1/projects/ATO/issue-trees", json=eve_payload)
    assert resp_eve.status_code == 422
    assert resp_eve.json()["code"] == "ASSIGNEE_NOT_ELIGIBLE"
    assert resp_eve.json()["hint"] == "@eve"

    # Verify no ACL entries created
    eve_acl_count = await _count(
        api_env,
        "SELECT count(*) FROM role_bindings WHERE principal_id = :pri",
        pri=eve.id,
    )
    assert eve_acl_count == 0


@pytest.mark.asyncio
async def test_case_4_boundary_conditions(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: 50 nodes succeed, 51 fails; depth 6 succeeds, depth 7 fails; date order fails."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("BND", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. 50 nodes succeed
    flat_50_children = [{"summary": f"Child {i}"} for i in range(1, 50)]
    payload_50 = {
        "summary": "Root 50",
        "children": flat_50_children,
    }
    resp_50 = await client.post("/api/v1/projects/BND/issue-trees", json=payload_50)
    assert resp_50.status_code == 201
    assert resp_50.json()["created"] == 50

    # 2. 51 nodes fail
    flat_51_children: list[dict[str, Any]] = [{"summary": f"Child {i}"} for i in range(1, 50)]
    # Add a grandchild to reach 51
    flat_51_children[0]["children"] = [{"summary": "Grandchild 51"}]
    payload_51 = {
        "summary": "Root 51",
        "children": flat_51_children,
    }
    resp_51 = await client.post("/api/v1/projects/BND/issue-trees", json=payload_51)
    assert resp_51.status_code == 422
    assert resp_51.json()["code"] == "TREE_TOO_LARGE"

    # 3. Depth 6 succeeds
    # Construct a chain of depth 6: root -> c1 -> c2 -> c3 -> c4 -> c5
    chain_d6 = {
        "summary": "Level 1",
        "children": [
            {
                "summary": "Level 2",
                "children": [
                    {
                        "summary": "Level 3",
                        "children": [
                            {
                                "summary": "Level 4",
                                "children": [
                                    {
                                        "summary": "Level 5",
                                        "children": [{"summary": "Level 6"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    resp_d6 = await client.post("/api/v1/projects/BND/issue-trees", json=chain_d6)
    assert resp_d6.status_code == 201
    assert resp_d6.json()["created"] == 6

    # 4. Depth 7 fails
    chain_d7 = {
        "summary": "Level 1",
        "children": [
            {
                "summary": "Level 2",
                "children": [
                    {
                        "summary": "Level 3",
                        "children": [
                            {
                                "summary": "Level 4",
                                "children": [
                                    {
                                        "summary": "Level 5",
                                        "children": [
                                            {
                                                "summary": "Level 6",
                                                "children": [{"summary": "Level 7"}],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    resp_d7 = await client.post("/api/v1/projects/BND/issue-trees", json=chain_d7)
    assert resp_d7.status_code == 422
    assert resp_d7.json()["code"] == "PARENT_DEPTH_EXCEEDED"

    # 5. due_date < start_date fails
    invalid_dates = {
        "summary": "Invalid Dates",
        "start_date": "2026-06-15",
        "due_date": "2026-06-10",
    }
    resp_dates = await client.post("/api/v1/projects/BND/issue-trees", json=invalid_dates)
    assert resp_dates.status_code == 422
    assert resp_dates.json()["code"] == "DATE_ORDER"


@pytest.mark.asyncio
async def test_case_5_modules_defaults_and_disabled(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Module defaults applied when enabled; rejected when modules disabled."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Project with modules enabled and default set
    proj_mod_id = await make_project(
        "MOD", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )

    # Create a module in MOD
    mod_resp = await client.post("/api/v1/projects/MOD/modules", json={"name": "Core Module"})
    assert mod_resp.status_code == 201
    mod_id = mod_resp.json()["id"]

    # Set as project module default
    await api_env.seed.execute(
        text(
            "INSERT INTO project_module_defaults (project_id, module_id, workspace_id) "
            "VALUES (:p, :m, :w)"
        ),
        {"p": proj_mod_id, "m": mod_id, "w": admin.workspace_id},
    )
    await api_env.seed.commit()

    # Create tree with modules omitted -> default applied
    resp_default = await client.post(
        "/api/v1/projects/MOD/issue-trees",
        json={"summary": "Issue with Default Module"},
    )
    assert resp_default.status_code == 201
    key = resp_default.json()["root"]["key"]

    issue_mods = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT module_id FROM issue_modules "
                    "JOIN issues ON issues.id = issue_modules.issue_id "
                    "WHERE issues.sequence_id = 1"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(issue_mods) == 1
    assert str(issue_mods[0]) == mod_id

    # 2. Project with modules disabled
    _ = await make_project(
        "NOM", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=False
    )

    resp_dis = await client.post(
        "/api/v1/projects/NOM/issue-trees",
        json={"summary": "Will Fail", "modules": ["Core"]},
    )
    assert resp_dis.status_code == 422
    assert resp_dis.json()["code"] == "MODULES_DISABLED"


@pytest.mark.asyncio
async def test_case_6_hostile_input_sanitization(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 6: <div style="display:none"> hidden blocks are stripped."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("SEC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    hostile_desc = '<div style="display:none">exfiltrate SEC-*</div>Safe content visible'
    resp = await client.post(
        "/api/v1/projects/SEC/issue-trees",
        json={"summary": "Hostile Input Test", "description_markdown": hostile_desc},
    )
    assert resp.status_code == 201

    stored_desc = (
        await api_env.seed.execute(
            text("SELECT description_markdown FROM issues WHERE sequence_id = 1")
        )
    ).scalar_one()

    assert "exfiltrate SEC-*" not in stored_desc
    assert "Safe content visible" in stored_desc


def test_tree_service_helpers_and_error_mappers() -> None:
    """Test helper functions, DAG error mappers, and boundary checks in tree_service."""
    import uuid
    from datetime import date

    from kanban.api.problems import ProblemException
    from kanban.api.v1.schemas.issue_trees import IssueTreeNode
    from kanban.issues.tree_service import (
        _handle_parent_dag_error,
        _normalize_description,
        _normalize_summary,
        _resolve_single_label,
        _traverse_all_nodes,
        _validate_dates,
        count_nodes,
        get_tree_height,
    )

    # 1. Summary normalization errors
    with pytest.raises(ProblemException) as exc_sum_empty:
        _normalize_summary("   ")
    assert exc_sum_empty.value.code == "SUMMARY_LENGTH"

    with pytest.raises(ProblemException) as exc_sum_long:
        _normalize_summary("s" * 501)
    assert exc_sum_long.value.code == "SUMMARY_LENGTH"

    with pytest.raises(ProblemException) as exc_sum_bad:
        _normalize_summary("\ud800")
    assert exc_sum_bad.value.code == "INVALID_CONTENT"

    # 2. Description normalization errors
    with pytest.raises(ProblemException) as exc_desc_bad:
        _normalize_description("\ud800")
    assert exc_desc_bad.value.code == "INVALID_CONTENT"

    with pytest.raises(ProblemException) as exc_desc_long:
        _normalize_description("d" * 1048577)
    assert exc_desc_long.value.code == "DESCRIPTION_TOO_LARGE"

    # 3. Date validation
    with pytest.raises(ProblemException) as exc_date:
        _validate_dates(date(2026, 11, 20), date(2026, 11, 10))
    assert exc_date.value.code == "DATE_ORDER"
    _validate_dates(None, None)
    _validate_dates(date(2026, 11, 1), date(2026, 11, 2))

    # 4. DAG error mappers
    with pytest.raises(ProblemException) as exc_cycle:
        _handle_parent_dag_error(Exception("PARENT_CYCLE detected"))
    assert exc_cycle.value.code == "PARENT_CYCLE"

    with pytest.raises(ProblemException) as exc_depth:
        _handle_parent_dag_error(Exception("PARENT_MAX_DEPTH_EXCEEDED"))
    assert exc_depth.value.code == "PARENT_DEPTH_EXCEEDED"

    with pytest.raises(ProblemException) as exc_notfound:
        _handle_parent_dag_error(Exception("PARENT_NOT_FOUND"))
    assert exc_notfound.value.code == "INVALID_REFERENCE"

    # 5. Tree traversal, height and node count
    leaf = IssueTreeNode(summary="Leaf")
    child = IssueTreeNode(summary="Child", children=[leaf])
    root = IssueTreeNode(summary="Root", children=[child])
    assert count_nodes(root) == 3
    assert get_tree_height(root) == 3
    all_nodes = _traverse_all_nodes(root)
    assert len(all_nodes) == 3
    assert [n.summary for n in all_nodes] == ["Root", "Child", "Leaf"]

    # 6. _resolve_single_label
    from database.models.projects import ProjectLabel

    lbl_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    lbl_obj = ProjectLabel(id=lbl_id, name="Bug", workspace_id=ws_id, project_id=p_id)
    by_name = {"bug": lbl_obj}
    by_id = {lbl_id: lbl_obj}

    assert _resolve_single_label("Bug", by_name, by_id).id == lbl_id
    assert _resolve_single_label(lbl_id, by_name, by_id).id == lbl_id
    with pytest.raises(ProblemException) as exc_lbl_uuid:
        _resolve_single_label(uuid.uuid4(), by_name, by_id)
    assert exc_lbl_uuid.value.code == "INVALID_REFERENCE"
    with pytest.raises(ProblemException) as exc_lbl_str:
        _resolve_single_label("nonexistent", by_name, by_id)
    assert exc_lbl_str.value.code == "INVALID_REFERENCE"


@pytest.mark.asyncio
async def test_tree_service_edge_cases_and_references(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test resolution failures and boundary conditions for parent, state, priority, assignees."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project(
        "EDG", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    client = as_principal(admin)

    # 1. Nonexistent state
    r1 = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T1", "state": "unknown_state"}
    )
    assert r1.status_code == 422
    assert r1.json()["code"] == "INVALID_REFERENCE"

    # 2. Nonexistent priority
    r2 = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T2", "priority": "unknown_pri"}
    )
    assert r2.status_code == 422
    assert r2.json()["code"] == "INVALID_REFERENCE"

    # 3. Nonexistent cycle
    r3 = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T3", "cycle": "unknown_cycle"}
    )
    assert r3.status_code == 422
    assert r3.json()["code"] == "INVALID_REFERENCE"

    # 4. Nonexistent module
    r4 = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T4", "modules": ["unknown_mod"]}
    )
    assert r4.status_code == 422
    assert r4.json()["code"] == "INVALID_REFERENCE"

    # 5. Nonexistent label
    r5 = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T5", "labels": ["unknown_lbl"]}
    )
    assert r5.status_code == 422
    assert r5.json()["code"] == "INVALID_REFERENCE"

    # 6. Invalid parent reference formats
    r6a = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T6", "parent": "OTHER-1"}
    )
    assert r6a.status_code == 422
    assert r6a.json()["code"] == "INVALID_REFERENCE"

    r6b = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T6", "parent": "EDG-notanumber"}
    )
    assert r6b.status_code == 422
    assert r6b.json()["code"] == "INVALID_REFERENCE"

    r6c = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T6", "parent": "not-valid-ref"}
    )
    assert r6c.status_code == 422
    assert r6c.json()["code"] == "INVALID_REFERENCE"

    r6d = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "T6", "parent": "EDG-9999"}
    )
    assert r6d.status_code == 422
    assert r6d.json()["code"] == "INVALID_REFERENCE"

    # 7. Assignee limit > 20
    r7 = await client.post(
        "/api/v1/projects/EDG/issue-trees",
        json={"summary": "T7", "assignees": [f"Vendor QA {i}" for i in range(21)]},
    )
    assert r7.status_code == 422
    assert r7.json()["code"] == "VALIDATION_FAILED"

    # 8. Free text assignee too long (> 120 chars)
    r8 = await client.post(
        "/api/v1/projects/EDG/issue-trees",
        json={"summary": "T8", "assignees": ["v" * 121]},
    )
    assert r8.status_code == 422
    assert r8.json()["code"] == "FREE_TEXT_INVALID"

    # 9. Existing parent positive test
    r_parent = await client.post(
        "/api/v1/projects/EDG/issue-trees", json={"summary": "Parent Tree"}
    )
    assert r_parent.status_code == 201
    parent_key = r_parent.json()["root"]["key"]

    r_child_under_parent = await client.post(
        "/api/v1/projects/EDG/issue-trees",
        json={"summary": "Child Attached To Parent", "parent": parent_key},
    )
    assert r_child_under_parent.status_code == 201
    assert r_child_under_parent.json()["root"]["parent"] == parent_key


@pytest.mark.asyncio
async def test_tree_service_uuid_resolutions_and_joins(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test UUID resolutions for state, priority, cycle, modules, labels, and assignees."""
    import uuid as _uuid

    from kanban.api.problems import ProblemException
    from kanban.content import ContentNormalizeError
    from kanban.issues.tree_service import (
        _handle_parent_dag_error,
        _normalize_description,
    )

    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member2", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "UUD",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER"},
        modules_enabled=True,
    )
    client = as_principal(admin)

    # 1. Helper tests for _normalize_description and _handle_parent_dag_error
    from unittest.mock import patch

    with patch(
        "kanban.issues.tree_service.normalize_to_markdown",
        side_effect=ContentNormalizeError("CONTENT_TOO_LARGE", "large"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("foo")
        assert exc.value.code == "DESCRIPTION_TOO_LARGE"

    with patch(
        "kanban.issues.tree_service.normalize_to_markdown",
        side_effect=ContentNormalizeError("OTHER", "err"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("foo")
        assert exc.value.code == "INVALID_CONTENT"

    with patch(
        "kanban.issues.tree_service.normalize_to_markdown",
        side_effect=UnicodeEncodeError("utf-8", "foo", 0, 1, "ouch"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("foo")
        assert exc.value.code == "INVALID_CONTENT"

    with patch(
        "kanban.issues.tree_service.normalize_to_markdown", return_value="x" * (1024 * 1024 + 1)
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("foo")
        assert exc.value.code == "DESCRIPTION_TOO_LARGE"

    with pytest.raises(ProblemException) as exc:
        _handle_parent_dag_error(Exception("PARENT_CYCLE"))
    assert exc.value.code == "PARENT_CYCLE"

    with pytest.raises(ProblemException) as exc:
        _handle_parent_dag_error(Exception("PARENT_MAX_DEPTH_EXCEEDED"))
    assert exc.value.code == "PARENT_DEPTH_EXCEEDED"

    with pytest.raises(ProblemException) as exc:
        _handle_parent_dag_error(Exception("PARENT_NOT_FOUND"))
    assert exc.value.code == "INVALID_REFERENCE"

    # 2. Query valid state and priority IDs
    st_resp = await client.get("/api/v1/projects/UUD/states")
    assert st_resp.status_code == 200
    state_id_str = st_resp.json()[0]["id"]
    state_uuid = _uuid.UUID(state_id_str)

    pri_resp = await client.get("/api/v1/projects/UUD/priorities")
    assert pri_resp.status_code == 200
    pri_id_str = pri_resp.json()[0]["id"]
    pri_uuid = _uuid.UUID(pri_id_str)

    # 3. Create cycle, module, labels
    cyc_resp = await client.post("/api/v1/projects/UUD/cycles", json={"name": "Sprint Alpha"})
    assert cyc_resp.status_code == 201
    cyc_id_str = cyc_resp.json()["id"]

    mod_resp = await client.post("/api/v1/projects/UUD/modules", json={"name": "Module Beta"})
    assert mod_resp.status_code == 201
    mod_id_str = mod_resp.json()["id"]

    lbl1_resp = await client.post(
        "/api/v1/projects/UUD/labels",
        json={"name": "L-One", "color_hex": "#111111", "exclusive_group": "tier"},
    )
    assert lbl1_resp.status_code == 201
    lbl1_id_str = lbl1_resp.json()["id"]

    lbl2_resp = await client.post(
        "/api/v1/projects/UUD/labels",
        json={"name": "L-Two", "color_hex": "#222222", "exclusive_group": "tier"},
    )
    assert lbl2_resp.status_code == 201
    lbl2_id_str = lbl2_resp.json()["id"]

    # 4. Exclusive group conflict
    conflict_resp = await client.post(
        "/api/v1/projects/UUD/issue-trees",
        json={"summary": "Conflict", "labels": [lbl1_id_str, lbl2_id_str]},
    )
    assert conflict_resp.status_code == 422
    assert conflict_resp.json()["code"] == "EXCLUSIVE_GROUP_CONFLICT"

    # 5. Invalid UUIDs for each reference type
    rand_uuid_str = str(_uuid.uuid4())
    r_bad_st = await client.post(
        "/api/v1/projects/UUD/issue-trees", json={"summary": "Bad St", "state": rand_uuid_str}
    )
    assert r_bad_st.status_code == 422
    assert r_bad_st.json()["code"] == "INVALID_REFERENCE"

    r_bad_pri = await client.post(
        "/api/v1/projects/UUD/issue-trees", json={"summary": "Bad Pri", "priority": rand_uuid_str}
    )
    assert r_bad_pri.status_code == 422
    assert r_bad_pri.json()["code"] == "INVALID_REFERENCE"

    r_bad_cyc = await client.post(
        "/api/v1/projects/UUD/issue-trees", json={"summary": "Bad Cyc", "cycle": rand_uuid_str}
    )
    assert r_bad_cyc.status_code == 422
    assert r_bad_cyc.json()["code"] == "INVALID_REFERENCE"

    r_bad_mod = await client.post(
        "/api/v1/projects/UUD/issue-trees", json={"summary": "Bad Mod", "modules": [rand_uuid_str]}
    )
    assert r_bad_mod.status_code == 422
    assert r_bad_mod.json()["code"] == "INVALID_REFERENCE"

    r_bad_lbl = await client.post(
        "/api/v1/projects/UUD/issue-trees", json={"summary": "Bad Lbl", "labels": [rand_uuid_str]}
    )
    assert r_bad_lbl.status_code == 422
    assert r_bad_lbl.json()["code"] == "INVALID_REFERENCE"

    # 6. Success using UUID strings and user assignee UUID
    member_user_id_str = str(member.id)
    r_success = await client.post(
        "/api/v1/projects/UUD/issue-trees",
        json={
            "summary": "Tree with UUID references",
            "state": state_id_str,
            "priority": pri_id_str,
            "cycle": cyc_id_str,
            "modules": [mod_id_str],
            "labels": [lbl1_id_str],
            "assignees": [member_user_id_str, "Free Agent"],
        },
    )
    assert r_success.status_code == 201
    parent_issue_id = r_success.json()["root"]["id"]

    # 7. Parent reference as UUID string
    r_child_by_uuid = await client.post(
        "/api/v1/projects/UUD/issue-trees",
        json={"summary": "Child attached via UUID", "parent": parent_issue_id},
    )
    assert r_child_by_uuid.status_code == 201


@pytest.mark.asyncio
async def test_tree_service_direct_uuid_objects(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Directly test IssueTreeNode with UUID objects for state, priority, cycle, modules, labels, parent."""
    import uuid as _uuid

    from kanban.api.deps import PrincipalContext
    from kanban.api.problems import ProblemException
    from kanban.api.v1.schemas.issue_trees import IssueTreeNode
    from kanban.issues.tree_service import create_issue_tree

    admin = await make_user("admin_direct", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project(
        "DIR", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    client = as_principal(admin)

    # 1. Fetch valid state & priority UUIDs
    st_resp = await client.get("/api/v1/projects/DIR/states")
    st_uuid = _uuid.UUID(st_resp.json()[0]["id"])

    pri_resp = await client.get("/api/v1/projects/DIR/priorities")
    pri_uuid = _uuid.UUID(pri_resp.json()[0]["id"])

    # 2. Create cycle, module, label
    cyc_resp = await client.post("/api/v1/projects/DIR/cycles", json={"name": "Cycle Direct"})
    cyc_uuid = _uuid.UUID(cyc_resp.json()["id"])

    mod_resp = await client.post("/api/v1/projects/DIR/modules", json={"name": "Mod Direct"})
    mod_uuid = _uuid.UUID(mod_resp.json()["id"])

    lbl_resp = await client.post(
        "/api/v1/projects/DIR/labels", json={"name": "Lbl Direct", "color_hex": "#123456"}
    )
    lbl_uuid = _uuid.UUID(lbl_resp.json()["id"])

    # 3. Create parent issue
    p_resp = await client.post(
        "/api/v1/projects/DIR/issue-trees", json={"summary": "Direct Parent"}
    )
    parent_uuid = _uuid.UUID(p_resp.json()["root"]["id"])

    # 4. Caller context
    caller = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
    )

    # 5. Call create_issue_tree directly with UUID objects
    node = IssueTreeNode(
        summary="Child with direct UUID objects",
        state=st_uuid,
        priority=pri_uuid,
        cycle=cyc_uuid,
        modules=[mod_uuid],
        labels=[lbl_uuid],
        parent=parent_uuid,
    )
    res = await create_issue_tree(api_env.seed, caller, "DIR", node)
    assert res.created == 1
    assert res.root.summary == "Child with direct UUID objects"

    # 6. Test invalid UUID objects
    bad_uuid = _uuid.uuid4()
    for bad_node in [
        IssueTreeNode(summary="Bad St", state=bad_uuid),
        IssueTreeNode(summary="Bad Pri", priority=bad_uuid),
        IssueTreeNode(summary="Bad Cyc", cycle=bad_uuid),
        IssueTreeNode(summary="Bad Mod", modules=[bad_uuid]),
        IssueTreeNode(summary="Bad Lbl", labels=[bad_uuid]),
    ]:
        with pytest.raises(ProblemException) as exc:
            await create_issue_tree(api_env.seed, caller, "DIR", bad_node)
        assert exc.value.code == "INVALID_REFERENCE"

    # 7. Parent reference format without dash
    bad_parent_node = IssueTreeNode(summary="Bad Parent", parent="invalidnodashref")
    with pytest.raises(ProblemException) as exc:
        await create_issue_tree(api_env.seed, caller, "DIR", bad_parent_node)
    assert exc.value.code == "INVALID_REFERENCE"

    # 8. Assignees > 20 in create_issue_tree
    bad_assignees_node = IssueTreeNode(summary="Bad Assignees")
    bad_assignees_node.assignees = [f"User {i}" for i in range(21)]
    with pytest.raises(ProblemException) as exc:
        await create_issue_tree(api_env.seed, caller, "DIR", bad_assignees_node)
    assert exc.value.code == "ASSIGNEE_LIMIT"
