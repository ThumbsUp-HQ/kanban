# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Markdown section parsing and surgical section patching (S11.3 item 3, KB-P4-08)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from mcp.errors import KbMcpError, McpErrorCode

__all__ = [
    "AtxHeading",
    "extract_atx_headings",
    "patch_markdown_section",
]

_ATX_HEADING_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$"
)
_FENCE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[ \t]*(```|~~~)")


@dataclass(frozen=True, slots=True)
class AtxHeading:
    """Represents a parsed ATX heading outside fenced code blocks."""

    level: int
    text: str
    line_index: int
    raw_line: str


def extract_atx_headings(body: str) -> list[AtxHeading]:
    """Extract all ATX headings outside fenced code blocks."""
    lines = body.splitlines()
    headings: list[AtxHeading] = []
    in_fence = False
    fence_marker: str | None = None

    for idx, line in enumerate(lines):
        # Check code fence toggle
        fence_match = _FENCE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker == marker:
                in_fence = False
                fence_marker = None
            continue

        if in_fence:
            continue

        match = _ATX_HEADING_PATTERN.match(line)
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            headings.append(
                AtxHeading(
                    level=level,
                    text=heading_text,
                    line_index=idx,
                    raw_line=line,
                )
            )

    return headings


def patch_markdown_section(body: str, section_heading: str, replacement: str) -> str:
    """Locate ATX heading matching section_heading and replace its section.

    Args:
        body: The canonical Markdown document.
        section_heading: Case-sensitive heading to locate (e.g. 'PKCE' or '## PKCE').
        replacement: New markdown content for the section.

    Returns:
        The patched Markdown document.

    Raises:
        KbMcpError(SECTION_NOT_FOUND): If no heading matches.
        KbMcpError(AMBIGUOUS_IDENTIFIER): If multiple headings match.

    """
    headings = extract_atx_headings(body)
    cleaned_target = section_heading.lstrip("#").strip()
    target_level = (
        len(section_heading) - len(section_heading.lstrip("#"))
        if section_heading.startswith("#")
        else 0
    )

    # Locate matching headings
    matched: list[AtxHeading] = []
    for h in headings:
        if target_level > 0:
            if h.level == target_level and h.text == cleaned_target:
                matched.append(h)
        elif h.text == cleaned_target:
            matched.append(h)

    if not matched:
        msg = f"Heading '{section_heading}' not found in document"
        raise KbMcpError(McpErrorCode.SECTION_NOT_FOUND, msg)

    if len(matched) > 1:
        msg = (
            f"Multiple headings ({len(matched)}) match '{section_heading}': "
            "cannot patch ambiguously. Use a more specific heading."
        )
        raise KbMcpError(McpErrorCode.AMBIGUOUS_IDENTIFIER, msg)

    target_heading = matched[0]
    lines = body.splitlines()

    # Find the boundary of this section: next heading of level <= target_heading.level
    start_line_idx = target_heading.line_index
    end_line_idx = len(lines)

    for h in headings:
        if h.line_index > start_line_idx and h.level <= target_heading.level:
            end_line_idx = h.line_index
            break

    # Determine whether replacement includes the heading line
    norm_replacement = replacement.strip()
    rep_has_heading = bool(re.match(r"^#{1,6}[ \t]+", norm_replacement))
    slice_start = start_line_idx if rep_has_heading else start_line_idx + 1

    replacement_lines = replacement.splitlines() if replacement else []

    new_lines = lines[:slice_start] + replacement_lines + lines[end_line_idx:]

    # Preserve trailing newline if original document had one
    result = "\n".join(new_lines)
    if body.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result
