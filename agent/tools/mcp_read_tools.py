# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Ephemeral MCP read toolkit for transition interceptors (S14.2, S14.3)."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Final

from agent.tools.repo_path_guard import RepoToolPolicyError
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from agent.context.transition_context import McpAccess

__all__ = [
    "ALLOWED_MCP_READ_TOOLS",
    "CODE_MCP_CALL_CAP_EXCEEDED",
    "CODE_TOOL_NOT_PERMITTED",
    "MAX_MCP_CALLS",
    "EphemeralMcpReadToolkit",
]

CODE_TOOL_NOT_PERMITTED: Final[str] = "TOOL_NOT_PERMITTED"
CODE_MCP_CALL_CAP_EXCEEDED: Final[str] = "MCP_CALL_CAP_EXCEEDED"

ALLOWED_MCP_READ_TOOLS: Final[frozenset[str]] = frozenset(
    {"search_tickets", "read_ticket", "search_knowledge", "read_doc"}
)
MAX_MCP_CALLS: Final[int] = 25


def _scrub_object(obj: object) -> object:
    """Recursively scrub secrets from strings in structured JSON objects."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        return {k: _scrub_object(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_object(v) for v in obj]
    return obj


class EphemeralMcpReadToolkit:
    """Bounded, read-only Model Context Protocol client for transition gates."""

    def __init__(
        self,
        mcp_access: McpAccess | None,
        ephemeral_token: bytearray | bytes | str | None,
        allowed_tools: Sequence[str] | set[str] | frozenset[str] | None = None,
        *,
        transport: (Callable[[str, str, dict[str, object]], object] | None) = None,
        http_client: object = None,
    ) -> None:
        """Initialize ephemeral MCP read toolkit."""
        self.mcp_access = mcp_access
        self.ephemeral_token = ephemeral_token
        self.allowed_tools = frozenset(allowed_tools or ()) & ALLOWED_MCP_READ_TOOLS
        self._transport = transport
        self._http_client = http_client
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Return total number of MCP read tool calls made."""
        return self._call_count

    def reset_call_count(self) -> None:
        """Reset internal tool call counter."""
        self._call_count = 0

    def set_faked_transport(
        self,
        transport: Callable[[str, str, dict[str, object]], Awaitable[dict[str, object] | str]],
    ) -> None:
        """Configure mock transport for offline test isolation."""
        self._transport = transport

    async def execute_tool(self, tool_name: str, args: dict[str, object]) -> object:
        """Execute tool call with strict permission and call-limit enforcement."""
        if tool_name not in self.allowed_tools:
            msg = f"Tool '{tool_name}' is not permitted or is not declared in allowed tools"
            raise RepoToolPolicyError(CODE_TOOL_NOT_PERMITTED, msg)

        if self._call_count >= MAX_MCP_CALLS:
            msg = f"Client-side MCP call limit ({MAX_MCP_CALLS} calls) exceeded"
            raise RepoToolPolicyError(CODE_MCP_CALL_CAP_EXCEEDED, msg)

        self._call_count += 1

        if tool_name == "search_tickets":
            return await self.search_tickets(**args)  # type: ignore[arg-type]
        if tool_name == "read_ticket":
            return await self.read_ticket(**args)  # type: ignore[arg-type]
        if tool_name == "search_knowledge":
            return await self.search_knowledge(**args)  # type: ignore[arg-type]
        if tool_name == "read_doc":
            return await self.read_doc(**args)  # type: ignore[arg-type]

        msg = f"Tool '{tool_name}' is not implemented"
        raise RepoToolPolicyError(CODE_TOOL_NOT_PERMITTED, msg)

    def _get_bearer_header(self) -> str:
        """Extract token as string header value without persisting."""
        if isinstance(self.ephemeral_token, (bytearray, bytes)):
            token_str = self.ephemeral_token.decode("utf-8", errors="replace")
        elif isinstance(self.ephemeral_token, str):
            token_str = self.ephemeral_token
        else:
            token_str = ""
        return f"Bearer {token_str}"

    async def _call_mcp(self, url: str, tool_name: str, args: dict[str, object]) -> object:
        """Dispatch MCP tool call via custom transport or HTTP client."""
        if self._transport is not None:
            raw_res = self._transport(url, tool_name, args)
            res = await raw_res if inspect.isawaitable(raw_res) else raw_res
            return _scrub_object(res)

        if self._http_client is not None:
            # Mock or provided HTTP client
            post_method = getattr(self._http_client, "post", None)
            if callable(post_method):
                payload = {
                    "jsonrpc": "2.0",
                    "id": self._call_count,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": args},
                }
                headers = {
                    "Authorization": self._get_bearer_header(),
                    "Content-Type": "application/json",
                }
                resp = await post_method(url, json=payload, headers=headers)
                if hasattr(resp, "json"):
                    return _scrub_object(resp.json())
                if hasattr(resp, "text"):
                    return scrub_text(str(resp.text))
                return _scrub_object(resp)

        # Default fallback response for offline simulated contexts
        default_res = {
            "tool": tool_name,
            "status": "ok",
            "args": args,
            "result": f"Simulated output for {tool_name}",
        }
        return _scrub_object(default_res)

    async def search_tickets(self, query: str, limit: int = 10) -> object:
        """Search issues via /mcp/agent."""
        agent_url = (
            self.mcp_access.agent_url if self.mcp_access else "https://kanban.internal/mcp/agent"
        )
        return await self._call_mcp(
            agent_url,
            "search_tickets",
            {"query": query, "limit": limit},
        )

    async def read_ticket(self, identifier: str) -> object:
        """Read issue details via /mcp/agent."""
        agent_url = (
            self.mcp_access.agent_url if self.mcp_access else "https://kanban.internal/mcp/agent"
        )
        return await self._call_mcp(
            agent_url,
            "read_ticket",
            {"identifier": identifier},
        )

    async def search_knowledge(self, query: str, limit: int = 10) -> object:
        """Search knowledge base docs via /mcp/docs."""
        docs_url = (
            self.mcp_access.docs_url if self.mcp_access else "https://kanban.internal/mcp/docs"
        )
        return await self._call_mcp(
            docs_url,
            "search_knowledge",
            {"query": query, "limit": limit},
        )

    async def read_doc(self, slug: str) -> object:
        """Read document contents via /mcp/docs."""
        docs_url = (
            self.mcp_access.docs_url if self.mcp_access else "https://kanban.internal/mcp/docs"
        )
        return await self._call_mcp(
            docs_url,
            "read_doc",
            {"slug": slug},
        )
