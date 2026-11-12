# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for RFC 4515 LDAP filter escaping and RFC 4514 DN normalization (KB-P2-07)."""

from __future__ import annotations

import re

import pytest

import kanban.auth.ldap.escape as esc
from kanban.auth.ldap.escape import (
    FilterAnd,
    FilterLeaf,
    FilterNode,
    FilterNot,
    FilterOr,
    LdapFilterError,
    _get_ast_depth,
    _normalize_ava,
    escape_dn_value,
    escape_filter_chars,
    escape_filter_value,
    normalize_dn,
    parse_filter,
    render_user_filter,
    unescape_dn_value,
)


def test_escape_filter_chars_basic() -> None:
    """Test basic character escaping per RFC 4515 section 3."""
    assert escape_filter_chars("simple") == "simple"
    assert escape_filter_chars(b"bytes_simple") == "bytes_simple"

    # RFC 4515 special characters
    assert escape_filter_chars("*") == r"\2a"
    assert escape_filter_chars("(") == r"\28"
    assert escape_filter_chars(")") == r"\29"
    assert escape_filter_chars("\\") == r"\5c"
    assert escape_filter_chars("\x00") == r"\00"
    assert escape_filter_chars(b"\x00") == r"\00"

    # Alias
    assert escape_filter_value("*") == r"\2a"


def test_escape_filter_chars_strict_ascii() -> None:
    """Test strict_ascii escaping for control and high-byte characters."""
    assert escape_filter_chars("\n", strict_ascii=True) == r"\0a"
    assert escape_filter_chars("\t", strict_ascii=True) == r"\09"
    assert escape_filter_chars("ü", strict_ascii=True) == r"\c3\bc"
    assert escape_filter_chars("ü", strict_ascii=False) == "ü"


def test_escape_filter_injection_payloads() -> None:
    """Test Case 7: Hostile injection payloads are escaped and neutral."""
    payloads = [
        ("admin)(|(uid=*", r"admin\29\28|\28uid=\2a"),
        ("*\x00admin", r"\2a\00admin"),
        (r"\2a(objectClass=*)", r"\5c2a\28objectClass=\2a\29"),
        (r"a\b(c)d*", r"a\5cb\28c\29d\2a"),
    ]
    for raw, expected in payloads:
        assert escape_filter_chars(raw) == expected


def test_render_user_filter_positive() -> None:
    """Test render_user_filter with valid usernames and injection strings."""
    template = "(&(objectClass=person)(uid={username}))"

    # Standard clean username
    rendered = render_user_filter(template, "johndoe")
    assert rendered == "(&(objectClass=person)(uid=johndoe))"

    # Injection payload: must be escaped and preserve AST invariance
    injections = [
        "admin)(|(uid=*",
        "*\x00admin",
        r"\2a(objectClass=*)",
        r"a\b(c)d*",
    ]
    for injection in injections:
        res = render_user_filter(template, injection)
        ast = parse_filter(res)
        assert isinstance(ast, FilterAnd)
        assert len(ast.children) == 2
        assert isinstance(ast.children[0], FilterLeaf)
        assert ast.children[0].attr == "objectClass"
        assert ast.children[0].val == "person"
        assert isinstance(ast.children[1], FilterLeaf)
        assert ast.children[1].attr == "uid"
        assert ast.children[1].val == escape_filter_chars(injection)


def test_render_user_filter_template_validation() -> None:
    """Test template validation errors in render_user_filter."""
    # Missing placeholder
    with pytest.raises(LdapFilterError, match=re.escape("exactly one '{username}'")):
        render_user_filter("(&(objectClass=person)(uid=admin))", "user")

    # Multiple placeholders
    with pytest.raises(LdapFilterError, match=re.escape("exactly one '{username}'")):
        render_user_filter("(&(uid={username})(cn={username}))", "user")


def test_parse_filter_syntax_errors() -> None:
    """Test filter parsing syntax error branches."""
    with pytest.raises(LdapFilterError, match="enclosed in parentheses"):
        parse_filter("objectClass=person")

    with pytest.raises(LdapFilterError, match="Empty filter string"):
        parse_filter("()")

    with pytest.raises(LdapFilterError, match="AND filter must contain at least one child"):
        parse_filter("(&)")

    with pytest.raises(LdapFilterError, match="OR filter must contain at least one child"):
        parse_filter("(|)")

    with pytest.raises(LdapFilterError, match=r"Expected '\(' at index"):
        parse_filter("(&(objectClass=person)invalid)")

    with pytest.raises(LdapFilterError, match="Unbalanced parentheses in child filter"):
        parse_filter("(&(objectClass=person)(uid=foo)")

    with pytest.raises(LdapFilterError, match="Unrecognized filter item"):
        parse_filter("(invalid_leaf_assertion)")


def test_parse_filter_operators_and_not() -> None:
    """Test parsing NOT filters, OR filters, and leaf operators."""
    ast = parse_filter("(!(status=disabled))")
    assert isinstance(ast, FilterNot)
    assert isinstance(ast.child, FilterLeaf)
    assert ast.child.attr == "status"
    assert ast.child.val == "disabled"

    ast_or = parse_filter("(|(cn=alice)(cn=bob))")
    assert isinstance(ast_or, FilterOr)
    assert len(ast_or.children) == 2

    # Leaf operators: >=, <=, ~=, =*, =
    leaf_gte = parse_filter("(age>=18)")
    assert isinstance(leaf_gte, FilterLeaf)
    assert leaf_gte.op == ">="

    leaf_lte = parse_filter("(age<=65)")
    assert isinstance(leaf_lte, FilterLeaf)
    assert leaf_lte.op == "<="

    leaf_approx = parse_filter("(name~=smith)")
    assert isinstance(leaf_approx, FilterLeaf)
    assert leaf_approx.op == "~="

    leaf_pres = parse_filter("(mail=*)")
    assert isinstance(leaf_pres, FilterLeaf)
    assert leaf_pres.op == "=*"


def test_ast_depth_coverage() -> None:
    """Test edge cases in _get_ast_depth."""
    empty_and = FilterAnd(())
    assert _get_ast_depth(empty_and) == 1

    leaf = FilterLeaf(attr="a", op="=", val="b")
    assert _get_ast_depth(leaf) == 1


def test_render_user_filter_invariance_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error when AST counts or depth mismatch."""

    def bad_escape(_v: str) -> str:
        return "a)(uid=injected"

    monkeypatch.setattr(esc, "escape_filter_chars", bad_escape)
    with pytest.raises(LdapFilterError, match="STRUCTURAL_AST_INVARIANCE_VIOLATION"):
        render_user_filter("(&(objectClass=person)(uid={username}))", "evil")


def test_normalize_dn_rfc4514() -> None:
    """Test RFC 4514 DN parsing and normalization."""
    # Empty DN
    assert normalize_dn("") == ""
    assert normalize_dn("   ") == ""

    # Standard DN
    raw = "CN=Core-Backend,OU=Groups,DC=corp,DC=example"
    expected = "cn=core-backend,ou=groups,dc=corp,dc=example"
    assert normalize_dn(raw) == expected

    # Spacing around commas and equals
    raw_spaced = " CN = Core-Backend , OU = Groups , DC = example "
    expected_spaced = "cn=core-backend,ou=groups,dc=example"
    assert normalize_dn(raw_spaced) == expected_spaced

    # Escaped comma in value
    raw_comma = r"CN=Smith\, John,OU=Users,DC=example,DC=com"
    expected_comma = r"cn=smith\, john,ou=users,dc=example,dc=com"
    assert normalize_dn(raw_comma) == expected_comma

    # Quoted string in DN component
    raw_quoted = 'CN="Smith, John",OU=Users,DC=example,DC=com'
    expected_quoted = "cn=smith\\, john,ou=users,dc=example,dc=com"
    assert normalize_dn(raw_quoted) == expected_quoted

    # Multi-valued RDN with +
    raw_multi = "CN=John+OU=Admins,DC=corp"
    expected_multi = "cn=john+ou=admins,dc=corp"
    assert normalize_dn(raw_multi) == expected_multi

    # Attribute value without equals
    assert normalize_dn("invalidAVA,DC=com") == "invalidava,dc=com"

    # Empty AVA component skipped
    assert normalize_dn("CN=User,,DC=com") == "cn=user,dc=com"

    # Escaped character in AVA
    raw_esc_ava = r"CN\=Special=Value,DC=com"
    assert normalize_dn(raw_esc_ava) == r"cn\=special=value,dc=com"


def test_complex_filter_ast_walk_and_depth() -> None:
    """Test render_user_filter with complex AST (AND, OR, NOT)."""
    template = "(&(|(objectClass=person)(objectClass=user))(!(status=disabled))(uid={username}))"
    rendered = render_user_filter(template, "alice")
    assert "uid=alice" in rendered
    ast = parse_filter(rendered)
    assert isinstance(ast, FilterAnd)
    assert len(ast.children) == 3


def test_filter_list_whitespace() -> None:
    """Test whitespace in filter list."""
    ast = parse_filter("(&  (cn=alice)   (mail=bob)   )")
    assert isinstance(ast, FilterAnd)
    assert len(ast.children) == 2


def test_escape_edge_coverage() -> None:
    """Test edge cases in AST depth and normalize_ava."""

    class CustomNode(FilterNode):
        pass

    assert _get_ast_depth(CustomNode()) == 1
    assert _normalize_ava("") == ""
    assert _normalize_ava("   ") == ""


def test_escape_and_unescape_dn_value() -> None:
    """Test escape_dn_value and unescape_dn_value."""
    # Special characters
    specials = r",+\"<\>;="
    escaped = escape_dn_value(specials)
    for ch in specials:
        assert f"\\{ch}" in escaped

    # Leading/trailing space and leading #
    assert escape_dn_value(" space ") == r"\ space\ "
    assert escape_dn_value("#tag") == r"\#tag"
    assert escape_dn_value("mid#tag") == "mid#tag"
    assert escape_dn_value("\x00") == r"\00"

    # Unescape
    assert unescape_dn_value(r"Smith\, John") == "Smith, John"
    assert unescape_dn_value(r"\#123") == "#123"
    # Hex escape: \c4\8d is č
    assert unescape_dn_value(r"Lu\c4\8di\c4\87") == "Lučić"
