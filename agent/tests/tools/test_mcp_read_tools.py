# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, ARG001, ARG002, ANN401, SLF001, E501
"""Feature unit tests for EphemeralMcpReadToolkit (KB-P5-20)."""

from __future__ import annotations

from typing import Any

import pytest

from agent.context.transition_context import McpAccess
from agent.tools.mcp_read_tools import (
    ALLOWED_MCP_READ_TOOLS,
    MAX_MCP_CALLS,
    EphemeralMcpReadToolkit,
)
from agent.tools.repo_path_guard import RepoToolPolicyError


async def test_mcp_read_tools_allowed_execution() -> None:
    """Declared read tools dispatch cleanly through faked transport."""
    mcp_access = McpAccess(
        agent_url="https://kanban.internal/mcp/agent",
        docs_url="https://kanban.internal/mcp/docs",
    )
    token = bytearray(b"kb_agt_eph_sampletoken123456789")

    dispatched_calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_transport(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        dispatched_calls.append((url, tool, args))
        return {"result": f"mocked_{tool}", "echo_args": args}

    toolkit = EphemeralMcpReadToolkit(
        mcp_access=mcp_access,
        ephemeral_token=token,
        allowed_tools=["search_tickets", "read_ticket", "search_knowledge", "read_doc"],
        transport=fake_transport,
    )

    t1 = await toolkit.execute_tool("read_ticket", {"identifier": "KAN-100"})
    assert isinstance(t1, dict)
    assert t1["result"] == "mocked_read_ticket"
    assert len(dispatched_calls) == 1
    assert dispatched_calls[0][1] == "read_ticket"

    t2 = await toolkit.execute_tool("search_tickets", {"query": "auth", "limit": 5})
    assert isinstance(t2, dict)
    assert t2["result"] == "mocked_search_tickets"

    t3 = await toolkit.execute_tool("search_knowledge", {"query": "security", "limit": 2})
    assert isinstance(t3, dict)
    assert t3["result"] == "mocked_search_knowledge"

    t4 = await toolkit.execute_tool("read_doc", {"slug": "security-arch"})
    assert isinstance(t4, dict)
    assert t4["result"] == "mocked_read_doc"

    assert toolkit.call_count == 4


async def test_mcp_read_tools_write_and_undeclared_forbidden() -> None:
    """Test Case 5: Write tools or undeclared tools rejected with TOOL_NOT_PERMITTED and 0 calls."""
    http_call_count = 0

    async def track_transport(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal http_call_count
        http_call_count += 1
        return {}

    toolkit = EphemeralMcpReadToolkit(
        mcp_access=None,
        ephemeral_token="token",
        allowed_tools=["read_ticket"],  # Only read_ticket declared
        transport=track_transport,
    )

    # Write tools
    write_tools = ["update_ticket", "complete_work", "transition_ticket", "add_comment"]
    for w in write_tools:
        with pytest.raises(RepoToolPolicyError) as exc_info:
            await toolkit.execute_tool(w, {"identifier": "KAN-100"})
        assert exc_info.value.code == "TOOL_NOT_PERMITTED"

    # Undeclared read tool
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.execute_tool("read_doc", {"slug": "arch"})
    assert exc_info.value.code == "TOOL_NOT_PERMITTED"

    # Invariant: 0 HTTP calls dispatched
    assert http_call_count == 0


async def test_mcp_read_tools_call_limit_exceeded() -> None:
    """Test Case 6: 26th MCP read call blocked locally with MCP_CALL_CAP_EXCEEDED."""

    async def noop_transport(_url: str, _tool: str, _args: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}

    toolkit = EphemeralMcpReadToolkit(
        mcp_access=None,
        ephemeral_token="token",
        allowed_tools=ALLOWED_MCP_READ_TOOLS,
        transport=noop_transport,
    )

    # Execute exactly 25 calls successfully
    for _ in range(MAX_MCP_CALLS):
        res = await toolkit.execute_tool("read_ticket", {"identifier": "KAN-1"})
        assert isinstance(res, dict)
        assert res["status"] == "ok"

    assert toolkit.call_count == 25

    # 26th call must fail locally
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.execute_tool("read_ticket", {"identifier": "KAN-1"})
    assert exc_info.value.code == "MCP_CALL_CAP_EXCEEDED"


async def test_mcp_read_tools_secret_scrubbing() -> None:
    """Sensitive tokens returned from MCP tools are redacted before reaching agent."""

    async def leaky_transport(_url: str, _tool: str, _args: dict[str, Any]) -> dict[str, Any]:
        return {
            "ticket": "KAN-100",
            "body": "Private token: ghp_111122223333444455556666777788889999 and sk-proj-1234567890abcdef1234567890",
        }

    toolkit = EphemeralMcpReadToolkit(
        mcp_access=None,
        ephemeral_token="token",
        allowed_tools=["read_ticket"],
        transport=leaky_transport,
    )

    res = await toolkit.execute_tool("read_ticket", {"identifier": "KAN-100"})
    assert isinstance(res, dict)
    body_text = str(res["body"])
    assert "ghp_111122223333444455556666777788889999" not in body_text
    assert "sk-proj-1234567890abcdef1234567890" not in body_text
    assert "[REDACTED_GITHUB_TOKEN]" in body_text or "REDACTED" in body_text


async def test_mcp_read_tools_http_client_and_bearer_types() -> None:
    """HTTP client dispatch and diverse token representations."""

    class MockResponse:
        def __init__(self, data: Any) -> None:
            self._data = data

        def json(self) -> Any:
            return self._data

    class MockHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, Any]] = []

        async def post(
            self, url: str, json: dict[str, Any], headers: dict[str, str]
        ) -> MockResponse:
            self.requests.append({"url": url, "json": json, "headers": headers})
            return MockResponse({"status": "ok", "items": ["ticket1", "ticket2", 123]})

    client = MockHttpClient()
    toolkit = EphemeralMcpReadToolkit(
        mcp_access=McpAccess(agent_url="https://kanban/mcp", docs_url="https://kanban/docs"),
        ephemeral_token=b"byte_token_123",
        allowed_tools=["search_tickets", "read_ticket"],
        http_client=client,
    )

    assert toolkit.call_count == 0
    res = await toolkit.search_tickets(query="bug")
    assert isinstance(res, dict)
    assert res["status"] == "ok"
    assert res["items"] == ["ticket1", "ticket2", 123]
    assert len(client.requests) == 1
    assert client.requests[0]["headers"]["Authorization"] == "Bearer byte_token_123"

    toolkit.reset_call_count()
    assert toolkit.call_count == 0

    # Test string token and None token
    tk_str = EphemeralMcpReadToolkit(
        mcp_access=None, ephemeral_token="str_token", allowed_tools=["read_ticket"]
    )
    assert tk_str._get_bearer_header() == "Bearer str_token"

    tk_none = EphemeralMcpReadToolkit(
        mcp_access=None, ephemeral_token=None, allowed_tools=["read_ticket"]
    )
    assert tk_none._get_bearer_header() == "Bearer "

    # Test default fallback response when no transport or http_client
    tk_default = EphemeralMcpReadToolkit(
        mcp_access=None, ephemeral_token="tok", allowed_tools=["read_doc"]
    )
    doc_res = await tk_default.read_doc(slug="my-doc")
    assert isinstance(doc_res, dict)
    assert doc_res["tool"] == "read_doc"
    assert doc_res["status"] == "ok"

    # Test HTTP client returning text response and bytearray token
    class MockTextResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    class MockTextHttpClient:
        async def post(
            self, url: str, json: dict[str, Any], headers: dict[str, str]
        ) -> MockTextResponse:
            return MockTextResponse("Response plain text")

    tk_txt = EphemeralMcpReadToolkit(
        mcp_access=None,
        ephemeral_token=bytearray(b"bytearray_token"),
        allowed_tools=["read_ticket"],
        http_client=MockTextHttpClient(),
    )
    res_txt = await tk_txt.read_ticket(identifier="KAN-1")
    assert res_txt == "Response plain text"


async def test_mcp_read_tools_unimplemented_tool() -> None:
    """Internal unimplemented tool raises TOOL_NOT_PERMITTED."""
    toolkit = EphemeralMcpReadToolkit(mcp_access=None, ephemeral_token="tok")
    # Bypass allowed_tools check to hit the safeguard branch
    toolkit.allowed_tools = frozenset({"unimplemented_tool"})
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.execute_tool("unimplemented_tool", {})
    assert exc_info.value.code == "TOOL_NOT_PERMITTED"
