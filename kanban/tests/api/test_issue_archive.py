"""Unit tests for issue archive and unarchive endpoints (S7.2 8p; KB-P3-09a)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from database.models import WorkflowState

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _count(env: ApiEnv, sql: str, **params: Any) -> int:  # noqa: ANN401
    """Return scalar count from the committed test session."""
    await env.seed.rollback()
    return int((await env.seed.execute(text(sql), params)).scalar_one())


async def test_case_1_positive_archive_unarchive_and_list_filtering(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive archive of Done issue returns 200 and filters correctly."""
    admin = await make_user("arc_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("ARC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Fetch Done workflow state
    done_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == proj_id,
                WorkflowState.state_group == "completed",
            )
        )
    ).first()
    assert done_row is not None
    done_state_id = done_row[0]

    # Create issue in Done state
    resp = await client.post(
        "/api/v1/projects/ARC/issues",
        json={
            "summary": "Completed task ready for archive",
            "description_markdown": "Work finished.",
            "state_id": str(done_state_id),
        },
    )
    assert resp.status_code == 201, resp.text
    issue_key = resp.json()["key"]
    assert resp.json()["archived_at"] is None
    assert resp.json()["archive_eligibility"]["allowed"] is True

    # 1. Archive the Done issue
    arc_resp = await client.post(f"/api/v1/issues/{issue_key}/archive")
    contract_recorder.record("archive_issue_200", arc_resp.request, arc_resp)
    assert arc_resp.status_code == 200, arc_resp.text
    body = arc_resp.json()
    assert body["archived_at"] is not None
    assert body["archive_eligibility"]["allowed"] is False
    assert body["archive_eligibility"]["reason"] == "Issue is already archived"

    # Verify ISSUE_ARCHIVED activity event
    archived_count = await _count(
        api_env,
        "SELECT count(*) FROM activity_records WHERE event_type = 'ISSUE_ARCHIVED'",
    )
    assert archived_count == 1

    # 2. Test list filtering
    # Default list excludes archived issues
    list_default = await client.get("/api/v1/projects/ARC/issues")
    assert list_default.status_code == 200
    assert len(list_default.json()["items"]) == 0

    # include_archived=true includes it
    list_included = await client.get("/api/v1/projects/ARC/issues?include_archived=true")
    assert list_included.status_code == 200
    assert len(list_included.json()["items"]) == 1
    assert list_included.json()["items"][0]["key"] == issue_key

    # include_archived=true&only_archived=true includes only archived
    list_url = "/api/v1/projects/ARC/issues?include_archived=true&only_archived=true"
    list_only = await client.get(list_url)
    assert list_only.status_code == 200
    assert len(list_only.json()["items"]) == 1

    # 3. Archiving already-archived issue returns 409 ALREADY_ARCHIVED
    arc_again = await client.post(f"/api/v1/issues/{issue_key}/archive")
    assert arc_again.status_code == 409
    assert arc_again.json()["code"] == "ALREADY_ARCHIVED"

    # 4. Unarchive issue
    unarc_resp = await client.post(f"/api/v1/issues/{issue_key}/unarchive")
    contract_recorder.record("unarchive_issue_200", unarc_resp.request, unarc_resp)
    assert unarc_resp.status_code == 200, unarc_resp.text
    unarc_body = unarc_resp.json()
    assert unarc_body["archived_at"] is None
    assert unarc_body["archive_eligibility"]["allowed"] is True

    # Verify ISSUE_UNARCHIVED activity event
    unarchived_count = await _count(
        api_env,
        "SELECT count(*) FROM activity_records WHERE event_type = 'ISSUE_UNARCHIVED'",
    )
    assert unarchived_count == 1

    # Unarchiving already-unarchived issue returns 409 NOT_ARCHIVED
    unarc_again = await client.post(f"/api/v1/issues/{issue_key}/unarchive")
    assert unarc_again.status_code == 409
    assert unarc_again.json()["code"] == "NOT_ARCHIVED"

    # Default list includes unarchived issue again
    list_after = await client.get("/api/v1/projects/ARC/issues")
    assert list_after.status_code == 200
    assert len(list_after.json()["items"]) == 1


async def test_case_2_rule_archive_in_progress_and_open_subissues(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: Archiving In Progress issue returns 409; open sub-issues block archive."""
    admin = await make_user("rule_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("RUL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Fetch In Progress and Done workflow states
    in_prog_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == proj_id,
                WorkflowState.state_group == "started",
            )
        )
    ).first()
    assert in_prog_row is not None
    in_prog_state_id = in_prog_row[0]

    done_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == proj_id,
                WorkflowState.state_group == "completed",
            )
        )
    ).first()
    assert done_row is not None
    done_state_id = done_row[0]

    # Create issue in In Progress state
    resp = await client.post(
        "/api/v1/projects/RUL/issues",
        json={
            "summary": "Feature currently being implemented",
            "description_markdown": "In progress work.",
            "state_id": str(in_prog_state_id),
        },
    )
    assert resp.status_code == 201
    in_prog_key = resp.json()["key"]
    assert resp.json()["archive_eligibility"]["allowed"] is False
    assert (
        resp.json()["archive_eligibility"]["reason"]
        == "Only completed or canceled work items can be archived"
    )

    # Attempt to archive In Progress issue
    arc_resp = await client.post(f"/api/v1/issues/{in_prog_key}/archive")
    contract_recorder.record("archive_issue_409_not_allowed", arc_resp.request, arc_resp)
    assert arc_resp.status_code == 409, arc_resp.text
    err = arc_resp.json()
    assert err["code"] == "ARCHIVE_NOT_ALLOWED"
    assert err["title"] == "Archive not allowed"
    assert err["detail"] == "Only completed or canceled work items can be archived"
    assert err["state_group"] == "started"

    # Now test open sub-issues blocking archive
    # Create parent issue in Done state
    parent_resp = await client.post(
        "/api/v1/projects/RUL/issues",
        json={
            "summary": "Parent epic marked done",
            "description_markdown": "Epic description.",
            "state_id": str(done_state_id),
        },
    )
    assert parent_resp.status_code == 201
    parent_key = parent_resp.json()["key"]
    parent_id = parent_resp.json()["id"]

    # Create child issue in In Progress state under parent
    child_resp = await client.post(
        "/api/v1/projects/RUL/issues",
        json={
            "summary": "Child subtask still open",
            "description_markdown": "Subtask details.",
            "state_id": str(in_prog_state_id),
            "parent": parent_id,
        },
    )
    assert child_resp.status_code == 201
    child_key = child_resp.json()["key"]

    # Verify parent serializer shows archive_eligibility allowed = False due to open subtask
    parent_get = await client.get(f"/api/v1/issues/{parent_key}")
    assert parent_get.status_code == 200
    assert parent_get.json()["archive_eligibility"]["allowed"] is False
    assert (
        parent_get.json()["archive_eligibility"]["reason"]
        == "Cannot archive work item with open sub-issues"
    )

    # Attempt to archive parent issue -> 409 ARCHIVE_OPEN_SUBISSUES
    arc_parent = await client.post(f"/api/v1/issues/{parent_key}/archive")
    assert arc_parent.status_code == 409
    parent_err = arc_parent.json()
    assert parent_err["code"] == "ARCHIVE_OPEN_SUBISSUES"
    assert child_key in parent_err["open_subissue_keys"]
    assert parent_err["hidden_open_count"] == 0

    # Also verify hidden open sub-issue increments hidden_open_count
    with patch("kanban.services.issue_archive.evaluate_capabilities", return_value=set()):
        arc_parent_hidden = await client.post(f"/api/v1/issues/{parent_key}/archive")
        assert arc_parent_hidden.status_code == 409
        hidden_err = arc_parent_hidden.json()
        assert hidden_err["hidden_open_count"] == 1
        assert hidden_err["open_subissue_keys"] == []

    # Transition child to Done
    child_patch = await client.patch(
        f"/api/v1/issues/{child_key}",
        json={"state_id": str(done_state_id)},
    )
    assert child_patch.status_code == 200

    # Parent archive succeeds now
    arc_parent_ok = await client.post(f"/api/v1/issues/{parent_key}/archive")
    assert arc_parent_ok.status_code == 200
    assert arc_parent_ok.json()["archived_at"] is not None


async def test_case_3_security_permissions_patch_guard_and_query_conflict(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Non-viewer 404, VIEW-only 403, PATCH on archived issue returns 409."""
    admin = await make_user("sec_admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("sec_viewer")
    outsider = await make_user("sec_outsider")

    proj_roles = {admin: "PROJECT_ADMIN", viewer: "VIEWER"}
    proj_id = await make_project("SEC", created_by=admin, roles=proj_roles)

    # Fetch Done workflow state
    done_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == proj_id,
                WorkflowState.state_group == "completed",
            )
        )
    ).first()
    assert done_row is not None
    done_state_id = done_row[0]

    admin_client = as_principal(admin)
    create_resp = await admin_client.post(
        "/api/v1/projects/SEC/issues",
        json={
            "summary": "Security tested issue",
            "description_markdown": "Sec test.",
            "state_id": str(done_state_id),
        },
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    # 1. Non-viewer receives 404 (anti-enumeration)
    outsider_client = as_principal(outsider)
    r_out_arc = await outsider_client.post(f"/api/v1/issues/{issue_key}/archive")
    contract_recorder.record("archive_issue_404_not_found", r_out_arc.request, r_out_arc)
    assert r_out_arc.status_code == 404
    assert r_out_arc.json()["code"] == "NOT_FOUND"

    r_out_unarc = await outsider_client.post(f"/api/v1/issues/{issue_key}/unarchive")
    assert r_out_unarc.status_code == 404
    assert r_out_unarc.json()["code"] == "NOT_FOUND"

    # 2. VIEW-only caller receives 403 INSUFFICIENT_CAPABILITY
    viewer_client = as_principal(viewer)
    r_view_arc = await viewer_client.post(f"/api/v1/issues/{issue_key}/archive")
    assert r_view_arc.status_code == 403
    assert r_view_arc.json()["code"] == "INSUFFICIENT_CAPABILITY"

    r_view_unarc = await viewer_client.post(f"/api/v1/issues/{issue_key}/unarchive")
    assert r_view_unarc.status_code == 403
    assert r_view_unarc.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. Archive issue as admin
    arc_ok = await as_principal(admin).post(f"/api/v1/issues/{issue_key}/archive")
    assert arc_ok.status_code == 200

    # 4. PATCH on archived issue returns 409 ISSUE_ARCHIVED
    patch_resp = await as_principal(admin).patch(
        f"/api/v1/issues/{issue_key}",
        json={"summary": "Attempting edit on archived issue"},
    )
    assert patch_resp.status_code == 409
    assert patch_resp.json()["code"] == "ISSUE_ARCHIVED"
    assert patch_resp.json()["title"] == "Issue Archived"

    # 5. Query filter conflict: include_archived=false & only_archived=true -> 422
    conflict_resp = await as_principal(admin).get(
        "/api/v1/projects/SEC/issues?include_archived=false&only_archived=true"
    )
    contract_recorder.record("archive_conflict_422", conflict_resp.request, conflict_resp)
    assert conflict_resp.status_code == 422
    assert conflict_resp.json()["code"] == "ARCHIVE_FILTER_CONFLICT"
