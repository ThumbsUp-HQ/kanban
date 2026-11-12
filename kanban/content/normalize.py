"""Unified server Markdown ingestion normalizer.

Enforces the Canonical Markdown-Only Database Invariant. Classifies input,
prunes hidden DOM paste-jacking trees BEFORE style removal, sanitizes remaining
HTML via Rust nh3, converts semantic HTML to canonical GFM Markdown, and strips
zero-width and Unicode Plane-14 tag characters.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

import nh3

from kanban.content.hidden_dom import prune_hidden_dom
from kanban.content.html_to_gfm import (
    disarm_dangerous_markdown_links,
    nh3_clean_html,
    nh3_sanitize_and_serialize_gfm,
)
from kanban.content.unicode_guard import (
    SURROGATE_MAX,
    SURROGATE_MIN,
    ContentNormalizeError,
    strip_invisible_and_control_chars,
)

__all__ = [
    "ContentNormalizeError",
    "InputKind",
    "NormalizationReport",
    "normalize_inspect",
    "normalize_markdown",
    "normalize_plain_text",
    "normalize_to_markdown",
]

InputKind = Literal["auto", "markdown", "html", "plain"]

HTML_DETECTION_PATTERN = re.compile(
    r"<(?:html|body|div|p|table|ul|ol|h[1-6]|span|pre|blockquote|section|article|a|img|style|script)\b|<!--",
    re.IGNORECASE,
)

SEMANTIC_TAGS: frozenset[str] = frozenset(
    {
        "a",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "img",
        "blockquote",
        "hr",
        "details",
        "summary",
        "input",
        "p",
        "section",
        "article",
    }
)

IDE_ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "div",
        "pre",
        "span",
        "br",
        "code",
        "#text",
    }
)

DEFAULT_MAX_INPUT_BYTES = 2_097_152
DEFAULT_PLAIN_MAX_INPUT_BYTES = 65_536


@dataclass(frozen=True)
class NormalizationReport:
    """Forensic report returned by normalize_inspect."""

    input_kind: InputKind
    input_bytes: int
    output_bytes: int
    zero_width_stripped: int
    control_chars_stripped: int
    hidden_nodes_pruned: int
    pruned_reasons: list[str]
    links_disarmed: int
    output_markdown: str


class _IdeDetectorNode:
    """Lightweight node for inspecting IDE wrapper candidates."""

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        """Initialize IDE detector node."""
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[_IdeDetectorNode] = []
        self.text: str = ""


class _IdeDetectorParser(HTMLParser):
    """Parses pruned HTML to inspect structure for IDE syntax-highlighted blocks."""

    VOID_TAGS = frozenset({"br", "hr", "img", "input"})

    def __init__(self) -> None:
        """Initialize parser with root."""
        super().__init__()
        self.root = _IdeDetectorNode("[root]")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening tag."""
        attr_dict = {k: v for k, v in attrs if v is not None}
        node = _IdeDetectorNode(tag.lower(), attr_dict)
        self.stack[-1].children.append(node)
        if node.tag not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        """Handle closing tag."""
        t = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == t:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data: str) -> None:
        """Handle text data."""
        node = _IdeDetectorNode("#text")
        node.text = data
        self.stack[-1].children.append(node)


def _check_ide_descendants(node: _IdeDetectorNode) -> bool:
    """Return True if all descendants are purely IDE wrapper elements without semantic tags."""
    if node.tag in SEMANTIC_TAGS or node.tag not in IDE_ALLOWED_TAGS:
        return False
    return all(_check_ide_descendants(c) for c in node.children)


def _extract_ide_code_lines(node: _IdeDetectorNode, lines: list[str]) -> None:
    """Recursively extract code lines from IDE elements."""
    if node.tag == "#text":
        lines[-1] += node.text
    elif node.tag == "br":
        lines.append("")
    elif node.tag == "div":
        if lines[-1]:
            lines.append("")
        for c in node.children:
            _extract_ide_code_lines(c, lines)
        if lines[-1]:
            lines.append("")
    else:
        for c in node.children:
            _extract_ide_code_lines(c, lines)


def _detect_and_bypass_ide_wrapper(pruned_html: str) -> tuple[bool, str]:
    """Detect if pruned HTML is an IDE syntax-highlighted block and extract code.

    Specification S5.2 item 2: If HTML input consists solely of a single outer div or pre
    containing only span / br elements with inline color/font styles and zero semantic tags,
    extract visible text lines and emit a canonical fenced code block directly.
    """
    parser = _IdeDetectorParser()
    parser.feed(pruned_html)
    parser.close()

    root_elements = [c for c in parser.root.children if c.tag != "#text" or c.text.strip()]
    if len(root_elements) != 1:
        return False, ""

    top = root_elements[0]
    if top.tag not in {"div", "pre"}:
        return False, ""

    if not all(_check_ide_descendants(c) for c in top.children):
        return False, ""

    lines: list[str] = [""]
    for c in top.children:
        _extract_ide_code_lines(c, lines)

    while lines and not lines[-1]:
        lines.pop()

    code_text = "\n".join(lines)
    return True, f"```\n{code_text}\n```"


def _strip_inline_spans(line: str) -> str:
    """Strip text inside inline code spans from a line."""
    tokens = re.split(r"(`+)", line)
    out: list[str] = []
    in_span = False
    span_delim = ""
    for token in tokens:
        if not token:
            continue
        if token.startswith("`"):
            if not in_span:
                in_span = True
                span_delim = token
            elif token == span_delim:
                in_span = False
            continue
        if not in_span:
            out.append(token)
    return " ".join(out)


def _extract_non_code_text(text: str) -> str:
    """Extract concatenated text outside fenced code blocks and inline code spans."""
    lines = text.split("\n")
    out_parts: list[str] = []
    in_code_block = False
    fence_char = ""
    fence_len = 0

    for line in lines:
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            fchars = fence_match.group(1)
            char = fchars[0]
            flen = len(fchars)
            if not in_code_block:
                in_code_block = True
                fence_char = char
                fence_len = flen
                continue
            if char == fence_char and flen >= fence_len:
                in_code_block = False
                continue

        if not in_code_block:
            out_parts.append(_strip_inline_spans(line))

    return " ".join(out_parts)


def _classify_input(text: str) -> Literal["html", "markdown"]:
    """Classify input as html or markdown based on balanced semantic tags outside code."""
    non_code = _extract_non_code_text(text)
    if HTML_DETECTION_PATTERN.search(non_code):
        return "html"
    return "markdown"


def _normalize_plain(text: str, max_input_bytes: int) -> tuple[str, int, int, int, list[str], int]:
    """Normalize input to single-line plain text."""
    clean_str, zw_count, ctrl_count = strip_invisible_and_control_chars(
        text, max_input_bytes=max_input_bytes
    )
    stripped_tags = nh3.clean(clean_str, tags=set())
    unescaped = html.unescape(stripped_tags)
    clean_again, zw2, ctrl2 = strip_invisible_and_control_chars(
        unescaped, max_input_bytes=max_input_bytes
    )
    single_line = re.sub(r"\s+", " ", clean_again).strip()
    return single_line, zw_count + zw2, ctrl_count + ctrl2, 0, [], 0


def _normalize_html_content(
    clean_text: str,
) -> tuple[str, int, list[str], int]:
    """Process HTML content through Step A pruner, IDE check, nh3, and GFM serialization."""
    pruned_html, pruned_records = prune_hidden_dom(clean_text)
    hidden_count = len(pruned_records)
    reasons = [r["reason"] for r in pruned_records]

    is_ide, fenced_code = _detect_and_bypass_ide_wrapper(pruned_html)
    if is_ide:
        return fenced_code, hidden_count, reasons, 0

    gfm = nh3_sanitize_and_serialize_gfm(pruned_html)
    disarmed_gfm, disarmed_count = disarm_dangerous_markdown_links(gfm)
    return disarmed_gfm, hidden_count, reasons, disarmed_count


def _process_markdown_segment(
    segment: str,
) -> tuple[str, int, list[str], int]:
    """Sanitize embedded HTML tags and disarm dangerous links within a markdown segment."""
    hidden_count = 0
    reasons: list[str] = []
    text = segment

    if "<" in text:
        pruned, records = prune_hidden_dom(text)
        hidden_count += len(records)
        reasons.extend(r["reason"] for r in records)
        text = nh3_clean_html(pruned)

    disarmed_text, disarmed_count = disarm_dangerous_markdown_links(text)
    return disarmed_text, hidden_count, reasons, disarmed_count


def _process_markdown_line_spans(
    line: str,
) -> tuple[str, int, list[str], int]:
    """Process a single markdown line outside code fence, preserving inline code spans."""
    tokens = re.split(r"(`+)", line)
    new_tokens: list[str] = []
    in_span = False
    span_delim = ""
    line_hidden = 0
    line_reasons: list[str] = []
    line_disarmed = 0

    for token in tokens:
        if not token:
            continue
        if token.startswith("`"):
            if not in_span:
                in_span = True
                span_delim = token
            elif token == span_delim:
                in_span = False
            new_tokens.append(token)
            continue

        if in_span:
            new_tokens.append(token)
            continue

        seg_out, h_cnt, seg_reasons, d_cnt = _process_markdown_segment(token)
        line_hidden += h_cnt
        line_reasons.extend(seg_reasons)
        line_disarmed += d_cnt
        new_tokens.append(seg_out)

    return "".join(new_tokens), line_hidden, line_reasons, line_disarmed


def _normalize_markdown_content(
    clean_text: str,
) -> tuple[str, int, list[str], int]:
    """Process markdown input preserving code fences/spans while sanitizing embedded markup."""
    lines = clean_text.split("\n")
    out_lines: list[str] = []
    in_code_block = False
    fence_char = ""
    fence_len = 0
    total_hidden = 0
    total_reasons: list[str] = []
    total_disarmed = 0

    for line in lines:
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            fchars = fence_match.group(1)
            char = fchars[0]
            flen = len(fchars)
            if not in_code_block:
                in_code_block = True
                fence_char = char
                fence_len = flen
                out_lines.append(line)
                continue
            if char == fence_char and flen >= fence_len:
                in_code_block = False
                out_lines.append(line)
                continue

        if in_code_block:
            out_lines.append(line)
            continue

        line_out, h_cnt, reasons, d_cnt = _process_markdown_line_spans(line)
        total_hidden += h_cnt
        total_reasons.extend(reasons)
        total_disarmed += d_cnt
        out_lines.append(line_out)

    assembled = "\n".join(out_lines)
    normalized = re.sub(r"\n{3,}", "\n\n", assembled).strip()
    return normalized, total_hidden, total_reasons, total_disarmed


def normalize_inspect(
    raw: str,
    *,
    mode: Literal["auto", "markdown", "html", "plain"] = "auto",
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
) -> NormalizationReport:
    """Inspect and normalize input, returning a detailed forensic report.

    Args:
        raw: Raw input content string.
        mode: Ingestion mode ('auto', 'markdown', 'html', 'plain').
        max_input_bytes: Maximum allowed UTF-8 byte length.

    Returns:
        NormalizationReport containing metrics and canonical markdown output.

    Raises:
        ContentNormalizeError: If input size, complexity, or surrogate boundaries are violated.

    """
    for ch in raw:
        if SURROGATE_MIN <= ord(ch) <= SURROGATE_MAX:
            err_code = "INVALID_UTF8_SURROGATE"
            raise ContentNormalizeError(err_code)

    input_bytes = len(raw.encode("utf-8"))

    if mode == "plain":
        output_text, zw, ctrl, hid, reasons, disarmed = _normalize_plain(
            raw, max_input_bytes=max_input_bytes
        )
        return NormalizationReport(
            input_kind="plain",
            input_bytes=input_bytes,
            output_bytes=len(output_text.encode("utf-8")),
            zero_width_stripped=zw,
            control_chars_stripped=ctrl,
            hidden_nodes_pruned=hid,
            pruned_reasons=reasons,
            links_disarmed=disarmed,
            output_markdown=output_text,
        )

    clean_text, zw, ctrl = strip_invisible_and_control_chars(raw, max_input_bytes=max_input_bytes)

    effective_kind: Literal["html", "markdown"]
    if mode == "auto":
        effective_kind = _classify_input(clean_text)
    elif mode == "html":
        effective_kind = "html"
    else:
        effective_kind = "markdown"

    if effective_kind == "html":
        out_md, hid, reasons, disarmed = _normalize_html_content(clean_text)
    else:
        out_md, hid, reasons, disarmed = _normalize_markdown_content(clean_text)

    return NormalizationReport(
        input_kind=effective_kind,
        input_bytes=input_bytes,
        output_bytes=len(out_md.encode("utf-8")),
        zero_width_stripped=zw,
        control_chars_stripped=ctrl,
        hidden_nodes_pruned=hid,
        pruned_reasons=reasons,
        links_disarmed=disarmed,
        output_markdown=out_md,
    )


def normalize_to_markdown(
    raw: str,
    *,
    mode: Literal["auto", "markdown", "html", "plain"] = "auto",
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
) -> str:
    """Normalize input string to canonical GFM Markdown."""
    report = normalize_inspect(raw, mode=mode, max_input_bytes=max_input_bytes)
    return report.output_markdown


normalize_markdown = normalize_to_markdown


def normalize_plain_text(
    raw: str,
    *,
    max_input_bytes: int = DEFAULT_PLAIN_MAX_INPUT_BYTES,
) -> str:
    """Normalize input string to single-line sanitized plain text."""
    report = normalize_inspect(raw, mode="plain", max_input_bytes=max_input_bytes)
    return report.output_markdown
