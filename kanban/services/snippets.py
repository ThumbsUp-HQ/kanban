# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Heading-anchored Markdown snippet builder for search results (S11.3, S12.2, KB-P3-17)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from kanban.services.markdown_outline import extract_markdown_outline

__all__ = [
    "AnchoredSnippet",
    "build_anchored_snippet",
]

_CONTROL_CHARS_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f]")
_HTML_SCRIPT_RE: Final[re.Pattern[str]] = re.compile(r"(?i)<script[\s\S]*?</script>")
_HTML_TAGS_RE: Final[re.Pattern[str]] = re.compile(
    r"</?(?:b|mark|strong|em|span|div|p|h[1-6]|script|a|style)[^>]*>",
    flags=re.IGNORECASE,
)
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\w+")
_MIN_TOKEN_LEN: Final[int] = 2


@dataclass(frozen=True, slots=True)
class AnchoredSnippet:
    """Structured excerpt with optional heading anchor and character match spans."""

    anchor: str | None
    snippet: str
    match_spans: list[tuple[int, int]]

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary representation."""
        return {
            "anchor": self.anchor,
            "snippet": self.snippet,
            "match_spans": self.match_spans,
        }


def _clean_markdown(text: str) -> str:
    """Sanitize raw Markdown text, removing script elements and HTML wrapper tags."""
    without_scripts = _HTML_SCRIPT_RE.sub("", text)
    return _HTML_TAGS_RE.sub("", without_scripts)


def _find_match_offsets(
    snippet: str, query_phrase: str, tokens: list[str]
) -> list[tuple[int, int]]:
    """Locate 0-indexed character spans for query matches within a snippet."""
    spans: list[tuple[int, int]] = []
    snippet_lower = snippet.lower()

    if query_phrase and query_phrase in snippet_lower:
        pos = 0
        phrase_len = len(query_phrase)
        while True:
            idx = snippet_lower.find(query_phrase, pos)
            if idx == -1:
                break
            spans.append((idx, idx + phrase_len))
            pos = idx + phrase_len
    elif tokens:
        for token in tokens:
            pos = 0
            token_len = len(token)
            while True:
                idx = snippet_lower.find(token, pos)
                if idx == -1:
                    break
                spans.append((idx, idx + token_len))
                pos = idx + token_len

    spans.sort(key=lambda s: (s[0], s[1]))
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _locate_match_span(clean_lower: str, query_phrase: str, tokens: list[str]) -> tuple[int, int]:
    """Find start and end character offsets of the highest-scoring query match."""
    if query_phrase and query_phrase in clean_lower:
        start = clean_lower.find(query_phrase)
        return start, start + len(query_phrase)
    if tokens:
        for token in tokens:
            pos = clean_lower.find(token)
            if pos != -1:
                return pos, pos + len(token)
    return -1, -1


def _resolve_heading_anchor(markdown: str, clean_md: str, match_start: int) -> str | None:
    """Determine nearest preceding ATX heading anchor above the match."""
    if match_start == -1:
        return None
    match_line = clean_md[:match_start].count("\n") + 1
    outline = extract_markdown_outline(markdown)
    anchor: str | None = None
    for heading in outline:
        if heading.start_line <= match_line:
            anchor = f"#{heading.anchor}"
    return anchor


def _slice_snippet_window(clean_md: str, match_start: int, match_end: int, max_chars: int) -> str:
    """Extract excerpt bounded by max_chars centered around match position."""
    if len(clean_md) <= max_chars:
        return clean_md
    if match_start == -1:
        return clean_md[:max_chars]

    match_len = max(match_end - match_start, 1)
    half_window = (max_chars - match_len) // 2
    start_idx = max(0, match_start - half_window)
    end_idx = min(len(clean_md), start_idx + max_chars)
    if end_idx - start_idx < max_chars and start_idx > 0:
        start_idx = max(0, end_idx - max_chars)
    snippet = clean_md[start_idx:end_idx]
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars]
    return snippet


def build_anchored_snippet(
    markdown: str,
    query: str,
    max_chars: int = 300,
) -> AnchoredSnippet:
    """Build a heading-anchored excerpt around the highest-scoring query match.

    Args:
        markdown: Raw or canonical Markdown document body.
        query: User search query string.
        max_chars: Maximum character length of the returned snippet (default 300).

    Returns:
        AnchoredSnippet containing anchor slug (e.g. ``#pkce-s256``), excerpt <= max_chars,
        and 0-indexed match offsets for client-side highlighting without HTML tags.

    """
    if not markdown:
        return AnchoredSnippet(anchor=None, snippet="", match_spans=[])

    clean_md = _clean_markdown(markdown)
    cleaned_query = _CONTROL_CHARS_RE.sub(" ", query).strip()
    query_phrase = cleaned_query.lower()
    tokens = [t.lower() for t in _TOKEN_RE.findall(cleaned_query) if len(t) >= _MIN_TOKEN_LEN]

    match_start, match_end = _locate_match_span(clean_md.lower(), query_phrase, tokens)
    anchor = _resolve_heading_anchor(markdown, clean_md, match_start)
    snippet = _slice_snippet_window(clean_md, match_start, match_end, max_chars)
    match_spans = _find_match_offsets(snippet, query_phrase, tokens)

    return AnchoredSnippet(
        anchor=anchor,
        snippet=snippet,
        match_spans=match_spans,
    )
