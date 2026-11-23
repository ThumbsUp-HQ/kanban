# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Types and data structures for workflow gate decision evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping


class GateEventType(StrEnum):
    """Event types for asynchronous transition gates."""

    DISPATCH = "workflow.gate.dispatch"
    PENDING = "workflow.gate.pending"
    APPROVED = "workflow.gate.approved"
    REJECTED = "workflow.gate.rejected"
    TIMED_OUT = "workflow.gate.timed_out"
    CANCELLED = "workflow.gate.cancelled"


class DeterministicGateType(StrEnum):
    """Deterministic non-LLM workflow transition gate types (KB-DEVSECOPS-ATTEST-01)."""

    COMMIT_SIGNATURE = "commit_signature"
    CI_CHECK_RUN = "ci_check_run"
    SLSA_PROVENANCE = "slsa_provenance"


@dataclass(frozen=True)
class ProvenanceGateVerdict:
    """Consolidated verdict payload from deterministic provenance gates."""

    decision: Literal["approve", "reject"]
    gate_type: str
    verified: bool
    reason_markdown: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LinkSpec:
    """Specification of an object link proposed by an agent gate."""

    link_type: Literal["RELATES_TO", "BLOCKS", "BLOCKED_BY", "VERIFIED_BY_DOC"]
    target: str


@dataclass(frozen=True)
class GateDecision:
    """Parsed and validated decision produced by an AI transition gate."""

    decision: Literal["approve", "reject"]
    reason_markdown: str
    field_updates: Mapping[str, Any] = field(default_factory=dict)
    add_labels: tuple[str, ...] = ()
    add_links: tuple[LinkSpec, ...] = ()
    cited_files: tuple[str, ...] = ()
    verdict_sha256: bytes = b""
    latency_ms: int = 0
