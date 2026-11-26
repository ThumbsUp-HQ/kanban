# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for Workspace Settings REST API (KB-P4-09a)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.admin.workspace_settings import (
    WorkspaceSettingsUpdate,
    _get_or_create_settings,
    update_workspace_settings,
)
from kanban.app import create_app
from kanban.auth.mfa.policy import assert_admin_routes_protected
from kanban.tests.api.conftest import SeededUser
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv

pytestmark = pytest.mark.committed_db


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _as_admin_aal2(
    api_env: ApiEnv,
    user: SeededUser,
    *,
    aal2_verified_at: datetime | None = None,
) -> None:
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

    v_time = aal2_verified_at if aal2_verified_at is not None else datetime.now(UTC)
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
        aal2_verified_at=v_time,
    )


@pytest.mark.asyncio
async def test_workspace_settings_get_default(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """GET /api/v1/admin/workspace-settings returns default settings with 200."""
    admin = await make_user("ws_admin_1", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    resp = await api_env.client.get("/api/v1/admin/workspace-settings")
    assert resp.status_code == 200
    data = resp.json()

    assert data["workspace_id"] == str(admin.workspace_id)
    assert data["default_project_visibility"] == "private"
    assert data["session_idle_timeout_min"] == 60
    assert data["session_absolute_timeout_min"] == 720
    assert data["trash_retention_days"] == 30
    assert data["mcp_key_max_ttl_days"] == 90
    assert data["air_gap_mode"] is False
    assert data["default_skip_loaded_sequence_numbers"] is False
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_workspace_settings_patch_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """PATCH /api/v1/admin/workspace-settings updates fields and emits activity."""
    admin = await make_user("ws_admin_2", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    patch_payload = {
        "display_name": "Acme Engineering Core",
        "trash_retention_days": 45,
        "session_idle_timeout_min": 120,
        "session_absolute_timeout_min": 1440,
        "mcp_key_max_ttl_days": 60,
        "default_project_visibility": "workspace",
        "default_skip_loaded_sequence_numbers": True,
    }
    resp = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json=patch_payload,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["display_name"] == "Acme Engineering Core"
    assert data["trash_retention_days"] == 45
    assert data["session_idle_timeout_min"] == 120
    assert data["session_absolute_timeout_min"] == 1440
    assert data["mcp_key_max_ttl_days"] == 60
    assert data["default_project_visibility"] == "workspace"
    assert data["default_skip_loaded_sequence_numbers"] is True

    # Verify activity record was appended
    act_stmt = text(
        "SELECT event_type, payload FROM activity_records "
        "WHERE workspace_id = :ws_id AND event_type = 'WORKSPACE_SETTINGS_CHANGED'"
    )
    act_row = (await api_env.seed.execute(act_stmt, {"ws_id": admin.workspace_id})).first()
    assert act_row is not None
    assert act_row[0] == "WORKSPACE_SETTINGS_CHANGED"
    payload = act_row[1]
    assert "diff" in payload
    assert payload["diff"]["trash_retention_days"] == 45
    assert payload["diff"]["default_skip_loaded_sequence_numbers"] is True
    assert payload["before"]["default_skip_loaded_sequence_numbers"] is False
    assert payload["after"]["default_skip_loaded_sequence_numbers"] is True

    # Verify workspaces.trash_retention_days is synchronized
    ws_row = (
        await api_env.seed.execute(
            text("SELECT trash_retention_days FROM workspaces WHERE id = :id"),
            {"id": admin.workspace_id},
        )
    ).scalar_one()
    assert ws_row == 45


@pytest.mark.asyncio
async def test_workspace_settings_air_gap_toggle_and_aal2(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Toggling air_gap_mode requires AAL2 and emits AIR_GAP_MODE_CHANGED activity."""
    admin = await make_user("ws_admin_3", workspace_role="WORKSPACE_ADMIN")

    # Enroll factor so require_admin_aal2 evaluates AAL level rather than MFA_ENROLLMENT_REQUIRED
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": admin.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": admin.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    # 1. Caller with AAL1 session attempting to toggle air_gap_mode -> 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    resp_aal1 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"air_gap_mode": True},
    )
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    # 2. Caller with AAL2 session succeeds
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    resp_aal2 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"air_gap_mode": True},
    )
    assert resp_aal2.status_code == 200
    assert resp_aal2.json()["air_gap_mode"] is True

    # 3. Verify AIR_GAP_MODE_CHANGED activity record
    act_stmt = text(
        "SELECT event_type, payload FROM activity_records "
        "WHERE workspace_id = :ws_id AND event_type = 'AIR_GAP_MODE_CHANGED'"
    )
    act_row = (await api_env.seed.execute(act_stmt, {"ws_id": admin.workspace_id})).first()
    assert act_row is not None
    assert act_row[1]["air_gap_mode"] is True
    assert act_row[1]["previous"] is False


@pytest.mark.asyncio
async def test_workspace_settings_validation_boundaries(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Boundary and constraint violations return 422 VALIDATION_FAILED."""
    admin = await make_user("ws_admin_4", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # trash_retention_days out of bounds (0, 6 and 366)
    r0 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 0},
    )
    assert r0.status_code == 422

    r1 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 6},
    )
    assert r1.status_code == 422

    r2 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 366},
    )
    assert r2.status_code == 422

    # idle timeout > 720
    r3 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"session_idle_timeout_min": 721},
    )
    assert r3.status_code == 422

    # idle timeout < 5
    r4 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"session_idle_timeout_min": 4},
    )
    assert r4.status_code == 422

    # absolute timeout < idle timeout
    r5 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"session_idle_timeout_min": 100, "session_absolute_timeout_min": 60},
    )
    assert r5.status_code == 422
    assert "VALIDATION_FAILED" in str(r5.json())

    # empty display_name
    r6 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"display_name": ""},
    )
    assert r6.status_code == 422

    # display_name too long (> 80)
    r7 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"display_name": "x" * 81},
    )
    assert r7.status_code == 422

    # invalid default_project_visibility
    r8 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"default_project_visibility": "public"},
    )
    assert r8.status_code == 422


@pytest.mark.asyncio
async def test_workspace_settings_authz_and_admin_protection(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Non-admin and unauthenticated callers are rejected; admin routes are protected."""
    member = await make_user("ws_member", workspace_role="WORKSPACE_MEMBER")

    # 1. Unauthenticated -> 401
    api_env.resolver.principal = None
    r_unauth = await api_env.client.get("/api/v1/admin/workspace-settings")
    assert r_unauth.status_code == 401

    # 2. Member without administrative role -> 403
    api_env.resolver.principal = PrincipalContext(
        principal_id=member.id,
        workspace_id=member.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    r_member = await api_env.client.get("/api/v1/admin/workspace-settings")
    assert r_member.status_code == 403

    # 3. Section 4.3 invariant: assert_admin_routes_protected returns empty list
    app = create_app()
    unprotected = assert_admin_routes_protected(app)
    assert unprotected == []


@pytest.mark.asyncio
async def test_workspace_settings_rls_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Workspace B admin sees only Workspace B settings."""
    admin_a = await make_user("admin_a", workspace_role="WORKSPACE_ADMIN")

    ws_b_id = await create_workspace(api_env.seed, name="Workspace B")
    user_b_id = await create_user(api_env.seed, ws_b_id, handle="@admin_b", display_name="Admin B")
    await add_role_binding(
        api_env.seed,
        ws_b_id,
        user_b_id,
        role="WORKSPACE_ADMIN",
        scope_type="workspace",
    )
    await rebuild_era(api_env.seed, ws_b_id)
    await api_env.seed.commit()
    admin_b = SeededUser(id=user_b_id, workspace_id=ws_b_id, handle="admin_b")

    await _as_admin_aal2(api_env, admin_a)
    await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"display_name": "Workspace A Custom Name"},
    )

    await _as_admin_aal2(api_env, admin_b)
    resp_b = await api_env.client.get("/api/v1/admin/workspace-settings")
    assert resp_b.status_code == 200
    data_b = resp_b.json()

    assert data_b["workspace_id"] == str(admin_b.workspace_id)
    assert data_b["display_name"] != "Workspace A Custom Name"


@pytest.mark.asyncio
async def test_workspace_settings_project_admin_rejected(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """PROJECT_ADMIN passes require_admin_aal2.

    Rejected by require_workspace_or_server_admin.
    """
    proj_admin = await make_user("proj_admin_only", workspace_role=None)
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="TST",
        name="Test Proj",
        created_by_id=proj_admin.id,
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        proj_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    await _as_admin_aal2(api_env, proj_admin)
    resp = await api_env.client.get("/api/v1/admin/workspace-settings")
    assert resp.status_code == 403
    assert resp.json()["code"] == "INSUFFICIENT_CAPABILITY"


@pytest.mark.asyncio
async def test_workspace_settings_fallback_creation(
    api_env: ApiEnv,
) -> None:
    """_get_or_create_settings creates a new row when settings row is missing."""
    ws_c_id = await create_workspace(api_env.seed, name="Workspace C")
    # Delete the auto-initialized row to test fallback creation
    await api_env.seed.execute(
        text("DELETE FROM workspace_settings WHERE workspace_id = :ws_id"),
        {"ws_id": ws_c_id},
    )
    await api_env.seed.commit()

    created = await _get_or_create_settings(api_env.seed, ws_c_id)
    assert created.workspace_id == ws_c_id
    assert created.trash_retention_days == 30
    assert created.session_idle_timeout_min == 60


@pytest.mark.asyncio
async def test_workspace_settings_direct_aal2_enforcement(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """update_workspace_settings rejects air_gap_mode change if caller aal_level < 2."""
    admin = await make_user("ws_admin_direct", workspace_role="WORKSPACE_ADMIN")
    caller_aal1 = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    body = WorkspaceSettingsUpdate(air_gap_mode=True)
    with pytest.raises(ProblemException) as exc_info:
        await update_workspace_settings(
            body=body,
            caller=caller_aal1,
            session=api_env.seed,
        )
    assert exc_info.value.code == "AAL2_REQUIRED"


@pytest.mark.asyncio
async def test_workspace_settings_trash_retention_sync(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Updating trash_retention_days synchronizes workspaces.trash_retention_days."""
    admin = await make_user("ws_admin_sync", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    resp = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 45},
    )
    assert resp.status_code == 200
    assert resp.json()["trash_retention_days"] == 45

    res = await api_env.seed.execute(
        text("SELECT trash_retention_days FROM workspaces WHERE id = :ws_id"),
        {"ws_id": admin.workspace_id},
    )
    assert res.scalar_one() == 45


@pytest.mark.asyncio
async def test_workspace_settings_trash_retention_aal2_freshness(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Updating trash_retention_days requires fresh AAL2 (<= 900s)."""
    admin = await make_user("ws_admin_fresh", workspace_role="WORKSPACE_ADMIN")

    # 1. Stale AAL2 session (> 900s) -> 403 AAL2_STALE
    stale_time = datetime.now(UTC) - timedelta(seconds=905)
    await _as_admin_aal2(api_env, admin, aal2_verified_at=stale_time)
    r_stale = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 40},
    )
    assert r_stale.status_code == 403
    assert r_stale.json()["code"] == "AAL2_STALE"

    # 2. Missing verification timestamp -> 403 AAL2_STALE
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
        aal_level=2,
        aal2_verified_at=None,
    )
    r_null = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 40},
    )
    assert r_null.status_code == 403
    assert r_null.json()["code"] == "AAL2_STALE"

    # 3. AAL1 caller -> 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    r_aal1 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 40},
    )
    assert r_aal1.status_code == 403
    assert r_aal1.json()["code"] == "AAL2_REQUIRED"

    # 4. Fresh AAL2 session succeeds
    fresh_time = datetime.now(UTC)
    await _as_admin_aal2(api_env, admin, aal2_verified_at=fresh_time)
    r_fresh = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 40},
    )
    assert r_fresh.status_code == 200
    assert r_fresh.json()["trash_retention_days"] == 40


@pytest.mark.asyncio
async def test_workspace_settings_trash_retention_shortening_warn(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Shortening trash_retention_days emits TRASH_RETENTION_SHORTENED_WARN audit record."""
    admin = await make_user("ws_admin_warn", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # First set retention to 60 days
    r1 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 60},
    )
    assert r1.status_code == 200
    assert r1.json()["trash_retention_days"] == 60

    # Now shorten retention from 60 to 14 days
    r2 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"trash_retention_days": 14},
    )
    assert r2.status_code == 200
    assert r2.json()["trash_retention_days"] == 14

    # Verify TRASH_RETENTION_SHORTENED_WARN activity record was emitted
    act_stmt = text(
        "SELECT event_type, payload FROM activity_records "
        "WHERE workspace_id = :ws_id AND event_type = 'TRASH_RETENTION_SHORTENED_WARN'"
    )
    act_row = (await api_env.seed.execute(act_stmt, {"ws_id": admin.workspace_id})).first()
    assert act_row is not None
    assert act_row[0] == "TRASH_RETENTION_SHORTENED_WARN"
    payload = act_row[1]
    assert payload["previous_retention_days"] == 60
    assert payload["new_retention_days"] == 14
    assert "warning" in payload


@pytest.mark.asyncio
async def test_workspace_settings_name_and_slug_updates(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Updating workspace name and slug with validation checks."""
    admin = await make_user("ws_admin_nameslug", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Update name without display_name
    r1 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"name": "New Team Workspace"},
    )
    assert r1.status_code == 200
    assert r1.json()["name"] == "New Team Workspace"

    # 2. Update slug with valid format
    r2 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"slug": "new-team-slug"},
    )
    assert r2.status_code == 200
    assert r2.json()["slug"] == "new-team-slug"

    # 3. Invalid slug format -> 422
    r3 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"slug": "-invalid_slug"},
    )
    assert r3.status_code == 422

    # 4. Slug conflict with existing workspace -> 409
    await api_env.seed.execute(
        text(
            "INSERT INTO workspaces (id, name, slug) "
            "VALUES (uuidv7(), 'Taken Workspace', 'taken-slug')"
        ),
    )
    await api_env.seed.commit()

    r4 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"slug": "taken-slug"},
    )
    assert r4.status_code == 409
    assert r4.json()["code"] == "WORKSPACE_SLUG_CONFLICT"


@pytest.mark.asyncio
async def test_workspace_settings_export_import_toggles(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Exercise issue/report export and import policy toggles and role lists."""
    admin = await make_user("ws_admin_export_toggles", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Update export and import toggles and allowed roles
    r = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={
            "issue_export_enabled": False,
            "issue_import_enabled": False,
            "issue_export_allowed_roles": ["workspace_admin", "project_admin"],
            "report_export_enabled": False,
            "report_export_allowed_roles": ["ADMIN"],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["issue_export_enabled"] is False
    assert data["issue_import_enabled"] is False
    assert data["issue_export_allowed_roles"] == ["workspace_admin", "project_admin"]
    assert data["report_export_enabled"] is False
    assert data["report_export_allowed_roles"] == ["ADMIN"]

    # 2. Toggle back to true
    r2 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={
            "issue_export_enabled": True,
            "issue_import_enabled": True,
            "report_export_enabled": True,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["issue_export_enabled"] is True
    assert r2.json()["issue_import_enabled"] is True
    assert r2.json()["report_export_enabled"] is True
