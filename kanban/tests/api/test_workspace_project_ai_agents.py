# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, TC002
"""Integration tests for workspace and project-level AI Providers & Autonomous Agents (KAN-402)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING
from unittest import mock

import httpx
import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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


@pytest.mark.asyncio
async def test_workspace_admin_ai_providers_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """WORKSPACE_ADMIN can create, list, probe, test, disable, reorder, budget, and delete workspace-scoped AI providers."""
    ws_admin = await make_user("ws_admin_ai", workspace_role="WORKSPACE_ADMIN")
    as_principal(ws_admin)
    client = api_env.client
    wid = str(api_env.workspace_id)

    # 1. Create workspace-scoped ollama provider
    create_payload = {
        "provider_kind": "ollama",
        "display_name": "Workspace Ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_allowlist": ["llama3:8b", "codellama:7b"],
        "residency_tier": "default",
        "priority": 10,
        "settings": {"temperature": 0.2},
        "is_enabled": True,
    }
    resp = await client.post(f"/api/v1/workspaces/{wid}/ai-providers", json=create_payload)
    assert resp.status_code == 201, resp.text
    prov_data = resp.json()
    prov_id = prov_data["id"]
    assert prov_data["display_name"] == "Workspace Ollama"
    assert prov_data["project_id"] is None

    # 2. List workspace providers
    resp = await client.get(f"/api/v1/workspaces/{wid}/ai-providers")
    assert resp.status_code == 200
    providers = resp.json()
    assert any(p["id"] == prov_id for p in providers)

    # 2b. Fetch workspace settings: GET /api/v1/workspaces/{wid}/ai-providers/settings
    resp_settings = await client.get(f"/api/v1/workspaces/{wid}/ai-providers/settings")
    assert resp_settings.status_code == 200
    assert resp_settings.json()["air_gap_mode"] is False

    # 2c. Get provider by ID: GET /api/v1/workspaces/{wid}/ai-providers/{prov_id}
    resp_get = await client.get(f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == prov_id
    assert resp_get.json()["display_name"] == "Workspace Ollama"

    # 2d. Negative: Get non-existent provider -> 404
    fake_prov_id = str(uuid.uuid4())
    resp_fake_get = await client.get(f"/api/v1/workspaces/{wid}/ai-providers/{fake_prov_id}")
    assert resp_fake_get.status_code == 404

    # 2e. Update provider: PATCH /api/v1/workspaces/{wid}/ai-providers/{prov_id}
    resp_patch = await client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}",
        json={"display_name": "Workspace Ollama Renamed", "priority": 15},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["display_name"] == "Workspace Ollama Renamed"
    assert resp_patch.json()["priority"] == 15

    # 2f. Update provider with api_key
    resp_patch_key = await client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}",
        json={"api_key": "test-ws-secret-key-1234"},
    )
    assert resp_patch_key.status_code == 200
    assert resp_patch_key.json()["api_key_set"] is True

    # 2g. Clear api_key with null
    resp_clear_key = await client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}",
        json={"api_key": None},
    )
    assert resp_clear_key.status_code == 200
    assert resp_clear_key.json()["api_key_set"] is False

    # 2h. Negative: Update with invalid base_url -> 422
    resp_bad_url = await client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}",
        json={"base_url": "http://169.254.169.254"},
    )
    assert resp_bad_url.status_code == 422

    # 2i. Negative: Update non-existent provider -> 404
    resp_patch_404 = await client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{fake_prov_id}",
        json={"display_name": "Ghost"},
    )
    assert resp_patch_404.status_code == 404

    # 3. Create second provider for reordering
    create_payload2 = {
        "provider_kind": "ollama",
        "display_name": "Workspace Ollama Secondary",
        "base_url": "http://127.0.0.1:11435",
        "model_allowlist": ["qwen2.5-coder:7b"],
        "residency_tier": "default",
        "priority": 20,
        "settings": {},
        "is_enabled": True,
    }
    resp2 = await client.post(f"/api/v1/workspaces/{wid}/ai-providers", json=create_payload2)
    assert resp2.status_code == 201
    prov_id2 = resp2.json()["id"]

    # 4. Reorder workspace providers
    reorder_payload = {"ordered_ids": [prov_id2, prov_id], "project_id": None}
    resp = await client.put(f"/api/v1/workspaces/{wid}/ai-providers/order", json=reorder_payload)
    assert resp.status_code == 200
    reordered = resp.json()
    assert reordered[0]["id"] == prov_id2
    assert reordered[0]["priority"] == 10
    assert reordered[1]["id"] == prov_id
    assert reordered[1]["priority"] == 20

    # 5. Probe models (mocking Ollama response) on body-based endpoint
    with mock.patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3:8b"}, {"name": "codellama:7b"}]}
        mock_get.return_value = mock_resp

        resp = await client.post(
            f"/api/v1/workspaces/{wid}/ai-providers/probe-models",
            json={"provider_kind": "ollama", "base_url": "http://127.0.0.1:11434"},
        )
        assert resp.status_code == 200
        probe_res = resp.json()
        assert probe_res["ok"] is True
        assert "llama3:8b" in probe_res["models"]

    # 5b. Probe models on saved provider: POST /api/v1/workspaces/{wid}/ai-providers/{prov_id}/probe-models
    with mock.patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3:8b"}]}
        mock_get.return_value = mock_resp

        resp_probe_saved = await client.post(
            f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}/probe-models",
            json={},
        )
        assert resp_probe_saved.status_code == 200
        assert resp_probe_saved.json()["ok"] is True

    # 5c. Negative: Probe models on non-existent provider -> 404
    resp_probe_404 = await client.post(
        f"/api/v1/workspaces/{wid}/ai-providers/{fake_prov_id}/probe-models",
        json={},
    )
    assert resp_probe_404.status_code == 404

    # 6. Test connection on saved provider
    with mock.patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3:8b"}]}
        mock_get.return_value = mock_resp

        resp = await client.post(
            f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}/test-connection",
            json={},
        )
        assert resp.status_code == 200
        test_res = resp.json()
        assert test_res["ok"] is True

    # 6b. Negative: Test connection on non-existent provider -> 404
    resp_test_404 = await client.post(
        f"/api/v1/workspaces/{wid}/ai-providers/{fake_prov_id}/test-connection",
        json={},
    )
    assert resp_test_404.status_code == 404

    # 7. Disable provider (colon endpoint and slash endpoint)
    resp = await client.post(f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}:disable")
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    resp_slash_dis = await client.post(f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}/disable")
    assert resp_slash_dis.status_code == 200
    assert resp_slash_dis.json()["is_enabled"] is False

    # 7b. Negative: Disable non-existent provider -> 404
    resp_dis_404 = await client.post(
        f"/api/v1/workspaces/{wid}/ai-providers/{fake_prov_id}:disable"
    )
    assert resp_dis_404.status_code == 404

    # 8. Set and fetch budget
    budget_payload = {
        "provider_config_id": prov_id,
        "period_kind": "daily",
        "token_cap": 500000,
    }
    resp = await client.put(f"/api/v1/workspaces/{wid}/ai-providers/budgets", json=budget_payload)
    assert resp.status_code == 200
    assert resp.json()["token_cap"] == 500000

    resp = await client.get(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        params={"provider_config_id": prov_id},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 8b. Negative: Set budget on non-existent provider -> 404
    resp_b_404 = await client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={"provider_config_id": fake_prov_id, "period_kind": "daily", "token_cap": 1000},
    )
    assert resp_b_404.status_code == 404

    # 8c. Negative: Set budget with invalid token cap -> 422
    resp_b_bad = await client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={"provider_config_id": prov_id, "period_kind": "daily", "token_cap": -100},
    )
    assert resp_b_bad.status_code == 422

    resp_b_overflow = await client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={"provider_config_id": prov_id, "period_kind": "daily", "token_cap": 20_000_000_000},
    )
    assert resp_b_overflow.status_code == 422

    # 8d. Negative: Get budgets on non-existent provider -> 404
    resp_b_missing = await client.get(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        params={"provider_config_id": fake_prov_id},
    )
    assert resp_b_missing.status_code == 404

    # 8e. Air gap mode validations
    await api_env.seed.execute(
        text("UPDATE workspace_settings SET air_gap_mode = true WHERE workspace_id = :wid"),
        {"wid": api_env.workspace_id},
    )
    await api_env.seed.commit()

    resp_settings_air = await client.get(f"/api/v1/workspaces/{wid}/ai-providers/settings")
    assert resp_settings_air.status_code == 200
    assert resp_settings_air.json()["air_gap_mode"] is True

    resp_air_create = await client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={
            "provider_kind": "gemini",
            "display_name": "Cloud Gemini",
            "model_allowlist": ["gemini-2.5-flash"],
        },
    )
    assert resp_air_create.status_code == 409
    assert resp_air_create.json()["code"] == "AIR_GAP_EGRESS_DENIED"

    resp_air_probe = await client.post(
        f"/api/v1/workspaces/{wid}/ai-providers/probe-models",
        json={"provider_kind": "gemini"},
    )
    assert resp_air_probe.status_code == 200
    assert resp_air_probe.json()["ok"] is False
    assert resp_air_probe.json()["error_code"] == "AIR_GAP_EGRESS_DENIED"

    await api_env.seed.execute(
        text("UPDATE workspace_settings SET air_gap_mode = false WHERE workspace_id = :wid"),
        {"wid": api_env.workspace_id},
    )
    await api_env.seed.commit()

    # 9. Delete provider
    resp = await client.delete(f"/api/v1/workspaces/{wid}/ai-providers/{prov_id2}")
    assert resp.status_code == 204

    # 9b. Negative: Delete non-existent provider -> 404
    resp_del_404 = await client.delete(f"/api/v1/workspaces/{wid}/ai-providers/{fake_prov_id}")
    assert resp_del_404.status_code == 404

    # 10. Workspace ref checks
    resp_curr = await client.get("/api/v1/workspaces/current/ai-providers")
    assert resp_curr.status_code == 200

    resp_bad_ws = await client.get(f"/api/v1/workspaces/{uuid.uuid4()}/ai-providers")
    assert resp_bad_ws.status_code == 404

    resp_bad_slug = await client.get("/api/v1/workspaces/nonexistent-workspace-slug/ai-providers")
    assert resp_bad_slug.status_code == 404


@pytest.mark.asyncio
async def test_project_admin_ai_providers_scoping_and_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """PROJECT_ADMIN can manage their project-scoped AI providers, but cannot touch workspace or other project scopes."""
    admin_a = await make_user("admin_proj_a", workspace_role="WORKSPACE_MEMBER")
    admin_b = await make_user("admin_proj_b", workspace_role="WORKSPACE_MEMBER")
    ws_admin = await make_user("ws_admin_scope", workspace_role="WORKSPACE_ADMIN")
    viewer_user = await make_user("viewer_user", workspace_role="WORKSPACE_MEMBER")

    proj_a_id = await make_project(
        "PRJA", created_by=admin_a, roles={admin_a: "PROJECT_ADMIN", viewer_user: "VIEWER"}
    )
    proj_b_id = await make_project("PRJB", created_by=admin_b, roles={admin_b: "PROJECT_ADMIN"})

    wid = str(api_env.workspace_id)
    p_a_str = str(proj_a_id)
    p_b_str = str(proj_b_id)

    # Provision workspace-level provider as ws_admin
    as_principal(ws_admin)
    resp_ws_prov = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Shared WS Ollama",
            "base_url": "http://127.0.0.1:11434",
            "model_allowlist": ["llama3:8b"],
            "priority": 10,
        },
    )
    assert resp_ws_prov.status_code == 201
    prov_ws_id = resp_ws_prov.json()["id"]

    # 1. Admin A creates project-scoped provider on Project A -> 201
    as_principal(admin_a)
    create_payload_a = {
        "provider_kind": "ollama",
        "display_name": "Project A Ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_allowlist": ["qwen2.5-coder:7b"],
        "residency_tier": "default",
        "priority": 10,
        "is_enabled": True,
        "project_id": p_a_str,
    }
    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers", json=create_payload_a
    )
    assert resp.status_code == 201, resp.text
    prov_a_id = resp.json()["id"]
    assert resp.json()["project_id"] == p_a_str

    # 1b. Admin A fetches their project provider -> 200
    resp_get_a = await api_env.client.get(f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}")
    assert resp_get_a.status_code == 200
    assert resp_get_a.json()["id"] == prov_a_id

    # 1c. Admin A probes and tests their project provider
    with mock.patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen2.5-coder:7b"}]}
        mock_get.return_value = mock_resp

        resp_probe = await api_env.client.post(
            f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}/probe-models",
            json={},
        )
        assert resp_probe.status_code == 200

        resp_test = await api_env.client.post(
            f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}/test-connection",
            json={},
        )
        assert resp_test.status_code == 200

    # 1d. Admin A patches their project provider -> 200
    resp_patch_a = await api_env.client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}",
        json={"display_name": "Project A Ollama Updated"},
    )
    assert resp_patch_a.status_code == 200
    assert resp_patch_a.json()["display_name"] == "Project A Ollama Updated"

    # 2. Admin A lists providers filtered by project_id -> returns provider A
    resp = await api_env.client.get(
        f"/api/v1/workspaces/{wid}/ai-providers", params={"project_id": p_a_str}
    )
    assert resp.status_code == 200
    providers = resp.json()
    assert len(providers) == 1
    assert providers[0]["id"] == prov_a_id

    # 3. Negative: Admin A attempts to create workspace-level provider (project_id=None) -> 403 Forbidden
    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={"provider_kind": "ollama", "display_name": "Rogue WS Prov"},
    )
    assert resp.status_code == 403, resp.text

    # 4. Negative: Admin A attempts to create provider for Project B -> 403 Forbidden
    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={"provider_kind": "ollama", "display_name": "Rogue Prov B", "project_id": p_b_str},
    )
    assert resp.status_code == 403, resp.text

    # 5. Negative: Admin B attempts to get, mutate, probe, test, delete provider A -> 403/404
    as_principal(admin_b)
    resp = await api_env.client.get(f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}")
    assert resp.status_code in (403, 404)

    resp = await api_env.client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}",
        json={"display_name": "Hacked Name"},
    )
    assert resp.status_code in (403, 404), resp.text

    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}/probe-models",
        json={},
    )
    assert resp.status_code in (403, 404)

    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}/test-connection",
        json={},
    )
    assert resp.status_code in (403, 404)

    resp = await api_env.client.delete(f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}")
    assert resp.status_code in (403, 404)

    # 6. Negative: Viewer attempts to mutate or create provider -> 403
    as_principal(viewer_user)
    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={"provider_kind": "ollama", "display_name": "Viewer Prov", "project_id": p_a_str},
    )
    assert resp.status_code == 403, resp.text

    # 7. Create second provider for Project A to test project-scoped reordering
    as_principal(admin_a)
    resp2 = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Project A Ollama 2",
            "base_url": "http://127.0.0.1:11434",
            "model_allowlist": ["qwen2.5-coder:7b"],
            "priority": 20,
            "project_id": p_a_str,
        },
    )
    assert resp2.status_code == 201
    prov_a_2_id = resp2.json()["id"]

    # Reorder project providers as Admin A -> 200
    reorder_payload = {
        "ordered_ids": [prov_a_2_id, prov_a_id],
        "project_id": p_a_str,
    }
    resp = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order", json=reorder_payload
    )
    assert resp.status_code == 200
    reordered = resp.json()
    assert reordered[0]["id"] == prov_a_2_id
    assert reordered[1]["id"] == prov_a_id

    # Negative: Admin B tries to reorder Project A providers -> 403
    as_principal(admin_b)
    resp = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order", json=reorder_payload
    )
    assert resp.status_code == 403

    # Negative: Admin A tries to reorder without project_id -> 403
    as_principal(admin_a)
    resp = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order",
        json={"ordered_ids": [prov_a_2_id, prov_a_id]},
    )
    assert resp.status_code == 403

    # 8. Budget Scope Isolation & Bypass Prevention (KAN-402 Finding 2):
    # Positive: Admin A can set budget on their own project provider
    resp_budget_ok = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={
            "provider_config_id": prov_a_id,
            "period_kind": "daily",
            "token_cap": 250000,
            "project_id": p_a_str,
        },
    )
    assert resp_budget_ok.status_code == 200
    assert resp_budget_ok.json()["token_cap"] == 250000

    # Negative: Admin A attempts to set budget on Project A provider with project_id=Project B -> 422 SCOPE_MISMATCH
    resp_b_mismatch = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={
            "provider_config_id": prov_a_id,
            "period_kind": "daily",
            "token_cap": 300000,
            "project_id": p_b_str,
        },
    )
    assert resp_b_mismatch.status_code == 422
    assert resp_b_mismatch.json()["code"] == "SCOPE_MISMATCH"

    # Negative: Admin A attempts to set budget on workspace provider with project_id=Project A -> 403/404/422
    resp_ws_bypass = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={
            "provider_config_id": prov_ws_id,
            "period_kind": "daily",
            "token_cap": 500000,
            "project_id": p_a_str,
        },
    )
    assert resp_ws_bypass.status_code in (403, 404, 422)

    # Negative: Admin A attempts to set budget on workspace provider with project_id=None -> 403/404
    resp_ws_no_proj = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={
            "provider_config_id": prov_ws_id,
            "period_kind": "daily",
            "token_cap": 500000,
        },
    )
    assert resp_ws_no_proj.status_code in (403, 404)

    # Negative: Admin B attempts to set budget on Project A provider -> 403/404
    as_principal(admin_b)
    resp_b_hijack = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/budgets",
        json={
            "provider_config_id": prov_a_id,
            "period_kind": "daily",
            "token_cap": 100000,
            "project_id": p_a_str,
        },
    )
    assert resp_b_hijack.status_code in (403, 404)

    # Delete second project provider
    as_principal(admin_a)
    resp_del_a2 = await api_env.client.delete(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_2_id}"
    )
    assert resp_del_a2.status_code == 204


@pytest.mark.asyncio
async def test_workspace_reorder_with_project_providers_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Workspace provider reordering succeeds even when project-scoped providers exist in the workspace (KAN-402 Finding 1)."""
    ws_admin = await make_user("ws_admin_reorder", workspace_role="WORKSPACE_ADMIN")
    proj_admin = await make_user("proj_admin_reorder", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project("ROPRJ", created_by=ws_admin, roles={proj_admin: "PROJECT_ADMIN"})

    wid = str(api_env.workspace_id)
    pid_str = str(proj_id)

    # 1. WS Admin creates two workspace-level providers
    as_principal(ws_admin)
    resp_w1 = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={
            "provider_kind": "ollama",
            "display_name": "WS Prov 1",
            "base_url": "http://127.0.0.1:11434",
            "model_allowlist": ["llama3:8b"],
            "priority": 10,
        },
    )
    assert resp_w1.status_code == 201
    w1_id = resp_w1.json()["id"]

    resp_w2 = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={
            "provider_kind": "ollama",
            "display_name": "WS Prov 2",
            "base_url": "http://127.0.0.1:11435",
            "model_allowlist": ["llama3:8b"],
            "priority": 20,
        },
    )
    assert resp_w2.status_code == 201
    w2_id = resp_w2.json()["id"]

    # 2. Project Admin creates a project-scoped provider
    as_principal(proj_admin)
    resp_p = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/ai-providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Project Prov",
            "base_url": "http://127.0.0.1:11434",
            "model_allowlist": ["qwen2.5-coder:7b"],
            "priority": 10,
            "project_id": pid_str,
        },
    )
    assert resp_p.status_code == 201
    p_id = resp_p.json()["id"]

    # 3. WS Admin lists workspace providers without project_id -> returns ONLY workspace providers
    as_principal(ws_admin)
    resp_list = await api_env.client.get(f"/api/v1/workspaces/{wid}/ai-providers")
    assert resp_list.status_code == 200
    listed_ids = [p["id"] for p in resp_list.json()]
    assert w1_id in listed_ids
    assert w2_id in listed_ids
    assert p_id not in listed_ids

    # 4. WS Admin reorders workspace providers -> MUST SUCCEED (not fail with 422 INVALID_REORDER_MEMBERSHIP)
    resp_reorder = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order",
        json={"ordered_ids": [w2_id, w1_id], "project_id": None},
    )
    assert resp_reorder.status_code == 200
    reordered = resp_reorder.json()
    assert reordered[0]["id"] == w2_id
    assert reordered[1]["id"] == w1_id

    # 5. Negative: Including project provider in workspace reorder fails with 422
    resp_bad_reorder = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order",
        json={"ordered_ids": [w2_id, w1_id, p_id], "project_id": None},
    )
    assert resp_bad_reorder.status_code == 422
    assert resp_bad_reorder.json()["code"] == "INVALID_REORDER_MEMBERSHIP"

    # 5b. Negative: Duplicate IDs in reorder fails with 422
    resp_dup = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order",
        json={"ordered_ids": [w2_id, w2_id], "project_id": None},
    )
    assert resp_dup.status_code == 422
    assert resp_dup.json()["code"] == "INVALID_REORDER_REQUEST"

    # 5c. Negative: Missing provider ID in reorder fails with 422
    resp_missing = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order",
        json={"ordered_ids": [w2_id], "project_id": None},
    )
    assert resp_missing.status_code == 422
    assert resp_missing.json()["code"] == "INVALID_REORDER_MEMBERSHIP"


@pytest.mark.asyncio
async def test_workspace_and_project_agent_definitions_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Workspace and Project scoped Autonomous Agent definitions lifecycle and validation."""
    ws_admin = await make_user("ws_admin_agent", workspace_role="WORKSPACE_ADMIN")
    proj_admin = await make_user("proj_admin_agent", workspace_role="WORKSPACE_MEMBER")
    member_user = await make_user("member_agent", workspace_role="WORKSPACE_MEMBER")

    proj_id = await make_project(
        "AGNT", created_by=proj_admin, roles={proj_admin: "PROJECT_ADMIN", member_user: "MEMBER"}
    )

    wid = str(api_env.workspace_id)
    pid_str = str(proj_id)

    # 1. WS Admin creates workspace-scoped agent
    as_principal(ws_admin)
    ws_agent_payload = {
        "slug": "ws-reality-checker",
        "display_name": "Workspace Reality Checker",
        "harness_kind": "in_app_sdk",
        "provider_kind": "gemini",
        "model_id": "gemini-2.5-flash",
        "timeout_ms": 45000,
    }
    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/agent-definitions", json=ws_agent_payload
    )
    assert resp.status_code == 201, resp.text
    ws_agent_id = resp.json()["id"]

    # 2. WS Admin provisions project-scoped agent
    as_principal(ws_admin)
    proj_agent_payload = {
        "slug": "proj-reviewer",
        "display_name": "Project Code Reviewer",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "agy",
        "cli_args": ["-p"],
        "project_id": pid_str,
        "timeout_ms": 60000,
    }
    resp = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/agent-definitions", json=proj_agent_payload
    )
    assert resp.status_code == 201, resp.text
    proj_agent_id = resp.json()["id"]
    assert resp.json()["project_id"] == pid_str

    # 3. Filtering agent definitions by project_id
    resp_proj = await api_env.client.get(
        f"/api/v1/workspaces/{wid}/agent-definitions",
        params={"project_id": pid_str},
    )
    assert resp_proj.status_code == 200
    proj_defs = resp_proj.json()
    assert any(d["id"] == proj_agent_id for d in proj_defs)
    # Workspace-scoped agent without project_id should not appear when filtered by project_id
    assert not any(d["id"] == ws_agent_id for d in proj_defs)

    # 4. Agent Validation route: POST /api/v1/agent-definitions/{agent}:validate
    # Project Admin can validate their project agent
    as_principal(proj_admin)
    resp = await api_env.client.post(f"/api/v1/agent-definitions/{proj_agent_id}:validate")
    assert resp.status_code == 200
    val_res = resp.json()
    assert val_res["valid"] is True
    assert val_res["status"] == "ok"

    # Slash-validate endpoint also works
    resp = await api_env.client.post(f"/api/v1/agent-definitions/{proj_agent_id}/validate")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True

    # 4b. Create remote_runner agent and validate
    as_principal(ws_admin)
    resp_rr = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/agent-definitions",
        json={
            "slug": "ws-remote-runner",
            "display_name": "Workspace Remote Runner",
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "test-pool",
            "timeout_ms": 30000,
        },
    )
    assert resp_rr.status_code == 201
    rr_id = resp_rr.json()["id"]

    resp_rr_val = await api_env.client.post(f"/api/v1/agent-definitions/{rr_id}:validate")
    assert resp_rr_val.status_code == 200
    assert resp_rr_val.json()["valid"] is True

    # 4c. Create cli_pipe agent and tamper with banned arg to test policy violation validation
    resp_cli_viol = await api_env.client.post(
        f"/api/v1/workspaces/{wid}/agent-definitions",
        json={
            "slug": "ws-cli-violator",
            "display_name": "Workspace CLI Violator",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "codex",
            "cli_args": ["exec", "-s", "read-only", "-"],
            "timeout_ms": 30000,
        },
    )
    assert resp_cli_viol.status_code == 201
    cli_viol_id = resp_cli_viol.json()["id"]

    # Directly tamper the row via SQL to inject a banned argument
    await api_env.seed.execute(
        text("UPDATE agent_definitions SET cli_args_json = '[\"--yolo\"]'::jsonb WHERE id = :id"),
        {"id": uuid.UUID(cli_viol_id)},
    )
    await api_env.seed.commit()

    resp_cli_val = await api_env.client.post(f"/api/v1/agent-definitions/{cli_viol_id}:validate")
    assert resp_cli_val.status_code == 200
    assert resp_cli_val.json()["valid"] is False
    assert resp_cli_val.json()["status"] == "policy_violation"

    # Negative: Standard member without project admin cannot validate agent -> 403
    as_principal(member_user)
    resp = await api_env.client.post(f"/api/v1/agent-definitions/{proj_agent_id}:validate")
    assert resp.status_code == 403

    # Negative: Project Admin cannot validate workspace-scoped agent without workspace admin -> 403
    as_principal(proj_admin)
    resp = await api_env.client.post(f"/api/v1/agent-definitions/{ws_agent_id}:validate")
    assert resp.status_code == 403

    # WS Admin CAN validate workspace agent
    as_principal(ws_admin)
    resp = await api_env.client.post(f"/api/v1/agent-definitions/{ws_agent_id}:validate")
    assert resp.status_code == 200

    # 5. Non-existent agent returns 404
    as_principal(ws_admin)
    missing_id = str(uuid.uuid4())
    resp = await api_env.client.post(f"/api/v1/agent-definitions/{missing_id}:validate")
    assert resp.status_code == 404

    # 5b. GET agent definition by UUID and by slug
    resp_get_uuid = await api_env.client.get(f"/api/v1/agent-definitions/{ws_agent_id}")
    assert resp_get_uuid.status_code == 200
    assert resp_get_uuid.json()["slug"] == "ws-reality-checker"

    resp_get_slug = await api_env.client.get("/api/v1/agent-definitions/ws-reality-checker")
    assert resp_get_slug.status_code == 200
    assert resp_get_slug.json()["id"] == ws_agent_id

    resp_get_missing = await api_env.client.get(f"/api/v1/agent-definitions/{missing_id}")
    assert resp_get_missing.status_code == 404

    # 5c. List agent definitions by workspace slug
    resp_list_slug = await api_env.client.get("/api/v1/workspaces/current/agent-definitions")
    assert resp_list_slug.status_code == 200
    assert any(a["id"] == ws_agent_id for a in resp_list_slug.json())

    # 6. Update agent definition: PATCH /api/v1/agent-definitions/{agent}
    as_principal(proj_admin)
    resp_patch_proj = await api_env.client.patch(
        f"/api/v1/agent-definitions/{proj_agent_id}",
        json={"display_name": "Patched Project Reviewer", "timeout_ms": 75000},
    )
    assert resp_patch_proj.status_code == 200
    assert resp_patch_proj.json()["display_name"] == "Patched Project Reviewer"
    assert resp_patch_proj.json()["timeout_ms"] == 75000

    # Negative: Project Admin attempts to patch workspace agent -> 403
    resp_patch_ws = await api_env.client.patch(
        f"/api/v1/agent-definitions/{ws_agent_id}",
        json={"display_name": "Hacked WS Agent"},
    )
    assert resp_patch_ws.status_code == 403

    # Negative: Member attempts to patch project agent -> 403
    as_principal(member_user)
    resp_patch_mem = await api_env.client.patch(
        f"/api/v1/agent-definitions/{proj_agent_id}",
        json={"display_name": "Member Hack"},
    )
    assert resp_patch_mem.status_code == 403

    # Negative: Patch non-existent agent -> 404
    as_principal(ws_admin)
    resp_patch_404 = await api_env.client.patch(
        f"/api/v1/agent-definitions/{missing_id}",
        json={"display_name": "Ghost"},
    )
    assert resp_patch_404.status_code == 404

    # 7. Delete agent definition: DELETE /api/v1/agent-definitions/{agent}
    # Negative: Project Admin attempts to delete workspace agent -> 403
    as_principal(proj_admin)
    resp_del_ws = await api_env.client.delete(f"/api/v1/agent-definitions/{ws_agent_id}")
    assert resp_del_ws.status_code == 403

    # Negative: Member attempts to delete project agent -> 403
    as_principal(member_user)
    resp_del_mem = await api_env.client.delete(f"/api/v1/agent-definitions/{proj_agent_id}")
    assert resp_del_mem.status_code == 403

    # Project Admin deletes project agent -> 204
    as_principal(proj_admin)
    resp_del_ok = await api_env.client.delete(f"/api/v1/agent-definitions/{proj_agent_id}")
    assert resp_del_ok.status_code == 204

    # WS Admin deletes workspace agent -> 204
    as_principal(ws_admin)
    resp_del_ws_ok = await api_env.client.delete(f"/api/v1/agent-definitions/{ws_agent_id}")
    assert resp_del_ws_ok.status_code == 204

    # Negative: Delete non-existent agent -> 404
    resp_del_404 = await api_env.client.delete(f"/api/v1/agent-definitions/{missing_id}")
    assert resp_del_404.status_code == 404


@pytest.mark.asyncio
async def test_server_admin_agent_definitions_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """SERVER_ADMIN with AAL2 can manage agent definitions via admin routes."""
    admin_user = await make_user("server_admin_agnt", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    # 1. Create agent via admin route
    create_payload = {
        "slug": "admin-reality-checker",
        "display_name": "Admin Reality Checker",
        "harness_kind": "in_app_sdk",
        "provider_kind": "gemini",
        "model_id": "gemini-2.5-flash",
        "timeout_ms": 40000,
    }
    resp = await client.post("/api/v1/admin/agent-definitions", json=create_payload)
    assert resp.status_code == 201
    ag_id = resp.json()["id"]

    # 2. List agents via admin route
    resp_list = await client.get("/api/v1/admin/agent-definitions")
    assert resp_list.status_code == 200
    assert any(a["id"] == ag_id for a in resp_list.json())

    # 3. Get agent via admin route
    resp_get = await client.get(f"/api/v1/admin/agent-definitions/{ag_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == ag_id

    # 4. Patch agent via admin route
    resp_patch = await client.patch(
        f"/api/v1/admin/agent-definitions/{ag_id}",
        json={"display_name": "Admin Reality Checker Renamed"},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["display_name"] == "Admin Reality Checker Renamed"

    # 5. Validate agent via admin route
    resp_val = await client.post(f"/api/v1/admin/agent-definitions/{ag_id}:validate")
    assert resp_val.status_code == 200
    assert resp_val.json()["valid"] is True

    # 6. Delete agent via admin route
    resp_del = await client.delete(f"/api/v1/admin/agent-definitions/{ag_id}")
    assert resp_del.status_code == 204
