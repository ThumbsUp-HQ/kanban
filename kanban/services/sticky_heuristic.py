# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Sticky complexity heuristics and snooze evaluation (S8.1, S8.2, KB-P3-15).

Evaluates 5 complexity triggers outside fenced code blocks (with fence checks in trigger 4),
calculates >= 1.5x integer snooze growth thresholds, and determines promotion recommendations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import uuid

__all__ = [
    "PromotionAssessment",
    "evaluate_sticky_promotion",
]

_MAX_CHAR_LENGTH: Final[int] = 600
_MAX_LINE_COUNT: Final[int] = 10
_MIN_HEADINGS: Final[int] = 2
_MAX_CODE_FENCE_LINES: Final[int] = 6
_MIN_OUTBOUND_LINKS: Final[int] = 3

_FENCE_START_RE: Final[re.Pattern[str]] = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^ {0,3}#{1,6}\s+\S")
_GFM_DELIMITER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$"
)
_MD_LINK_RE: Final[re.Pattern[str]] = re.compile(r"\[[^\]]+\]\([^\s)]+\)")
_AUTOLINK_RE: Final[re.Pattern[str]] = re.compile(r"<(?:https?|mailto):[^>]+>")
_ISSUE_REF_RE: Final[re.Pattern[str]] = re.compile(r"\[([A-Za-z0-9_]+-\d+)\]")
_SVG_REF_RE: Final[re.Pattern[str]] = re.compile(r"\.svg(?:[?#\s\"')\]>]|$)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PromotionAssessment:
    """Outcome of evaluating sticky promotion complexity heuristics."""

    recommended: bool
    triggers: list[str]
    snoozed: bool


@dataclass(slots=True)
class _BlockAnalysis:
    """Aggregated structural metrics extracted from markdown parsing."""

    heading_count: int = 0
    outbound_link_count: int = 0
    has_gfm_table: bool = False
    has_mermaid: bool = False
    has_svg: bool = False
    has_large_code_fence: bool = False


def _count_outbound_links(text_line: str) -> int:
    """Count Markdown links, autolinks, and bracketed issue keys on an outside-fence line."""
    md_matches = _MD_LINK_RE.findall(text_line)
    md_count = len(md_matches)
    line_no_md = _MD_LINK_RE.sub(" ", text_line)

    auto_matches = _AUTOLINK_RE.findall(line_no_md)
    auto_count = len(auto_matches)
    line_no_auto = _AUTOLINK_RE.sub(" ", line_no_md)

    issue_matches = _ISSUE_REF_RE.findall(line_no_auto)
    issue_count = len(issue_matches)

    return md_count + auto_count + issue_count


def _handle_outside_fence_line(line: str, res: _BlockAnalysis, *, prev_pipe: bool) -> bool:
    """Process a markdown line outside any code fence and update analysis metrics."""
    if _HEADING_RE.match(line):
        res.heading_count += 1
    if prev_pipe and _GFM_DELIMITER_RE.match(line):
        res.has_gfm_table = True
    if _SVG_REF_RE.search(line):
        res.has_svg = True
    res.outbound_link_count += _count_outbound_links(line)
    return "|" in line


def _analyze_blocks(body_markdown: str) -> _BlockAnalysis:
    """Scan markdown line by line, distinguishing outside-fence vs. inside-fence constructs."""
    res = _BlockAnalysis()
    lines = body_markdown.splitlines()
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_inner_lines = 0
    prev_line_has_pipe = False

    for line in lines:
        if not in_fence:
            fence_match = _FENCE_START_RE.match(line)
            if fence_match:
                chars = fence_match.group(1)
                info = fence_match.group(2).strip().lower()
                in_fence = True
                fence_char = chars[0]
                fence_len = len(chars)
                fence_inner_lines = 0
                prev_line_has_pipe = False
                if info.startswith("mermaid"):
                    res.has_mermaid = True
                continue

            prev_line_has_pipe = _handle_outside_fence_line(line, res, prev_pipe=prev_line_has_pipe)
        else:
            close_re = re.compile(rf"^ {{0,3}}\{fence_char}{{{fence_len},}}\s*$")
            if close_re.match(line):
                if fence_inner_lines > _MAX_CODE_FENCE_LINES:
                    res.has_large_code_fence = True
                in_fence = False
            else:
                fence_inner_lines += 1

    if in_fence and fence_inner_lines > _MAX_CODE_FENCE_LINES:
        res.has_large_code_fence = True

    return res


def evaluate_sticky_promotion(
    body_markdown: str,
    snoozed_at_length: int | None = None,
    promoted_to_doc_id: uuid.UUID | None = None,
) -> PromotionAssessment:
    r"""Evaluate complexity heuristics and snooze gate for a sticky note.

    Triggers evaluated:
      1. char_length: len(body_markdown) > 600.
      2. line_count: (body_markdown.count("\n") + (1 if body_markdown else 0)) > 10.
      3. headings: ATX heading count (^#{1,6}\s+\S) >= 2 outside code fences.
      4. structured_block: GFM table, mermaid, svg, or code block > 6 inner lines.
      5. outbound_links: Markdown links, autolinks, and [KEY-123] refs >= 3.
    """
    if promoted_to_doc_id is not None:
        return PromotionAssessment(recommended=False, triggers=[], snoozed=False)

    char_len = len(body_markdown)
    line_cnt = body_markdown.count("\n") + (1 if body_markdown else 0)
    analysis = _analyze_blocks(body_markdown)

    triggers: list[str] = []
    if char_len > _MAX_CHAR_LENGTH:
        triggers.append("char_length")
    if line_cnt > _MAX_LINE_COUNT:
        triggers.append("line_count")
    if analysis.heading_count >= _MIN_HEADINGS:
        triggers.append("headings")
    if (
        analysis.has_gfm_table
        or analysis.has_mermaid
        or analysis.has_svg
        or analysis.has_large_code_fence
    ):
        triggers.append("structured_block")
    if analysis.outbound_link_count >= _MIN_OUTBOUND_LINKS:
        triggers.append("outbound_links")

    raw_triggered = len(triggers) > 0

    if snoozed_at_length is not None:
        if snoozed_at_length == 0:
            snooze_cleared = char_len > 0
        else:
            snooze_cleared = (char_len * 2) >= (snoozed_at_length * 3)
        is_snoozed = not snooze_cleared
    else:
        snooze_cleared = True
        is_snoozed = False

    recommended = raw_triggered and (snoozed_at_length is None or snooze_cleared)

    return PromotionAssessment(
        recommended=recommended,
        triggers=triggers,
        snoozed=is_snoozed,
    )
