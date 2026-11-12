"""Markdown and content normalization package for Kanban.

Provides canonical Markdown conversion, hidden-DOM paste-jacking pruning,
Rust nh3 sanitization, Unicode/control-character guards, safe URI enforcement,
and server-side SVG geometry sanitization with acyclic DAG validation.
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
from kanban.content.svg_dag import (
    MAX_SVG_EXPANDED_NODES,
    MAX_SVG_USE_DEPTH,
    SvgDagResult,
    SvgSanitizeError,
    validate_svg_use_dag,
)
from kanban.content.svg_sanitizer import (
    ALLOWED_SVG_ATTRS,
    ALLOWED_SVG_ELEMENTS,
    DEFAULT_MAX_SVG_BYTES,
    MAX_COORDINATE_DIMENSION,
    MAX_RAW_ELEMENTS,
    MAX_XML_DEPTH,
    SvgSanitizeReport,
    sanitize_svg,
    sanitize_svg_with_report,
)
from kanban.content.unicode_guard import (
    is_c0_c1_control,
    is_zero_width_or_invisible,
    strip_invisible_and_control_chars,
)

__all__ = [
    "ALLOWED_SVG_ATTRS",
    "ALLOWED_SVG_ELEMENTS",
    "DEFAULT_MAX_SVG_BYTES",
    "MAX_COORDINATE_DIMENSION",
    "MAX_RAW_ELEMENTS",
    "MAX_SVG_EXPANDED_NODES",
    "MAX_SVG_USE_DEPTH",
    "MAX_XML_DEPTH",
    "ContentNormalizeError",
    "InputKind",
    "NormalizationReport",
    "SvgDagResult",
    "SvgSanitizeError",
    "SvgSanitizeReport",
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
    "sanitize_svg",
    "sanitize_svg_with_report",
    "strip_invisible_and_control_chars",
    "validate_svg_use_dag",
]
