# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Request context propagation for MCP tool handlers."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient
    from mcp.registry import Surface

__all__ = [
    "McpRequestContext",
    "get_current_mcp_context",
    "reset_current_mcp_context",
    "set_current_mcp_context",
]


@dataclass(frozen=True)
class McpRequestContext:
    """Invocation context passed or bound to MCP tool handlers."""

    surface: Surface
    client: KanbanApiClient | None = None
    subject_token: str | None = None
    session_id: str | None = None
    caller_scopes: frozenset[str] | None = None


_CURRENT_CONTEXT: Final[ContextVar[McpRequestContext | None]] = ContextVar(
    "current_mcp_context", default=None
)


def get_current_mcp_context() -> McpRequestContext | None:
    """Retrieve the active MCP request context for the current async task."""
    return _CURRENT_CONTEXT.get()


def set_current_mcp_context(context: McpRequestContext | None) -> Token[McpRequestContext | None]:
    """Set the active MCP request context for the current async task."""
    return _CURRENT_CONTEXT.set(context)


def reset_current_mcp_context(token: Token[McpRequestContext | None]) -> None:
    """Reset the active MCP request context using the token from set."""
    _CURRENT_CONTEXT.reset(token)
