# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration test for AI providers explicit commit and immediate refetch sync (KAN-434)."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

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


async def _enroll_totp_and_set_aal2(
    api_env: ApiEnv,
    user: SeededUser,
) -> None:
    """Enroll and confirm TOTP factor to permit AAL2 evaluation for user."""
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
        aal_level=2,
    )


async def test_post_ai_provider_immediate_refetch_sync(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify POST /api/v1/workspaces/current/ai-providers commits cleanly and GET returns it."""
    ws_admin = await make_user("ws_admin_sync", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, ws_admin)
    as_principal(ws_admin)
    client = api_env.client

    # 1. Create provider via /current endpoint
    create_payload = {
        "provider_kind": "ollama",
        "display_name": "Immediate Sync Ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_allowlist": ["llama3:8b"],
        "residency_tier": "default",
        "priority": 10,
        "settings": {"temperature": 0.5},
        "is_enabled": True,
    }
    resp = await client.post("/api/v1/workspaces/current/ai-providers", json=create_payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    prov_id = created["id"]
    assert created["display_name"] == "Immediate Sync Ollama"

    # 2. Immediate GET /api/v1/workspaces/current/ai-providers must return newly committed provider
    resp_get = await client.get("/api/v1/workspaces/current/ai-providers")
    assert resp_get.status_code == 200, resp_get.text
    providers = resp_get.json()
    found = [p for p in providers if p["id"] == prov_id]
    assert len(found) == 1
    assert found[0]["display_name"] == "Immediate Sync Ollama"

    # 3. Test include_projects flag on workspace list endpoint
    resp_no_proj = await client.get(
        "/api/v1/workspaces/current/ai-providers?include_projects=false"
    )
    assert resp_no_proj.status_code == 200
    assert any(p["id"] == prov_id for p in resp_no_proj.json())

    # 4. Mutating operations commit cleanly:
    # 4a. Update
    patch_resp = await client.patch(
        f"/api/v1/workspaces/current/ai-providers/{prov_id}",
        json={"display_name": "Updated Sync Ollama"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["display_name"] == "Updated Sync Ollama"

    # Immediate GET reflects update
    resp_get2 = await client.get(f"/api/v1/workspaces/current/ai-providers/{prov_id}")
    assert resp_get2.status_code == 200
    assert resp_get2.json()["display_name"] == "Updated Sync Ollama"

    # 4b. Disable
    dis_resp = await client.post(f"/api/v1/workspaces/current/ai-providers/{prov_id}:disable")
    assert dis_resp.status_code == 200
    assert dis_resp.json()["is_enabled"] is False

    # 4c. Delete
    del_resp = await client.delete(f"/api/v1/workspaces/current/ai-providers/{prov_id}")
    assert del_resp.status_code == 204

    # Confirm deleted
    resp_get_after = await client.get("/api/v1/workspaces/current/ai-providers")
    assert resp_get_after.status_code == 200
    assert not any(p["id"] == prov_id for p in resp_get_after.json())
