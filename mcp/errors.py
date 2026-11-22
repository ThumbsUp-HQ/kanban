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
    CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED = "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"
    MENTION_ACCESS_WARNING = "MENTION_ACCESS_WARNING"
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
    GROUP_CYCLE_REJECTED = "GROUP_CYCLE_REJECTED"
    GROUP_DEPTH_EXCEEDED = "GROUP_DEPTH_EXCEEDED"
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
    NO_STARTED_STATE = "NO_STARTED_STATE"
    USE_COMPLETE_WORK = "USE_COMPLETE_WORK"
    OPEN_CHILD_BLOCKERS = "OPEN_CHILD_BLOCKERS"
    QA_VERDICT_NOT_READY = "QA_VERDICT_NOT_READY"
    TRANSITION_HELD = "TRANSITION_HELD"
    TRANSITION_PENDING = "TRANSITION_PENDING"
    ACTION_NOT_AVAILABLE = "ACTION_NOT_AVAILABLE"
    PATCH_TARGET_NOT_FOUND = "PATCH_TARGET_NOT_FOUND"
    PATCH_TARGET_AMBIGUOUS = "PATCH_TARGET_AMBIGUOUS"
    SECRET_DETECTED_IN_PAYLOAD = "SECRET_DETECTED_IN_PAYLOAD"  # noqa: S105
    SECRET_DETECTED_PUSH_PROTECTION = "SECRET_DETECTED_PUSH_PROTECTION"  # noqa: S105


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
        blockers: list[str] | None = None,
        field: str | None = None,
        fix_hint: str | None = None,
        cli_example: str | None = None,
        valid_options: list[str] | None = None,
        did_you_mean: list[str] | None = None,
        closest_match: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize KbMcpError with code, message, and progressive-disclosure fields."""
        enum_code = McpErrorCode(code)
        super().__init__(f"[{enum_code.value}] {message}")
        self.code: Final[McpErrorCode] = enum_code
        self.message: Final[str] = message
        resolved_hint = hint if hint is not None else fix_hint
        resolved_fix_hint = fix_hint if fix_hint is not None else hint
        self.hint: Final[str | None] = resolved_hint
        self.candidates: Final[list[dict[str, str]] | None] = candidates
        self.allowed_tools: Final[list[str] | None] = allowed_tools
        self.budget: Final[dict[str, int] | None] = budget
        self.extra: Final[dict[str, Any] | None] = extra
        self.blockers: Final[list[str] | None] = blockers
        self.field: Final[str | None] = field
        self.fix_hint: Final[str | None] = resolved_fix_hint
        self.cli_example: Final[str | None] = cli_example
        self.valid_options: Final[list[str] | None] = valid_options
        self.did_you_mean: Final[list[str] | None] = did_you_mean
        self.closest_match: Final[list[dict[str, Any]] | None] = closest_match

    def to_yaml(self) -> str:
        """Serialize error payload containing code, message, optional hint, candidates, blockers."""
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        optional_fields: tuple[tuple[str, Any], ...] = (
            ("field", self.field),
            ("valid_options", self.valid_options),
            ("did_you_mean", self.did_you_mean),
            ("closest_match", self.closest_match),
            ("allowed_tools", self.allowed_tools),
            ("budget", self.budget),
            ("hint", self.hint),
            ("fix_hint", self.fix_hint),
            ("cli_example", self.cli_example),
            ("candidates", self.candidates),
            ("blockers", self.blockers),
        )
        payload.update({key: val for key, val in optional_fields if val is not None})
        if self.extra:
            payload.update(self.extra)
        return dump_yaml({"error": payload}, strip_nulls=True)
