"""Step A: Hidden-DOM Paste-Jacking Pruner.

Runs BEFORE nh3 strips style attributes. Parses HTML into an inert tree,
enforces complexity caps (depth <= 256, nodes <= 50,000), evaluates visibility
rules against inherited backgrounds, and completely deletes hidden subtrees
and their descendant text.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any

from kanban.content.unicode_guard import ContentNormalizeError

VOID_TAGS: frozenset[str] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

BANNED_TAGS: frozenset[str] = frozenset(
    {
        "script",
        "style",
        "template",
        "noscript",
        "iframe",
        "frame",
        "object",
        "embed",
        "applet",
        "svg",
        "math",
        "meta",
        "link",
        "head",
        "title",
    }
)

CSS_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "silver": (192, 192, 192),
    "maroon": (128, 0, 0),
    "olive": (128, 128, 0),
    "lime": (0, 255, 0),
    "aqua": (0, 255, 255),
    "teal": (0, 128, 128),
    "navy": (0, 0, 128),
}

MAX_NODES = 50_000
MAX_DEPTH = 256
OFF_SCREEN_MIN = -999.0
OFF_SCREEN_MAX = 9999.0
CONTRAST_THRESHOLD = 1.15
OPACITY_THRESHOLD = 0.05
FONT_SIZE_THRESHOLD = 1.0

SRGB_GAMMA_THRESHOLD = 0.04045
SRGB_LINEAR_DIVISOR = 12.92
SRGB_OFFSET = 0.055
SRGB_DIVISOR = 1.055
SRGB_POWER = 2.4

HEX_LEN_3 = 3
HEX_LEN_4 = 4
HEX_LEN_6 = 6
HEX_LEN_8 = 8


def decode_css_escapes(css: str) -> str:
    """Strip CSS comments and decode CSS hex escapes and punctuation escapes."""
    # 1. Strip CSS comments /* ... */
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.DOTALL)
    # 2. Decode hex escapes: \h{1,6}\s?
    css = re.sub(
        r"\\([0-9a-fA-F]{1,6})\s?",
        lambda m: chr(int(m.group(1), 16)),
        css,
    )
    # 3. Decode escaped punctuation and characters
    return re.sub(r"\\([^0-9a-fA-F\r\n\f])", r"\1", css)


def _srgb_to_linear(val: float) -> float:
    """Convert an 8-bit sRGB channel (0-255) to linear luminance."""
    c = val / 255.0
    if c <= SRGB_GAMMA_THRESHOLD:
        return c / SRGB_LINEAR_DIVISOR
    return float(((c + SRGB_OFFSET) / SRGB_DIVISOR) ** SRGB_POWER)


def calculate_relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Calculate relative luminance per WCAG 2.1 formula."""
    r_lin = _srgb_to_linear(rgb[0])
    g_lin = _srgb_to_linear(rgb[1])
    b_lin = _srgb_to_linear(rgb[2])
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def calculate_contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    """Calculate WCAG 2.1 contrast ratio between two RGB colors (returns 1.0 to 21.0)."""
    l1 = calculate_relative_luminance(rgb1)
    l2 = calculate_relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_hex_color(h: str) -> tuple[int, int, int] | None:
    """Parse 3, 4, 6, or 8 character hex color."""
    if len(h) in (HEX_LEN_3, HEX_LEN_4):
        return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16))
    if len(h) in (HEX_LEN_6, HEX_LEN_8):
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return None


def parse_css_color(color_str: str) -> tuple[int, int, int] | None:
    """Parse CSS color string to (r, g, b) tuple or None if unsupported/transparent."""
    raw = color_str.strip().lower()
    if not raw or raw in ("transparent", "currentcolor", "inherit", "initial"):
        return None

    if raw in CSS_NAMED_COLORS:
        return CSS_NAMED_COLORS[raw]

    hex_match = re.match(r"^#([0-9a-f]{3,8})$", raw)
    if hex_match:
        return _parse_hex_color(hex_match.group(1))

    # Handle rgb and rgba syntax
    rgb_match = re.match(
        r"^rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})",
        raw,
    )
    if rgb_match:
        r, g, b = (
            min(255, int(rgb_match.group(1))),
            min(255, int(rgb_match.group(2))),
            min(255, int(rgb_match.group(3))),
        )
        return (r, g, b)

    return None


class DomNode:
    """Inert node in HTML document tree for visibility evaluation."""

    def __init__(
        self,
        tag: str,
        attrs: dict[str, str],
        *,
        is_void: bool = False,
        text_content: str | None = None,
    ) -> None:
        """Initialize DOM node."""
        self.tag = tag.lower()
        self.attrs = attrs
        self.is_void = is_void
        self.text_content = text_content
        self.children: list[DomNode] = []
        self.is_pruned = False
        self.prune_reason: str | None = None


class HiddenDomTreeBuilder(HTMLParser):
    """HTML parser enforcing complexity limits and constructing DomNode tree."""

    def __init__(self) -> None:
        """Initialize parser and tree root."""
        super().__init__(convert_charrefs=False)
        self.root = DomNode(tag="[document]", attrs={})
        self.stack: list[DomNode] = [self.root]
        self.node_count = 0
        self.pruned_comments_count = 0

    def check_limits(self, additional_depth: int = 0) -> None:
        """Verify node count and tree depth remain within bounds."""
        self.node_count += 1
        if self.node_count > MAX_NODES:
            err_code = "HTML_COMPLEXITY_EXCEEDED"
            raise ContentNormalizeError(err_code)
        if len(self.stack) + additional_depth > MAX_DEPTH:
            err_code = "HTML_COMPLEXITY_EXCEEDED"
            raise ContentNormalizeError(err_code)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening HTML tag."""
        t = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        is_void = t in VOID_TAGS
        self.check_limits(additional_depth=0 if is_void else 1)

        node = DomNode(tag=t, attrs=attr_dict, is_void=is_void)
        self.stack[-1].children.append(node)
        if not is_void:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        """Handle closing HTML tag."""
        t = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == t:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data: str) -> None:
        """Handle text data."""
        if not data:
            return
        self.check_limits(additional_depth=0)
        node = DomNode(tag="#text", attrs={}, text_content=data)
        self.stack[-1].children.append(node)

    def handle_comment(self, _data: str) -> None:
        """Handle HTML comment: drop immediately per Rule 1."""
        self.pruned_comments_count += 1


def parse_inline_style_declarations(style_val: str) -> dict[str, str]:
    """Parse inline style attribute into a dictionary of property -> value."""
    decoded = decode_css_escapes(style_val)
    decls: dict[str, str] = {}
    for raw_part in decoded.split(";"):
        part = raw_part.strip()
        if not part or ":" not in part:
            continue
        prop, val = part.split(":", 1)
        decls[prop.strip().lower()] = val.strip().lower()
    return decls


def _check_opacity_and_font(decls: dict[str, str]) -> tuple[bool, str]:
    """Check opacity and font-size rules."""
    if "opacity" in decls:
        op_match = re.match(r"^([0-9]*\.?[0-9]+)%?$", decls["opacity"])
        if op_match:
            op_val = float(op_match.group(1))
            if decls["opacity"].endswith("%"):
                op_val /= 100.0
            if op_val <= OPACITY_THRESHOLD:
                return True, "opacity<=0.05"

    if "font-size" in decls:
        fs_match = re.match(r"^([0-9]*\.?[0-9]+)(?:px|pt|em|rem|%|vw|vh)?$", decls["font-size"])
        if fs_match:
            fs_val = float(fs_match.group(1))
            if fs_val < FONT_SIZE_THRESHOLD:
                return True, "font-size<1"

    return False, ""


def _check_color_and_clip(decls: dict[str, str]) -> tuple[bool, str]:
    """Check transparent color, alpha, and clipping rules."""
    if "color" in decls:
        col = decls["color"]
        if col == "transparent":
            return True, "color:transparent"
        rgba_match = re.match(
            r"^rgba?\(\s*[0-9]+\s*,\s*[0-9]+\s*,\s*[0-9]+\s*,\s*([0-9]*\.?[0-9]+)%?\)",
            col,
        )
        if rgba_match:
            alpha = float(rgba_match.group(1))
            if "%" in col:
                alpha /= 100.0
            if alpha <= OPACITY_THRESHOLD:
                return True, "color:rgba-alpha<=0.05"

    if "clip" in decls and re.search(
        r"rect\(\s*0(?:px)?[\s,]+0(?:px)?[\s,]+0(?:px)?[\s,]+0(?:px)?\s*\)",
        decls["clip"],
    ):
        return True, "clip:rect(0,0,0,0)"

    if "clip-path" in decls and re.search(r"inset\(\s*(?:50|[5-9][0-9]|100)%", decls["clip-path"]):
        return True, "clip-path:inset(>=50%)"

    return False, ""


def _check_zero_box_and_position(decls: dict[str, str]) -> tuple[bool, str]:
    """Check zero-box clipping and off-screen positioning rules."""
    zero_box = any(
        dim in decls and re.match(r"^0(\.0+)?(px|%|em|rem|pt)?$", decls[dim])
        for dim in ("height", "max-height", "width", "max-width")
    )
    if zero_box:
        for ov_prop in ("overflow", "overflow-x", "overflow-y"):
            if ov_prop in decls and decls[ov_prop] in ("hidden", "clip"):
                return True, "zero-box-clipped"

    for pos_prop in ("left", "top", "text-indent"):
        if pos_prop in decls:
            pos_match = re.match(r"^(-?[0-9]+(?:\.[0-9]+)?)(?:px|em|rem|pt)?$", decls[pos_prop])
            if pos_match:
                num = float(pos_match.group(1))
                if num <= OFF_SCREEN_MIN or num >= OFF_SCREEN_MAX:
                    return True, f"off-screen:{pos_prop}"

    return False, ""


def _check_style_contrast(
    decls: dict[str, str], current_bg_rgb: tuple[int, int, int] | None
) -> tuple[bool, str | None]:
    """Check foreground contrast against background color."""
    if "color" in decls and current_bg_rgb is not None:
        parsed_fg = parse_css_color(decls["color"])
        if parsed_fg is not None:
            ratio = calculate_contrast_ratio(parsed_fg, current_bg_rgb)
            if ratio < CONTRAST_THRESHOLD:
                return True, f"low-contrast:{ratio:.2f}"
    return False, None


def _check_simple_style_rules(
    decls: dict[str, str],
) -> tuple[bool, str | None]:
    """Check display, visibility, opacity, font, color, clip, and positioning."""
    if "display" in decls and decls["display"] == "none":
        return True, "display:none"
    if "visibility" in decls and decls["visibility"] in ("hidden", "collapse"):
        return True, f"visibility:{decls['visibility']}"

    for checker in (_check_opacity_and_font, _check_color_and_clip, _check_zero_box_and_position):
        is_bad, reason = checker(decls)
        if is_bad:
            return True, reason
    return False, None


def _check_style_visibility(
    decls: dict[str, str], ancestor_bg_rgb: tuple[int, int, int] | None
) -> tuple[bool, str | None, tuple[int, int, int] | None]:
    """Check visibility rules on style declarations."""
    is_bad, reason = _check_simple_style_rules(decls)
    if is_bad:
        return True, reason, ancestor_bg_rgb

    current_bg_rgb = ancestor_bg_rgb
    bg_val = decls.get("background-color") or decls.get("background")
    if bg_val:
        parsed_bg = parse_css_color(bg_val)
        if parsed_bg is not None:
            current_bg_rgb = parsed_bg

    is_low_contrast, contrast_reason = _check_style_contrast(decls, current_bg_rgb)
    if is_low_contrast:
        return True, contrast_reason, current_bg_rgb

    return False, None, current_bg_rgb


def check_node_visibility(
    node: DomNode, ancestor_bg_rgb: tuple[int, int, int] | None
) -> tuple[bool, str | None, tuple[int, int, int] | None]:
    """Evaluate Step A visibility rules on node.

    Returns:
        (is_hidden, reason_code, effective_bg_rgb)

    """
    if node.tag in BANNED_TAGS:
        return True, f"banned-tag:{node.tag}", ancestor_bg_rgb

    if "hidden" in node.attrs:
        return True, "attr:hidden", ancestor_bg_rgb
    if node.attrs.get("aria-hidden", "").strip().lower() == "true":
        return True, "attr:aria-hidden=true", ancestor_bg_rgb

    if "style" in node.attrs:
        decls = parse_inline_style_declarations(node.attrs["style"])
        return _check_style_visibility(decls, ancestor_bg_rgb)

    return False, None, ancestor_bg_rgb


def evaluate_tree(
    node: DomNode,
    ancestor_bg_rgb: tuple[int, int, int] | None,
    pruned_records: list[dict[str, Any]],
) -> None:
    """Traverse AST and mark nodes/subtrees as pruned based on visibility rules."""
    if node.tag in ("[document]", "#text"):
        for child in node.children:
            evaluate_tree(child, ancestor_bg_rgb, pruned_records)
        return

    is_hidden, reason, effective_bg = check_node_visibility(node, ancestor_bg_rgb)
    if is_hidden:
        node.is_pruned = True
        node.prune_reason = reason
        pruned_records.append(
            {
                "tag": node.tag,
                "reason": reason or "hidden",
                "attrs": dict(node.attrs),
            }
        )
        return

    for child in node.children:
        evaluate_tree(child, effective_bg, pruned_records)


def serialize_unpruned(node: DomNode) -> str:
    """Reconstruct HTML string from unpruned DomNode elements."""
    if node.is_pruned:
        return ""
    if node.tag == "#text":
        return node.text_content or ""
    if node.tag == "[document]":
        return "".join(serialize_unpruned(child) for child in node.children)

    attrs_str = ""
    if node.attrs:
        parts: list[str] = [f'{k}="{html.escape(v, quote=True)}"' for k, v in node.attrs.items()]
        attrs_str = " " + " ".join(parts)

    if node.is_void:
        return f"<{node.tag}{attrs_str}>"

    inner = "".join(serialize_unpruned(child) for child in node.children)
    return f"<{node.tag}{attrs_str}>{inner}</{node.tag}>"


def prune_hidden_dom(html_content: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse HTML and prune hidden DOM subtrees matching Step A security rules.

    Args:
        html_content: Raw input HTML.

    Returns:
        Tuple of (sanitized_html, pruned_records_list).

    Raises:
        ContentNormalizeError: If max depth (256) or max nodes (50,000) is exceeded.

    """
    if not html_content:
        return "", []

    builder = HiddenDomTreeBuilder()
    builder.feed(html_content)
    builder.close()

    pruned_records: list[dict[str, Any]] = [
        {"tag": "#comment", "reason": "html-comment", "attrs": {}}
        for _ in range(builder.pruned_comments_count)
    ]

    evaluate_tree(builder.root, ancestor_bg_rgb=None, pruned_records=pruned_records)
    sanitized_html = serialize_unpruned(builder.root)
    return sanitized_html, pruned_records
