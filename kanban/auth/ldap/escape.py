# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RFC 4515 LDAP filter escaping and RFC 4514 DN normalization (KB-P2-07)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "FilterAnd",
    "FilterLeaf",
    "FilterNode",
    "FilterNot",
    "FilterOr",
    "LdapFilterError",
    "escape_dn_value",
    "escape_filter_chars",
    "escape_filter_value",
    "normalize_dn",
    "parse_filter",
    "render_user_filter",
    "unescape_dn_value",
]

BYTE_NUL: Final[int] = 0x00
BYTE_LPAREN: Final[int] = 0x28
BYTE_RPAREN: Final[int] = 0x29
BYTE_ASTERISK: Final[int] = 0x2A
BYTE_BACKSLASH: Final[int] = 0x5C
ASCII_PRINT_MIN: Final[int] = 0x20
ASCII_PRINT_MAX: Final[int] = 0x7E


class LdapFilterError(Exception):
    """Raised when LDAP filter parsing, syntax, or structural invariance fails."""


@dataclass(frozen=True, slots=True)
class FilterNode:
    """Base class for RFC 4515 filter AST nodes."""


@dataclass(frozen=True, slots=True)
class FilterAnd(FilterNode):
    """RFC 4515 AND filter (& (f1) (f2) ...)."""

    children: tuple[FilterNode, ...]


@dataclass(frozen=True, slots=True)
class FilterOr(FilterNode):
    """RFC 4515 OR filter (| (f1) (f2) ...)."""

    children: tuple[FilterNode, ...]


@dataclass(frozen=True, slots=True)
class FilterNot(FilterNode):
    """RFC 4515 NOT filter (! (f))."""

    child: FilterNode


@dataclass(frozen=True, slots=True)
class FilterLeaf(FilterNode):
    """RFC 4515 leaf filter (attr=val, attr>=val, attr<=val, attr~=val, attr=*)."""

    attr: str
    op: str
    val: str


def escape_filter_chars(
    assertion_value: str | bytes,
    strict_ascii: bool = False,  # noqa: FBT001, FBT002
) -> str:
    r"""Escape an assertion value for safe interpolation into an RFC 4515 LDAP filter.

    Escapes:
      \x00 (NUL) -> \00
      * (0x2a)   -> \2a
      ( (0x28)   -> \28
      ) (0x29)   -> \29
      \ (0x5c)   -> \5c
    When strict_ascii is True, any byte < 0x20 or > 0x7e is escaped as \<two-hex-lowercase>.
    """
    raw: bytes = (
        assertion_value.encode("utf-8")
        if isinstance(assertion_value, str)
        else bytes(assertion_value)
    )

    out_parts: list[bytes] = []
    for b in raw:
        if b == BYTE_NUL:
            out_parts.append(b"\\00")
        elif b == BYTE_ASTERISK:
            out_parts.append(b"\\2a")
        elif b == BYTE_LPAREN:
            out_parts.append(b"\\28")
        elif b == BYTE_RPAREN:
            out_parts.append(b"\\29")
        elif b == BYTE_BACKSLASH:
            out_parts.append(b"\\5c")
        elif strict_ascii and (b < ASCII_PRINT_MIN or b > ASCII_PRINT_MAX):
            out_parts.append(f"\\{b:02x}".encode("ascii"))
        else:
            out_parts.append(bytes([b]))
    return b"".join(out_parts).decode("utf-8", errors="surrogateescape")


# Alias per ticket specification
escape_filter_value = escape_filter_chars


def _parse_leaf(inner: str) -> FilterLeaf:
    """Parse a single leaf assertion item (e.g. attr=val, attr>=val)."""
    for op in (">=", "<=", "~="):
        if op in inner:
            parts = inner.split(op, 1)
            return FilterLeaf(attr=parts[0].strip(), op=op, val=parts[1].strip())
    if "=*" in inner:
        parts = inner.split("=*", 1)
        return FilterLeaf(attr=parts[0].strip(), op="=*", val="")
    if "=" in inner:
        parts = inner.split("=", 1)
        return FilterLeaf(attr=parts[0].strip(), op="=", val=parts[1].strip())

    msg = f"Unrecognized filter item: {inner}"
    raise LdapFilterError(msg)


def parse_filter(filter_str: str) -> FilterNode:
    """Parse an RFC 4515 filter string into an AST."""
    cleaned = filter_str.strip()
    if not (cleaned.startswith("(") and cleaned.endswith(")")):
        msg = "Filter must be enclosed in parentheses"
        raise LdapFilterError(msg)
    inner = cleaned[1:-1].strip()
    if not inner:
        msg = "Empty filter string"
        raise LdapFilterError(msg)

    if inner.startswith("&"):
        children = _parse_filter_list(inner[1:].strip())
        if not children:
            msg = "AND filter must contain at least one child filter"
            raise LdapFilterError(msg)
        return FilterAnd(tuple(children))
    if inner.startswith("|"):
        children = _parse_filter_list(inner[1:].strip())
        if not children:
            msg = "OR filter must contain at least one child filter"
            raise LdapFilterError(msg)
        return FilterOr(tuple(children))
    if inner.startswith("!"):
        return FilterNot(parse_filter(inner[1:].strip()))

    return _parse_leaf(inner)


def _parse_filter_list(s: str) -> list[FilterNode]:
    """Parse a sequence of parenthesized child filters: (f1)(f2)..."""
    children: list[FilterNode] = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break
        if s[i] != "(":
            msg = f"Expected '(' at index {i} in filter list: {s[i : i + 20]}"
            raise LdapFilterError(msg)
        start = i
        depth = 0
        while i < n:
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        if depth != 0:
            msg = "Unbalanced parentheses in child filter"
            raise LdapFilterError(msg)
        child_str = s[start:i]
        children.append(parse_filter(child_str))
    return children


def _get_ast_counts(node: FilterNode) -> dict[str, int]:
    """Count operator frequencies in a filter AST."""
    counts = {"AND": 0, "OR": 0, "NOT": 0, "LEAF": 0}

    def walk(n: FilterNode) -> None:
        if isinstance(n, FilterAnd):
            counts["AND"] += 1
            for c in n.children:
                walk(c)
        elif isinstance(n, FilterOr):
            counts["OR"] += 1
            for c in n.children:
                walk(c)
        elif isinstance(n, FilterNot):
            counts["NOT"] += 1
            walk(n.child)
        elif isinstance(n, FilterLeaf):
            counts["LEAF"] += 1

    walk(node)
    return counts


def _get_ast_depth(node: FilterNode) -> int:
    """Compute maximum depth of a filter AST."""
    if isinstance(node, (FilterAnd, FilterOr)):
        if not node.children:
            return 1
        return 1 + max(_get_ast_depth(c) for c in node.children)
    if isinstance(node, FilterNot):
        return 1 + _get_ast_depth(node.child)
    if isinstance(node, FilterLeaf):
        return 1
    return 1


def render_user_filter(template: str, username: str) -> str:
    """Substitute {username} into template with RFC 4515 escaping and verify AST invariance.

    Guarantees that a hostile username cannot alter the logical tree of the LDAP filter.
    """
    cleaned_template = template.strip()
    if cleaned_template.count("{username}") != 1:
        msg = "Template must contain exactly one '{username}' placeholder"
        raise LdapFilterError(msg)

    dummy_filter = cleaned_template.replace("{username}", "a")
    dummy_ast = parse_filter(dummy_filter)
    dummy_counts = _get_ast_counts(dummy_ast)
    dummy_depth = _get_ast_depth(dummy_ast)

    escaped_username = escape_filter_chars(username)
    rendered_filter = cleaned_template.replace("{username}", escaped_username)
    rendered_ast = parse_filter(rendered_filter)
    rendered_counts = _get_ast_counts(rendered_ast)
    rendered_depth = _get_ast_depth(rendered_ast)

    if dummy_counts != rendered_counts or dummy_depth != rendered_depth:
        msg = (
            f"STRUCTURAL_AST_INVARIANCE_VIOLATION: operator counts or depth mismatch "
            f"(dummy={dummy_counts}, d={dummy_depth}; "
            f"rendered={rendered_counts}, d={rendered_depth})"
        )
        raise LdapFilterError(msg)

    return rendered_filter


_MIN_QUOTED_LENGTH: Final[int] = 2


def unescape_dn_value(val: str) -> str:
    """Unescape an RFC 4514 attribute value."""
    stripped = val.strip()
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= _MIN_QUOTED_LENGTH:
        val = stripped[1:-1]
    out_bytes = bytearray()
    i = 0
    n = len(val)
    while i < n:
        if val[i] == "\\" and i + 1 < n:
            if i + 2 < n and re.match(r"^[0-9a-fA-F]{2}$", val[i + 1 : i + 3]):
                out_bytes.append(int(val[i + 1 : i + 3], 16))
                i += 3
            else:
                out_bytes.extend(val[i + 1].encode("utf-8"))
                i += 2
        else:
            out_bytes.extend(val[i].encode("utf-8"))
            i += 1
    return out_bytes.decode("utf-8", errors="replace").strip()


def escape_dn_value(val: str) -> str:
    """Escape an RFC 4514 attribute value for canonical representation."""
    out: list[str] = []
    for idx, ch in enumerate(val):
        if ch in (",", "+", '"', "\\", "<", ">", ";", "="):
            out.append(f"\\{ch}")
        elif ch == "\x00":
            out.append(r"\00")
        elif ch == " " and (idx == 0 or idx == len(val) - 1):
            out.append(r"\ ")
        elif ch == "#" and idx == 0:
            out.append(r"\#")
        else:
            out.append(ch)
    return "".join(out)


def _split_dn_components(dn: str, delimiter: str = ",") -> list[str]:
    """Split a DN string into components respecting backslash escapes and quotes."""
    parts: list[str] = []
    curr: list[str] = []
    escaped = False
    in_quotes = False
    for ch in dn:
        if escaped:
            curr.append(ch)
            escaped = False
        elif ch == "\\":
            curr.append(ch)
            escaped = True
        elif ch == '"':
            in_quotes = not in_quotes
            curr.append(ch)
        elif ch == delimiter and not in_quotes:
            parts.append("".join(curr))
            curr = []
        else:
            curr.append(ch)
    if curr:
        parts.append("".join(curr))
    return parts


def _normalize_ava(raw_ava: str) -> str:
    """Normalize a single attribute-value assertion."""
    cleaned_ava = raw_ava.strip()
    if not cleaned_ava:
        return ""
    eq_idx = -1
    escaped = False
    for idx, ch in enumerate(cleaned_ava):
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "=":
            eq_idx = idx
            break
    if eq_idx == -1:
        return cleaned_ava.lower()

    attr_type = cleaned_ava[:eq_idx].strip().lower()
    raw_val = cleaned_ava[eq_idx + 1 :].strip()
    unescaped_val = unescape_dn_value(raw_val).lower()
    return f"{attr_type}={escape_dn_value(unescaped_val)}"


def normalize_dn(dn: str) -> str:
    """Parse and normalize an RFC 4514 Distinguished Name for deterministic comparison.

    Normalizes attribute types to lowercase and lowercases attribute values for case-insensitive
    directory matching.
    """
    cleaned = dn.strip()
    if not cleaned:
        return ""

    rdns = _split_dn_components(cleaned, delimiter=",")
    norm_rdns: list[str] = []
    for rdn in rdns:
        avas = _split_dn_components(rdn.strip(), delimiter="+")
        norm_avas: list[str] = []
        for raw_ava in avas:
            norm_ava = _normalize_ava(raw_ava)
            if norm_ava:
                norm_avas.append(norm_ava)
        if norm_avas:
            norm_rdns.append("+".join(norm_avas))
    return ",".join(norm_rdns)
