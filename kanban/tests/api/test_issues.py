"""Issues API unit and integration tests (S7.2 8a, 8e, 8g, 8h, 8i; S12.2).

Covers all 8 mandatory feature test cases:
    1. Positive: create (201), Location, ETag, GET (200), If-None-Match (304), activity
    2. Concurrency: missing If-Match (428), stale ETag (412), race (first 200, second 412)
    3. Security: non-viewer 404 == absent 404, unreadable parent 422 == absent 422, restricted
    4. Sanitization: hidden HTML element exfiltration stripped, zero-width characters stripped
    5. Boundary: summary 500 vs 501, whitespace summary, description 1048576 vs 1048577
    6. Modules: defaults application on modules_enabled=True, modules_disabled rejection
    7. Labels: exclusive group replacement, intra-request collision 422
    8. Activity: multi-field scalar patch writes exactly N rows, no-op patch writes 0
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from database.models import Project, ProjectLabel
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issues import IssueCreate, IssuePatch, IssueResponse
from kanban.content import ContentNormalizeError
from kanban.services.issues import (
    _default_priority_id,
    _default_state_id,
    _handle_parent_dag_error,
    _normalize_description,
    _normalize_summary,
    _resolve_modules,
    _resolve_parent,
    _resolve_priority,
    decode_issue_cursor,
    encode_issue_cursor,
    initial_board_rank,
    to_base62,
    update_issue,
)
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_role_binding,
    create_registered_object,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _count(env: ApiEnv, sql: str, **params: Any) -> int:  # noqa: ANN401
    """Return a scalar count from the committed seed session."""
    await env.seed.rollback()
    return int((await env.seed.execute(text(sql), params)).scalar_one())


async def test_case_1_positive_create_get_etag_304_and_activity(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive create returns 201, ETag, Location, GET 200, If-None-Match 304."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project(
        "POS", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    client = as_principal(admin)

    desc = "# Description\n\nThis is a standard issue."
    expected_sha256 = hashlib.sha256(desc.encode("utf-8")).hexdigest()

    # Create issue
    resp = await client.post(
        "/api/v1/projects/POS/issues",
        json={
            "summary": "Fix authentication bug",
            "description_markdown": desc,
            "priority": "none",
            "start_date": "2026-11-11",
            "due_date": "2026-11-18",
        },
    )
    contract_recorder.record("create_issue_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    assert resp.headers["Location"] == "/api/v1/issues/POS-1"
    expected_etag = resp.headers["ETag"]
    assert expected_etag.startswith('"')
    assert expected_etag.endswith('"')

    body = resp.json()
    assert body["key"] == "POS-1"
    assert body["object_id"] == body["id"]
    assert str(uuid.UUID(body["object_id"])) == body["object_id"]
    assert body["summary"] == "Fix authentication bug"
    assert body["description_markdown"] == desc
    assert body["description_sha256"] == expected_sha256
    assert body["board_rank"] == "a000001"
    assert body["priority"]["slug"] == "none"
    assert body["state"]["name"] == "Backlog"
    assert body["start_date"] == "2026-11-11"
    assert body["due_date"] == "2026-11-18"
    assert body["parent"] is None
    assert body["labels"] == []
    assert body["module_ids"] == []
    assert "VIEW" in body["capabilities"]
    assert "EDIT" in body["capabilities"]

    issue_id = body["id"]

    # Verify ISSUE_CREATED activity recorded
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'ISSUE_CREATED' AND payload = CAST(:pl AS jsonb)",
            obj=issue_id,
            pl='{"key": "POS-1", "copied_from": null}',
        )
        == 1
    )

    # GET 200 with ETag
    get_resp = await client.get("/api/v1/issues/POS-1")
    assert get_resp.status_code == 200
    assert get_resp.headers["ETag"] == expected_etag
    assert get_resp.json()["id"] == issue_id

    # GET 304 with If-None-Match matching current ETag
    not_mod_resp = await client.get(
        "/api/v1/issues/POS-1", headers={"If-None-Match": expected_etag}
    )
    contract_recorder.record("get_issue_304", not_mod_resp.request, not_mod_resp)
    assert not_mod_resp.status_code == 304
    assert not_mod_resp.headers["ETag"] == expected_etag
    assert not_mod_resp.text == ""

    # GET 304 with unquoted/weak If-None-Match
    weak_304 = await client.get(
        "/api/v1/issues/POS-1", headers={"If-None-Match": f"W/{expected_etag}"}
    )
    assert weak_304.status_code == 304

    # GET 200 with non-matching If-None-Match
    mismatch_resp = await client.get(
        "/api/v1/issues/POS-1", headers={"If-None-Match": '"some-other-etag"'}
    )
    assert mismatch_resp.status_code == 200

    # Non-description property edit (priority) MUST change ETag and invalidate 304 cache
    patch_resp = await client.patch(
        "/api/v1/issues/POS-1",
        json={"priority": "urgent"},
    )
    assert patch_resp.status_code == 200
    patched_body = patch_resp.json()
    assert patched_body["priority"]["slug"] == "urgent"
    updated_etag = patch_resp.headers["ETag"]
    assert updated_etag != expected_etag

    # GET with old ETag returns 200 OK (NOT 304 stale cache) and reflects updated DB state
    stale_check_resp = await client.get(
        "/api/v1/issues/POS-1", headers={"If-None-Match": expected_etag}
    )
    assert stale_check_resp.status_code == 200
    assert stale_check_resp.json()["priority"]["slug"] == "urgent"
    assert stale_check_resp.headers["ETag"] == updated_etag

    # GET with updated ETag returns 304 Not Modified
    fresh_304_resp = await client.get(
        "/api/v1/issues/POS-1", headers={"If-None-Match": updated_etag}
    )
    assert fresh_304_resp.status_code == 304


async def test_case_2_concurrency_if_match_428_412_and_race(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: PATCH description requires If-Match (428), stale ETag 412, race 412."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("CONC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create issue
    create_resp = await client.post(
        "/api/v1/projects/CONC/issues",
        json={"summary": "Concurrent Issue", "description_markdown": "Initial content"},
    )
    assert create_resp.status_code == 201
    orig_etag = create_resp.headers["ETag"]

    # 1. Missing If-Match when patching description -> 428 PRECONDITION_REQUIRED
    missing_resp = await client.patch(
        "/api/v1/issues/CONC-1",
        json={"description_markdown": "Updated content without etag"},
    )
    contract_recorder.record("patch_description_428", missing_resp.request, missing_resp)
    assert missing_resp.status_code == 428
    assert missing_resp.json()["code"] == "PRECONDITION_REQUIRED"

    # 2. Stale ETag -> 412 PRECONDITION_FAILED with current_etag member
    stale_resp = await client.patch(
        "/api/v1/issues/CONC-1",
        json={"description_markdown": "Updated content"},
        headers={"If-Match": '"0000000000000000000000000000000000000000000000000000000000000000"'},
    )
    contract_recorder.record("patch_description_412", stale_resp.request, stale_resp)
    assert stale_resp.status_code == 412
    stale_body = stale_resp.json()
    assert stale_body["code"] == "PRECONDITION_FAILED"
    assert stale_body["current_etag"] == orig_etag

    # 3. Two sequential patches using same original ETag -> first 200, second 412
    p1 = await client.patch(
        "/api/v1/issues/CONC-1",
        json={"description_markdown": "First patch content"},
        headers={"If-Match": orig_etag},
    )
    assert p1.status_code == 200
    new_etag_1 = p1.headers["ETag"]
    assert new_etag_1 != orig_etag

    p2 = await client.patch(
        "/api/v1/issues/CONC-1",
        json={"description_markdown": "Second patch content"},
        headers={"If-Match": orig_etag},
    )
    assert p2.status_code == 412
    assert p2.json()["code"] == "PRECONDITION_FAILED"
    assert p2.json()["current_etag"] == new_etag_1

    # Optional If-Match on patch without description
    p3 = await client.patch(
        "/api/v1/issues/CONC-1",
        json={"summary": "New Summary"},
        headers={"If-Match": '"wrong-etag"'},
    )
    assert p3.status_code == 412


async def test_case_3_security_non_viewer_404_unreadable_parent_422_restricted_parent(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Non-viewer 404 == absent 404; unreadable parent 422 == absent; restricted parent."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    outsider = await make_user("outsider")

    proj_a_id = await make_project("PROJA", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    proj_b_id = await make_project("PROJB", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    # Grant outsider viewer role on PROJB only
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        outsider.id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_b_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Admin creates parent in PROJA
    parent_resp = await as_principal(admin).post(
        "/api/v1/projects/PROJA/issues",
        json={"summary": "Secret Epic in PROJA"},
    )
    assert parent_resp.status_code == 201
    parent_key = parent_resp.json()["key"]
    parent_id = parent_resp.json()["id"]

    # 1. Outsider GET PROJA-1 vs absent PROJA-999999 -> both 404 NOT_FOUND
    r_unreadable = await as_principal(outsider).get(f"/api/v1/issues/{parent_key}")
    contract_recorder.record("get_unreadable_issue_404", r_unreadable.request, r_unreadable)
    r_absent = await as_principal(outsider).get("/api/v1/issues/PROJA-999999")

    assert r_unreadable.status_code == 404
    assert r_absent.status_code == 404
    assert r_unreadable.json()["code"] == r_absent.json()["code"] == "NOT_FOUND"

    # 2. Outsider creating in PROJB referencing unreadable PROJA-1 vs nonexistent PROJB-999999
    r_parent_unreadable = await as_principal(outsider).post(
        "/api/v1/projects/PROJB/issues",
        json={"summary": "Child attempt", "parent": parent_key},
    )
    contract_recorder.record(
        "create_invalid_parent_422", r_parent_unreadable.request, r_parent_unreadable
    )

    r_parent_absent = await as_principal(outsider).post(
        "/api/v1/projects/PROJB/issues",
        json={"summary": "Child attempt 2", "parent": "PROJB-999999"},
    )

    assert r_parent_unreadable.status_code == 422
    assert r_parent_absent.status_code == 422
    assert r_parent_unreadable.json()["code"] == "INVALID_REFERENCE"
    assert r_parent_absent.json()["code"] == "INVALID_REFERENCE"
    assert r_parent_unreadable.json()["field"] == "parent"
    assert r_parent_absent.json()["field"] == "parent"

    # 3. Readable child of unreadable parent serializes restricted: true with no key or summary
    # Admin creates child in PROJA with parent PROJA-1
    child_resp = await as_principal(admin).post(
        "/api/v1/projects/PROJA/issues",
        json={"summary": "Public Child Issue", "parent": parent_key},
    )
    assert child_resp.status_code == 201
    child_key = child_resp.json()["key"]

    # Grant outsider VIEWER on PROJA, but add an explicit DENY override on parent_id
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        outsider.id,
        role="VIEWER",
        scope_type="project",
        project_id=proj_a_id,
    )
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        uuid.UUID(parent_id),
        outsider.id,
        effect="DENY",
        capability_mask=1,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Outsider views child
    outsider_child_resp = await as_principal(outsider).get(f"/api/v1/issues/{child_key}")
    contract_recorder.record(
        "get_restricted_parent_200", outsider_child_resp.request, outsider_child_resp
    )
    assert outsider_child_resp.status_code == 200
    child_body = outsider_child_resp.json()
    assert child_body["parent"] == {
        "restricted": True,
        "label": "🔒 Restricted Parent Issue",
    }
    assert "key" not in child_body["parent"]
    assert "id" not in child_body["parent"]
    assert "summary" not in child_body["parent"]


async def test_case_4_sanitization_hidden_html_and_zero_width_summary(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: Hidden element exfiltration disarmed; summary zero-width characters stripped."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("SAN", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Hidden element exfiltration in HTML
    payload_desc = '<div style="display:none">exfiltrate</div><p>ok</p>'
    summary_with_zw = "Summary with zero\u200bwidth\u200bspace"

    resp = await client.post(
        "/api/v1/projects/SAN/issues",
        json={"summary": summary_with_zw, "description_markdown": payload_desc},
    )
    assert resp.status_code == 201
    body = resp.json()

    assert "exfiltrate" not in body["description_markdown"]
    assert "ok" in body["description_markdown"]
    assert "\u200b" not in body["summary"]
    assert body["summary"] == "Summary with zerowidthspace"


async def test_case_5_boundaries_summary_description_dates(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Summary 500 ok vs 501 422, whitespace 422, desc byte cap, date ordering."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("BND", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Summary boundaries
    s500 = "a" * 500
    r500 = await client.post("/api/v1/projects/BND/issues", json={"summary": s500})
    assert r500.status_code == 201

    s501 = "a" * 501
    r501 = await client.post("/api/v1/projects/BND/issues", json={"summary": s501})
    assert r501.status_code == 422
    assert r501.json()["code"] == "SUMMARY_LENGTH"

    r_ws = await client.post("/api/v1/projects/BND/issues", json={"summary": "   \n\t  "})
    assert r_ws.status_code == 422
    assert r_ws.json()["code"] == "SUMMARY_LENGTH"

    # 2. Date ordering
    r_dates = await client.post(
        "/api/v1/projects/BND/issues",
        json={"summary": "Date check", "start_date": "2026-11-20", "due_date": "2026-11-10"},
    )
    assert r_dates.status_code == 422
    assert r_dates.json()["code"] == "DATE_ORDER"

    # 3. Description byte caps: exactly 1,048,576 bytes ok, 1,048,577 bytes 422
    desc_ok = "a" * 1048576
    r_desc_ok = await client.post(
        "/api/v1/projects/BND/issues",
        json={"summary": "Large desc ok", "description_markdown": desc_ok},
    )
    assert r_desc_ok.status_code == 201

    desc_too_large = "a" * 1048577
    r_desc_bad = await client.post(
        "/api/v1/projects/BND/issues",
        json={"summary": "Too large desc", "description_markdown": desc_too_large},
    )
    assert r_desc_bad.status_code == 422
    assert r_desc_bad.json()["code"] == "DESCRIPTION_TOO_LARGE"


async def test_case_6_modules_enabled_defaults_and_disabled_rejection(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    make_module: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 6: modules_enabled=true applies project defaults on null; rejects when disabled."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # Project with modules disabled
    await make_project("NOMOD", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    r_disabled = await client.post(
        "/api/v1/projects/NOMOD/issues",
        json={"summary": "No modules issue", "module_ids": []},
    )
    assert r_disabled.status_code == 422
    assert r_disabled.json()["code"] == "MODULES_DISABLED"

    # Project with modules enabled and 2 default modules
    proj_mod_id = await make_project("WITHMOD", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    m1 = await make_module(proj_mod_id, "Backend", created_by=admin)
    m2 = await make_module(proj_mod_id, "Frontend", created_by=admin)

    # Enable modules and configure default modules
    await api_env.seed.execute(
        text("UPDATE projects SET modules_enabled = true WHERE id = :p"),
        {"p": proj_mod_id},
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO project_module_defaults (project_id, module_id, workspace_id)"
            " VALUES (:p, :m1, :ws), (:p, :m2, :ws)"
        ),
        {"p": proj_mod_id, "m1": m1, "m2": m2, "ws": api_env.workspace_id},
    )
    await api_env.seed.commit()

    # Create issue with module_ids=null -> gets both defaults
    r_mod_ok = await client.post(
        "/api/v1/projects/WITHMOD/issues",
        json={"summary": "Default modules issue", "module_ids": None},
    )
    assert r_mod_ok.status_code == 201
    assert set(r_mod_ok.json()["module_ids"]) == {str(m1), str(m2)}


async def test_case_7_labels_exclusive_group_replacement_and_intra_request_conflict(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 7: Exclusive group replacement replaces old label; intra-request conflict 422."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("LBL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Seed 2 labels in exclusive group 'type', and 1 general label
    l_feat = uuid.uuid4()
    l_bug = uuid.uuid4()
    l_sec = uuid.uuid4()

    api_env.seed.add_all(
        [
            ProjectLabel(
                id=l_feat,
                workspace_id=api_env.workspace_id,
                project_id=proj_id,
                name="type:feature",
                color_hex="#3B82F6",
                exclusive_group="type",
            ),
            ProjectLabel(
                id=l_bug,
                workspace_id=api_env.workspace_id,
                project_id=proj_id,
                name="type:bug",
                color_hex="#EF4444",
                exclusive_group="type",
            ),
            ProjectLabel(
                id=l_sec,
                workspace_id=api_env.workspace_id,
                project_id=proj_id,
                name="security",
                color_hex="#10B981",
                exclusive_group=None,
            ),
        ]
    )
    await api_env.seed.commit()

    # 1. Attempt to create with both same-group labels -> 422 EXCLUSIVE_GROUP_CONFLICT
    r_conflict = await client.post(
        "/api/v1/projects/LBL/issues",
        json={"summary": "Conflict labels", "label_ids": [str(l_feat), str(l_bug)]},
    )
    assert r_conflict.status_code == 422
    assert r_conflict.json()["code"] == "EXCLUSIVE_GROUP_CONFLICT"

    # 2. Create with type:feature and security
    r_create = await client.post(
        "/api/v1/projects/LBL/issues",
        json={"summary": "Valid labels", "label_ids": [str(l_feat), str(l_sec)]},
    )
    assert r_create.status_code == 201
    assert {lbl["id"] for lbl in r_create.json()["labels"]} == {str(l_feat), str(l_sec)}

    # 3. Patch replacing type:feature with type:bug
    r_patch = await client.patch(
        "/api/v1/issues/LBL-1",
        json={"label_ids": [str(l_bug), str(l_sec)]},
    )
    assert r_patch.status_code == 200
    assert {lbl["id"] for lbl in r_patch.json()["labels"]} == {str(l_bug), str(l_sec)}

    # Verify ISSUE_LABELS_CHANGED activity recorded
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'ISSUE_LABELS_CHANGED'",
            obj=r_create.json()["id"],
        )
        == 1
    )


async def test_case_8_activity_scalar_patch_and_noop(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 8: Patch changing summary and due_date writes 2 rows; no-op patch writes 0."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("ACT", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/ACT/issues",
        json={"summary": "Original summary", "due_date": "2026-11-15"},
    )
    assert create_resp.status_code == 201
    issue_id = create_resp.json()["id"]

    # Patch changing summary and due_date
    patch_resp = await client.patch(
        "/api/v1/issues/ACT-1",
        json={"summary": "Changed summary", "due_date": "2026-11-25"},
    )
    assert patch_resp.status_code == 200

    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'ISSUE_FIELD_CHANGED'",
            obj=issue_id,
        )
        == 2
    )

    # No-op patch (all values equal)
    noop_resp = await client.patch(
        "/api/v1/issues/ACT-1",
        json={"summary": "Changed summary", "due_date": "2026-11-25"},
    )
    assert noop_resp.status_code == 200

    # Still exactly 2 rows
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'ISSUE_FIELD_CHANGED'",
            obj=issue_id,
        )
        == 2
    )


async def test_parent_cycle_and_depth_errors(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify cycle returns 409 PARENT_CYCLE and max depth returns PARENT_DEPTH_EXCEEDED."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("DAG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create root issue A
    ra = await client.post("/api/v1/projects/DAG/issues", json={"summary": "Issue A"})
    assert ra.status_code == 201

    # Create issue B with parent A
    rb = await client.post(
        "/api/v1/projects/DAG/issues", json={"summary": "Issue B", "parent": "DAG-1"}
    )
    assert rb.status_code == 201

    # Patch A with parent B -> cycle!
    r_cycle = await client.patch("/api/v1/issues/DAG-1", json={"parent": "DAG-2"})
    assert r_cycle.status_code == 409
    assert r_cycle.json()["code"] == "PARENT_CYCLE"

    # Patch A with parent A -> self-cycle!
    r_self = await client.patch("/api/v1/issues/DAG-1", json={"parent": "DAG-1"})
    assert r_self.status_code == 409
    assert r_self.json()["code"] == "PARENT_CYCLE"

    # Chain depth up to 6 levels: A(1) -> B(2) -> C(3) -> D(4) -> E(5) -> F(6)
    await client.post("/api/v1/projects/DAG/issues", json={"summary": "C", "parent": "DAG-2"})
    await client.post("/api/v1/projects/DAG/issues", json={"summary": "D", "parent": "DAG-3"})
    await client.post("/api/v1/projects/DAG/issues", json={"summary": "E", "parent": "DAG-4"})
    rf = await client.post("/api/v1/projects/DAG/issues", json={"summary": "F", "parent": "DAG-5"})
    assert rf.status_code == 201

    # 7th level fails with PARENT_DEPTH_EXCEEDED
    rg = await client.post("/api/v1/projects/DAG/issues", json={"summary": "G", "parent": "DAG-6"})
    assert rg.status_code == 409
    assert rg.json()["code"] == "PARENT_DEPTH_EXCEEDED"


async def test_list_issues_keyset_pagination(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify keyset pagination ordered by sequence_id DESC."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("LST", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create 5 issues
    for i in range(1, 6):
        r = await client.post("/api/v1/projects/LST/issues", json={"summary": f"Issue {i}"})
        assert r.status_code == 201

    # List with limit 2
    r_page1 = await client.get("/api/v1/projects/LST/issues?limit=2")
    assert r_page1.status_code == 200
    p1 = r_page1.json()
    assert len(p1["items"]) == 2
    assert p1["items"][0]["key"] == "LST-5"
    assert p1["items"][1]["key"] == "LST-4"
    assert p1["next_cursor"] is not None

    # Page 2
    r_page2 = await client.get(f"/api/v1/projects/LST/issues?limit=2&cursor={p1['next_cursor']}")
    assert r_page2.status_code == 200
    p2 = r_page2.json()
    assert len(p2["items"]) == 2
    assert p2["items"][0]["key"] == "LST-3"
    assert p2["items"][1]["key"] == "LST-2"

    # Page 3
    r_page3 = await client.get(f"/api/v1/projects/LST/issues?limit=2&cursor={p2['next_cursor']}")
    assert r_page3.status_code == 200
    p3 = r_page3.json()
    assert len(p3["items"]) == 1
    assert p3["items"][0]["key"] == "LST-1"
    assert p3["next_cursor"] is None

    # Invalid cursor
    r_inv = await client.get("/api/v1/projects/LST/issues?cursor=invalid_cursor")
    assert r_inv.status_code == 422
    assert r_inv.json()["code"] == "INVALID_CURSOR"


def test_base62_and_rank_unit() -> None:
    """Unit test base62 and initial board rank formulas."""
    assert to_base62(0) == "0"
    assert to_base62(1) == "1"
    assert to_base62(134) == "2A"
    assert initial_board_rank(1) == "a000001"
    assert initial_board_rank(134) == "a00002A"

    cursor = encode_issue_cursor(142)
    assert decode_issue_cursor(cursor) == 142
    with pytest.raises(ProblemException):
        decode_issue_cursor("bad!!!")


async def test_comprehensive_field_patching_and_validation(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Exercise all scalar and collection field patch branches, cycles, modules, and error paths."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("COMP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Fetch available workflow states and priorities
    states = (
        await api_env.seed.execute(
            text("SELECT id, name FROM workflow_states WHERE project_id = :p ORDER BY sort_order"),
            {"p": proj_id},
        )
    ).all()
    other_state_id = states[1][0]

    priorities = (
        await api_env.seed.execute(
            text(
                "SELECT id, slug FROM project_priorities WHERE project_id = :p ORDER BY sort_order"
            ),
            {"p": proj_id},
        )
    ).all()
    prio_map = {row[1]: row[0] for row in priorities}

    # Create cycle
    c1_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="cycle",
        key=f"cyc-{uuid.uuid4().hex[:6]}",
        title="Cycle 1",
        project_id=proj_id,
        created_by_id=admin.id,
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO cycles (id, workspace_id, project_id, name) "
            "VALUES (:id, :ws, :proj, 'Sprint 1')"
        ),
        {"id": c1_id, "ws": api_env.workspace_id, "proj": proj_id},
    )

    # Create 2 modules
    m1_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="module",
        key=f"mod-{uuid.uuid4().hex[:6]}",
        title="Module 1",
        project_id=proj_id,
        created_by_id=admin.id,
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO modules (id, workspace_id, project_id, name) "
            "VALUES (:id, :ws, :proj, 'Module 1')"
        ),
        {"id": m1_id, "ws": api_env.workspace_id, "proj": proj_id},
    )

    m2_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="module",
        key=f"mod-{uuid.uuid4().hex[:6]}",
        title="Module 2",
        project_id=proj_id,
        created_by_id=admin.id,
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO modules (id, workspace_id, project_id, name) "
            "VALUES (:id, :ws, :proj, 'Module 2')"
        ),
        {"id": m2_id, "ws": api_env.workspace_id, "proj": proj_id},
    )
    await api_env.seed.execute(
        text("UPDATE projects SET modules_enabled = TRUE WHERE id = :p"),
        {"p": proj_id},
    )
    await api_env.seed.commit()

    # Create root issue with module_ids=[m1_id]
    r_root = await client.post(
        "/api/v1/projects/COMP/issues",
        json={"summary": "Root Issue", "module_ids": [str(m1_id)]},
    )
    assert r_root.status_code == 201
    root_key = r_root.json()["key"]
    root_etag = r_root.headers["etag"]
    assert r_root.json()["module_ids"] == [str(m1_id)]
    assert len(r_root.json()["modules"]) == 1
    assert r_root.json()["modules"][0]["id"] == str(m1_id)
    assert r_root.json()["modules"][0]["name"] == "Module 1"

    # Patch root with Weak ETag W/"..."
    r_weak = await client.patch(
        f"/api/v1/issues/{root_key}",
        headers={"If-Match": f"W/{root_etag}"},
        json={"summary": "Root Issue Renamed"},
    )
    assert r_weak.status_code == 200

    # Patch summary: None -> 422 SUMMARY_LENGTH
    r_null_sum = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"summary": None},
    )
    assert r_null_sum.status_code == 422
    assert r_null_sum.json()["code"] == "SUMMARY_LENGTH"

    # Patch start_date and due_date
    r_dates = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"start_date": "2026-12-01", "due_date": "2026-12-10"},
    )
    assert r_dates.status_code == 200
    assert r_dates.json()["start_date"] == "2026-12-01"
    assert r_dates.json()["due_date"] == "2026-12-10"

    # Patch priority by slug and by UUID
    r_prio1 = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"priority": "urgent"},
    )
    assert r_prio1.status_code == 200
    assert r_prio1.json()["priority"]["slug"] == "urgent"

    r_prio2 = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"priority": str(prio_map["low"])},
    )
    assert r_prio2.status_code == 200
    assert r_prio2.json()["priority"]["slug"] == "low"

    # Patch state_id -> state transition
    r_state = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"state_id": str(other_state_id)},
    )
    assert r_state.status_code == 200
    assert r_state.json()["state"]["id"] == str(other_state_id)

    # Patch cycle_id -> set, then clear
    r_cyc = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"cycle_id": str(c1_id)},
    )
    assert r_cyc.status_code == 200
    assert r_cyc.json()["cycle_id"] == str(c1_id)
    assert r_cyc.json()["cycle"] is not None
    assert r_cyc.json()["cycle"]["id"] == str(c1_id)
    assert r_cyc.json()["cycle"]["name"] == "Sprint 1"

    r_cyc_clear = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"cycle_id": None},
    )
    assert r_cyc_clear.status_code == 200
    assert r_cyc_clear.json()["cycle_id"] is None
    assert r_cyc_clear.json()["cycle"] is None

    # Patch module_ids -> change to m2, then clear
    r_mod_change = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"module_ids": [str(m2_id)]},
    )
    assert r_mod_change.status_code == 200
    assert r_mod_change.json()["module_ids"] == [str(m2_id)]
    assert len(r_mod_change.json()["modules"]) == 1
    assert r_mod_change.json()["modules"][0]["name"] == "Module 2"
    assert r_mod_change.status_code == 200
    assert r_mod_change.json()["module_ids"] == [str(m2_id)]

    r_mod_clear = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"module_ids": []},
    )
    assert r_mod_clear.status_code == 200
    assert r_mod_clear.json()["module_ids"] == []

    # Create child issue referencing root by UUID
    root_id = r_root.json()["id"]
    r_child = await client.post(
        "/api/v1/projects/COMP/issues",
        json={"summary": "Child Issue", "parent": root_id},
    )
    assert r_child.status_code == 201
    child_key = r_child.json()["key"]
    assert r_child.json()["parent"]["key"] == root_key

    # Reparent child to None (unparent)
    r_unparent = await client.patch(
        f"/api/v1/issues/{child_key}",
        json={"parent": None},
    )
    assert r_unparent.status_code == 200
    assert r_unparent.json()["parent"] is None

    # Reparent child back to root_key
    r_reparent = await client.patch(
        f"/api/v1/issues/{child_key}",
        json={"parent": root_key},
    )
    assert r_reparent.status_code == 200
    assert r_reparent.json()["parent"]["key"] == root_key

    # Negative validation checks:
    # 1. Invalid parent format
    r_bad_parent = await client.post(
        "/api/v1/projects/COMP/issues",
        json={"summary": "Bad Parent", "parent": "Not-A-Key-Or-UUID-!!!"},
    )
    assert r_bad_parent.status_code == 422
    assert r_bad_parent.json()["code"] == "INVALID_REFERENCE"

    # 2. Nonexistent parent UUID
    r_absent_p_uuid = await client.post(
        "/api/v1/projects/COMP/issues",
        json={"summary": "Bad Parent", "parent": str(uuid.uuid4())},
    )
    assert r_absent_p_uuid.status_code == 422

    # 3. Invalid state_id
    r_bad_state = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"state_id": str(uuid.uuid4())},
    )
    assert r_bad_state.status_code == 422
    assert r_bad_state.json()["code"] == "INVALID_REFERENCE"

    # 4. Invalid priority slug
    r_bad_prio = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"priority": "nonexistent_priority_slug"},
    )
    assert r_bad_prio.status_code == 422
    assert r_bad_prio.json()["code"] == "INVALID_REFERENCE"

    # 5. Invalid cycle_id
    r_bad_cycle = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"cycle_id": str(uuid.uuid4())},
    )
    assert r_bad_cycle.status_code == 422
    assert r_bad_cycle.json()["code"] == "INVALID_REFERENCE"

    # 6. Invalid module_ids
    r_bad_mod = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"module_ids": [str(uuid.uuid4())]},
    )
    assert r_bad_mod.status_code == 422
    assert r_bad_mod.json()["code"] == "INVALID_REFERENCE"

    # 7. Invalid label_ids
    r_bad_lbl = await client.patch(
        f"/api/v1/issues/{root_key}",
        json={"label_ids": [str(uuid.uuid4())]},
    )
    assert r_bad_lbl.status_code == 422
    assert r_bad_lbl.json()["code"] == "INVALID_REFERENCE"


def test_issues_unit_helpers_and_error_handling() -> None:
    """Test helper functions, boundary edge cases, and parent dag error dispatch."""
    # to_base62 negative
    with pytest.raises(ValueError, match="num must be non-negative"):
        to_base62(-5)

    # decode_issue_cursor negative / 0
    with pytest.raises(ProblemException) as exc1:
        decode_issue_cursor(encode_issue_cursor(-1))
    assert exc1.value.code == "INVALID_CURSOR"

    with pytest.raises(ProblemException) as exc0:
        decode_issue_cursor(encode_issue_cursor(0))
    assert exc0.value.code == "INVALID_CURSOR"

    # _normalize_summary bounds
    with pytest.raises(ProblemException) as exc_sum:
        _normalize_summary("   ")
    assert exc_sum.value.code == "SUMMARY_LENGTH"

    with pytest.raises(ProblemException) as exc_sum_len:
        _normalize_summary("x" * 501)
    assert exc_sum_len.value.code == "SUMMARY_LENGTH"

    # _normalize_description bounds
    with pytest.raises(ProblemException) as exc_desc:
        _normalize_description("a" * (1048576 + 1))
    assert exc_desc.value.code == "DESCRIPTION_TOO_LARGE"

    # _handle_parent_dag_error with unhandled error message
    class DummyDBError(Exception):
        pass

    # Should not raise when message does not match DAG errors
    _handle_parent_dag_error(DummyDBError("Some unrelated DB error"))


async def test_services_edge_cases_and_missing_branches(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Cover edge cases, fallback branches, and TOCTOU concurrency in services.issues."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("EDGE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Unit tests on normalization errors
    with patch(
        "kanban.services.issues.normalize_plain_text",
        side_effect=ContentNormalizeError("TEST", "err"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_summary("test")
        assert exc.value.code == "INVALID_CONTENT"

    with patch(
        "kanban.services.issues.normalize_to_markdown",
        side_effect=ContentNormalizeError("CONTENT_TOO_LARGE", "err"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("test")
        assert exc.value.code == "DESCRIPTION_TOO_LARGE"

    with patch(
        "kanban.services.issues.normalize_to_markdown",
        side_effect=ContentNormalizeError("OTHER_ERR", "err"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("test")
        assert exc.value.code == "INVALID_CONTENT"

    with patch(
        "kanban.services.issues.normalize_to_markdown",
        side_effect=UnicodeEncodeError("utf-8", "test", 0, 1, "ouch"),
    ):
        with pytest.raises(ProblemException) as exc:
            _normalize_description("test")
        assert exc.value.code == "INVALID_CONTENT"

    with pytest.raises(ProblemException) as exc_dag:
        _handle_parent_dag_error(Exception("PARENT_NOT_FOUND"))
    assert exc_dag.value.code == "INVALID_REFERENCE"

    # 2. Database service helpers: _default_state_id fallback when no is_default
    await api_env.seed.execute(
        text("UPDATE workflow_states SET is_default = FALSE WHERE project_id = :p"),
        {"p": proj_id},
    )
    def_state = await _default_state_id(api_env.seed, proj_id)
    assert def_state is not None

    # _default_priority_id fallback when no is_default
    await api_env.seed.execute(
        text("UPDATE project_priorities SET is_default = FALSE WHERE project_id = :p"),
        {"p": proj_id},
    )
    def_prio = await _default_priority_id(api_env.seed, proj_id)
    assert def_prio is not None

    # _resolve_priority with UUID
    res_prio = await _resolve_priority(api_env.seed, proj_id, def_prio)
    assert res_prio == def_prio

    # Create an issue to test _resolve_parent with uuid.UUID
    r_iss = await client.post(
        "/api/v1/projects/EDGE/issues",
        json={"summary": "Edge Issue", "description_markdown": "Original desc"},
    )
    assert r_iss.status_code == 201
    iss_id = uuid.UUID(r_iss.json()["id"])
    iss_key = r_iss.json()["key"]
    iss_etag = r_iss.headers["etag"]

    proj_obj = await api_env.seed.get(Project, proj_id)
    assert proj_obj is not None
    assert api_env.resolver.principal is not None
    resolved_parent = await _resolve_parent(
        api_env.seed, api_env.resolver.principal, proj_obj, iss_id
    )
    assert resolved_parent.id == iss_id

    # _resolve_modules with module_ids=None and is_patch=True
    mod_patch_res = await _resolve_modules(api_env.seed, proj_obj, None, is_patch=True)
    assert mod_patch_res == []

    # 3. Test patch branches where passed values equal current values
    curr_issue_resp = (await client.get(f"/api/v1/issues/{iss_key}")).json()
    r_same = await client.patch(
        f"/api/v1/issues/{iss_key}",
        headers={"If-Match": iss_etag},
        json={
            "description_markdown": curr_issue_resp["description_markdown"],
            "priority": curr_issue_resp["priority"]["slug"],
            "state_id": curr_issue_resp["state"]["id"],
            "cycle_id": None,
            "parent": None,
        },
    )
    assert r_same.status_code == 200

    # 4. Test rowcount == 0 (TOCTOU) in update_issue (lines 875-881)
    orig_execute = api_env.seed.execute

    async def mock_execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        res = await orig_execute(stmt, *args, **kwargs)
        if hasattr(stmt, "is_update") and stmt.is_update:
            mock_res = MagicMock()
            mock_res.rowcount = 0
            return mock_res
        return res

    with patch.object(api_env.seed, "execute", side_effect=mock_execute):
        with pytest.raises(ProblemException) as exc_toctou:
            await update_issue(
                api_env.seed,
                api_env.resolver.principal,
                iss_key,
                IssuePatch(summary="New Summary"),
                if_match=iss_etag,
            )
        assert exc_toctou.value.code == "PRECONDITION_FAILED"


async def test_issue_and_comment_free_text_secret_scrubbing(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify outbound REST issue descriptions and comments redact known secret patterns."""
    user = await make_user("sec_scrub_user", workspace_role="WORKSPACE_ADMIN")
    await make_project("SCRUB", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    pem_block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Y1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJ\n"
        "KLMNOPQRSTUVWXYZ0123456789+/abcdefghijklmnopqrstuvwxyzABCDEFGHIJ\n"
        "-----END RSA PRIVATE KEY-----"
    )
    raw_desc = (
        "# Security Audit\n\n"
        "Configured credentials:\n"
        "- OpenAI: sk-proj-1234567890abcdef1234567890abcdef1234567890\n"
        "- GitHub: ghp_1234567890abcdefghijklmnopqrstuvwxyz12\n"
        "- AWS: AKIAIOSFODNN7EXAMPLE\n"
        "- Agent: kb_agt_0123456789abcdef\n"
        f"- PEM:\n```\n{pem_block}\n```\n\n"
        "Normal markdown: **bold** and `code` formatting."
    )

    # 1. Create issue
    resp_create = await client.post(
        "/api/v1/projects/SCRUB/issues",
        json={"summary": "Secret Issue", "description_markdown": raw_desc},
    )
    assert resp_create.status_code == 201
    created_data = resp_create.json()
    desc_out = created_data["description_markdown"]

    # Verify secrets are scrubbed in POST response
    assert "sk-proj-1234567890" not in desc_out
    assert "ghp_1234567890" not in desc_out
    assert "AKIAIOSFODNN7EXAMPLE" not in desc_out
    assert "kb_agt_0123456789" not in desc_out
    assert "BEGIN RSA PRIVATE KEY" not in desc_out

    assert "[REDACTED:API_KEY]" in desc_out
    assert "[REDACTED:GITHUB_TOKEN]" in desc_out
    assert "[REDACTED:AWS_ACCESS_KEY]" in desc_out
    assert "[REDACTED:KANBAN_KEY]" in desc_out
    assert "[REDACTED:PRIVATE_KEY]" in desc_out
    assert "# Security Audit" in desc_out
    assert "**bold** and `code` formatting." in desc_out

    issue_key = created_data["key"]
    etag = resp_create.headers["ETag"]

    # 2. GET issue
    resp_get = await client.get(f"/api/v1/issues/{issue_key}")
    assert resp_get.status_code == 200
    assert "[REDACTED:API_KEY]" in resp_get.json()["description_markdown"]
    assert "sk-proj-1234567890" not in resp_get.json()["description_markdown"]

    # 3. GET with matching ETag returns 304
    resp_304 = await client.get(f"/api/v1/issues/{issue_key}", headers={"If-None-Match": etag})
    assert resp_304.status_code == 304

    # 4. POST comment with secret
    resp_comm = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={
            "body_markdown": (
                "Found leaked token: ghp_1234567890abcdefghijklmnopqrstuvwxyz12 in deployment."
            )
        },
    )
    assert resp_comm.status_code == 201
    comm_data = resp_comm.json()
    assert "ghp_1234567890" not in comm_data["body_markdown"]
    assert "[REDACTED:GITHUB_TOKEN]" in comm_data["body_markdown"]

    # 5. GET comments
    resp_comm_list = await client.get(f"/api/v1/issues/{issue_key}/comments")
    assert resp_comm_list.status_code == 200
    comments_items = resp_comm_list.json()["items"]
    assert len(comments_items) == 1
    assert "[REDACTED:GITHUB_TOKEN]" in comments_items[0]["body_markdown"]
    assert "ghp_1234567890" not in comments_items[0]["body_markdown"]


def test_issue_schema_dedupe_and_json_schema() -> None:
    """Validate IssueCreate/IssuePatch label/module deduplication and OpenAPI schema generation."""
    u1 = uuid.uuid4()
    u2 = uuid.uuid4()

    # None branch
    ic_none = IssueCreate(summary="S", label_ids=None, module_ids=None)
    assert ic_none.label_ids is None
    assert ic_none.module_ids is None

    # Dedupe branch
    ic_dedupe = IssueCreate(summary="S", label_ids=[u1, u1, u2], module_ids=[u2, u2, u1])
    assert ic_dedupe.label_ids == [u1, u2]
    assert ic_dedupe.module_ids == [u2, u1]

    # IssuePatch None branch
    ip_none = IssuePatch(label_ids=None, module_ids=None)
    assert ip_none.label_ids is None
    assert ip_none.module_ids is None

    # IssuePatch Dedupe branch
    ip_dedupe = IssuePatch(label_ids=[u1, u1, u2], module_ids=[u2, u2, u1])
    assert ip_dedupe.label_ids == [u1, u2]
    assert ip_dedupe.module_ids == [u2, u1]

    # OpenAPI schema branch
    schema = IssueResponse.model_json_schema()
    assert "description" in schema
