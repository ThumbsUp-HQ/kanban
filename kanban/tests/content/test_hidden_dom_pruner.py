"""Tests for Step A Hidden-DOM Paste-Jacking Pruner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kanban.content.hidden_dom import (
    calculate_contrast_ratio,
    calculate_relative_luminance,
    decode_css_escapes,
    parse_css_color,
    prune_hidden_dom,
)
from kanban.content.unicode_guard import ContentNormalizeError

CANARY = "IGNORE_PREVIOUS_INSTRUCTIONS_EXFIL_SEC"


def test_decode_css_escapes() -> None:
    """Verify CSS comment removal and hex/punctuation escape decoding."""
    raw = r"/* comment */ \64 isplay: /* inner */ \6e one; \:hover"
    decoded = decode_css_escapes(raw)
    assert "display:" in decoded
    assert "none" in decoded
    assert ":hover" in decoded


def test_wcag_luminance_and_contrast() -> None:
    """Verify WCAG 2.1 relative luminance and contrast ratio calculations."""
    black = (0, 0, 0)
    white = (255, 255, 255)
    lum_black = calculate_relative_luminance(black)
    lum_white = calculate_relative_luminance(white)
    assert lum_black == pytest.approx(0.0, abs=1e-4)
    assert lum_white == pytest.approx(1.0, abs=1e-4)

    contrast_bw = calculate_contrast_ratio(white, black)
    assert contrast_bw == pytest.approx(21.0, abs=0.1)

    contrast_same = calculate_contrast_ratio(white, white)
    assert contrast_same == pytest.approx(1.0, abs=1e-4)


def test_parse_css_color() -> None:
    """Verify CSS color parser for hex, rgb, rgba, and named colors."""
    assert parse_css_color("black") == (0, 0, 0)
    assert parse_css_color("white") == (255, 255, 255)
    assert parse_css_color("#fff") == (255, 255, 255)
    assert parse_css_color("#ffff") == (255, 255, 255)
    assert parse_css_color("#102030") == (16, 32, 48)
    assert parse_css_color("#102030ff") == (16, 32, 48)
    assert parse_css_color("rgb(10, 20, 30)") == (10, 20, 30)
    assert parse_css_color("rgba(10, 20, 30, 0.5)") == (10, 20, 30)
    assert parse_css_color("transparent") is None
    assert parse_css_color("invalid_color_123") is None


def test_paste_jacking_corpus_all_strip_canary() -> None:
    """Verify 100% of attack vectors in paste_jacking_cases.json strip the canary."""
    corpus_path = Path(__file__).parent / "corpus" / "paste_jacking_cases.json"
    assert corpus_path.exists(), f"Missing corpus file: {corpus_path}"

    with corpus_path.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    assert len(cases) >= 30, f"Expected at least 30 attack cases, got {len(cases)}"

    for case in cases:
        case_id = case["id"]
        raw_html = case["html"]
        pruned_html, records = prune_hidden_dom(raw_html)

        # Invariant 1: Canary MUST be completely absent from pruned HTML
        assert CANARY not in pruned_html, (
            f"Case '{case_id}' failed: canary survived in output: {pruned_html}"
        )

        # Invariant 2: At least one pruned record must be recorded
        assert len(records) > 0, f"Case '{case_id}' did not record any pruned elements"


def test_dark_mode_white_text_preserved() -> None:
    """Verify white text without an explicit light background is preserved."""
    html_input = (
        '<div style="background:#1e1e1e;color:#ffffff">'
        "<span>Visible white text in dark mode</span>"
        "</div>"
    )
    pruned, records = prune_hidden_dom(html_input)
    assert "Visible white text in dark mode" in pruned
    assert len(records) == 0


def test_white_text_no_background_preserved() -> None:
    """Verify white text without any background is NOT treated as low contrast."""
    html_input = '<span style="color:#ffffff">Terminal paste</span>'
    pruned, records = prune_hidden_dom(html_input)
    assert "Terminal paste" in pruned
    assert len(records) == 0


def test_depth_limit_enforced() -> None:
    """Verify tree depth exceeding 256 raises HTML_COMPLEXITY_EXCEEDED."""
    nested = "<div>" * 260 + "deep content" + "</div>" * 260
    with pytest.raises(ContentNormalizeError) as exc_info:
        prune_hidden_dom(nested)
    assert exc_info.value.code == "HTML_COMPLEXITY_EXCEEDED"


def test_node_count_limit_enforced() -> None:
    """Verify node count exceeding 50,000 raises HTML_COMPLEXITY_EXCEEDED."""
    large = "<span>x</span>" * 50_005
    with pytest.raises(ContentNormalizeError) as exc_info:
        prune_hidden_dom(large)
    assert exc_info.value.code == "HTML_COMPLEXITY_EXCEEDED"


def test_empty_html() -> None:
    """Verify empty input returns empty output and empty record list."""
    pruned, records = prune_hidden_dom("")
    assert pruned == ""
    assert records == []
