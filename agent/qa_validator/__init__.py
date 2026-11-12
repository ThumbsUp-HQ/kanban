# Copyright 2026 Kanban Platform Contributors
"""Passive forensic reality-checker QA packet validator package."""

from __future__ import annotations

from agent.qa_validator.auditor import enforce_anti_fantasy, run_qa_packet_audit
from agent.qa_validator.bundle_inspector import (
    ProofBundle,
    ProofFileEntry,
    ProofInspectionError,
    inspect_proof_directory,
    parse_ticket_file,
)
from agent.qa_validator.schemas import (
    DeterministicCheckResult,
    DodItemAudit,
    QaPacketVerdict,
    TicketSpecInput,
)

__all__ = [
    "DeterministicCheckResult",
    "DodItemAudit",
    "ProofBundle",
    "ProofFileEntry",
    "ProofInspectionError",
    "QaPacketVerdict",
    "TicketSpecInput",
    "enforce_anti_fantasy",
    "inspect_proof_directory",
    "parse_ticket_file",
    "run_qa_packet_audit",
]
