# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Transition context building and verdict parsing (S14.3)."""

from __future__ import annotations

from agent.context.transition_context import (
    ContextDelimiterCollisionError,
    ContextTooLargeError,
    McpAccess,
    RenderedContext,
    RepoContext,
    TicketSnapshot,
    TransitionContextModel,
    TransitionMetadata,
    build_transition_context,
)
from agent.context.verdict import (
    MAX_VERDICT_OUTPUT_BYTES,
    TransitionVerdict,
    VerdictLinkSpec,
    VerdictParseError,
    VerdictResult,
    canonical_verdict_sha256,
    parse_verdict_output,
)

__all__ = [
    "MAX_VERDICT_OUTPUT_BYTES",
    "ContextDelimiterCollisionError",
    "ContextTooLargeError",
    "McpAccess",
    "RenderedContext",
    "RepoContext",
    "TicketSnapshot",
    "TransitionContextModel",
    "TransitionMetadata",
    "TransitionVerdict",
    "VerdictLinkSpec",
    "VerdictParseError",
    "VerdictResult",
    "build_transition_context",
    "canonical_verdict_sha256",
    "parse_verdict_output",
]
