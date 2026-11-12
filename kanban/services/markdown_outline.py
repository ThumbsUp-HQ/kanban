# Copyright 2026 Kanban Platform Contributors
"""Markdown heading outline extractor (S8.1, S12.2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "OutlineEntry",
    "extract_markdown_outline",
]

_HEADING_REGEX: Final[re.Pattern[str]] = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
_FENCE_START_REGEX: Final[re.Pattern[str]] = re.compile(r"^(```+|~~~+)")
_LINK_IMAGE_REGEX: Final[re.Pattern[str]] = re.compile(
    r"!\[([^\]]*)\]\([^)]*\)|\[([^\]]+)\]\([^)]*\)"
)
_INLINE_CODE_REGEX: Final[re.Pattern[str]] = re.compile(r"`([^`]+)`")
_BOLD_ITALIC_REGEX: Final[re.Pattern[str]] = re.compile(r"(\*{1,3}|_{1,3})([^*_]+)\1")
_STRIKE_REGEX: Final[re.Pattern[str]] = re.compile(r"~~([^~]+)~~")
_NON_ALPHANUM_REGEX: Final[re.Pattern[str]] = re.compile(r"[^\w\s-]")
_SPACES_REGEX: Final[re.Pattern[str]] = re.compile(r"[\s-]+")


@dataclass(frozen=True, slots=True)
class OutlineEntry:
    """Single heading outline item with display text, anchor slug, and line number."""

    level: int
    text: str
    anchor: str
    start_line: int

    def to_dict(self) -> dict[str, object]:
        """Serialize outline entry to a standard dictionary."""
        return {
            "level": self.level,
            "text": self.text,
            "anchor": self.anchor,
            "start_line": self.start_line,
        }


def _strip_inline_markdown(text: str) -> str:
    """Remove Markdown formatting characters from heading text."""

    # Replace links [text](url) with text and images ![alt](url) with alt
    def _link_sub(match: re.Match[str]) -> str:
        return match.group(1) or match.group(2) or ""

    cleaned = _LINK_IMAGE_REGEX.sub(_link_sub, text)
    cleaned = _INLINE_CODE_REGEX.sub(r"\1", cleaned)
    cleaned = _BOLD_ITALIC_REGEX.sub(r"\2", cleaned)
    cleaned = _STRIKE_REGEX.sub(r"\1", cleaned)
    return cleaned.strip()


def _slugify_anchor(text: str, seen_counts: dict[str, int]) -> str:
    """Compute deterministic GitHub-style heading anchor with duplicate suffixing."""
    base = _NON_ALPHANUM_REGEX.sub("", text.lower()).strip()
    slug = _SPACES_REGEX.sub("-", base).strip("-")
    if not slug:
        slug = "section"

    count = seen_counts.get(slug, 0)
    seen_counts[slug] = count + 1

    if count == 0:
        return slug
    return f"{slug}-{count}"


class _OutlineParserState:
    """Track fenced code blocks and HTML comments during outline extraction."""

    __slots__ = ("fence_char", "fence_length", "in_html_comment")

    def __init__(self) -> None:
        self.fence_char: str | None = None
        self.fence_length: int = 0
        self.in_html_comment: bool = False

    def should_skip(self, line: str) -> bool:
        """Update comment and fence state; return True if the line should be skipped."""
        if self.in_html_comment:
            if "-->" in line:
                self.in_html_comment = False
            return True

        if line.startswith("<!--"):
            if "-->" not in line:
                self.in_html_comment = True
            return True

        if self.fence_char is not None:
            fence_match = _FENCE_START_REGEX.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if marker[0] == self.fence_char and len(marker) >= self.fence_length:
                    self.fence_char = None
                    self.fence_length = 0
            return True

        fence_match = _FENCE_START_REGEX.match(line)
        if fence_match:
            marker = fence_match.group(1)
            self.fence_char = marker[0]
            self.fence_length = len(marker)
            return True

        return False


def extract_markdown_outline(body_markdown: str) -> list[OutlineEntry]:
    """Extract ATX headings outside fenced code blocks and HTML comments.

    Args:
        body_markdown: Raw UTF-8 Markdown text.

    Returns:
        Ordered list of OutlineEntry objects.

    """
    if not body_markdown:
        return []

    lines = body_markdown.splitlines()
    entries: list[OutlineEntry] = []
    seen_anchors: dict[str, int] = {}
    state = _OutlineParserState()

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if state.should_skip(line):
            continue

        heading_match = _HEADING_REGEX.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            raw_title = heading_match.group(2).strip()
            display_text = _strip_inline_markdown(raw_title)
            anchor = _slugify_anchor(display_text, seen_anchors)
            entries.append(
                OutlineEntry(
                    level=level,
                    text=display_text,
                    anchor=anchor,
                    start_line=idx,
                )
            )

    return entries
