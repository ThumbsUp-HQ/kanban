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

    # 5. Probe models (mocking Ollama response)
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

    # 7. Disable provider
    resp = await client.post(f"/api/v1/workspaces/{wid}/ai-providers/{prov_id}:disable")
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

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

    # 9. Delete provider
    resp = await client.delete(f"/api/v1/workspaces/{wid}/ai-providers/{prov_id2}")
    assert resp.status_code == 204


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
    viewer_user = await make_user("viewer_user", workspace_role="WORKSPACE_MEMBER")

    proj_a_id = await make_project("PRJA", created_by=admin_a, roles={admin_a: "PROJECT_ADMIN", viewer_user: "VIEWER"})
    proj_b_id = await make_project("PRJB", created_by=admin_b, roles={admin_b: "PROJECT_ADMIN"})

    wid = str(api_env.workspace_id)
    p_a_str = str(proj_a_id)
    p_b_str = str(proj_b_id)

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
    resp = await api_env.client.post(f"/api/v1/workspaces/{wid}/ai-providers", json=create_payload_a)
    assert resp.status_code == 201, resp.text
    prov_a_id = resp.json()["id"]
    assert resp.json()["project_id"] == p_a_str

    # 2. Admin A lists providers filtered by project_id -> returns provider A
    resp = await api_env.client.get(f"/api/v1/workspaces/{wid}/ai-providers", params={"project_id": p_a_str})
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

    # 5. Negative: Admin B attempts to mutate provider A -> 403/404
    as_principal(admin_b)
    resp = await api_env.client.patch(
        f"/api/v1/workspaces/{wid}/ai-providers/{prov_a_id}",
        json={"display_name": "Hacked Name"},
    )
    assert resp.status_code in (403, 404), resp.text

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
    resp = await api_env.client.put(f"/api/v1/workspaces/{wid}/ai-providers/order", json=reorder_payload)
    assert resp.status_code == 200
    reordered = resp.json()
    assert reordered[0]["id"] == prov_a_2_id
    assert reordered[1]["id"] == prov_a_id

    # Negative: Admin B tries to reorder Project A providers -> 403
    as_principal(admin_b)
    resp = await api_env.client.put(f"/api/v1/workspaces/{wid}/ai-providers/order", json=reorder_payload)
    assert resp.status_code == 403

    # Negative: Admin A tries to reorder without project_id -> 403
    as_principal(admin_a)
    resp = await api_env.client.put(
        f"/api/v1/workspaces/{wid}/ai-providers/order",
        json={"ordered_ids": [prov_a_2_id, prov_a_id]},
    )
    assert resp.status_code == 403


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

    proj_id = await make_project("AGNT", created_by=proj_admin, roles={proj_admin: "PROJECT_ADMIN", member_user: "MEMBER"})

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
    resp = await api_env.client.post(f"/api/v1/workspaces/{wid}/agent-definitions", json=ws_agent_payload)
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
    resp = await api_env.client.post(f"/api/v1/workspaces/{wid}/agent-definitions", json=proj_agent_payload)
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
