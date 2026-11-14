# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic schemas and canonical Markdown renderer for Sticky -> Doc AI proposals (KB-P5-26)."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kanban.content.normalize import normalize_to_markdown

__all__ = [
    "MAX_ACTION_ITEM_LENGTH",
    "DocSection",
    "StickyDocProposal",
    "render_canonical_doc_markdown",
]

MAX_ACTION_ITEM_LENGTH: Final[int] = 280


class DocSection(BaseModel):
    """Structured section within a Sticky -> Doc proposal."""

    model_config = ConfigDict(extra="forbid", strict=True)

    heading: str = Field(
        min_length=1,
        max_length=140,
        description="Section heading (single line, 1..140 characters)",
    )
    level: Literal[2, 3] = Field(
        description="Markdown heading level (strictly 2 or 3)",
    )
    body_markdown: str = Field(
        min_length=1,
        max_length=65536,
        description="Section body Markdown content (1..65536 characters)",
    )

    @field_validator("heading")
    @classmethod
    def _validate_heading(cls, v: str) -> str:
        if "\n" in v or "\r" in v:
            msg = "heading must be a single line"
            raise ValueError(msg)
        cleaned = v.strip()
        if not cleaned:
            msg = "heading cannot be empty or whitespace only"
            raise ValueError(msg)
        return cleaned


class StickyDocProposal(BaseModel):
    """Structured output proposal for promoting a scratchpad sticky to a document."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["kb-sticky-doc-proposal/v1"] = Field(
        default="kb-sticky-doc-proposal/v1",
        alias="schema",
        description="Schema identifier",
    )
    proposed_title: str = Field(
        min_length=1,
        max_length=200,
        description="Proposed document title (single line, 1..200 characters)",
    )
    summary_markdown: str = Field(
        min_length=1,
        max_length=1000,
        description="Executive summary in Markdown (1..1000 characters)",
    )
    sections: list[DocSection] = Field(
        min_length=1,
        max_length=20,
        description="Structured sections (1..20 items)",
    )
    extracted_action_items: list[str] = Field(
        default_factory=list,
        max_length=25,
        description="Extracted action items (0..25 items, each 1..280 characters)",
    )

    @field_validator("proposed_title")
    @classmethod
    def _validate_proposed_title(cls, v: str) -> str:
        if "\n" in v or "\r" in v:
            msg = "proposed_title must be a single line"
            raise ValueError(msg)
        cleaned = v.strip()
        if not cleaned:
            msg = "proposed_title cannot be empty or whitespace only"
            raise ValueError(msg)
        return cleaned

    @field_validator("extracted_action_items")
    @classmethod
    def _validate_action_items(cls, items: list[str]) -> list[str]:
        for item in items:
            if not (1 <= len(item) <= MAX_ACTION_ITEM_LENGTH):
                msg = f"Action item length must be between 1 and 280 characters: {item!r}"
                raise ValueError(msg)
            if "\n" in item or "\r" in item:
                msg = f"Action item must be a single line: {item!r}"
                raise ValueError(msg)
        return items


def render_canonical_doc_markdown(proposal: StickyDocProposal) -> str:
    """Assemble canonical Markdown representation of a StickyDocProposal.

    Renders `# <proposed_title>`, summary blockquote, `##`/`###` sections, and optional
    `## Open Action Items` checklist, then passes the full string through the KB-P2-13
    canonical Markdown normalizer (stripping any HTML/unsafe URIs).
    """
    parts: list[str] = [f"# {proposal.proposed_title}", ""]

    summary_clean = proposal.summary_markdown.strip()
    if summary_clean:
        summary_lines = summary_clean.split("\n")
        blockquote_lines = [f"> {line}" if line.strip() else ">" for line in summary_lines]
        parts.append("\n".join(blockquote_lines))
        parts.append("")

    for sec in proposal.sections:
        prefix = "#" * sec.level
        parts.append(f"{prefix} {sec.heading}")
        parts.append("")
        parts.append(sec.body_markdown.strip())
        parts.append("")

    if proposal.extracted_action_items:
        parts.append("## Open Action Items")
        parts.append("")
        for item in proposal.extracted_action_items:
            clean_item = item.strip()
            if clean_item.startswith(("- [ ]", "- [x]")):
                parts.append(clean_item)
            elif clean_item.startswith("- "):
                parts.append(f"- [ ] {clean_item[2:]}")
            else:
                parts.append(f"- [ ] {clean_item}")
        parts.append("")

    raw_doc = "\n".join(parts).strip() + "\n"
    return normalize_to_markdown(raw_doc)
