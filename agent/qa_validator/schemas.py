# Copyright 2026 Kanban Platform Contributors
"""Data schemas and Pydantic models for passive QA packet validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DeterministicCheckResult",
    "DodItemAudit",
    "QaPacketVerdict",
    "TicketSpecInput",
]


class TicketSpecInput(BaseModel):
    """Normalized ticket specification parsed from YAML or Markdown frontmatter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    epic: str | None = None
    gates: tuple[str, ...] = ()
    new_dependencies: tuple[str, ...] = ()
    definition_of_done: tuple[str, ...] = ()
    is_non_ui_ticket: bool = False
    has_ui_gate: bool = False
    has_api_gate: bool = False
    has_dep_gate: bool = False
    raw_text: str = ""
    body_markdown: str = ""


class DeterministicCheckResult(BaseModel):
    """Result of an individual deterministic proof bundle inspection check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str
    passed: bool
    detail: str


class DodItemAudit(BaseModel):
    """Forensic audit of an individual Definition of Done item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion: str
    passed: bool
    evidence_ref: str


class QaPacketVerdict(BaseModel):
    """Reality-checker forensic QA audit verdict for a ticket proof bundle."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["kb-qa-verdict/v1"] = Field(
        default="kb-qa-verdict/v1",
        alias="schema",
        description="Schema identifier for reality-checker verdict.",
    )
    grade: Literal["A", "B+", "B", "B-", "C+", "C", "F"]
    readiness: Literal["READY", "NEEDS_WORK", "FAILED"]
    dod_verdicts: list[DodItemAudit] = Field(min_length=1)
    critical_issues: list[str] = Field(default_factory=list)
    report_markdown: str = Field(min_length=1, max_length=16384)
    policy_override: str | None = None
