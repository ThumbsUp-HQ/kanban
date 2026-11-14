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
    NO_STARTED_STATE = "NO_STARTED_STATE"
    USE_COMPLETE_WORK = "USE_COMPLETE_WORK"
    OPEN_CHILD_BLOCKERS = "OPEN_CHILD_BLOCKERS"
    QA_VERDICT_NOT_READY = "QA_VERDICT_NOT_READY"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    TRANSITION_HELD = "TRANSITION_HELD"


class KbMcpError(Exception):
    """Structured MCP application error serializable to canonical YAML."""

    def __init__(
        self,
        code: McpErrorCode | str,
        message: str,
        *,
        hint: str | None = None,
        candidates: list[dict[str, str]] | None = None,
        blockers: list[str] | None = None,
    ) -> None:
        """Initialize KbMcpError with code, message, optional hint, candidates, blockers."""
        enum_code = McpErrorCode(code)
        super().__init__(f"[{enum_code.value}] {message}")
        self.code: Final[McpErrorCode] = enum_code
        self.message: Final[str] = message
        self.hint: Final[str | None] = hint
        self.candidates: Final[list[dict[str, str]] | None] = candidates
        self.blockers: Final[list[str] | None] = blockers

    def to_yaml(self) -> str:
        """Serialize error payload containing code, message, optional hint, candidates, blockers."""
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.hint:
            payload["hint"] = self.hint
        if self.candidates:
            payload["candidates"] = self.candidates
        if self.blockers:
            payload["blockers"] = self.blockers
        return dump_yaml({"error": payload}, strip_nulls=True)
