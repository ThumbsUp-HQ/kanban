# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for sticky complexity heuristics and snooze evaluation (KB-P3-15)."""

from __future__ import annotations

import uuid

from kanban.services.sticky_heuristic import evaluate_sticky_promotion


def test_char_length_trigger() -> None:
    """Independently verify 601 chars triggers char_length, while 600 does not."""
    # 600 chars of plain text on 1 line
    text_600 = "a" * 600
    res_600 = evaluate_sticky_promotion(text_600)
    assert not res_600.recommended
    assert "char_length" not in res_600.triggers

    # 601 chars of plain text on 1 line
    text_601 = "a" * 601
    res_601 = evaluate_sticky_promotion(text_601)
    assert res_601.recommended
    assert res_601.triggers == ["char_length"]


def test_line_count_trigger() -> None:
    """Independently verify 11 lines triggers line_count, while 10 does not."""
    # 10 lines
    text_10_lines = "\n".join(f"line {i}" for i in range(10))
    res_10 = evaluate_sticky_promotion(text_10_lines)
    assert not res_10.recommended
    assert "line_count" not in res_10.triggers

    # 11 lines
    text_11_lines = "\n".join(f"line {i}" for i in range(11))
    res_11 = evaluate_sticky_promotion(text_11_lines)
    assert res_11.recommended
    assert res_11.triggers == ["line_count"]


def test_headings_trigger_and_code_fence_exclusion() -> None:
    """Independently verify 2 ATX headings trigger, and headings in code fences are ignored."""
    # 1 heading -> not triggered
    text_1_heading = "# Heading One\nsome plain text"
    res_1 = evaluate_sticky_promotion(text_1_heading)
    assert not res_1.recommended
    assert "headings" not in res_1.triggers

    # 2 headings -> triggered
    text_2_headings = "# Heading One\n## Heading Two"
    res_2 = evaluate_sticky_promotion(text_2_headings)
    assert res_2.recommended
    assert "headings" in res_2.triggers

    # 1 real heading + 2 headings inside code fence -> not triggered
    text_fenced_heading = "# Real Heading\n```python\n# Fake Heading 1\n# Fake Heading 2\n```"
    res_fenced = evaluate_sticky_promotion(text_fenced_heading)
    assert not res_fenced.recommended
    assert "headings" not in res_fenced.triggers


def test_structured_block_triggers() -> None:
    """Verify GFM table, ```mermaid fence, .svg reference, and >6-line code block."""
    # GFM table
    table_text = "| Col A | Col B |\n| --- | --- |\n| 1 | 2 |"
    res_table = evaluate_sticky_promotion(table_text)
    assert res_table.recommended
    assert "structured_block" in res_table.triggers

    # ```mermaid fence
    mermaid_text = "```mermaid\ngraph TD;\nA-->B;\n```"
    res_mermaid = evaluate_sticky_promotion(mermaid_text)
    assert res_mermaid.recommended
    assert "structured_block" in res_mermaid.triggers

    # .svg reference
    svg_text = "Check the architecture diagram: ![arch](assets/diagram.svg)"
    res_svg = evaluate_sticky_promotion(svg_text)
    assert res_svg.recommended
    assert "structured_block" in res_svg.triggers

    # Code fence with exactly 6 inner lines -> not triggered
    code_6_lines = "```\n" + "\n".join(f"line {i}" for i in range(6)) + "\n```"
    res_code_6 = evaluate_sticky_promotion(code_6_lines)
    assert not res_code_6.recommended
    assert "structured_block" not in res_code_6.triggers

    # Code fence with 7 inner lines (> 6) -> triggered
    code_7_lines = "```\n" + "\n".join(f"line {i}" for i in range(7)) + "\n```"
    res_code_7 = evaluate_sticky_promotion(code_7_lines)
    assert res_code_7.recommended
    assert "structured_block" in res_code_7.triggers

    # Tilde fence with 7 inner lines
    tilde_7_lines = "~~~\n" + "\n".join(f"code {i}" for i in range(7)) + "\n~~~"
    res_tilde_7 = evaluate_sticky_promotion(tilde_7_lines)
    assert res_tilde_7.recommended
    assert "structured_block" in res_tilde_7.triggers

    # Unclosed code fence with 7 inner lines
    unclosed_code_7 = "```\n" + "\n".join(f"line {i}" for i in range(7))
    res_unclosed = evaluate_sticky_promotion(unclosed_code_7)
    assert res_unclosed.recommended
    assert "structured_block" in res_unclosed.triggers


def test_outbound_links_trigger() -> None:
    """Independently verify 3 outbound links trigger, while 2 do not."""
    # 2 links (1 markdown + 1 autolink) -> not triggered
    text_2_links = "See [doc](https://example.com) and <https://foo.bar>"
    res_2 = evaluate_sticky_promotion(text_2_links)
    assert not res_2.recommended
    assert "outbound_links" not in res_2.triggers

    # 3 links (1 markdown + 1 autolink + 1 issue ref) -> triggered
    text_3_links = "See [doc](https://example.com) and <https://foo.bar> and [KEY-123]"
    res_3 = evaluate_sticky_promotion(text_3_links)
    assert res_3.recommended
    assert "outbound_links" in res_3.triggers


def test_snooze_math_and_clearing() -> None:
    """Verify >= 1.5x integer snooze growth math and clearing behavior."""
    # Sticky of 620 chars with char_length trigger
    text_620 = "x" * 620
    res_initial = evaluate_sticky_promotion(text_620)
    assert res_initial.recommended
    assert "char_length" in res_initial.triggers

    # Snooze at length 620
    snoozed_res = evaluate_sticky_promotion(text_620, snoozed_at_length=620)
    assert not snoozed_res.recommended
    assert snoozed_res.snoozed
    assert "char_length" in snoozed_res.triggers

    # Grow to 929 chars (620 * 1.5 = 930; 929 * 2 = 1858 < 1860) -> still snoozed
    text_929 = "x" * 929
    res_929 = evaluate_sticky_promotion(text_929, snoozed_at_length=620)
    assert not res_929.recommended
    assert res_929.snoozed

    # Grow to 930 chars (930 * 2 = 1860 >= 1860) -> snooze cleared!
    text_930 = "x" * 930
    res_930 = evaluate_sticky_promotion(text_930, snoozed_at_length=620)
    assert res_930.recommended
    assert not res_930.snoozed

    # Snooze at 0 length clears on any text > 0
    res_snooze_0 = evaluate_sticky_promotion("", snoozed_at_length=0)
    assert not res_snooze_0.recommended
    assert res_snooze_0.snoozed


def test_promoted_sticky_never_recommends() -> None:
    """Verify sticky already promoted to doc returns recommended=False and triggers=[]."""
    large_text = "# Title\n## Section\n" + "x" * 1000
    doc_id = uuid.uuid4()
    res = evaluate_sticky_promotion(large_text, snoozed_at_length=None, promoted_to_doc_id=doc_id)
    assert not res.recommended
    assert res.triggers == []
    assert not res.snoozed
