# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: manage_ai_and_agent_runners (KB-P5-05b)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
import yaml
from sqlalchemy import text

from mcp.admin.tools.manage_ai_and_agent_runners import (
    create_manage_ai_and_agent_runners_tool,
    manage_ai_and_agent_runners,
)
from mcp.app import create_mcp_app
from mcp.auth import McpAuthMiddleware
from mcp.context import (
    McpRequestContext,
    reset_current_mcp_context,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_manage_ai_and_agent_runners(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke manage_ai_and_agent_runners via JSON-RPC 2.0 tools/call on /mcp/admin."""
    active_session_id = session_id
    if active_session_id is None:
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
            headers={"X-KB-Subject-Token": subject_token} if subject_token else {},
        )
        assert init_resp.status_code == 200
        active_session_id = init_resp.headers["mcp-session-id"]

    headers: dict[str, str] = {"mcp-session-id": active_session_id}
    if subject_token is not None:
        headers["X-KB-Subject-Token"] = subject_token
    if scopes is not None:
        headers["X-KB-Scopes"] = scopes
    if aal_level is not None:
        headers["X-KB-AAL-Level"] = str(aal_level)

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "manage_ai_and_agent_runners",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/admin", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data)


@pytest.mark.asyncio
async def test_case_2_positive_mcp_upsert_and_list(admin_env: AdminTestEnv) -> None:
    """Test Case 2: MCP upsert_provider then list_providers returns same id; YAML omits nulls."""
    # 1. Upsert (create) provider
    upsert_args = {
        "action": "upsert_provider",
        "provider_kind": "ollama",
        "display_name": "MCP Ollama Cluster",
        "base_url": "http://127.0.0.1:11434",
        "model_allowlist": ["llama3:8b", "mistral:7b"],
        "residency_tier": "default",
        "priority": 5,
        "lod": "standard",
    }
    res = await _call_manage_ai_and_agent_runners(
        admin_env,
        upsert_args,
        subject_token=admin_env.token_server_admin_full,
    )
    assert res.get("error") is None
    content = res["result"]["content"][0]["text"]
    parsed_created = yaml.safe_load(content)
    config_id = parsed_created["id"]
    assert config_id is not None
    assert parsed_created["provider_kind"] == "ollama"
    assert parsed_created["display_name"] == "MCP Ollama Cluster"

    # Verify YAML omits null fields (e.g. project_id is null, should be omitted)
    assert "null" not in content

    # 2. List providers
    list_res = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "list_providers", "lod": "summary"},
        subject_token=admin_env.token_server_admin_full,
    )
    assert list_res.get("error") is None
    list_content = list_res["result"]["content"][0]["text"]
    parsed_list = yaml.safe_load(list_content)
    assert isinstance(parsed_list, list)
    matching = [p for p in parsed_list if p["id"] == config_id]
    assert len(matching) == 1
    assert matching[0]["display_name"] == "MCP Ollama Cluster"
    assert "null" not in list_content

    # 3. Upsert (update) provider
    update_args = {
        "action": "upsert_provider",
        "id": config_id,
        "display_name": "MCP Ollama Cluster Updated",
        "lod": "summary",
    }
    update_res = await _call_manage_ai_and_agent_runners(
        admin_env,
        update_args,
        subject_token=admin_env.token_server_admin_full,
    )
    assert update_res.get("error") is None
    up_content = update_res["result"]["content"][0]["text"]
    parsed_up = yaml.safe_load(up_content)
    assert parsed_up["id"] == config_id
    assert parsed_up["display_name"] == "MCP Ollama Cluster Updated"


@pytest.mark.asyncio
async def test_case_3_mcp_security_secret_suppression(admin_env: AdminTestEnv) -> None:
    """Test Case 3: MCP YAML never contains the submitted API key string nor wrapped_ fields."""
    secret_key = "test-mcp-canary-secret-token-xyz-123"
    args = {
        "action": "upsert_provider",
        "provider_kind": "openai",
        "display_name": "MCP OpenAI",
        "model_allowlist": ["gpt-4o"],
        "api_key": secret_key,
        "lod": "full",
    }
    res = await _call_manage_ai_and_agent_runners(
        admin_env,
        args,
        subject_token=admin_env.token_server_admin_full,
    )
    assert res.get("error") is None
    text_out = res["result"]["content"][0]["text"]
    assert secret_key not in text_out
    assert "wrapped_" not in text_out
    assert "wrapped_api_key" not in text_out
    assert "wrapped_dek" not in text_out
    assert "api_key_nonce" not in text_out

    parsed = yaml.safe_load(text_out)
    assert parsed["api_key_set"] is True
    assert "api_key" not in parsed


@pytest.mark.asyncio
async def test_case_4_mcp_surface_binding_rejection(admin_env: AdminTestEnv) -> None:
    """Test Case 4: kb_agt_* key on /mcp/admin is rejected with 403 SURFACE_KEY_MISMATCH."""
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
                    "arguments": {"action": "list_providers"},
                },
            },
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "SURFACE_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_case_8_fault_action_not_available(admin_env: AdminTestEnv) -> None:
    """Test Case 8: Reserved actions return ACTION_NOT_AVAILABLE.

    mint_runner_enrollment_token, upsert/list_agent_definitions return ACTION_NOT_AVAILABLE.
    """
    # 1. mint_runner_enrollment_token
    res_mint = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "mint_runner_enrollment_token"},
        subject_token=admin_env.token_server_admin_full,
    )
    text_mint = res_mint["result"]["content"][0]["text"]
    parsed_mint = yaml.safe_load(text_mint)
    assert parsed_mint["error"] == "ACTION_NOT_AVAILABLE"
    assert "reserved" in parsed_mint["message"].lower()

    # 2. upsert_agent_definition
    res_up_agt = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "upsert_agent_definition"},
        subject_token=admin_env.token_server_admin_full,
    )
    payload_up_agt = yaml.safe_load(res_up_agt["result"]["content"][0]["text"])
    assert payload_up_agt["error"] == "ACTION_NOT_AVAILABLE"

    # 3. list_agent_definitions
    res_list_agt = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "list_agent_definitions"},
        subject_token=admin_env.token_server_admin_full,
    )
    payload_list_agt = yaml.safe_load(res_list_agt["result"]["content"][0]["text"])
    assert payload_list_agt["error"] == "ACTION_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_mcp_additional_actions_and_lod(admin_env: AdminTestEnv) -> None:
    """Verify disable_provider, set_budget, get_budget_usage, help, LOD tiers, and filtering."""
    # 1. Create provider
    create_args = {
        "action": "upsert_provider",
        "provider_kind": "ollama",
        "display_name": "Budgeted Ollama",
        "model_allowlist": ["llama3"],
        "lod": "full",
    }
    res_create = await _call_manage_ai_and_agent_runners(
        admin_env,
        create_args,
        subject_token=admin_env.token_server_admin_full,
    )
    cfg_id = yaml.safe_load(res_create["result"]["content"][0]["text"])["id"]

    # 1b. Update provider with new api_key
    up_args = {
        "action": "upsert_provider",
        "id": cfg_id,
        "display_name": "Budgeted Ollama Updated",
        "api_key": "test-mcp-update-test-key",
        "lod": "summary",
    }
    res_up = await _call_manage_ai_and_agent_runners(
        admin_env,
        up_args,
        subject_token=admin_env.token_server_admin_full,
    )
    parsed_up = yaml.safe_load(res_up["result"]["content"][0]["text"])
    assert parsed_up["api_key_set"] is True
    assert "test-mcp-update-test-key" not in res_up["result"]["content"][0]["text"]

    # 1c. List providers with is_enabled=True and lod="standard"
    res_list_std = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "list_providers", "is_enabled": True, "lod": "standard"},
        subject_token=admin_env.token_server_admin_full,
    )
    parsed_std_list = yaml.safe_load(res_list_std["result"]["content"][0]["text"])
    assert any(p["id"] == cfg_id for p in parsed_std_list)

    # 2. Set budget
    set_b_args = {
        "action": "set_budget",
        "provider_config_id": cfg_id,
        "period_kind": "daily",
        "token_cap": 100000,
        "lod": "summary",
    }
    res_budget = await _call_manage_ai_and_agent_runners(
        admin_env,
        set_b_args,
        subject_token=admin_env.token_server_admin_full,
    )
    parsed_b = yaml.safe_load(res_budget["result"]["content"][0]["text"])
    assert parsed_b["token_cap"] == 100000
    assert parsed_b["period_kind"] == "daily"

    # 3. Seed usage: set tokens_used=48
    await admin_env.seed_session.execute(
        text(
            "UPDATE ai_token_ledgers SET tokens_used = 48 "
            "WHERE provider_config_id = :id AND period_kind = 'daily'"
        ),
        {"id": uuid.UUID(cfg_id)},
    )
    await admin_env.seed_session.commit()

    # 4. Get budget usage in summary LOD (dense operational metrics)
    res_usage = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "get_budget_usage", "provider_config_id": cfg_id, "lod": "summary"},
        subject_token=admin_env.token_server_admin_full,
    )
    parsed_usage = yaml.safe_load(res_usage["result"]["content"][0]["text"])
    assert parsed_usage["token_cap"] == 100000
    assert parsed_usage["tokens_used"] == 48
    assert parsed_usage["tokens_reserved"] == 0

    # 5. Get budget usage in standard and full LOD
    res_usage_std = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "get_budget_usage", "provider_config_id": cfg_id, "lod": "standard"},
        subject_token=admin_env.token_server_admin_full,
    )
    parsed_std = yaml.safe_load(res_usage_std["result"]["content"][0]["text"])
    assert isinstance(parsed_std, list)
    assert parsed_std[0]["tokens_used"] == 48

    # 6. Disable provider
    res_disable = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "disable_provider", "id": cfg_id, "lod": "summary"},
        subject_token=admin_env.token_server_admin_full,
    )
    parsed_dis = yaml.safe_load(res_disable["result"]["content"][0]["text"])
    assert parsed_dis["id"] == cfg_id
    assert parsed_dis["is_enabled"] is False

    # 7. List providers filtered by is_enabled=True vs is_enabled=False
    res_enabled_false = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "list_providers", "is_enabled": False, "lod": "summary"},
        subject_token=admin_env.token_server_admin_full,
    )
    parsed_dis_list = yaml.safe_load(res_enabled_false["result"]["content"][0]["text"])
    assert any(p["id"] == cfg_id for p in parsed_dis_list)

    # 8. Help action
    res_help = await _call_manage_ai_and_agent_runners(
        admin_env,
        {"action": "help"},
        subject_token=admin_env.token_server_admin_full,
    )
    assert "manage_ai_and_agent_runners" in res_help["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_validation_and_error_branches(admin_env: AdminTestEnv) -> None:
    """Test validation errors, invalid parameters, missing requirements, and scope limits."""
    # 1. Unknown parameter
    with pytest.raises(KbMcpError) as exc_info:
        await manage_ai_and_agent_runners({"action": "list_providers", "unknown_param": 123})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    # 2. Invalid action
    with pytest.raises(KbMcpError) as exc_act:
        await manage_ai_and_agent_runners({"action": "invalid_action"})
    assert exc_act.value.code == McpErrorCode.VALIDATION_FAILED

    # 3. Missing client
    with pytest.raises(KbMcpError) as exc_client:
        await manage_ai_and_agent_runners({"action": "list_providers"})
    assert exc_client.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # 4. Missing required args for actions
    ctx = McpRequestContext(
        client=admin_env.internal_client,
        surface=Surface.ADMIN,
        subject_token=admin_env.token_server_admin_full,
        caller_scopes=frozenset({"admin:read", "admin:write"}),
    )
    token = set_current_mcp_context(ctx)
    try:
        # Create without provider_kind
        with pytest.raises(KbMcpError) as exc_pk:
            await manage_ai_and_agent_runners({"action": "upsert_provider", "display_name": "Test"})
        assert exc_pk.value.code == McpErrorCode.VALIDATION_FAILED

        # Create without display_name
        with pytest.raises(KbMcpError) as exc_dn:
            await manage_ai_and_agent_runners(
                {"action": "upsert_provider", "provider_kind": "ollama"}
            )
        assert exc_dn.value.code == McpErrorCode.VALIDATION_FAILED

        # Disable without id
        with pytest.raises(KbMcpError) as exc_dis:
            await manage_ai_and_agent_runners({"action": "disable_provider"})
        assert exc_dis.value.code == McpErrorCode.VALIDATION_FAILED

        # set_budget without required args
        with pytest.raises(KbMcpError) as exc_sb:
            await manage_ai_and_agent_runners({"action": "set_budget", "provider_config_id": "bad"})
        assert exc_sb.value.code == McpErrorCode.VALIDATION_FAILED

        # get_budget_usage without provider_config_id
        with pytest.raises(KbMcpError) as exc_gbu:
            await manage_ai_and_agent_runners({"action": "get_budget_usage"})
        assert exc_gbu.value.code == McpErrorCode.VALIDATION_FAILED

        # Scope violation: read-only token attempting write action
        ctx_read = McpRequestContext(
            client=admin_env.internal_client,
            surface=Surface.ADMIN,
            subject_token=admin_env.token_server_admin_read,
            caller_scopes=frozenset({"admin:read"}),
        )
        reset_current_mcp_context(token)
        token = set_current_mcp_context(ctx_read)

        with pytest.raises(KbMcpError) as exc_scope:
            await manage_ai_and_agent_runners(
                {
                    "action": "upsert_provider",
                    "provider_kind": "ollama",
                    "display_name": "Scope Test",
                }
            )
        assert exc_scope.value.code == McpErrorCode.INSUFFICIENT_SCOPE

        # Scope violation: no admin scopes attempting read action
        ctx_no_scope = McpRequestContext(
            client=admin_env.internal_client,
            surface=Surface.ADMIN,
            subject_token=admin_env.token_server_admin_read,
            caller_scopes=frozenset({"user:read"}),
        )
        reset_current_mcp_context(token)
        token = set_current_mcp_context(ctx_no_scope)
        with pytest.raises(KbMcpError) as exc_no_scope:
            await manage_ai_and_agent_runners({"action": "list_providers"})
        assert exc_no_scope.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    finally:
        reset_current_mcp_context(token)

    # 5. create_manage_ai_and_agent_runners_tool spec
    spec = create_manage_ai_and_agent_runners_tool()
    assert spec.name == "manage_ai_and_agent_runners"
    assert spec.surface == Surface.ADMIN


@pytest.mark.asyncio
async def test_mcp_upstream_error_branches(admin_env: AdminTestEnv) -> None:
    """Test unexpected upstream response formats from API client."""

    class MockBadClient:
        async def request(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            return "unexpected string payload"

    ctx = McpRequestContext(
        client=MockBadClient(),  # type: ignore[arg-type]
        surface=Surface.ADMIN,
        subject_token=admin_env.token_server_admin_full,
        caller_scopes=frozenset({"admin:read", "admin:write"}),
    )
    token = set_current_mcp_context(ctx)
    try:
        # 1. list_providers upstream error
        with pytest.raises(KbMcpError) as e1:
            await manage_ai_and_agent_runners(
                {"action": "list_providers", "project_id": str(uuid.uuid4())}
            )
        assert e1.value.code == McpErrorCode.UPSTREAM_ERROR

        # 2. upsert_provider create upstream error
        with pytest.raises(KbMcpError) as e2:
            await manage_ai_and_agent_runners(
                {"action": "upsert_provider", "provider_kind": "ollama", "display_name": "Bad"}
            )
        assert e2.value.code == McpErrorCode.UPSTREAM_ERROR

        # 3. upsert_provider update upstream error
        with pytest.raises(KbMcpError) as e3:
            await manage_ai_and_agent_runners(
                {"action": "upsert_provider", "id": str(uuid.uuid4()), "api_key": "test-key-123"}
            )
        assert e3.value.code == McpErrorCode.UPSTREAM_ERROR

        # 4. disable_provider upstream error
        with pytest.raises(KbMcpError) as e4:
            await manage_ai_and_agent_runners(
                {"action": "disable_provider", "id": str(uuid.uuid4())}
            )
        assert e4.value.code == McpErrorCode.UPSTREAM_ERROR

        # 5. set_budget upstream error
        with pytest.raises(KbMcpError) as e5:
            await manage_ai_and_agent_runners(
                {
                    "action": "set_budget",
                    "provider_config_id": str(uuid.uuid4()),
                    "period_kind": "daily",
                    "token_cap": 100,
                    "project_id": str(uuid.uuid4()),
                }
            )
        assert e5.value.code == McpErrorCode.UPSTREAM_ERROR

        # 6. get_budget_usage upstream error
        with pytest.raises(KbMcpError) as e6:
            await manage_ai_and_agent_runners(
                {"action": "get_budget_usage", "provider_config_id": str(uuid.uuid4())}
            )
        assert e6.value.code == McpErrorCode.UPSTREAM_ERROR
    finally:
        reset_current_mcp_context(token)
