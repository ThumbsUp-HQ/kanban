# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLC0415, PT011, I001, PLR0915
"""Feature unit tests for /mcp/agent tool: link_objects (KB-P4-07)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from mcp.errors import McpErrorCode
from mcp.surfaces.agent.link_objects import _validate_link_objects_arguments

if TYPE_CHECKING:
    from mcp.tests.agent.conftest import AgentTestEnv

pytestmark = pytest.mark.committed_db


async def _call_link_objects(
    env: AgentTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke link_objects via JSON-RPC 2.0 tools/call."""
    active_session_id = session_id
    if active_session_id is None:
        init_resp = await env.mcp_client.post(
            "/mcp/agent",
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-agent", "version": "1.0"},
                },
            },
            headers={"X-KB-Subject-Token": subject_token} if subject_token else {},
        )
        assert init_resp.status_code == 200
        active_session_id = init_resp.headers["mcp-session-id"]

    headers: dict[str, str] = {"mcp-session-id": active_session_id}
    if subject_token is not None:
        headers["X-KB-Subject-Token"] = subject_token

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "link_objects",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/agent", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data["result"])


@pytest.mark.asyncio
async def test_case_1_positive_link_and_remove(agent_test_env: AgentTestEnv) -> None:
    """Case 1: Positive link KAN-142 BLOCKS KAN-150, then remove the link."""
    env = agent_test_env

    # 1. Create link
    res_link = await _call_link_objects(
        env,
        {
            "source": "KAN-142",
            "target": "KAN-150",
            "link_type": "blocks",
            "action": "add",
        },
        subject_token=env.token_adam,
    )
    assert res_link["isError"] is False
    parsed_link = yaml.safe_load(res_link["content"][0]["text"])
    assert parsed_link["status"] == "linked"
    link_info = parsed_link["link"]
    assert link_info["source"] == "KAN-142"
    assert link_info["target"] == "KAN-150"
    assert link_info["link_type"] == "blocks"

    # 2. Remove link
    res_remove = await _call_link_objects(
        env,
        {
            "source": "KAN-142",
            "target": "KAN-150",
            "link_type": "blocks",
            "action": "remove",
        },
        subject_token=env.token_adam,
    )
    assert res_remove["isError"] is False
    parsed_remove = yaml.safe_load(res_remove["content"][0]["text"])
    assert parsed_remove["status"] == "unlinked"
    assert parsed_remove["link"]["source"] == "KAN-142"
    assert parsed_remove["link"]["target"] == "KAN-150"


@pytest.mark.asyncio
async def test_case_2_link_objects_help(agent_test_env: AgentTestEnv) -> None:
    """Case 2: link_objects(source='help') returns JIT help documentation."""
    env = agent_test_env

    res = await _call_link_objects(env, {"source": "help"})
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert "tool" in parsed or "help" in parsed or "commands" in parsed or "description" in parsed


def test_case_3_argument_validation() -> None:
    """Case 3: Unit validation of link arguments and boundaries."""
    # Source == help early exit
    _validate_link_objects_arguments({"source": "help"})
    _validate_link_objects_arguments({"action": "help"})

    # Unknown parameter
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "A", "target": "B", "link_type": "blocks", "bad": 1}
        )
    assert "Unknown parameter" in str(exc_info.value)

    # Missing source
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments({"target": "KAN-150", "link_type": "blocks"})
    assert "source is required" in str(exc_info.value)

    # Non-string source
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": 123, "target": "KAN-150", "link_type": "blocks"}
        )
    assert "non-empty string" in str(exc_info.value)

    # Empty source
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "  ", "target": "KAN-150", "link_type": "blocks"}
        )
    assert "non-empty string" in str(exc_info.value)

    # Long source (> 255 chars)
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "x" * 256, "target": "KAN-150", "link_type": "blocks"}
        )
    assert "exceeds maximum" in str(exc_info.value)

    # Missing target
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments({"source": "KAN-142", "link_type": "blocks"})
    assert "target is required" in str(exc_info.value)

    # Non-string target
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "KAN-142", "target": 123, "link_type": "blocks"}
        )
    assert "non-empty string" in str(exc_info.value)

    # Empty target
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "KAN-142", "target": " ", "link_type": "blocks"}
        )
    assert "non-empty string" in str(exc_info.value)

    # Long target (> 255 chars)
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "KAN-142", "target": "y" * 256, "link_type": "blocks"}
        )
    assert "exceeds maximum" in str(exc_info.value)

    # Missing link_type
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments({"source": "KAN-142", "target": "KAN-150"})
    assert "link_type is required" in str(exc_info.value)

    # Empty link_type
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "KAN-142", "target": "KAN-150", "link_type": "  "}
        )
    assert "Unsupported link_type" in str(exc_info.value)

    # Invalid link_type type
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "KAN-142", "target": "KAN-150", "link_type": 123}
        )
    assert "Unsupported link_type" in str(exc_info.value)

    # Invalid action type
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {
                "source": "KAN-142",
                "target": "KAN-150",
                "link_type": "blocks",
                "action": 123,
            }
        )
    assert "Unsupported action" in str(exc_info.value)

    # Self-link
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "KAN-142", "target": "KAN-142", "link_type": "relates_to"}
        )
    assert "Self-linking is not allowed" in str(exc_info.value)

    # Invalid link type
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {"source": "KAN-142", "target": "KAN-150", "link_type": "PARENT_OF"}
        )
    assert "Unsupported link_type: PARENT_OF" in str(exc_info.value)

    # Invalid action
    with pytest.raises(Exception) as exc_info:
        _validate_link_objects_arguments(
            {
                "source": "KAN-142",
                "target": "KAN-150",
                "link_type": "blocks",
                "action": "destroy",
            }
        )
    assert "Unsupported action: destroy" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_4_self_link_via_rpc(agent_test_env: AgentTestEnv) -> None:
    """Case 4: Self link rejected via RPC."""
    env = agent_test_env

    res = await _call_link_objects(
        env,
        {"source": "KAN-142", "target": "KAN-142", "link_type": "relates_to"},
        subject_token=env.token_adam,
    )
    assert res["isError"] is True
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["error"]["code"] == McpErrorCode.VALIDATION_FAILED.value


@pytest.mark.asyncio
async def test_case_5_invalid_link_type_via_rpc(agent_test_env: AgentTestEnv) -> None:
    """Case 5: PARENT_OF rejected as user-creatable link type."""
    env = agent_test_env

    res = await _call_link_objects(
        env,
        {"source": "KAN-142", "target": "KAN-150", "link_type": "PARENT_OF"},
        subject_token=env.token_adam,
    )
    assert res["isError"] is True
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["error"]["code"] == McpErrorCode.VALIDATION_FAILED.value


@pytest.mark.asyncio
async def test_case_6_nonexistent_object(agent_test_env: AgentTestEnv) -> None:
    """Case 6: link_objects with nonexistent target returns NOT_FOUND."""
    env = agent_test_env

    res = await _call_link_objects(
        env,
        {"source": "KAN-142", "target": "KAN-99999", "link_type": "blocks"},
        subject_token=env.token_adam,
    )
    assert res["isError"] is True
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["error"]["code"] == McpErrorCode.NOT_FOUND.value


@pytest.mark.asyncio
async def test_case_7_link_objects_remove_not_found_and_help(agent_test_env: AgentTestEnv) -> None:
    """Case 7: link_objects with action=help, remove non-existent link, and missing context."""
    from mcp.surfaces.agent.link_objects import link_objects

    env = agent_test_env

    # 1. Action == help
    res_help = await _call_link_objects(env, {"action": "help"})
    assert res_help["isError"] is False

    # 2. Remove non-existent link between KAN-142 and KAN-150
    res_rem = await _call_link_objects(
        env,
        {
            "source": "KAN-142",
            "target": "KAN-150",
            "link_type": "blocks",
            "action": "remove",
        },
        subject_token=env.token_adam,
    )
    assert res_rem["isError"] is True
    parsed_rem = yaml.safe_load(res_rem["content"][0]["text"])
    assert parsed_rem["error"]["code"] == McpErrorCode.NOT_FOUND.value

    # 3. Missing MCP context raises INTERNAL error
    with pytest.raises(Exception) as exc_ctx:
        await link_objects({"source": "KAN-142", "target": "KAN-150", "link_type": "blocks"})
    assert "MCP request context" in str(exc_ctx.value)

    # 4. Self-link after key resolution (different string identifiers resolving to same object)
    res_self_resolved = await _call_link_objects(
        env,
        {
            "source": "KAN-142",
            "target": str(env.issue_142_id),
            "link_type": "relates_to",
        },
        subject_token=env.token_adam,
    )
    assert res_self_resolved["isError"] is True
    parsed_self = yaml.safe_load(res_self_resolved["content"][0]["text"])
    assert parsed_self["error"]["code"] == McpErrorCode.VALIDATION_FAILED.value
    assert "cannot be linked to itself" in parsed_self["error"]["message"]

    # 5. Remove link via inbound direction
    # First create link KAN-150 BLOCKS KAN-142
    await _call_link_objects(
        env,
        {
            "source": "KAN-150",
            "target": "KAN-142",
            "link_type": "blocks",
            "action": "add",
        },
        subject_token=env.token_adam,
    )
    # Now remove from perspective of KAN-142 targeting KAN-150
    res_rem_inbound = await _call_link_objects(
        env,
        {
            "source": "KAN-142",
            "target": "KAN-150",
            "link_type": "blocks",
            "action": "remove",
        },
        subject_token=env.token_adam,
    )
    assert res_rem_inbound["isError"] is False
    parsed_inbound = yaml.safe_load(res_rem_inbound["content"][0]["text"])
    assert parsed_inbound["status"] == "unlinked"


@pytest.mark.asyncio
async def test_case_8_direct_handler_coverage(agent_test_env: AgentTestEnv) -> None:
    """Case 8: Direct handler branches: help, upstream error, non-dict target."""
    from unittest.mock import AsyncMock, MagicMock
    from mcp.context import McpRequestContext, reset_current_mcp_context, set_current_mcp_context
    from mcp.registry import Surface
    from mcp.surfaces.agent.link_objects import link_objects

    env = agent_test_env

    # 1. Direct call with source='help'
    req_ctx = McpRequestContext(
        surface=Surface.AGENT,
        client=env.internal_client,
        subject_token=env.token_adam,
        session_id="sess-1",
    )

    token = set_current_mcp_context(req_ctx)
    try:
        h = await link_objects({"source": "help"})
        assert "commands" in h or "help" in h or "tool" in h

        # 2. Action == "remove" with non-dict upstream response
        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=[
                {
                    "id": "s1",
                    "key": "KAN-142",
                    "kind": "issue",
                    "title": "Issue 142",
                },  # resolve source
                {
                    "id": "t1",
                    "key": "KAN-150",
                    "kind": "issue",
                    "title": "Issue 150",
                },  # resolve target
                "non-dict response",  # links get
            ]
        )
        set_current_mcp_context(
            McpRequestContext(
                surface=Surface.AGENT,
                client=mock_client,
                subject_token=env.token_adam,
                session_id="sess-1",
            )
        )
        with pytest.raises(Exception) as exc:
            await link_objects(
                {
                    "source": "KAN-142",
                    "target": "KAN-150",
                    "link_type": "blocks",
                    "action": "remove",
                }
            )
        assert "Failed to retrieve links" in str(exc.value)

        # 3. Action == "add" where res['target'] is not a dict
        mock_client.request = AsyncMock(
            side_effect=[
                {
                    "id": "s1",
                    "key": "KAN-142",
                    "kind": "issue",
                    "title": "Issue 142",
                },  # resolve source
                {
                    "id": "t1",
                    "key": "KAN-150",
                    "kind": "issue",
                    "title": "Issue 150",
                },  # resolve target
                {"status": "linked", "target": "string_target"},  # add
            ]
        )
        res = await link_objects(
            {
                "source": "KAN-142",
                "target": "KAN-150",
                "link_type": "blocks",
                "action": "add",
            }
        )
        assert res["status"] == "linked"
    finally:
        reset_current_mcp_context(token)
