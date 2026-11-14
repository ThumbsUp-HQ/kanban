# Copyright 2026 Kanban Platform Contributors
"""Shared MCP error codes and structured error representation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

from mcp.yaml_out import dump_yaml

__all__ = [
    "KbMcpError",
    "McpErrorCode",
]


class McpErrorCode(StrEnum):
    """Canonical error codes shared across all Kanban MCP surfaces."""

    UNAUTHENTICATED = "UNAUTHENTICATED"
    SURFACE_KEY_MISMATCH = "SURFACE_KEY_MISMATCH"
    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_IDENTIFIER = "AMBIGUOUS_IDENTIFIER"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT_ETAG = "CONFLICT_ETAG"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    INTERNAL = "INTERNAL"
    MODULES_DISABLED = "MODULES_DISABLED"
    EPHEMERAL_TOOL_FORBIDDEN = "EPHEMERAL_TOOL_FORBIDDEN"
    EPHEMERAL_CALL_BUDGET_EXCEEDED = "EPHEMERAL_CALL_BUDGET_EXCEEDED"
    TOKEN_EXPIRED_OR_REVOKED = "TOKEN_EXPIRED_OR_REVOKED"  # noqa: S105


class KbMcpError(Exception):
    """Structured MCP application error serializable to canonical YAML."""

    def __init__(  # noqa: PLR0913
        self,
        code: McpErrorCode | str,
        message: str,
        *,
        hint: str | None = None,
        candidates: list[dict[str, str]] | None = None,
        allowed_tools: list[str] | None = None,
        budget: dict[str, int] | None = None,
    ) -> None:
        """Initialize KbMcpError with code, message, optional hint, candidates, budget."""
        enum_code = McpErrorCode(code)
        super().__init__(f"[{enum_code.value}] {message}")
        self.code: Final[McpErrorCode] = enum_code
        self.message: Final[str] = message
        self.hint: Final[str | None] = hint
        self.candidates: Final[list[dict[str, str]] | None] = candidates
        self.allowed_tools: Final[list[str] | None] = allowed_tools
        self.budget: Final[dict[str, int] | None] = budget

    def to_yaml(self) -> str:
        """Serialize error payload containing code, message, optional hint and extra details."""
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.allowed_tools is not None:
            payload["allowed_tools"] = self.allowed_tools
        if self.budget is not None:
            payload["budget"] = self.budget
        if self.hint:
            payload["hint"] = self.hint
        if self.candidates:
            payload["candidates"] = self.candidates
        return dump_yaml({"error": payload}, strip_nulls=True)
