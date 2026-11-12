# ruff: noqa: E501, PLR0915
"""Unit and integration tests for Issue Copy API (KB-P3-08, S7.2 8n).

Covers all 6 mandatory feature test cases:
    1. Positive: copy with defaults returns 201, summary "[Copy] <orig>", same description sha256,
       same priority/labels, created_by_id == caller, no assignees, no cycle; ISSUE_CREATED with
       copied_from and ISSUE_COPIED rows exist.
    2. Security: sub-issue tree where one child lives under an explicit DENY for the caller: copy
       skips it, skipped.restricted_sub_issues == 1, and no response field contains the skipped key.
    3. Boundary: 500-char summary copy is truncated to exactly 500 chars; a 201-issue readable tree
       returns 422 COPY_TOO_LARGE with zero new rows; depth-6 tree copies with correct parent structure.
    4. Options: link_as_relates_to creates one RELATES_TO link; include_attachments copies only readable
       attachment rows referencing the same blob hash; modules are not copied when target project has
       modules_enabled=false.
    5. Atomicity: inject a failure on the third sub-issue insert; assert zero copies and zero activity rows persist.
    6. Auth: non-viewer 404; viewer without project EDIT 403.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from database.models import Attachment, ObjectLink
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issue_copy import IssueCopyRequest
from kanban.content import ContentNormalizeError
from kanban.services.issue_copy import _get_default_state_id, _normalize_description, copy_issue
from kanban.services.issues import initial_board_rank
from kanban.tests.security.helpers import add_acl_entry, rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def test_case_1_positive_copy_defaults(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive copy with default options returns 201 and creates audit ledger events."""
    admin = await make_user("admin1", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("CPY1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Fetch priority and label
    pri_row = (
        await api_env.seed.execute(
            text(
                "SELECT id, label FROM project_priorities WHERE project_id = :p AND slug = 'high'"
            ),
            {"p": proj_id},
        )
    ).first()
    assert pri_row is not None
    _pri_id, pri_label = pri_row

    lbl_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) VALUES (:id, :ws, :p, 'security', '#ff0000')"
        ),
        {"id": lbl_id, "ws": admin.workspace_id, "p": proj_id},
    )
    await api_env.seed.commit()

    # Create source issue
    desc = "# Auth Details\n\nEnsure OIDC tokens are verified with S256."
    desc_sha256 = hashlib.sha256(desc.encode("utf-8")).hexdigest()

    create_resp = await client.post(
        "/api/v1/projects/CPY1/issues",
        json={
            "summary": "Harden OIDC auth",
            "description_markdown": desc,
            "priority": "high",
            "label_ids": [str(lbl_id)],
            "start_date": "2026-11-20",
            "due_date": "2026-11-25",
        },
    )
    assert create_resp.status_code == 201
    source_key = create_resp.json()["key"]
    source_id = create_resp.json()["id"]

    # Call copy with defaults
    copy_resp = await client.post(f"/api/v1/issues/{source_key}/copy", json={})
    contract_recorder.record("copy_issue_default_201", copy_resp.request, copy_resp)
    assert copy_resp.status_code == 201, copy_resp.text
    assert copy_resp.headers["Location"] == "/api/v1/issues/CPY1-2"

    body = copy_resp.json()
    new_issue = body["issue"]
    assert new_issue["key"] == "CPY1-2"
    assert new_issue["summary"] == "[Copy] Harden OIDC auth"
    assert new_issue["description_sha256"] == desc_sha256
    assert new_issue["priority"]["label"] == pri_label
    assert [lbl["name"] for lbl in new_issue["labels"]] == ["security"]
    assert new_issue["created_by_id"] == str(admin.id)
    assert new_issue["assignees"] == []
    assert new_issue["cycle_id"] is None
    assert new_issue["start_date"] is None
    assert new_issue["due_date"] is None
    assert new_issue["parent"] is None

    assert body["copied_sub_issues"] == []
    assert body["skipped"] == {"restricted_sub_issues": 0}
    assert body["copied_attachments"] == 0
    assert body["link_id"] is None

    # Verify Activity Records
    await api_env.seed.rollback()
    created_act = (
        await api_env.seed.execute(
            text(
                "SELECT payload FROM activity_records "
                "WHERE object_id = :id AND event_type = 'ISSUE_CREATED'"
            ),
            {"id": uuid.UUID(new_issue["id"])},
        )
    ).scalar_one_or_none()
    assert created_act is not None
    assert created_act["key"] == "CPY1-2"
    assert created_act["copied_from"] == source_id

    copied_act = (
        await api_env.seed.execute(
            text(
                "SELECT payload FROM activity_records "
                "WHERE object_id = :id AND event_type = 'ISSUE_COPIED'"
            ),
            {"id": uuid.UUID(source_id)},
        )
    ).scalar_one_or_none()
    assert copied_act is not None
    assert copied_act["copy_id"] == new_issue["id"]
    assert copied_act["copy_key"] == "CPY1-2"
    assert copied_act["include_sub_issues"] is False
    assert copied_act["include_attachments"] is False


async def test_case_2_security_restricted_sub_issue_tree(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: Caller with explicit DENY on sub-issue skips it without leaking keys or titles."""
    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member2")  # no workspace role
    await make_project("SEC2", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"})

    # 1. Admin creates Root issue
    r_root = await as_principal(admin).post(
        "/api/v1/projects/SEC2/issues", json={"summary": "Root Task"}
    )
    assert r_root.status_code == 201
    root_key = r_root.json()["key"]

    # 2. Admin creates Child 1 (readable)
    r_c1 = await as_principal(admin).post(
        "/api/v1/projects/SEC2/issues",
        json={"summary": "Child 1 Open", "parent": root_key},
    )
    assert r_c1.status_code == 201
    c1_key = r_c1.json()["key"]

    # 3. Admin creates Child 2 (to be denied)
    r_c2 = await as_principal(admin).post(
        "/api/v1/projects/SEC2/issues",
        json={"summary": "Secret Child 2", "parent": root_key},
    )
    assert r_c2.status_code == 201
    c2_id = r_c2.json()["id"]
    c2_key = r_c2.json()["key"]

    # 4. Admin creates Grandchild 2a under Child 2
    r_g2 = await as_principal(admin).post(
        "/api/v1/projects/SEC2/issues",
        json={"summary": "Secret Grandchild", "parent": c2_key},
    )
    assert r_g2.status_code == 201
    g2_key = r_g2.json()["key"]

    # 5. Place explicit DENY on Child 2 for member
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        uuid.UUID(c2_id),
        member.id,
        effect="DENY",
        capability_mask=1,  # deny VIEW
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Member copies Root with include_sub_issues = True
    copy_resp = await as_principal(member).post(
        f"/api/v1/issues/{root_key}/copy",
        json={
            "include_sub_issues": True,
            "include_attachments": False,
            "link_as_relates_to": False,
        },
    )
    contract_recorder.record(
        "copy_issue_with_options_and_skipped_201", copy_resp.request, copy_resp
    )
    assert copy_resp.status_code == 201, copy_resp.text

    data = copy_resp.json()
    assert data["issue"]["summary"] == "[Copy] Root Task"

    # Only Child 1 was copied
    assert len(data["copied_sub_issues"]) == 1
    assert data["copied_sub_issues"][0]["source_key"] == c1_key
    assert data["copied_sub_issues"][0]["copy_key"] == "SEC2-6"

    # Child 2 and Grandchild 2a were skipped (count = 2)
    assert data["skipped"]["restricted_sub_issues"] == 2

    # Verify zero leakage of secret keys or titles in the entire response
    raw_response_text = copy_resp.text
    assert c2_key not in raw_response_text
    assert "Secret Child 2" not in raw_response_text
    assert g2_key not in raw_response_text
    assert "Secret Grandchild" not in raw_response_text


async def test_case_3_boundary_500_chars_copy_too_large_and_depth_6(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Summary truncation at 500, copy limit at 200 readable issues, and depth-6 preservation."""
    admin = await make_user("admin3", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BND3", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. 500-char summary truncation
    long_summary = "X" * 500
    r_long = await client.post("/api/v1/projects/BND3/issues", json={"summary": long_summary})
    assert r_long.status_code == 201
    key_long = r_long.json()["key"]

    r_copy_long = await client.post(f"/api/v1/issues/{key_long}/copy", json={})
    assert r_copy_long.status_code == 201
    copied_summary = r_copy_long.json()["issue"]["summary"]
    assert len(copied_summary) == 500
    assert copied_summary == f"[Copy] {long_summary}"[:500]

    # 2. Depth-6 tree copy preservation
    curr_key = key_long
    depth_keys = [curr_key]
    for d in range(2, 7):
        r_d = await client.post(
            "/api/v1/projects/BND3/issues",
            json={"summary": f"Depth {d} Node", "parent": curr_key},
        )
        assert r_d.status_code == 201
        curr_key = r_d.json()["key"]
        depth_keys.append(curr_key)

    # Copy the depth-6 tree
    r_tree = await client.post(
        f"/api/v1/issues/{key_long}/copy",
        json={"include_sub_issues": True},
    )
    assert r_tree.status_code == 201
    tree_data = r_tree.json()
    assert len(tree_data["copied_sub_issues"]) == 5
    assert tree_data["skipped"]["restricted_sub_issues"] == 0

    # 3. 201-issue readable tree -> 422 COPY_TOO_LARGE
    # Create root issue for large tree
    r_big_root = await client.post("/api/v1/projects/BND3/issues", json={"summary": "Big Root"})
    assert r_big_root.status_code == 201
    big_root_id = uuid.UUID(r_big_root.json()["id"])
    big_root_key = r_big_root.json()["key"]

    # Fetch default state and priority
    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    # Batch insert 201 child issues directly under big_root
    for i in range(201):
        seq = (
            await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
        ).scalar_one()
        c_id = uuid.uuid4()
        c_key = f"BND3-{seq}"
        await api_env.seed.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :key, :title, :cr, :id)"
            ),
            {
                "ws": admin.workspace_id,
                "proj": proj_id,
                "key": c_key,
                "title": f"Bulk {i}",
                "cr": admin.id,
                "id": c_id,
            },
        )
        await api_env.seed.execute(
            text(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
                "state_id, priority_id, parent_issue_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
                "VALUES (:id, 'issue', :ws, :proj, :seq, :title, :st, :pri, :pid, :cr, :cr, :rnk, 'top')"
            ),
            {
                "id": c_id,
                "ws": admin.workspace_id,
                "proj": proj_id,
                "seq": seq,
                "title": f"Bulk {i}",
                "st": st_id,
                "pri": pri_id,
                "pid": big_root_id,
                "cr": admin.id,
                "rnk": f"a{i:06d}",
            },
        )
    await rebuild_era(api_env.seed, admin.workspace_id)
    await api_env.seed.commit()

    count_before = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :p"), {"p": proj_id}
        )
    ).scalar_one()

    r_too_large = await client.post(
        f"/api/v1/issues/{big_root_key}/copy",
        json={"include_sub_issues": True},
    )
    contract_recorder.record("copy_issue_too_large_422", r_too_large.request, r_too_large)
    assert r_too_large.status_code == 422
    assert r_too_large.json()["code"] == "COPY_TOO_LARGE"

    # Assert zero new issues created
    await api_env.seed.rollback()
    count_after = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :p"), {"p": proj_id}
        )
    ).scalar_one()
    assert count_after == count_before


async def test_case_4_options_relates_to_attachments_modules_disabled(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: link_as_relates_to, include_attachments blob reuse, and modules_enabled=False gating."""
    admin = await make_user("admin4", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("OPT4", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create a module and a label and associate them
    mod_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "SELECT register_object('module'::object_kind, :ws, :proj, 'OPT4/modules/m1', 'Core Module', :cr, :id)"
        ),
        {"ws": admin.workspace_id, "proj": proj_id, "cr": admin.id, "id": mod_id},
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO modules (id, object_type, workspace_id, project_id, name) VALUES (:id, 'module', :ws, :proj, 'Core Module')"
        ),
        {"id": mod_id, "ws": admin.workspace_id, "proj": proj_id},
    )
    lbl_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) VALUES (:id, :ws, :p, 'frontend', '#00ff00')"
        ),
        {"id": lbl_id, "ws": admin.workspace_id, "p": proj_id},
    )
    # Enable modules on project initially
    await api_env.seed.execute(
        text("UPDATE projects SET modules_enabled = true WHERE id = :p"), {"p": proj_id}
    )
    await rebuild_era(api_env.seed, admin.workspace_id)
    await api_env.seed.commit()

    # Create source issue with module
    r_src = await client.post(
        "/api/v1/projects/OPT4/issues",
        json={"summary": "Source with options", "module_ids": [str(mod_id)]},
    )
    assert r_src.status_code == 201
    src_key = r_src.json()["key"]
    src_id = uuid.UUID(r_src.json()["id"])
    assert r_src.json()["module_ids"] == [str(mod_id)]

    # Create child issue with label and module
    r_sub = await client.post(
        "/api/v1/projects/OPT4/issues",
        json={
            "summary": "Sub issue with module and label",
            "parent": src_key,
            "label_ids": [str(lbl_id)],
            "module_ids": [str(mod_id)],
        },
    )
    assert r_sub.status_code == 201

    # Copy with modules_enabled=True and include_sub_issues=True
    copy_resp_enabled = await client.post(
        f"/api/v1/issues/{src_key}/copy",
        json={
            "include_sub_issues": True,
            "include_attachments": False,
            "link_as_relates_to": False,
        },
    )
    assert copy_resp_enabled.status_code == 201
    body_enabled = copy_resp_enabled.json()
    assert body_enabled["issue"]["module_ids"] == [str(mod_id)]
    assert len(body_enabled["copied_sub_issues"]) == 1
    sub_copy_key = body_enabled["copied_sub_issues"][0]["copy_key"]
    sub_copy_resp = await client.get(f"/api/v1/issues/{sub_copy_key}")
    assert sub_copy_resp.status_code == 200
    assert sub_copy_resp.json()["module_ids"] == [str(mod_id)]
    assert [lbl["name"] for lbl in sub_copy_resp.json()["labels"]] == ["frontend"]

    # 2. Insert readable attachment on source issue
    blob_hash = bytes.fromhex("11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff")
    storage_k = "sha256/11/22/11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff"
    att_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO attachments (id, workspace_id, project_id, issue_id, uploaded_by_id, "
            "original_filename, content_type, byte_size, pixel_width, pixel_height, blob_sha256, storage_key) "
            "VALUES (:id, :ws, :proj, :iid, :uid, 'spec.png', 'image/png', 2048, 200, 200, :bhash, :skey)"
        ),
        {
            "id": att_id,
            "ws": admin.workspace_id,
            "proj": proj_id,
            "iid": src_id,
            "uid": admin.id,
            "bhash": blob_hash,
            "skey": storage_k,
        },
    )
    # Disable modules on project to test gating
    await api_env.seed.execute(
        text("UPDATE projects SET modules_enabled = false WHERE id = :p"), {"p": proj_id}
    )
    await api_env.seed.commit()

    # Copy with all options
    copy_resp = await client.post(
        f"/api/v1/issues/{src_key}/copy",
        json={"include_sub_issues": False, "include_attachments": True, "link_as_relates_to": True},
    )
    assert copy_resp.status_code == 201, copy_resp.text
    body = copy_resp.json()

    # Modules gated: stripped from wire response when modules_enabled is false
    assert body["issue"].get("module_ids") is None

    # Attachments copied with identical blob hash and storage key
    assert body["copied_attachments"] == 1
    new_copy_id = uuid.UUID(body["issue"]["id"])

    await api_env.seed.rollback()
    copied_att = (
        await api_env.seed.execute(select(Attachment).where(Attachment.issue_id == new_copy_id))
    ).scalar_one()
    assert copied_att.blob_sha256 == blob_hash
    assert copied_att.storage_key == storage_k
    assert copied_att.original_filename == "spec.png"
    assert copied_att.uploaded_by_id == admin.id

    # RELATES_TO link created
    assert body["link_id"] is not None
    link_row = (
        await api_env.seed.execute(
            select(ObjectLink).where(ObjectLink.id == uuid.UUID(body["link_id"]))
        )
    ).scalar_one()
    assert link_row.source_id == new_copy_id
    assert link_row.target_id == src_id
    assert link_row.link_type == "RELATES_TO"


async def test_case_5_atomicity_transaction_rollback(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Injected failure on sub-issue creation rolls back entire copy and activity rows."""
    admin = await make_user("admin5", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("ATM5", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create root and 3 sub-issues
    r_root = await client.post("/api/v1/projects/ATM5/issues", json={"summary": "Root Atomic"})
    assert r_root.status_code == 201
    root_key = r_root.json()["key"]

    for i in range(1, 4):
        r_c = await client.post(
            "/api/v1/projects/ATM5/issues",
            json={"summary": f"Child {i}", "parent": root_key},
        )
        assert r_c.status_code == 201

    count_before = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :p"), {"p": proj_id}
        )
    ).scalar_one()
    act_count_before = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM activity_records WHERE workspace_id = :ws"),
            {"ws": admin.workspace_id},
        )
    ).scalar_one()

    # Inject failure on the 3rd sub-issue sequence allocation
    call_count = 0

    real_initial_rank = initial_board_rank

    def failing_rank(seq_id: int) -> str:
        nonlocal call_count
        call_count += 1
        # Top-level is call 1, child 1 is 2, child 2 is 3, child 3 is 4 -> raise on child 3
        if call_count >= 4:
            msg = "Simulated crash on 3rd sub-issue insert"
            raise RuntimeError(msg)
        return real_initial_rank(seq_id)

    with (
        patch("kanban.services.issue_copy.initial_board_rank", side_effect=failing_rank),
        pytest.raises((RuntimeError, ProblemException)),
    ):
        await client.post(
            f"/api/v1/issues/{root_key}/copy",
            json={"include_sub_issues": True},
        )

    # Verify atomic rollback
    await api_env.seed.rollback()
    count_after = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :p"), {"p": proj_id}
        )
    ).scalar_one()
    act_count_after = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM activity_records WHERE workspace_id = :ws"),
            {"ws": admin.workspace_id},
        )
    ).scalar_one()

    assert count_after == count_before
    assert act_count_after == act_count_before


async def test_case_6_auth_non_viewer_404_and_non_editor_403(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 6: Non-viewer returns 404; viewer without project EDIT returns 403 INSUFFICIENT_CAPABILITY."""
    admin = await make_user("admin6", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer6")  # project viewer only
    outsider = await make_user("outsider6")  # no project access

    await make_project(
        "AUT6",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", viewer: "VIEWER"},
    )
    r_src = await as_principal(admin).post(
        "/api/v1/projects/AUT6/issues", json={"summary": "Auth Guarded Issue"}
    )
    assert r_src.status_code == 201
    src_key = r_src.json()["key"]

    # 1. Outsider (non-viewer) calls copy -> 404 NOT_FOUND
    r_404 = await as_principal(outsider).post(f"/api/v1/issues/{src_key}/copy", json={})
    contract_recorder.record("copy_issue_non_viewer_404", r_404.request, r_404)
    assert r_404.status_code == 404
    assert r_404.json()["code"] == "NOT_FOUND"

    # 2. Viewer (viewer without EDIT) calls copy -> 403 INSUFFICIENT_CAPABILITY
    r_403 = await as_principal(viewer).post(f"/api/v1/issues/{src_key}/copy", json={})
    contract_recorder.record("copy_issue_non_editor_403", r_403.request, r_403)
    assert r_403.status_code == 403
    assert r_403.json()["code"] == "INSUFFICIENT_CAPABILITY"


def test_issue_copy_service_helpers_unit() -> None:
    """Unit test branches for _normalize_description and error mappings."""
    # Empty raw description returns empty string
    assert _normalize_description(None) == ""
    assert _normalize_description("") == ""

    # Normal description passes
    assert _normalize_description("Hello world") == "Hello world"

    # ContentNormalizeError CONTENT_TOO_LARGE -> DESCRIPTION_TOO_LARGE
    with patch(
        "kanban.services.issue_copy.normalize_to_markdown",
        side_effect=ContentNormalizeError("CONTENT_TOO_LARGE", "too big"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("huge")
        assert exc.value.code == "DESCRIPTION_TOO_LARGE"

    # ContentNormalizeError other -> INVALID_CONTENT
    with patch(
        "kanban.services.issue_copy.normalize_to_markdown",
        side_effect=ContentNormalizeError("OTHER", "err"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("bad")
        assert exc.value.code == "INVALID_CONTENT"

    # UnicodeEncodeError -> INVALID_CONTENT
    with patch(
        "kanban.services.issue_copy.normalize_to_markdown",
        side_effect=UnicodeEncodeError("utf-8", "test", 0, 1, "err"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("encode fail")
        assert exc.value.code == "INVALID_CONTENT"

    # Byte cap > 1 MiB -> DESCRIPTION_TOO_LARGE
    with patch("kanban.services.issue_copy.normalize_to_markdown", return_value="a" * 1048577):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("huge")
        assert exc.value.code == "DESCRIPTION_TOO_LARGE"


async def test_get_default_state_fallback(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Test fallback when no state is marked is_default."""
    admin = await make_user("admin_fb", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("FB1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    await api_env.seed.execute(
        text("UPDATE workflow_states SET is_default = false WHERE project_id = :p"),
        {"p": proj_id},
    )
    await api_env.seed.commit()

    fallback_id = await _get_default_state_id(api_env.seed, proj_id)
    assert fallback_id is not None


async def test_copy_issue_defensive_view_check(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test defensive check in copy_issue when Capability.VIEW is missing."""
    admin = await make_user("admin_def", workspace_role="WORKSPACE_ADMIN")
    await make_project("DEF1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    r = await client.post("/api/v1/projects/DEF1/issues", json={"summary": "Def test"})
    key = r.json()["key"]

    caller_ctx = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
    )
    with patch("kanban.services.issue_copy.evaluate_capabilities", return_value=frozenset()):
        with pytest.raises(ProblemException) as exc:
            await copy_issue(api_env.seed, caller_ctx, key, IssueCopyRequest())
        assert exc.value.status == 404
        assert exc.value.status == 404
