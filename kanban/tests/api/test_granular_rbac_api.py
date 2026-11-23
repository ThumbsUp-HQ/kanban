# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit test suite for Granular RBAC API enforcement and Tier Governance (KAN-83)."""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from PIL import Image
from sqlalchemy import text

from kanban.attachments.service import AttachmentService
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    generate_csrf_token,
)
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit.pg import PgRateLimiter

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _seed_workspace_roles_if_needed(seed: AsyncSession, ws_id: uuid.UUID) -> None:
    """Ensure built-in RBAC roles exist for the workspace in test database."""
    role_check = await seed.execute(
        text("SELECT COUNT(*) FROM rbac_roles WHERE workspace_id = :ws_id"),
        {"ws_id": ws_id},
    )
    if role_check.scalar_one() > 0:
        return

    await seed.execute(
        text("SELECT seed_workspace_rbac_roles(:ws_id)"),
        {"ws_id": ws_id},
    )
    await seed.commit()


async def _enroll_and_confirm_totp(session: AsyncSession, p_id: uuid.UUID) -> None:
    """Enroll and confirm TOTP factor so require_admin_aal2 passes."""
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {
            "p_id": p_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": p_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await session.commit()


def _setup_attachments_app_state(env: ApiEnv, tmp_path: Path) -> None:
    """Ensure key material, rate limiter, and blob store are configured on app state."""
    app: Any = getattr(env.client._transport, "app")  # noqa: B009, SLF001
    km = KeyMaterial(
        master_kek=b"\x11" * 32,
        auth_pepper=b"\x22" * 32,
        session_hmac_key=b"\x33" * 32,
    )
    blob_store = LocalFilesystemBlobStore(tmp_path / "blobs")
    app.state.key_material = km
    app.state.attachment_blob_store = blob_store
    app.state.attachment_service = AttachmentService(blob_store, km.session_hmac_key)
    app_engine = app.state.session_factory._engine  # noqa: SLF001
    app.state.rate_limiter = PgRateLimiter(engine=app_engine)
    csrf_tok = generate_csrf_token(PRE_SESSION_ID, km.session_hmac_key)
    env.client.headers[CSRF_HEADER_NAME] = csrf_tok
    env.client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)


@pytest.mark.usefixtures("api_env")
async def test_workspace_creation_granular_permission(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify POST /api/v1/workspaces enforces workspace:create permission."""
    member = await make_user("regular_user", workspace_role="WORKSPACE_MEMBER")
    srv_admin = await make_user("srv_admin", workspace_role="SERVER_ADMIN")

    # 1. Standard member lacks workspace:create -> 403 INSUFFICIENT_PERMISSION
    client_member = as_principal(member)
    res_forbidden = await client_member.post(
        "/api/v1/workspaces",
        json={"name": "New Team Workspace", "slug": f"team-{uuid.uuid4().hex[:8]}"},
    )
    assert res_forbidden.status_code == 403
    err_body = res_forbidden.json()
    assert err_body["code"] == "INSUFFICIENT_PERMISSION"
    assert "workspace:create" in err_body.get("missing_permissions", [])

    # 2. Server admin has workspace:create -> 201 Created
    client_admin = as_principal(srv_admin, aal_level=2)
    res_ok = await client_admin.post(
        "/api/v1/workspaces",
        json={"name": "Admin Team Workspace", "slug": f"admin-{uuid.uuid4().hex[:8]}"},
    )
    assert res_ok.status_code == 201
    assert res_ok.json()["name"] == "Admin Team Workspace"


async def test_workspace_settings_and_members_aal2_and_granular_permissions(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify PATCH /workspaces/{id} and role-bindings require AAL2 and granular permissions."""
    member = await make_user("ws_member", workspace_role="WORKSPACE_MEMBER")
    ws_admin = await make_user("ws_admin", workspace_role="WORKSPACE_ADMIN")
    target_user = await make_user("target_user")
    await _enroll_and_confirm_totp(api_env.seed, ws_admin.id)

    # 1. Standard member without workspace:edit_settings -> 403
    client_member = as_principal(member)
    res_patch_forbidden = await client_member.patch(
        f"/api/v1/workspaces/{api_env.workspace_id}",
        json={"name": "Hacked Workspace"},
    )
    assert res_patch_forbidden.status_code == 403

    # 2. WS Admin without AAL2 (aal_level=1) -> 403 (AAL2 required)
    client_admin_aal1 = as_principal(ws_admin, aal_level=1)
    res_patch_aal1 = await client_admin_aal1.patch(
        f"/api/v1/workspaces/{api_env.workspace_id}",
        json={"name": "Updated Name AAL1"},
    )
    assert res_patch_aal1.status_code == 403

    # 3. WS Admin with AAL2 -> 200 OK
    client_admin_aal2 = as_principal(ws_admin, aal_level=2)
    res_patch_ok = await client_admin_aal2.patch(
        f"/api/v1/workspaces/{api_env.workspace_id}",
        json={"name": "Properly Renamed Workspace"},
    )
    assert res_patch_ok.status_code == 200

    # 4. Role bindings require AAL2 and workspace:manage_members
    client_admin_aal1 = as_principal(ws_admin, aal_level=1)
    res_bind_aal1 = await client_admin_aal1.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/role-bindings",
        json={"principal_id": str(target_user.id), "role": "WORKSPACE_MEMBER"},
    )
    assert res_bind_aal1.status_code == 403

    client_admin_aal2 = as_principal(ws_admin, aal_level=2)
    res_bind_ok = await client_admin_aal2.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/role-bindings",
        json={"principal_id": str(target_user.id), "role": "WORKSPACE_MEMBER"},
    )
    assert res_bind_ok.status_code == 200

    res_unbind_ok = await client_admin_aal2.request(
        "DELETE",
        f"/api/v1/workspaces/{api_env.workspace_id}/role-bindings",
        json={"principal_id": str(target_user.id), "role": "WORKSPACE_MEMBER"},
    )
    assert res_unbind_ok.status_code == 200


async def test_viewer_attachment_upload_bug_closed(
    api_env: ApiEnv,
    tmp_path: Path,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify VIEWER role cannot upload attachments (field:attach_files missing) closing bug."""
    _setup_attachments_app_state(api_env, tmp_path)

    admin = await make_user("proj_admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("proj_viewer", workspace_role="WORKSPACE_GUEST")

    client_admin = as_principal(admin)
    res_proj = await client_admin.post(
        "/api/v1/projects",
        json={"identifier": "ATT", "name": "Attachment Project", "description_markdown": "Test"},
    )
    assert res_proj.status_code == 201

    # Add viewer to project
    res_mem = await client_admin.post(
        "/api/v1/projects/ATT/members",
        json={"principal_id": str(viewer.id), "role": "VIEWER"},
    )
    assert res_mem.status_code == 201

    im = Image.new("RGB", (32, 32), color="red")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # 1. VIEWER upload rejected with 403 INSUFFICIENT_PERMISSION
    client_viewer = as_principal(viewer)
    res_viewer = await client_viewer.post(
        "/api/v1/projects/ATT/attachments",
        files={"file": ("test.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert res_viewer.status_code == 403
    err_body = res_viewer.json()
    assert err_body["code"] == "INSUFFICIENT_PERMISSION"
    assert "field:attach_files" in err_body.get("missing_permissions", [])

    # 2. Project admin (with field:attach_files) succeeds
    client_admin = as_principal(admin)
    res_admin = await client_admin.post(
        "/api/v1/projects/ATT/attachments",
        files={"file": ("test.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert res_admin.status_code == 201
    assert "id" in res_admin.json()


async def test_issue_field_level_permissions_and_response_fields(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify editable_fields & issue_permissions on IssueResponse and field-level PATCH gating."""
    await _seed_workspace_roles_if_needed(api_env.seed, api_env.workspace_id)

    admin = await make_user("lead_dev", workspace_role="WORKSPACE_ADMIN")
    contributor = await make_user("contributor", workspace_role="WORKSPACE_GUEST")
    await _enroll_and_confirm_totp(api_env.seed, admin.id)

    client_admin = as_principal(admin, aal_level=2)
    res_p = await client_admin.post(
        "/api/v1/projects",
        json={"identifier": "FLDG", "name": "Field Gating Project", "description_markdown": "Test"},
    )
    assert res_p.status_code == 201

    await client_admin.post(
        "/api/v1/projects/FLDG/members",
        json={"principal_id": str(contributor.id), "role": "VIEWER"},
    )

    # Create an issue as admin
    resp_create = await client_admin.post(
        "/api/v1/projects/FLDG/issues",
        json={
            "summary": "Original Summary",
            "description_markdown": "Original desc",
            "priority": "low",
        },
    )
    assert resp_create.status_code == 201
    created_data = resp_create.json()
    issue_key = created_data["key"]

    # Verify admin gets full editable_fields and issue_permissions
    assert "summary" in created_data["editable_fields"]
    assert "priority" in created_data["editable_fields"]
    assert "issue:comment" in created_data["issue_permissions"]

    # Grant contributor only 'field:modify_summary' via custom role label
    res_role = await client_admin.post(
        "/api/v1/admin/rbac/roles",
        json={"name": "Summary Editor Only", "slug": f"sum-edit-{uuid.uuid4().hex[:6]}"},
    )
    assert res_role.status_code == 201
    custom_role_id = res_role.json()["id"]

    res_perm = await client_admin.put(
        f"/api/v1/admin/rbac/roles/{custom_role_id}/permissions",
        json={"permissions": ["field:modify_summary"]},
    )
    assert res_perm.status_code == 200

    res_label = await client_admin.post(
        f"/api/v1/admin/principals/{contributor.id}/role-labels",
        json={"role_id": custom_role_id},
    )
    assert res_label.status_code == 201

    # Contributor reads issue
    client_contributor = as_principal(contributor)
    resp_get = await client_contributor.get(f"/api/v1/issues/{issue_key}")
    assert resp_get.status_code == 200
    issue_data = resp_get.json()
    assert "summary" in issue_data["editable_fields"]
    assert "priority" not in issue_data["editable_fields"]

    # Contributor edits summary -> Success 200
    resp_patch_sum = await client_contributor.patch(
        f"/api/v1/issues/{issue_key}",
        json={"summary": "Updated Summary by Contributor"},
    )
    assert resp_patch_sum.status_code == 200
    assert resp_patch_sum.json()["summary"] == "Updated Summary by Contributor"

    # Contributor edits priority -> Forbidden 403 INSUFFICIENT_PERMISSION
    resp_patch_prio = await client_contributor.patch(
        f"/api/v1/issues/{issue_key}",
        json={"priority": "urgent"},
    )
    assert resp_patch_prio.status_code == 403
    err_body = resp_patch_prio.json()
    assert err_body["code"] == "INSUFFICIENT_PERMISSION"
    assert "field:modify_priority" in err_body.get("missing_permissions", [])


async def test_admin_rbac_roles_crud_and_tier_governance(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify RBAC Role CRUD and Rules 1, 2, 3 governance enforcement."""
    await _seed_workspace_roles_if_needed(api_env.seed, api_env.workspace_id)

    standard_user = await make_user("normie", workspace_role="WORKSPACE_MEMBER")
    ws_admin = await make_user("ws_manager", workspace_role="WORKSPACE_ADMIN")
    srv_admin = await make_user("srv_boss", workspace_role="SERVER_ADMIN")

    await _enroll_and_confirm_totp(api_env.seed, ws_admin.id)
    await _enroll_and_confirm_totp(api_env.seed, srv_admin.id)

    # 1. Standard user cannot access admin RBAC endpoints -> 403
    client_normie = as_principal(standard_user)
    res_normie = await client_normie.get("/api/v1/admin/rbac/roles")
    assert res_normie.status_code == 403

    client_ws = as_principal(ws_admin, aal_level=2)
    # 2. WS Admin can list roles
    res_list = await client_ws.get("/api/v1/admin/rbac/roles")
    assert res_list.status_code == 200
    roles = res_list.json()
    assert len(roles) >= 6
    sys_admin_role = next(r for r in roles if r["slug"] == "system-admin")

    # 3. WS Admin creates a new custom role by cloning system-admin (Rule 3)
    res_create = await client_ws.post(
        "/api/v1/admin/rbac/roles",
        json={
            "name": "Cloned Sys Admin",
            "slug": "cloned-sys-admin",
            "clone_from_role_id": sys_admin_role["id"],
        },
    )
    assert res_create.status_code == 201
    cloned_role = res_create.json()
    cloned_role_id = cloned_role["id"]

    # Verify Rule 3: all workspace:* permissions were stripped on clone!
    res_cloned_perms = await client_ws.get(f"/api/v1/admin/rbac/roles/{cloned_role_id}/permissions")
    assert res_cloned_perms.status_code == 200
    cloned_perms = res_cloned_perms.json()["permissions"]
    for p in cloned_perms:
        assert not p.startswith("workspace:")

    # 4. Rule 1: WS Admin cannot add workspace:* permissions to a role
    res_escalate = await client_ws.put(
        f"/api/v1/admin/rbac/roles/{cloned_role_id}/permissions",
        json={"permissions": ["issue:view", "workspace:edit_settings"]},
    )
    assert res_escalate.status_code == 403
    assert res_escalate.json()["code"] == "WORKSPACE_PERMISSION_LOCKED"

    # Also via batch endpoint
    res_batch_escalate = await client_ws.put(
        "/api/v1/admin/rbac/roles/permissions:batch",
        json={
            "role_ids": [str(cloned_role_id)],
            "permission_key": "workspace:edit_settings",
            "granted": True,
        },
    )
    assert res_batch_escalate.status_code == 403
    assert res_batch_escalate.json()["code"] == "WORKSPACE_PERMISSION_LOCKED"

    # 5. Rule 1: WS Admin cannot modify or delete system-admin role
    res_patch_sys = await client_ws.patch(
        f"/api/v1/admin/rbac/roles/{sys_admin_role['id']}",
        json={"name": "Hacked System Admin"},
    )
    assert res_patch_sys.status_code == 403
    assert res_patch_sys.json()["code"] == "WORKSPACE_PERMISSION_LOCKED"

    res_del_sys = await client_ws.delete(
        f"/api/v1/admin/rbac/roles/{sys_admin_role['id']}",
    )
    assert res_del_sys.status_code == 403
    assert res_del_sys.json()["code"] in ("WORKSPACE_PERMISSION_LOCKED", "SYSTEM_ROLE_PROTECTED")

    # 6. Server Admin can grant workspace:* permissions
    client_srv = as_principal(srv_admin, aal_level=2)
    res_srv_grant = await client_srv.put(
        f"/api/v1/admin/rbac/roles/{cloned_role_id}/permissions",
        json={"permissions": ["issue:view", "workspace:edit_settings"]},
    )
    assert res_srv_grant.status_code == 200
    assert "workspace:edit_settings" in res_srv_grant.json()["permissions"]


async def test_admin_principals_role_labels_and_escalation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify principal role labels endpoints and escalation guard."""
    await _seed_workspace_roles_if_needed(api_env.seed, api_env.workspace_id)

    ws_admin = await make_user("ws_admin_user", workspace_role="WORKSPACE_ADMIN")
    target_user = await make_user("label_target")
    await _enroll_and_confirm_totp(api_env.seed, ws_admin.id)

    client_ws = as_principal(ws_admin, aal_level=2)

    # 1. Fetch system-admin role and viewer role
    res_roles = await client_ws.get("/api/v1/admin/rbac/roles")
    roles = res_roles.json()
    sys_admin_role = next(r for r in roles if r["slug"] == "system-admin")
    viewer_role = next(r for r in roles if r["slug"] == "viewer")

    # 2. WS Admin attempts to assign system-admin role label -> 403 ROLE_ESCALATION_DENIED
    res_escalate_post = await client_ws.post(
        f"/api/v1/admin/principals/{target_user.id}/role-labels",
        json={"role_id": sys_admin_role["id"]},
    )
    assert res_escalate_post.status_code == 403
    assert res_escalate_post.json()["code"] == "ROLE_ESCALATION_DENIED"

    # Same via PUT
    res_escalate_put = await client_ws.put(
        f"/api/v1/admin/principals/{target_user.id}/role-labels",
        json={"role_ids": [sys_admin_role["id"]]},
    )
    assert res_escalate_put.status_code == 403
    assert res_escalate_put.json()["code"] == "ROLE_ESCALATION_DENIED"

    # 3. WS Admin assigns viewer role label -> 201 Created
    res_assign_ok = await client_ws.post(
        f"/api/v1/admin/principals/{target_user.id}/role-labels",
        json={"role_id": viewer_role["id"]},
    )
    assert res_assign_ok.status_code == 201

    # 4. List user role labels
    res_list = await client_ws.get(f"/api/v1/admin/principals/{target_user.id}/role-labels")
    assert res_list.status_code == 200
    assigned_roles = res_list.json()
    assert any(r["role_id"] == viewer_role["id"] for r in assigned_roles)

    # 5. Remove role label
    res_del = await client_ws.delete(
        f"/api/v1/admin/principals/{target_user.id}/role-labels/{viewer_role['id']}"
    )
    assert res_del.status_code == 200


async def test_multi_role_label_additive_union_in_api(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify assigning multiple role labels grants additive union of granular permissions."""
    await _seed_workspace_roles_if_needed(api_env.seed, api_env.workspace_id)

    admin = await make_user("proj_lead", workspace_role="WORKSPACE_ADMIN")
    worker = await make_user("multi_role_worker", workspace_role="WORKSPACE_GUEST")
    await _enroll_and_confirm_totp(api_env.seed, admin.id)

    client_admin = as_principal(admin, aal_level=2)

    res_p = await client_admin.post(
        "/api/v1/projects",
        json={"identifier": "UNN", "name": "Union Project", "description_markdown": "Test"},
    )
    assert res_p.status_code == 201

    await client_admin.post(
        "/api/v1/projects/UNN/members",
        json={"principal_id": str(worker.id), "role": "VIEWER"},
    )

    # Create issue
    res_issue = await client_admin.post(
        "/api/v1/projects/UNN/issues",
        json={
            "summary": "Union Test Issue",
            "description_markdown": "Test desc",
            "priority": "low",
        },
    )
    assert res_issue.status_code == 201
    issue_key = res_issue.json()["key"]

    # Create Role 1: Grants field:modify_summary
    res_r1 = await client_admin.post(
        "/api/v1/admin/rbac/roles",
        json={"name": "Role Summary", "slug": f"role-sum-{uuid.uuid4().hex[:6]}"},
    )
    assert res_r1.status_code == 201
    r1_id = res_r1.json()["id"]
    await client_admin.put(
        f"/api/v1/admin/rbac/roles/{r1_id}/permissions",
        json={"permissions": ["field:modify_summary"]},
    )

    # Create Role 2: Grants field:modify_priority
    res_r2 = await client_admin.post(
        "/api/v1/admin/rbac/roles",
        json={"name": "Role Priority", "slug": f"role-prio-{uuid.uuid4().hex[:6]}"},
    )
    assert res_r2.status_code == 201
    r2_id = res_r2.json()["id"]
    await client_admin.put(
        f"/api/v1/admin/rbac/roles/{r2_id}/permissions",
        json={"permissions": ["field:modify_priority"]},
    )

    # Assign both roles to worker
    res_put = await client_admin.put(
        f"/api/v1/admin/principals/{worker.id}/role-labels",
        json={"role_ids": [r1_id, r2_id]},
    )
    assert res_put.status_code == 200

    # Worker can now modify BOTH summary and priority, but NOT state
    client_worker = as_principal(worker)

    res_sum = await client_worker.patch(
        f"/api/v1/issues/{issue_key}",
        json={"summary": "New Union Summary"},
    )
    assert res_sum.status_code == 200
    assert res_sum.json()["summary"] == "New Union Summary"

    res_prio = await client_worker.patch(
        f"/api/v1/issues/{issue_key}",
        json={"priority": "urgent"},
    )
    assert res_prio.status_code == 200
    assert res_prio.json()["priority"]["slug"] == "urgent"

    res_state = await client_worker.patch(
        f"/api/v1/issues/{issue_key}",
        json={"state": "COMPLETED"},
    )
    assert res_state.status_code == 403
    assert res_state.json()["code"] in ("INSUFFICIENT_PERMISSION", "INSUFFICIENT_CAPABILITY")
