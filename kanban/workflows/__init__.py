# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Workflow engine types, transition pipeline, and gate coordinator (KB-P5-17a)."""

from __future__ import annotations

from kanban.workflows.engine import (
    AsyncGateDispatcher,
    FailClosedAsyncGateDispatcher,
    TransitionEngine,
    TransitionOutcome,
)
from kanban.workflows.gate_types import (
    GateDecision,
    GateEventType,
    LinkSpec,
    resolve_effective_gate_timeout_ms,
)
from kanban.workflows.manifest import compute_hook_manifest_sha256
from kanban.workflows.mutations import (
    MUTABLE_FIELD_UNIVERSE,
    apply_field_updates,
    is_in_mutable_universe,
    validate_field_updates,
)

__all__ = [
    "MUTABLE_FIELD_UNIVERSE",
    "AsyncGateDispatcher",
    "FailClosedAsyncGateDispatcher",
    "GateDecision",
    "GateEventType",
    "LinkSpec",
    "TransitionEngine",
    "TransitionOutcome",
    "apply_field_updates",
    "compute_hook_manifest_sha256",
    "is_in_mutable_universe",
    "resolve_effective_gate_timeout_ms",
    "validate_field_updates",
]
