"""Mandatory feature unit tests for server Markdown ingestion normalizer.

Validates all 8 required feature test cases specified in KB-P2-13:
1. Positive HTML -> GFM goldens (Confluence, Jira, Google Docs)
2. Positive IDE wrapper bypass (VS Code syntax-highlighted blocks)
3. Positive clean Markdown preservation (mermaid, tables, script in code fence)
4. Security Step A hidden-DOM paste-jacking corpus (zero canary survival)
5. Security XSS and embedded HTML in Markdown
6. Security Unicode smuggling and BiDi trojan source overrides
7. Plain-text mode normalization
8. Boundary conditions (size and depth limits)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kanban.content.normalize import (
    ContentNormalizeError,
    normalize_inspect,
    normalize_markdown,
    normalize_plain_text,
    normalize_to_markdown,
)

CANARY = "IGNORE_PREVIOUS_INSTRUCTIONS_EXFIL_SEC"


def test_case_1_positive_html_to_gfm_goldens() -> None:
    """Case 1: Confluence/Jira/Google Docs HTML converts to exact canonical GFM."""
    goldens_path = Path(__file__).parent / "corpus" / "rich_html_to_gfm_goldens.json"
    assert goldens_path.exists(), f"Missing goldens file: {goldens_path}"

    with goldens_path.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        case_id = case["id"]
        raw_html = case["html"]
        expected_md = case["expected_markdown"]
        actual_md = normalize_to_markdown(raw_html, mode="html")
        assert actual_md == expected_md, f"Case '{case_id}' GFM mismatch:\n{actual_md}"


def test_case_2_positive_ide_wrapper_bypass() -> None:
    """Case 2: VS Code snippet wraps into fenced code block without losing indent or escaping."""
    vs_code_html = (
        '<div><span style="color:#d4d4d4">def f():</span><br>'
        '<span style="color:#ce9178">    return 1</span></div>'
    )
    result = normalize_to_markdown(vs_code_html, mode="auto")
    assert result == "```\ndef f():\n    return 1\n```"
    assert "    return 1" in result
    assert "\\_" not in result  # Zero unnecessary backslash escaping of underscores

    # Dark-mode white text without light background is preserved
    dark_mode_html = (
        '<div style="background-color:#1e1e1e">'
        '<span style="color:#ffffff">visible_identifier</span>'
        "</div>"
    )
    dark_result = normalize_to_markdown(dark_mode_html, mode="auto")
    assert "visible_identifier" in dark_result
    assert "```" in dark_result


def test_case_3_positive_clean_markdown_preservation() -> None:
    """Case 3: Clean Markdown with mermaid, pipe tables, and script in code fence is preserved."""
    markdown_input = (
        "# Architectural Diagram\n\n"
        "```mermaid\n"
        "A -->|label| B\n"
        "```\n\n"
        "| Component | Status |\n"
        "| --- | --- |\n"
        "| Normalizer | Verified |\n\n"
        "```python\n"
        "<script>not html</script>\n"
        "```"
    )
    report = normalize_inspect(markdown_input, mode="auto")
    assert report.input_kind == "markdown"
    assert "<script>not html</script>" in report.output_markdown
    assert "A -->|label| B" in report.output_markdown
    assert "| Normalizer | Verified |" in report.output_markdown


def test_case_4_security_hidden_dom_paste_jacking_corpus() -> None:
    """Case 4: Hidden-DOM paste-jacking corpus leaves zero canary occurrences in output."""
    corpus_path = Path(__file__).parent / "corpus" / "paste_jacking_cases.json"
    with corpus_path.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        raw_html = case["html"]
        report = normalize_inspect(raw_html, mode="auto")
        assert CANARY not in report.output_markdown, (
            f"Canary survived in output for case {case['id']}: {report.output_markdown}"
        )
        assert report.hidden_nodes_pruned > 0


def test_case_5_security_xss_and_embedded_html_in_markdown() -> None:
    """Case 5: Embedded XSS vectors in Markdown have zero executable markup in output."""
    vectors = [
        ("<img src=x onerror=alert(1)>", ["onerror", "alert"]),
        ("<svg onload=alert(1)>", ["<svg", "onload"]),
        ("<math><mtext><script>alert(1)</script>", ["<math", "<script", "alert"]),
        ("[click](javascript:alert(1))", ["javascript:"]),
        ("[click-entity](jav&#x09;ascript:alert(1))", ["javascript:"]),
        (
            "[click-data](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
            ["data:text/html"],
        ),
        ("[click-proto](//evil.example/x)", ["//evil.example"]),
    ]

    for raw, forbidden_substrings in vectors:
        report = normalize_inspect(raw, mode="markdown")
        out = report.output_markdown
        for forbidden in forbidden_substrings:
            assert forbidden not in out, f"Vector '{raw}' leaked '{forbidden}' in output: {out}"

    # Also test mixed document with links and safe markdown
    mixed_doc = (
        "Heading\n\n"
        "<img src=x onerror=alert(1)>\n\n"
        "[click](javascript:alert(1)) and [safe](https://example.com) and [proto](//evil.example/x)"
    )
    mixed_report = normalize_inspect(mixed_doc, mode="markdown")
    assert "onerror" not in mixed_report.output_markdown
    assert "javascript:" not in mixed_report.output_markdown
    assert "//evil.example" not in mixed_report.output_markdown
    assert "[safe](https://example.com)" in mixed_report.output_markdown
    assert mixed_report.links_disarmed == 2


def test_case_6_security_unicode_smuggling_and_bidi() -> None:
    """Case 6: Unicode smuggling, Plane-14 tags, and BiDi trojan-source overrides stripped."""
    plane_14_tags = "".join(chr(0xE0000 + ord(c)) for c in "ignore rules")
    raw = f"Visible content\u200b with\u202e reversed text {plane_14_tags}."
    report = normalize_inspect(raw, mode="auto")

    assert "\u200b" not in report.output_markdown
    assert "\u202e" not in report.output_markdown
    for c in plane_14_tags:
        assert c not in report.output_markdown
    assert report.zero_width_stripped > 0


def test_case_7_plain_text_mode() -> None:
    """Case 7: normalize_plain_text strips tags, unescapes entities, and collapses newlines."""
    raw = "<b>Fix</b>\n\u200bSummary"
    result = normalize_plain_text(raw)
    assert result == "Fix Summary"

    entity_raw = "Summary &amp; Details &gt; Info\nSecond Line"
    result2 = normalize_plain_text(entity_raw)
    assert result2 == "Summary & Details > Info Second Line"


def test_case_8_boundary_conditions() -> None:
    """Case 8: Size limit 2,097,152 and depth limit 256 raise ContentNormalizeError."""
    # Size boundary: 2,097,153 bytes -> CONTENT_TOO_LARGE
    oversized = "a" * (2_097_152 + 1)
    with pytest.raises(ContentNormalizeError) as exc_info:
        normalize_to_markdown(oversized)
    assert exc_info.value.code == "CONTENT_TOO_LARGE"

    # Depth boundary: 260-deep nested div -> HTML_COMPLEXITY_EXCEEDED
    nested = "<div>" * 260 + "deep" + "</div>" * 260
    with pytest.raises(ContentNormalizeError) as exc_info:
        normalize_to_markdown(nested, mode="html")
    assert exc_info.value.code == "HTML_COMPLEXITY_EXCEEDED"


def test_normalize_inspect_metrics() -> None:
    """Verify NormalizationReport metrics accuracy."""
    raw = "<p>Text <span style='display:none'>hidden</span> [link](https://example.com)</p>"
    report = normalize_inspect(raw, mode="auto")
    assert report.input_kind == "html"
    assert report.input_bytes == len(raw.encode("utf-8"))
    assert report.output_bytes == len(report.output_markdown.encode("utf-8"))
    assert report.hidden_nodes_pruned == 1
    assert "display:none" in report.pruned_reasons
    assert report.links_disarmed == 0
    assert "[link](https://example.com)" in report.output_markdown


def test_lone_surrogate_rejection_before_utf8_encode() -> None:
    """Verify lone surrogate characters raise INVALID_UTF8_SURROGATE before byte encode."""
    # Isolated high surrogate
    with pytest.raises(ContentNormalizeError) as exc_info:
        normalize_inspect("\ud800")
    assert exc_info.value.code == "INVALID_UTF8_SURROGATE"

    # Embedded low surrogate in text
    with pytest.raises(ContentNormalizeError) as exc_info:
        normalize_inspect("prefix \udfff suffix")
    assert exc_info.value.code == "INVALID_UTF8_SURROGATE"

    # Surrogate via normalize_markdown alias
    with pytest.raises(ContentNormalizeError) as exc_info:
        normalize_markdown("\ud83d")
    assert exc_info.value.code == "INVALID_UTF8_SURROGATE"

    # Surrogate in plain text mode
    with pytest.raises(ContentNormalizeError) as exc_info:
        normalize_plain_text("plain \udc00 text")
    assert exc_info.value.code == "INVALID_UTF8_SURROGATE"


def test_normalize_markdown_alias() -> None:
    """Verify normalize_markdown is an alias for normalize_to_markdown."""
    assert normalize_markdown is normalize_to_markdown
    text_input = "# Header\n\nSome paragraph text."
    assert normalize_markdown(text_input) == normalize_to_markdown(text_input)
