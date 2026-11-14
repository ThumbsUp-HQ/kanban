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
    SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
    ALREADY_PROMOTED = "ALREADY_PROMOTED"
    LINK_TYPE_NOT_ALLOWED = "LINK_TYPE_NOT_ALLOWED"
    EPHEMERAL_TOOL_FORBIDDEN = "EPHEMERAL_TOOL_FORBIDDEN"
    EPHEMERAL_CALL_BUDGET_EXCEEDED = "EPHEMERAL_CALL_BUDGET_EXCEEDED"
    TOKEN_EXPIRED_OR_REVOKED = "TOKEN_EXPIRED_OR_REVOKED"  # noqa: S105
    KEY_SCOPE_VIOLATION = "KEY_SCOPE_VIOLATION"
    CONNECTION_SCOPE_VIOLATION = "CONNECTION_SCOPE_VIOLATION"
    CONFLICTING_SCOPE_HEADERS = "CONFLICTING_SCOPE_HEADERS"
    LOCKOUT_PREVENTED = "LOCKOUT_PREVENTED"
    CONFIRM_PHRASE_MISMATCH = "CONFIRM_PHRASE_MISMATCH"
    AAL2_REQUIRED = "AAL2_REQUIRED"
    INSUFFICIENT_PERMISSION = "INSUFFICIENT_PERMISSION"
    LINK_NOT_FLAGGED = "LINK_NOT_FLAGGED"
    CREATOR_NOT_ELIGIBLE = "CREATOR_NOT_ELIGIBLE"
    CREATOR_UNCHANGED = "CREATOR_UNCHANGED"
    NOT_ARCHIVED = "NOT_ARCHIVED"
    CONFIRMATION_TOKEN_INVALID_OR_EXPIRED = "CONFIRMATION_TOKEN_INVALID_OR_EXPIRED"  # noqa: S105
    TOKEN_CALLER_MISMATCH = "TOKEN_CALLER_MISMATCH"  # noqa: S105
    TOKEN_TARGET_MISMATCH = "TOKEN_TARGET_MISMATCH"  # noqa: S105
    BLAST_RADIUS_CHANGED = "BLAST_RADIUS_CHANGED"
    SOFT_TRASH_REQUIRED_FIRST = "SOFT_TRASH_REQUIRED_FIRST"
    SERVER_ADMIN_REQUIRED = "SERVER_ADMIN_REQUIRED"
    PLAN_STALE = "PLAN_STALE"
    STATE_IN_USE = "STATE_IN_USE"
    PRIORITY_IN_USE = "PRIORITY_IN_USE"
    INVALID_TRANSITION = "INVALID_TRANSITION"


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
        extra: dict[str, Any] | None = None,
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
        self.extra: Final[dict[str, Any] | None] = extra

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
        if self.extra:
            payload.update(self.extra)
        if self.hint:
            payload["hint"] = self.hint
        if self.candidates:
            payload["candidates"] = self.candidates
        if self.extra:
            payload.update(self.extra)
        return dump_yaml({"error": payload}, strip_nulls=True)
