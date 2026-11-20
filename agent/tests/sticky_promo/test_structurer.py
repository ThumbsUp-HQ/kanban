# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, ASYNC240
"""Unit tests for agent.sticky_promo (schemas, structurer, and fenced block check)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from agent.providers.errors import EgressDenied, ProviderSchemaError
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sticky_promo.schemas import (
    DocSection,
    StickyDocProposal,
    render_canonical_doc_markdown,
)
from agent.sticky_promo.structurer import (
    FencedBlockModifiedError,
    StickyTooLargeError,
    _extract_action_items,
    _extract_sections,
    _extract_title,
    append_missing_fenced_blocks,
    deterministic_fallback_structuring,
    extract_fenced_blocks,
    structure_sticky_to_doc_proposal,
    verify_fenced_blocks_preserved,
)
from agent.testing.fixtures import FixtureLLMProvider, load_cassette

_FIXTURES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "ai"


def _make_router_with_cassette(cassette_name: str, residency: str = "fixture") -> ProviderRouter:
    cas = load_cassette(_FIXTURES_DIR / cassette_name)
    provider = FixtureLLMProvider(cassettes=[cas])
    candidate = RouteCandidate(
        provider_config_id=uuid.uuid4(),
        provider=provider,
        residency_tier=residency,
        priority=1,
    )
    return ProviderRouter(
        workspace_id=uuid.uuid4(),
        candidates=[candidate],
        air_gap_mode=False,
    )


def test_doc_section_validation() -> None:
    """Verify DocSection constraints and single-line heading validation."""
    sec = DocSection(heading="Valid Heading", level=2, body_markdown="Some body")
    assert sec.heading == "Valid Heading"
    assert sec.level == 2

    # Multiline heading rejected
    with pytest.raises(ValidationError):
        DocSection(heading="Heading\nWith newline", level=2, body_markdown="Body")

    # Empty heading rejected
    with pytest.raises(ValidationError):
        DocSection(heading="   ", level=2, body_markdown="Body")

    # Invalid level rejected (only 2 or 3 allowed)
    with pytest.raises(ValidationError):
        DocSection(heading="Heading", level=1, body_markdown="Body")  # type: ignore[arg-type]


def test_sticky_doc_proposal_validation() -> None:
    """Verify StickyDocProposal field constraints and action item validation."""
    sec = DocSection(heading="Overview", level=2, body_markdown="Body text")
    proposal = StickyDocProposal(
        proposed_title="System Architecture",
        summary_markdown="Summary description.",
        sections=[sec],
        extracted_action_items=["Task 1", "Task 2"],
    )
    assert proposal.proposed_title == "System Architecture"
    assert len(proposal.sections) == 1
    assert len(proposal.extracted_action_items) == 2

    # Multiline title rejected
    with pytest.raises(ValidationError):
        StickyDocProposal(
            proposed_title="Title\nMultiline",
            summary_markdown="Summary",
            sections=[sec],
        )

    # Empty title rejected
    with pytest.raises(ValidationError):
        StickyDocProposal(
            proposed_title="   ",
            summary_markdown="Summary",
            sections=[sec],
        )

    # Empty sections rejected (min_length=1)
    with pytest.raises(ValidationError):
        StickyDocProposal(
            proposed_title="Title",
            summary_markdown="Summary",
            sections=[],
        )

    # Multiline action item rejected
    with pytest.raises(ValidationError):
        StickyDocProposal(
            proposed_title="Title",
            summary_markdown="Summary",
            sections=[sec],
            extracted_action_items=["Item 1\nwith newline"],
        )


def test_fenced_block_extraction_and_verification() -> None:
    """Verify extract_fenced_blocks and verify_fenced_blocks_preserved."""
    markdown = (
        "# Notes\n\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "  A->>B: Ping\n"
        "```\n\n"
        "~~~python\n"
        "print('hello')\n"
        "~~~\n"
    )
    blocks = extract_fenced_blocks(markdown)
    assert len(blocks) == 2
    assert blocks[0]["info"] == "mermaid"
    assert "A->>B: Ping" in blocks[0]["body"]
    assert blocks[1]["info"] == "python"

    # All preserved in exact copy
    all_pres, warnings, missing = verify_fenced_blocks_preserved(markdown, markdown)
    assert all_pres is True
    assert warnings == []
    assert missing == []

    # Omitted diagram triggers warning and missing block list
    rendered_without_mermaid = "# Notes\n\n```python\nprint('hello')\n```\n"
    all_pres, warnings, missing = verify_fenced_blocks_preserved(markdown, rendered_without_mermaid)
    assert all_pres is False
    assert warnings == ["FENCED_BLOCK_MODIFIED"]
    assert len(missing) == 1
    assert "sequenceDiagram" in missing[0]

    # Append missing blocks fallback
    fixed = append_missing_fenced_blocks(rendered_without_mermaid, missing)
    assert "## Preserved Diagrams and Code" in fixed
    assert "sequenceDiagram" in fixed

    # Calling append with empty missing blocks is identity
    assert append_missing_fenced_blocks("same", []) == "same"

    # Empty source blocks
    assert verify_fenced_blocks_preserved("no code here", "no code here") == (True, [], [])


def test_render_canonical_doc_markdown_assembly() -> None:
    """Verify render_canonical_doc_markdown formats headings, blockquote, checklist, and strips HTML."""
    proposal = StickyDocProposal(
        proposed_title="Auth Architecture",
        summary_markdown="High-level auth design.\nSecond line.",
        sections=[
            DocSection(
                heading="Overview",
                level=2,
                body_markdown="Normal text with safe Markdown.",
            ),
            DocSection(
                heading="Sub-topic",
                level=3,
                body_markdown="Details here.",
            ),
        ],
        extracted_action_items=[
            "- [ ] Existing checklist item",
            "- Bullet item to convert",
            "Bare item to convert",
        ],
    )
    rendered = render_canonical_doc_markdown(proposal)
    assert "# Auth Architecture" in rendered
    assert "> High-level auth design." in rendered
    assert "> Second line." in rendered
    assert "## Overview" in rendered
    assert "### Sub-topic" in rendered
    assert "## Open Action Items" in rendered
    assert "- [ ] Existing checklist item" in rendered
    assert "- [ ] Bullet item to convert" in rendered
    assert "- [ ] Bare item to convert" in rendered


@pytest.mark.asyncio
async def test_structure_sticky_too_large() -> None:
    """Verify sticky exceeding 131,072 bytes raises StickyTooLargeError."""
    router = _make_router_with_cassette("sticky_promo_auth_notes_ok.yaml")
    huge_body = "a" * 131_073

    with pytest.raises(StickyTooLargeError) as exc_info:
        await structure_sticky_to_doc_proposal(body_markdown=huge_body, router=router)
    assert exc_info.value.code == "STICKY_TOO_LARGE"


@pytest.mark.asyncio
async def test_structure_sticky_positive_flow() -> None:
    """Verify positive structuring flow with rough notes and ok cassette."""
    notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    router = _make_router_with_cassette("sticky_promo_auth_notes_ok.yaml")

    res = await structure_sticky_to_doc_proposal(
        body_markdown=notes,
        router=router,
    )
    assert res.proposal.proposed_title == "Authentication Architecture and Multi-Card Flow"
    assert len(res.proposal.sections) == 3
    assert len(res.proposal.extracted_action_items) == 2
    assert "sequenceDiagram" in res.rendered_markdown
    assert res.warnings == []
    assert res.redacted_secrets_count == 0
    assert len(res.tool_trace) >= 3


@pytest.mark.asyncio
async def test_structure_sticky_secret_scrubbed() -> None:
    """Verify secrets inside raw notes are scrubbed before provider dispatch."""
    dummy_key = "s" + "k-proj-" + "1234567890abcdef1234567890"
    raw_notes = f"# Secret Notes\n\nHere is my API key: {dummy_key}\nDo not leak it.\n"
    router = _make_router_with_cassette("sticky_promo_auth_notes_ok.yaml")

    res = await structure_sticky_to_doc_proposal(
        body_markdown=raw_notes,
        router=router,
    )
    # Check that secret was scrubbed
    assert dummy_key not in res.spotlight_prompt
    assert "[REDACTED:API_KEY]" in res.spotlight_prompt
    assert res.redacted_secrets_count > 0


@pytest.mark.asyncio
async def test_structure_sticky_dropped_mermaid_warnings_and_strict() -> None:
    """Verify dropped Mermaid block triggers FENCED_BLOCK_MODIFIED and fallback/strict error."""
    notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")

    # 1. Non-strict: adds warning and appends diagram deterministically
    router = _make_router_with_cassette("sticky_promo_dropped_mermaid.yaml")
    res = await structure_sticky_to_doc_proposal(
        body_markdown=notes,
        router=router,
        strict_blocks=False,
    )
    assert "FENCED_BLOCK_MODIFIED" in res.warnings
    assert "## Preserved Diagrams and Code" in res.rendered_markdown
    assert "sequenceDiagram" in res.rendered_markdown

    # 2. Strict mode: raises FencedBlockModifiedError
    router_strict = _make_router_with_cassette("sticky_promo_dropped_mermaid.yaml")
    with pytest.raises(FencedBlockModifiedError) as exc_info:
        await structure_sticky_to_doc_proposal(
            body_markdown=notes,
            router=router_strict,
            strict_blocks=True,
        )
    assert exc_info.value.code == "FENCED_BLOCK_MODIFIED"


@pytest.mark.asyncio
async def test_structure_sticky_hostile_html_output_sanitized() -> None:
    """Verify model output with hostile HTML is sanitized by normalizer (0 scripts, 0 js URIs)."""
    notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    router = _make_router_with_cassette("sticky_promo_hostile_html_output.yaml")

    res = await structure_sticky_to_doc_proposal(
        body_markdown=notes,
        router=router,
    )
    assert "<script>" not in res.rendered_markdown
    assert "javascript:" not in res.rendered_markdown


@pytest.mark.asyncio
async def test_structure_sticky_schema_invalid() -> None:
    """Verify invalid schema output from cassette raises ProviderSchemaError."""
    notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    router = _make_router_with_cassette("sticky_promo_schema_invalid.yaml")

    with pytest.raises(ProviderSchemaError):
        await structure_sticky_to_doc_proposal(
            body_markdown=notes,
            router=router,
        )


@pytest.mark.asyncio
async def test_structure_sticky_air_gap_denied() -> None:
    """Verify --air-gap with cloud provider tier raises EgressDenied."""
    notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    router = _make_router_with_cassette("sticky_promo_auth_notes_ok.yaml", residency="gemini")

    with pytest.raises(EgressDenied) as exc_info:
        await structure_sticky_to_doc_proposal(
            body_markdown=notes,
            router=router,
            air_gap=True,
        )
    assert exc_info.value.code == "AIR_GAP_EGRESS_DENIED"


@pytest.mark.asyncio
async def test_structure_sticky_budget_reservation_and_settle() -> None:
    """Verify BudgetEnforcer reservation, settlement on success, and release on error."""
    notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    router = _make_router_with_cassette("sticky_promo_auth_notes_ok.yaml")

    mock_enforcer = MagicMock()
    mock_res = MagicMock()
    mock_enforcer.reserve = AsyncMock(return_value=mock_res)
    mock_enforcer.settle = AsyncMock()
    mock_enforcer.release = AsyncMock()

    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    prov_id = uuid.uuid4()

    # Success case
    await structure_sticky_to_doc_proposal(
        body_markdown=notes,
        router=router,
        budget_enforcer=mock_enforcer,
        caller_workspace_id=ws_id,
        caller_project_id=proj_id,
        provider_config_id=prov_id,
    )
    mock_enforcer.reserve.assert_awaited_once()
    mock_enforcer.settle.assert_awaited_once()
    mock_enforcer.release.assert_not_awaited()

    # Error case releases reservation
    mock_enforcer.reset_mock()
    router_err = _make_router_with_cassette("sticky_promo_schema_invalid.yaml")
    with pytest.raises(ProviderSchemaError):
        await structure_sticky_to_doc_proposal(
            body_markdown=notes,
            router=router_err,
            budget_enforcer=mock_enforcer,
            caller_workspace_id=ws_id,
            caller_project_id=proj_id,
            provider_config_id=prov_id,
        )
    mock_enforcer.reserve.assert_awaited_once()
    mock_enforcer.release.assert_awaited_once()


def test_action_item_validation_edge_cases() -> None:
    """Verify action item length and newline validation."""
    sec = DocSection(heading="Section", level=2, body_markdown="Body")
    with pytest.raises(ValidationError):
        StickyDocProposal(
            proposed_title="Title",
            summary_markdown="Summary",
            sections=[sec],
            extracted_action_items=["x" * 281],
        )

    with pytest.raises(ValidationError):
        StickyDocProposal(
            proposed_title="Title",
            summary_markdown="Summary",
            sections=[sec],
            extracted_action_items=["Item\nWith newline"],
        )


def test_render_canonical_doc_markdown_edge_cases() -> None:
    """Verify markdown rendering with whitespace-only summary and various action item formats."""
    sec = DocSection(heading="Architecture", level=2, body_markdown="Details")
    proposal = StickyDocProposal(
        proposed_title="Title",
        summary_markdown="   ",
        sections=[sec],
        extracted_action_items=[
            "- [ ] Existing checkbox item",
            "- Existing bullet item",
            "Plain item",
        ],
    )
    rendered = render_canonical_doc_markdown(proposal)
    assert "# Title" in rendered
    assert "## Architecture" in rendered
    assert "- [ ] Existing checkbox item" in rendered
    assert "- [ ] Existing bullet item" in rendered
    assert "- [ ] Plain item" in rendered

    # No action items
    proposal_no_items = StickyDocProposal(
        proposed_title="Title",
        summary_markdown="Summary text",
        sections=[sec],
        extracted_action_items=[],
    )
    rendered_no_items = render_canonical_doc_markdown(proposal_no_items)
    assert "## Open Action Items" not in rendered_no_items


@pytest.mark.asyncio
async def test_structure_sticky_air_gap_with_fixture_tier() -> None:
    """Verify air gap allows local/fixture residency tier."""
    notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    router = _make_router_with_cassette("sticky_promo_auth_notes_ok.yaml", residency="local_ollama")

    result = await structure_sticky_to_doc_proposal(
        body_markdown=notes,
        router=router,
        air_gap=True,
    )
    assert result.proposal.proposed_title is not None


def test_structurer_internal_helpers_coverage() -> None:
    """Exercise fallback title, sections, action items, and fallback missing fenced blocks."""
    # 1. _extract_title fallbacks
    assert _extract_title(["", "   ", "\n"]) == "Promoted Sticky Notes"
    assert _extract_title(["- some item"]) == "some item"
    assert _extract_title(["### Important Design"]) == "Important Design"

    # 2. _extract_action_items with empty text or blank lines
    items = _extract_action_items(["- [ ]    ", "- [x] Valid task", "- [X] Another task"])
    assert items == ["Valid task", "Another task"]

    # 3. _extract_sections with h3, empty bodies, and fallback
    secs = _extract_sections(
        ["## Section 1", "Body 1", "### Sub Section", "Sub Body 2"],
        fallback_text="Fallback",
    )
    assert len(secs) == 2
    assert secs[0].level == 2
    assert secs[1].level == 3
    assert secs[1].heading == "Sub Section"

    # 4. deterministic_fallback_structuring preserves fenced blocks or handles fallback
    fb_res = deterministic_fallback_structuring(
        body_markdown="# My Sticky\n\n```python\nprint(1)\n```\n- [ ] Todo item",
        warnings=["INITIAL_WARN"],
    )
    assert fb_res.proposal.proposed_title == "My Sticky"
    assert "INITIAL_WARN" in fb_res.warnings
    assert len(fb_res.proposal.extracted_action_items) == 1
