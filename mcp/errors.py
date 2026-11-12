# Copyright 2026 Kanban Platform Contributors
"""Shared MCP error codes and structured error representation."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

import yaml

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


class KbMcpError(Exception):
    """Structured MCP application error serializable to canonical YAML."""

    def __init__(
        self,
        code: McpErrorCode | str,
        message: str,
        *,
        hint: str | None = None,
    ) -> None:
        """Initialize KbMcpError with code, human-readable message, and optional hint."""
        enum_code = McpErrorCode(code)
        super().__init__(f"[{enum_code.value}] {message}")
        self.code: Final[McpErrorCode] = enum_code
        self.message: Final[str] = message
        self.hint: Final[str | None] = hint

    def to_yaml(self) -> str:
        """Serialize error payload strictly containing code, message, and optional hint."""
        payload: dict[str, str] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.hint:
            payload["hint"] = self.hint
        return yaml.safe_dump({"error": payload}, sort_keys=False)
