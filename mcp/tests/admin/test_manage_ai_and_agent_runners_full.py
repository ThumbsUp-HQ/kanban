# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: manage_ai_and_agent_runners (KB-P5-22a full actions)."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from mcp.app import create_mcp_app
from mcp.auth import McpAuthMiddleware
from mcp.registry import Surface
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _call_manage_tool(
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Invoke manage_ai_and_agent_runners via JSON-RPC 2.0 tools/call on /mcp/admin."""
    token = subject_token if subject_token is not None else env.token_server_admin_full
    init_resp = await env.mcp_client.post(
        "/mcp/admin",
        json={
            "jsonrpc": "2.0",
            "id": 999,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-admin", "version": "1.0"},
            },
        },
        headers={"X-KB-Subject-Token": token} if token else {},
    )
    assert init_resp.status_code == 200, init_resp.text
    session_id = init_resp.headers["mcp-session-id"]

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "manage_ai_and_agent_runners",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post(
        "/mcp/admin",
        json=req_payload,
        headers={"mcp-session-id": session_id, "X-KB-Subject-Token": token},
    )
    assert resp.status_code == 200, resp.text
    return cast("dict[str, Any]", resp.json())


@pytest.mark.asyncio
async def test_mcp_agent_definition_crud_and_yolo_rejection(admin_env: AdminTestEnv) -> None:
    """Verify upsert, list, delete agent_definition and --yolo rejection."""
    # 1. Reject --yolo flag in cli_args
    yolo_call = await _call_manage_tool(
        admin_env,
        {
            "action": "upsert_agent_definition",
            "slug": "yolo-agent",
            "display_name": "YOLO Agent",
            "harness_kind": "cli_pipe",
            "cli_args": ["--yolo", "--verbose"],
        },
    )
    assert "error" in yolo_call or yolo_call.get("result", {}).get("isError") is True

    # 2. Valid create: upsert_agent_definition for remote_runner
    create_call = await _call_manage_tool(
        admin_env,
        {
            "action": "upsert_agent_definition",
            "slug": "sec-gate-auditor",
            "display_name": "Security Gate Auditor",
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "audit-pool",
            "timeout_ms": 45000,
            "system_instructions_md": "Performs remote security gate audits.",
            "lod": "standard",
        },
    )
    assert "result" in create_call
    create_data = yaml.safe_load(create_call["result"]["content"][0]["text"])
    assert create_data["slug"] == "sec-gate-auditor"
    assert create_data["harness_kind"] == "remote_runner"
    assert create_data["remote_runner_pool_slug"] == "audit-pool"
    assert create_data["timeout_ms"] == 45000

    # 3. List definitions: verify created agent is returned
    list_call = await _call_manage_tool(admin_env, {"action": "list_agent_definitions"})
    assert "result" in list_call
    list_data = yaml.safe_load(list_call["result"]["content"][0]["text"])
    assert any(a["slug"] == "sec-gate-auditor" for a in list_data)

    # 4. Update: modify display_name
    update_call = await _call_manage_tool(
        admin_env,
        {
            "action": "upsert_agent_definition",
            "slug": "sec-gate-auditor",
            "display_name": "Updated Security Gate Auditor",
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "audit-pool",
        },
    )
    assert "result" in update_call
    update_data = yaml.safe_load(update_call["result"]["content"][0]["text"])
    assert update_data["display_name"] == "Updated Security Gate Auditor"

    # 5. Delete without confirm: true -> returns confirmation required preview
    preview_del = await _call_manage_tool(
        admin_env,
        {
            "action": "delete_agent_definition",
            "slug": "sec-gate-auditor",
        },
    )
    assert "result" in preview_del
    prev_data = yaml.safe_load(preview_del["result"]["content"][0]["text"])
    assert prev_data["status"] == "confirmation_required"
    assert prev_data["agent"] == "sec-gate-auditor"

    # 6. Delete with confirm: true -> performs deletion
    confirmed_del = await _call_manage_tool(
        admin_env,
        {
            "action": "delete_agent_definition",
            "slug": "sec-gate-auditor",
            "confirm": True,
        },
    )
    assert "result" in confirmed_del
    del_data = yaml.safe_load(confirmed_del["result"]["content"][0]["text"])
    assert del_data["status"] == "deleted"

    # 7. List definitions: verify sec-gate-auditor is gone
    list_call_after = await _call_manage_tool(admin_env, {"action": "list_agent_definitions"})
    list_data_after = yaml.safe_load(list_call_after["result"]["content"][0]["text"])
    assert not any(a["slug"] == "sec-gate-auditor" for a in list_data_after)


@pytest.mark.asyncio
async def test_mcp_mint_enrollment_token_and_list_runners(admin_env: AdminTestEnv) -> None:
    """Verify mint_runner_enrollment_token and list_remote_runners via MCP."""
    # 1. Invalid pool slug -> error
    bad_slug_call = await _call_manage_tool(
        admin_env,
        {
            "action": "mint_runner_enrollment_token",
            "pool_slug": "INVALID_SLUG!",
            "ttl_seconds": 300,
        },
    )
    assert "error" in bad_slug_call or bad_slug_call.get("result", {}).get("isError") is True

    # 2. Mint valid token: token returned once in plaintext
    mint_call = await _call_manage_tool(
        admin_env,
        {
            "action": "mint_runner_enrollment_token",
            "pool_slug": "mcp-gpu-pool",
            "ttl_seconds": 600,
        },
    )
    assert "result" in mint_call
    mint_data = yaml.safe_load(mint_call["result"]["content"][0]["text"])
    token = mint_data["enrollment_token"]
    assert token.startswith("kb_rnr_enroll_")
    assert mint_data["pool_slug"] == "mcp-gpu-pool"

    # 3. List runners with pool filter
    list_call = await _call_manage_tool(
        admin_env,
        {
            "action": "list_remote_runners",
            "pool_slug": "mcp-gpu-pool",
        },
    )
    assert "result" in list_call
    runners_data = yaml.safe_load(list_call["result"]["content"][0]["text"])
    assert isinstance(runners_data, list)


@pytest.mark.asyncio
async def test_mcp_revoke_remote_runner_confirmation_lifecycle(admin_env: AdminTestEnv) -> None:
    """Verify revoke_remote_runner preview vs confirm: true execution."""
    mint_call = await _call_manage_tool(
        admin_env,
        {
            "action": "mint_runner_enrollment_token",
            "pool_slug": "mcp-revoke-pool",
            "ttl_seconds": 300,
        },
    )
    token = yaml.safe_load(mint_call["result"]["content"][0]["text"])["enrollment_token"]

    k = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "revoke-target")])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(name)
        .sign(k, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )

    # We can call internal client enroll endpoint
    enroll_resp = await admin_env.internal_client._client.post(  # noqa: SLF001
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token, "csr_pem": csr, "hostname": "revoke-target.box"},
    )
    assert enroll_resp.status_code == 201
    runner_id = enroll_resp.json()["runner_id"]

    # 1. Revoke preview without confirm: true
    preview_call = await _call_manage_tool(
        admin_env,
        {
            "action": "revoke_remote_runner",
            "runner_id": runner_id,
        },
    )
    assert "result" in preview_call
    prev_data = yaml.safe_load(preview_call["result"]["content"][0]["text"])
    assert prev_data["status"] == "confirmation_required"
    assert prev_data["runner_id"] == runner_id

    # 2. Confirmed revocation with confirm: true
    confirm_call = await _call_manage_tool(
        admin_env,
        {
            "action": "revoke_remote_runner",
            "runner_id": runner_id,
            "confirm": True,
        },
    )
    assert "result" in confirm_call
    rev_data = yaml.safe_load(confirm_call["result"]["content"][0]["text"])
    assert rev_data["status"] == "revoked"
    assert rev_data["id"] == str(runner_id)

    # 3. List runners and verify status is 'revoked'
    list_call = await _call_manage_tool(
        admin_env,
        {
            "action": "list_remote_runners",
            "pool_slug": "mcp-revoke-pool",
        },
    )
    runners = yaml.safe_load(list_call["result"]["content"][0]["text"])
    match = [r for r in runners if r["id"] == runner_id]
    assert len(match) == 1
    assert match[0]["status"] == "revoked"


@pytest.mark.asyncio
async def test_mcp_agent_key_rejected_on_admin_surface(admin_env: AdminTestEnv) -> None:
    """Verify kb_agt_* key is rejected on /mcp/admin with SURFACE_KEY_MISMATCH."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    mcp_app_auth = create_mcp_app(settings, kanban_app=admin_env.fastapi_app)

    mw = McpAuthMiddleware(
        mcp_app_auth,
        surface=Surface.ADMIN,
        internal_client=admin_env.internal_client,
        settings=settings,
    )
    transport = httpx.ASGITransport(app=mw)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        agent_key = "kb_agt_" + "9" * 32
        resp = await client.post(
            "/mcp/admin",
            headers={"Authorization": f"Bearer {agent_key}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "manage_ai_and_agent_runners",
                    "arguments": {"action": "list_remote_runners"},
                },
            },
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "SURFACE_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_mcp_ai_provider_and_budget_actions(admin_env: AdminTestEnv) -> None:
    """Verify actions 1-5 (upsert, list, disable provider, set/get budget)."""
    # 1. Upsert (create) provider
    upsert_call = await _call_manage_tool(
        admin_env,
        {
            "action": "upsert_provider",
            "provider_kind": "ollama",
            "display_name": "Full Tool 9 Ollama",
            "base_url": "http://127.0.0.1:11434",
            "model_allowlist": ["llama3:8b", "mistral:7b"],
            "residency_tier": "default",
            "priority": 10,
            "lod": "full",
        },
    )
    assert "result" in upsert_call
    created_data = yaml.safe_load(upsert_call["result"]["content"][0]["text"])
    config_id = created_data["id"]
    assert config_id is not None
    assert created_data["display_name"] == "Full Tool 9 Ollama"

    # 2. List providers with LOD tiers
    list_std = await _call_manage_tool(admin_env, {"action": "list_providers", "lod": "standard"})
    assert "result" in list_std
    std_data = yaml.safe_load(list_std["result"]["content"][0]["text"])
    assert any(p["id"] == config_id for p in std_data)

    list_sum = await _call_manage_tool(admin_env, {"action": "list_providers", "lod": "summary"})
    assert "result" in list_sum

    # 3. Update provider
    update_call = await _call_manage_tool(
        admin_env,
        {
            "action": "upsert_provider",
            "id": config_id,
            "display_name": "Full Tool 9 Ollama Updated",
            "lod": "summary",
        },
    )
    assert "result" in update_call
    updated_data = yaml.safe_load(update_call["result"]["content"][0]["text"])
    assert updated_data["display_name"] == "Full Tool 9 Ollama Updated"

    # 4. Set budget
    budget_call = await _call_manage_tool(
        admin_env,
        {
            "action": "set_budget",
            "provider_config_id": config_id,
            "period_kind": "daily",
            "token_cap": 100000,
        },
    )
    assert "result" in budget_call
    budget_data = yaml.safe_load(budget_call["result"]["content"][0]["text"])
    assert budget_data["token_cap"] == 100000

    # 5. Get budget usage
    usage_call = await _call_manage_tool(
        admin_env,
        {
            "action": "get_budget_usage",
            "provider_config_id": config_id,
        },
    )
    assert "result" in usage_call

    # 6. Disable provider
    disable_call = await _call_manage_tool(
        admin_env,
        {
            "action": "disable_provider",
            "id": config_id,
        },
    )
    assert "result" in disable_call
    dis_data = yaml.safe_load(disable_call["result"]["content"][0]["text"])
    assert dis_data.get("is_enabled") is False

    # 7. Validation errors
    bad_action = await _call_manage_tool(admin_env, {"action": "unhandled_unknown_action"})
    assert "error" in bad_action or bad_action.get("result", {}).get("isError") is True
