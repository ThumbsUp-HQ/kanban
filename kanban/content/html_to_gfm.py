"""Step B: Rust nh3 Sanitization, URI Allowlist, and Canonical GFM Serializer.

Sanitizes HTML using nh3 with a strict 32-tag allowlist and safe relative URL
filter, disarms dangerous link schemes, and serializes the AST to canonical
GitHub-Flavored Markdown.
"""

from __future__ import annotations

import contextlib
import html
import re
import urllib.parse
from html.parser import HTMLParser

import nh3

# Strict 32-tag allowlist permitted by specification S5.2 item 4
ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "br",
        "hr",
        "strong",
        "b",
        "em",
        "i",
        "del",
        "s",
        "code",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "li",
        "input",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "a",
        "img",
        "details",
        "summary",
    }
)

ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "code": {"class"},
    "input": {"type", "checked", "disabled"},
    "th": {"colspan", "rowspan", "align"},
    "td": {"colspan", "rowspan", "align"},
    "details": {"open"},
}

DANGEROUS_SCHEME_PREFIXES: tuple[str, ...] = (
    "javascript:",
    "vbscript:",
    "data:",
    "file:",
    "blob:",
)

ALLOWED_SCHEME_PREFIXES: tuple[str, ...] = (
    "https://",
    "mailto:",
    "attachment://",
)

DEL_CODE_POINT = 127
SPACE_CODE_POINT = 32


def _url_relative_filter(url: str) -> str | None:
    r"""Allow only safe same-origin relative #fragment and /path matching ^/(?![/\\])."""
    if url.startswith("#"):
        return url
    if re.match(r"^/(?![/\\])", url):
        return url
    return None


def _attribute_filter(tag: str, attr: str, value: str) -> str | None:
    """Filter attributes: class permitted only on code, type=checkbox only on input."""
    if tag == "code" and attr == "class":
        if re.match(r"^language-[a-z0-9_+-]{1,32}$", value):
            return value
        return None
    if tag == "input" and attr == "type":
        if value.lower() == "checkbox":
            return "checkbox"
        return None
    return value


def nh3_clean_html(html_content: str) -> str:
    """Sanitize HTML fragment using nh3 with strict allowlist and relative URL filter."""
    return nh3.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"https", "mailto", "attachment"},
        url_relative=_url_relative_filter,
        attribute_filter=_attribute_filter,
        link_rel=None,
    )


def _has_dangerous_scheme(clean_url_lower: str) -> bool:
    """Return True if clean URL starts with a banned scheme or tricky prefix."""
    for bad in DANGEROUS_SCHEME_PREFIXES:
        if clean_url_lower.startswith(bad):
            return True
    return clean_url_lower.startswith(("//", "/\\", "\\"))


def is_safe_url(raw_url: str) -> bool:
    """Return True if URL is allowed, False if dangerous or disallowed.

    Allowed schemes: https, mailto, attachment, and safe relative #frag or /path.
    Explicitly denied: javascript, vbscript, data, file, blob, //protocol-relative.
    """
    if not raw_url:
        return False

    url = raw_url.strip()
    if url.startswith("<") and url.endswith(">"):
        url = url[1:-1].strip()

    url = html.unescape(url).strip()
    with contextlib.suppress(Exception):
        url = urllib.parse.unquote(url)

    clean_url = "".join(c for c in url if ord(c) > SPACE_CODE_POINT and ord(c) != DEL_CODE_POINT)
    clean_url_lower = clean_url.lower()

    if _has_dangerous_scheme(clean_url_lower):
        return False

    if clean_url.startswith("#") or re.match(r"^/(?![/\\])", clean_url):
        return True

    return any(clean_url_lower.startswith(sch) for sch in ALLOWED_SCHEME_PREFIXES)


def _extract_url_from_target(target: str) -> str:
    """Extract raw URL part from a markdown link target (url "optional title")."""
    target = target.strip()
    if target.startswith("<"):
        m = re.match(r"^<([^>]+)>", target)
        if m:
            return m.group(1).strip()
    parts = target.split(None, 1)
    return parts[0] if parts else ""


def _find_matching_paren(token: str, paren_start: int) -> int:
    """Find matching close parenthesis taking nested parens into account."""
    paren_depth = 0
    for idx in range(paren_start, len(token)):
        if token[idx] == "(":
            paren_depth += 1
        elif token[idx] == ")":
            paren_depth -= 1
            if paren_depth == 0:
                return idx
    return -1


def _disarm_token_links(token: str) -> tuple[str, int]:
    """Scan token for markdown links/images and disarm dangerous schemes."""
    pos = 0
    disarmed = 0
    res: list[str] = []
    while pos < len(token):
        start_bracket = -1
        if token[pos : pos + 2] == "![":
            start_bracket = pos + 1
        elif token[pos] == "[":
            start_bracket = pos

        if start_bracket == -1:
            res.append(token[pos])
            pos += 1
            continue

        end_bracket = token.find("]", start_bracket)
        if end_bracket == -1 or end_bracket + 1 >= len(token) or token[end_bracket + 1] != "(":
            res.append(token[pos])
            pos += 1
            continue

        paren_start = end_bracket + 1
        paren_end = _find_matching_paren(token, paren_start)
        if paren_end == -1:
            res.append(token[pos])
            pos += 1
            continue

        label = token[start_bracket + 1 : end_bracket]
        target = token[paren_start + 1 : paren_end]
        url = _extract_url_from_target(target)

        if is_safe_url(url):
            res.append(token[pos : paren_end + 1])
        else:
            disarmed += 1
            res.append(label)

        pos = paren_end + 1

    return "".join(res), disarmed


def _disarm_line_spans(line: str) -> tuple[str, int]:
    """Process line tokens, preserving inline code spans."""
    tokens = re.split(r"(`+)", line)
    new_tokens: list[str] = []
    in_code_span = False
    span_delim = ""
    disarmed_count = 0

    for token in tokens:
        if not token:
            continue
        if token.startswith("`"):
            if not in_code_span:
                in_code_span = True
                span_delim = token
            elif token == span_delim:
                in_code_span = False
            new_tokens.append(token)
            continue

        if in_code_span:
            new_tokens.append(token)
            continue

        disarmed_text, count = _disarm_token_links(token)
        disarmed_count += count
        new_tokens.append(disarmed_text)

    return "".join(new_tokens), disarmed_count


def disarm_dangerous_markdown_links(markdown: str) -> tuple[str, int]:
    """Disarm dangerous links in markdown outside code blocks and code spans.

    Replaces [label](dangerous_url) with label, and ![alt](dangerous_url) with alt.

    Returns:
        Tuple of (disarmed_markdown, count_of_disarmed_links).

    """
    disarmed_count = 0
    lines = markdown.split("\n")
    out_lines: list[str] = []
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
                out_lines.append(line)
                continue
            if char == fence_char and flen >= fence_len:
                in_code_block = False
                out_lines.append(line)
                continue

        if in_code_block:
            out_lines.append(line)
            continue

        line_out, count = _disarm_line_spans(line)
        disarmed_count += count
        out_lines.append(line_out)

    return "\n".join(out_lines), disarmed_count


class AstNode:
    """Node in sanitized HTML AST."""

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        """Initialize AST node."""
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[AstNode] = []
        self.text: str = ""


class AstBuilder(HTMLParser):
    """Parses sanitized HTML into a lightweight AstNode tree."""

    VOID_TAGS: frozenset[str] = frozenset({"br", "hr", "img", "input"})

    def __init__(self) -> None:
        """Initialize builder with root node."""
        super().__init__()
        self.root = AstNode("[root]")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening element tag."""
        attr_dict = {k: v for k, v in attrs if v is not None}
        node = AstNode(tag.lower(), attr_dict)
        self.stack[-1].children.append(node)
        if node.tag not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        """Handle closing element tag."""
        t = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == t:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data: str) -> None:
        """Handle text data."""
        node = AstNode("#text")
        node.text = data
        self.stack[-1].children.append(node)


def _get_text_content(node: AstNode) -> str:
    """Extract concatenated text content from node subtree."""
    if node.tag == "#text":
        return node.text
    return "".join(_get_text_content(c) for c in node.children)


def _wrap_inline(inner: str, marker: str) -> str:
    """Wrap inline text in markdown markers while preserving outer whitespace."""
    if not inner.strip():
        return inner
    lead_ws = inner[: len(inner) - len(inner.lstrip())]
    trail_ws = inner[len(inner.rstrip()) :]
    core = inner.strip()
    return f"{lead_ws}{marker}{core}{marker}{trail_ws}"


def _serialize_pre(node: AstNode) -> str:
    """Serialize pre/code block to fenced code block."""
    lang = ""
    for c in node.children:
        if c.tag == "code" and "class" in c.attrs:
            m = re.match(r"^language-([a-z0-9_+-]{1,32})$", c.attrs["class"])
            if m:
                lang = m.group(1)
                break
    code_text = _get_text_content(node).strip("\r\n")
    return f"\n\n```{lang}\n{code_text}\n```\n\n"


def _serialize_blockquote(node: AstNode, list_depth: int) -> str:
    """Serialize blockquote lines with > prefix."""
    inner = "".join(_serialize_ast_node(c, list_depth) for c in node.children).strip()
    lines = inner.split("\n")
    quoted_lines = [f"> {line}" if line.strip() else ">" for line in lines]
    return "\n\n" + "\n".join(quoted_lines) + "\n\n"


def _serialize_list(node: AstNode, list_depth: int) -> str:
    """Serialize ul or ol list items to GFM list."""
    out_items: list[str] = []
    is_ordered = node.tag == "ol"
    item_idx = 1
    indent = "  " * list_depth

    for child in node.children:
        if child.tag == "#text" and not child.text.strip():
            continue
        if child.tag != "li":
            continue

        prefix = f"{indent}{item_idx}. " if is_ordered else f"{indent}- "
        item_idx += 1
        has_checkbox = False
        checkbox_checked = False
        li_parts: list[str] = []

        for li_child in child.children:
            if (
                not has_checkbox
                and li_child.tag == "input"
                and li_child.attrs.get("type") == "checkbox"
            ):
                has_checkbox = True
                checkbox_checked = "checked" in li_child.attrs
                continue
            if li_child.tag in {"ul", "ol"}:
                if li_parts:
                    li_parts[-1] = li_parts[-1].rstrip()
                li_parts.append(_serialize_ast_node(li_child, list_depth + 1))
            else:
                li_parts.append(_serialize_ast_node(li_child, list_depth))

        if has_checkbox:
            prefix = f"{indent}- [x] " if checkbox_checked else f"{indent}- [ ] "

        item_text = "".join(li_parts).strip()
        out_items.append(f"{prefix}{item_text}")

    if list_depth > 0:
        return "\n" + "\n".join(out_items)
    return "\n\n" + "\n".join(out_items) + "\n\n"


def _collect_table_rows(
    node: AstNode, list_depth: int, rows: list[list[str]], alignments: list[str]
) -> None:
    """Recursively collect rows and alignments from table elements."""
    if node.tag == "tr":
        cell_texts: list[str] = []
        for cell in node.children:
            if cell.tag in {"th", "td"}:
                t = "".join(_serialize_ast_node(c, list_depth) for c in cell.children).strip()
                t = t.replace("\n", " ").replace("|", "\\|")
                cell_texts.append(t)
                if len(alignments) < len(cell_texts):
                    align = cell.attrs.get("align", "").lower()
                    if align == "center":
                        alignments.append(":---:")
                    elif align == "right":
                        alignments.append("---:")
                    elif align == "left":
                        alignments.append(":---")
                    else:
                        alignments.append("---")
        if cell_texts:
            rows.append(cell_texts)
    else:
        for c in node.children:
            _collect_table_rows(c, list_depth, rows, alignments)


def _serialize_table(node: AstNode, list_depth: int) -> str:
    """Serialize HTML table to GFM pipe table."""
    rows: list[list[str]] = []
    alignments: list[str] = []
    _collect_table_rows(node, list_depth, rows, alignments)
    if not rows:
        return ""

    max_cols = max(len(r) for r in rows)
    if len(alignments) < max_cols:
        alignments.extend(["---"] * (max_cols - len(alignments)))

    lines: list[str] = []
    header = rows[0] + [""] * (max_cols - len(rows[0]))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(alignments[:max_cols]) + " |")
    for r in rows[1:]:
        padded = r + [""] * (max_cols - len(r))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n\n" + "\n".join(lines) + "\n\n"


def _serialize_inline_element(node: AstNode, list_depth: int) -> str:
    """Serialize inline formatting tags."""
    tag = node.tag
    if tag in {"strong", "b"}:
        return _wrap_inline(
            "".join(_serialize_ast_node(c, list_depth) for c in node.children), "**"
        )
    if tag in {"em", "i"}:
        return _wrap_inline("".join(_serialize_ast_node(c, list_depth) for c in node.children), "*")
    if tag in {"del", "s"}:
        return _wrap_inline(
            "".join(_serialize_ast_node(c, list_depth) for c in node.children), "~~"
        )
    if tag == "code":
        inner = "".join(_serialize_ast_node(c, list_depth) for c in node.children)
        return f"`` {inner} ``" if "`" in inner else f"`{inner}`"
    return ""


def _serialize_link_or_image(node: AstNode, list_depth: int) -> str:
    """Serialize a or img elements."""
    if node.tag == "a":
        href = node.attrs.get("href", "")
        inner = "".join(_serialize_ast_node(c, list_depth) for c in node.children).strip()
        if href and is_safe_url(href):
            return f"[{inner}]({href})"
        return inner
    if node.tag == "img":
        src = node.attrs.get("src", "")
        alt = node.attrs.get("alt", "")
        if src and is_safe_url(src):
            return f"![{alt}]({src})"
        return alt
    return ""


def _serialize_details(node: AstNode, list_depth: int) -> str:
    """Serialize details/summary elements."""
    summary_text = "Details"
    body_parts: list[str] = []
    for c in node.children:
        if c.tag == "summary":
            summary_text = _get_text_content(c).strip()
        else:
            body_parts.append(_serialize_ast_node(c, list_depth))
    body = "".join(body_parts).strip()
    return f"\n\n<details>\n<summary>{summary_text}</summary>\n\n{body}\n</details>\n\n"


def _serialize_heading(node: AstNode, list_depth: int) -> str:
    """Serialize heading h1..h6 to markdown."""
    level = int(node.tag[1])
    inner = "".join(_serialize_ast_node(c, list_depth) for c in node.children).strip()
    return f"\n\n{'#' * level} {inner}\n\n"


def _serialize_block(node: AstNode, list_depth: int) -> str:
    """Serialize p, br, hr blocks."""
    if node.tag == "p":
        inner = "".join(_serialize_ast_node(c, list_depth) for c in node.children).strip()
        return f"\n\n{inner}\n\n"
    if node.tag == "br":
        return "\n"
    return "\n\n---\n\n"


def _serialize_compound(node: AstNode, list_depth: int) -> str:
    """Serialize compound containers: pre, blockquote, lists, tables, details."""
    tag = node.tag
    if tag == "pre":
        return _serialize_pre(node)
    if tag == "blockquote":
        return _serialize_blockquote(node, list_depth)
    if tag in {"ul", "ol"}:
        return _serialize_list(node, list_depth)
    if tag == "table":
        return _serialize_table(node, list_depth)
    if tag == "details":
        return _serialize_details(node, list_depth)
    return "".join(_serialize_ast_node(c, list_depth) for c in node.children)


def _serialize_ast_node(node: AstNode, list_depth: int = 0) -> str:
    """Serialize an AstNode to canonical GFM Markdown."""
    tag = node.tag
    if tag == "#text":
        return node.text
    if tag in {"strong", "b", "em", "i", "del", "s", "code"}:
        return _serialize_inline_element(node, list_depth)
    if tag in {"a", "img"}:
        return _serialize_link_or_image(node, list_depth)
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return _serialize_heading(node, list_depth)
    if tag in {"p", "br", "hr"}:
        return _serialize_block(node, list_depth)
    return _serialize_compound(node, list_depth)


def nh3_sanitize_and_serialize_gfm(html_str: str) -> str:
    """Sanitize HTML via nh3 and serialize the resulting AST to canonical GFM Markdown."""
    if not html_str:
        return ""
    cleaned = nh3_clean_html(html_str)
    parser = AstBuilder()
    parser.feed(cleaned)
    parser.close()
    gfm = _serialize_ast_node(parser.root)
    return re.sub(r"\n{3,}", "\n\n", gfm).strip()
