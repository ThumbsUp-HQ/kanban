# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for search snippet extraction and heading anchor resolution (KB-P3-17)."""

from __future__ import annotations

from kanban.services.snippets import AnchoredSnippet, build_anchored_snippet


def test_empty_markdown() -> None:
    """Verify empty input returns clean empty AnchoredSnippet."""
    snippet = build_anchored_snippet("", "test")
    assert snippet == AnchoredSnippet(anchor=None, snippet="", match_spans=[])
    assert snippet.to_dict() == {"anchor": None, "snippet": "", "match_spans": []}


def test_heading_anchor_resolution() -> None:
    """Verify nearest preceding ATX heading anchor is resolved."""
    markdown = """# Authentication Architecture
Initial introductory paragraph about identity.

## PKCE (S256)
All public clients must implement Proof Key for Code Exchange (PKCE) with S256.

## Session Management
Session cookies are configured with __Host- prefix.
"""
    result = build_anchored_snippet(markdown, "PKCE")
    assert result.anchor == "#pkce-s256"
    assert "Proof Key for Code Exchange" in result.snippet
    assert len(result.snippet) <= 300
    assert len(result.match_spans) >= 1
    # Check span matches 'PKCE'
    for start, end in result.match_spans:
        assert "pkce" in result.snippet[start:end].lower()


def test_lead_paragraph_without_preceding_heading() -> None:
    """Verify match prior to any ATX heading yields anchor=None."""
    markdown = """OAuth authorization server configuration guide.

# Setup
Instructions follow.
"""
    result = build_anchored_snippet(markdown, "OAuth")
    assert result.anchor is None
    assert "OAuth" in result.snippet


def test_document_without_headings() -> None:
    """Verify content without headings yields anchor=None."""
    markdown = "A plain sticky note discussing database migration scripts."
    result = build_anchored_snippet(markdown, "migration")
    assert result.anchor is None
    assert len(result.match_spans) == 1
    start, end = result.match_spans[0]
    assert result.snippet[start:end].lower() == "migration"


def test_long_document_window_bounds() -> None:
    """Verify excerpt around match in a large document is strictly <= 300 chars."""
    filler_before = "Alpha " * 300  # 1800 chars
    filler_after = " Omega" * 300  # 1800 chars
    target_phrase = "CRITICAL_SECURITY_KEYWORD"
    markdown = f"{filler_before}\n## Security Policy\n{target_phrase}\n{filler_after}"

    result = build_anchored_snippet(markdown, target_phrase, max_chars=300)
    assert len(result.snippet) <= 300
    assert target_phrase in result.snippet
    assert result.anchor == "#security-policy"
    assert len(result.match_spans) == 1
    start, end = result.match_spans[0]
    assert result.snippet[start:end] == target_phrase


def test_html_and_script_sanitization() -> None:
    """Verify raw HTML and script elements are stripped from snippet output."""
    markdown = (
        "### Overview\n"
        "Here is a <script>alert('pwn')</script>dangerous payload with "
        "<b>bold text</b> and <mark>highlight</mark> tags."
    )
    result = build_anchored_snippet(markdown, "dangerous", max_chars=300)
    assert "<script>" not in result.snippet
    assert "</script>" not in result.snippet
    assert "<b>" not in result.snippet
    assert "</b>" not in result.snippet
    assert "<mark>" not in result.snippet
    assert "</mark>" not in result.snippet
    assert "dangerous" in result.snippet


def test_control_characters_in_query() -> None:
    """Verify control characters in user query do not cause errors."""
    markdown = "Safe system authorization using PKCE protocol."
    result = build_anchored_snippet(markdown, "PKCE\x00\x08\x1f")
    assert "PKCE" in result.snippet
    assert len(result.match_spans) >= 1


def test_no_match_fallback() -> None:
    """Verify fallback to start of document when query does not match body."""
    markdown = "Some content about database query indexing and performance."
    result = build_anchored_snippet(markdown, "unmatched_query_string", max_chars=30)
    assert result.anchor is None
    assert len(result.snippet) <= 30
    assert result.match_spans == []


def test_token_only_match_and_overlapping_spans() -> None:
    """Verify token matching when full query phrase does not match, and span merging."""
    markdown = "Protocol details covering oauth authentication."
    # Query phrase "oauth authorization" is not present, but token "oauth" is
    result = build_anchored_snippet(markdown, "oauth authorization")
    assert "oauth" in result.snippet
    assert len(result.match_spans) >= 1


def test_match_near_end_of_long_document() -> None:
    """Verify start index shifts left when match is near the end of a long document."""
    filler = "Filler sentence. " * 50  # ~850 chars
    markdown = f"{filler}Tail keyword found here."
    result = build_anchored_snippet(markdown, "Tail keyword", max_chars=100)
    assert len(result.snippet) <= 100
    assert "Tail keyword" in result.snippet
    assert len(result.match_spans) >= 1


def test_query_without_alphanumeric_tokens() -> None:
    """Verify query with only punctuation handles cleanly."""
    markdown = "Some document body."
    result = build_anchored_snippet(markdown, "???")
    assert result.anchor is None
    assert result.snippet == markdown
    assert result.match_spans == []


def test_overlapping_token_spans() -> None:
    """Verify overlapping token matches merge properly."""
    markdown = "Protocol details covering authentication."
    result = build_anchored_snippet(markdown, "auth authentication")
    assert "authentication" in result.snippet
    assert len(result.match_spans) == 1
