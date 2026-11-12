"""Markdown and content normalization package for Kanban.

Provides canonical Markdown conversion, hidden-DOM paste-jacking pruning,
Rust nh3 sanitization, Unicode/control-character guards, and safe URI enforcement.
"""

from __future__ import annotations

from kanban.content.hidden_dom import prune_hidden_dom
from kanban.content.html_to_gfm import (
    disarm_dangerous_markdown_links,
    is_safe_url,
    nh3_clean_html,
    nh3_sanitize_and_serialize_gfm,
)
from kanban.content.normalize import (
    ContentNormalizeError,
    InputKind,
    NormalizationReport,
    normalize_inspect,
    normalize_plain_text,
    normalize_to_markdown,
)
from kanban.content.unicode_guard import (
    is_c0_c1_control,
    is_zero_width_or_invisible,
    strip_invisible_and_control_chars,
)

__all__ = [
    "ContentNormalizeError",
    "InputKind",
    "NormalizationReport",
    "disarm_dangerous_markdown_links",
    "is_c0_c1_control",
    "is_safe_url",
    "is_zero_width_or_invisible",
    "nh3_clean_html",
    "nh3_sanitize_and_serialize_gfm",
    "normalize_inspect",
    "normalize_plain_text",
    "normalize_to_markdown",
    "prune_hidden_dom",
    "strip_invisible_and_control_chars",
]
