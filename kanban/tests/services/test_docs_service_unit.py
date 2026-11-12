# Copyright 2026 Kanban Platform Contributors
"""Targeted unit tests for internal domain helpers in docs service (S8.1, S12.2)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import DBAPIError

from kanban.api.problems import ProblemException
from kanban.security.permissions import Capability
from kanban.services.docs import (
    _capabilities_to_list,
    _clean_body,
    _clean_title,
    _compute_new_sort_rank,
    _extract_ancestor_uuids,
    _format_etag,
    _handle_page_db_error,
    _to_slug,
    _verify_if_match,
)


def test_extract_ancestor_uuids() -> None:
    """Ancestors extracted from ltree labels; handles empty, invalid, and valid paths."""
    assert _extract_ancestor_uuids(None) == []
    assert _extract_ancestor_uuids("") == []

    u1 = uuid.uuid4()
    u2 = uuid.uuid4()
    u3 = uuid.uuid4()

    hpath = f"d{uuid.uuid4().hex}.p{u1.hex}.p{u2.hex}.p{u3.hex}"
    ancestors = _extract_ancestor_uuids(hpath)
    assert ancestors == [u1, u2]

    # Non-uuid hex or bad format skipped gracefully
    assert _extract_ancestor_uuids("d123.pNotAHexStringAtAll123456789012.p456") == []
    assert _extract_ancestor_uuids("d123.unknown.p456") == []
    assert _extract_ancestor_uuids(f"d0.p{'g' * 32}.p1") == []


def test_format_etag() -> None:
    """ETag formatting produces quoted hex string or empty quotes on None."""
    assert _format_etag(None) == '""'
    sha = b"\x01\x02\x03\x04"
    assert _format_etag(sha) == '"01020304"'


def test_verify_if_match() -> None:
    """Precondition checks validate presence, wildcards, quoted and unquoted matching."""
    with pytest.raises(ProblemException) as exc_req:
        _verify_if_match(None, b"test")
    assert exc_req.value.code == "PRECONDITION_REQUIRED"

    # Wildcard matches anything
    _verify_if_match("*", b"test")

    sha = b"\xaa\xbb"
    # Matches quoted
    _verify_if_match('"aabb"', sha)
    # Matches unquoted hex
    _verify_if_match("aabb", sha)

    # Mismatch raises 412
    with pytest.raises(ProblemException) as exc_fail:
        _verify_if_match('"ccdd"', sha)
    assert exc_fail.value.code == "PRECONDITION_FAILED"
    assert exc_fail.value.status == 412


def test_capabilities_to_list() -> None:
    """Capabilities bitmask converts to sorted list of non-NONE/ALL names."""
    assert _capabilities_to_list(Capability.NONE) == []
    assert _capabilities_to_list(Capability.ALL) == [
        "ADMIN",
        "COMMENT",
        "DELETE",
        "EDIT",
        "LINK",
        "SHARE",
        "TRANSITION",
        "VIEW",
    ]
    assert _capabilities_to_list(Capability.VIEW | Capability.EDIT) == ["EDIT", "VIEW"]


def test_handle_page_db_error() -> None:
    """DB trigger exceptions mapped to standard ProblemExceptions; unknowns re-raised."""

    def _mock_db_err(msg: str) -> DBAPIError:
        return DBAPIError(statement="SELECT 1", params={}, orig=Exception(msg))

    with pytest.raises(ProblemException) as exc_depth:
        _handle_page_db_error(_mock_db_err("PAGE_MAX_DEPTH_EXCEEDED"))
    assert exc_depth.value.code == "PAGE_MAX_DEPTH_EXCEEDED"
    assert exc_depth.value.status == 422

    with pytest.raises(ProblemException) as exc_cycle:
        _handle_page_db_error(_mock_db_err("PAGE_CYCLE"))
    assert exc_cycle.value.code == "PAGE_CYCLE"
    assert exc_cycle.value.status == 409

    with pytest.raises(ProblemException) as exc_mismatch:
        _handle_page_db_error(_mock_db_err("PAGE_PARENT_DOC_MISMATCH"))
    assert exc_mismatch.value.code == "PAGE_PARENT_DOC_MISMATCH"
    assert exc_mismatch.value.status == 422

    with pytest.raises(DBAPIError):
        _handle_page_db_error(_mock_db_err("SOME_UNEXPECTED_PG_ERROR"))


def test_clean_title_and_body() -> None:
    """Title normalization removes zero-width characters and checks length."""
    clean = _clean_title(" \u200b Hello World \ufeff ")
    assert clean == "Hello World"

    with pytest.raises(ProblemException) as exc_short:
        _clean_title("   \u200b   ")
    assert exc_short.value.code == "TITLE_LENGTH"

    with pytest.raises(ProblemException) as exc_long:
        _clean_title("x" * 501)
    assert exc_long.value.code == "TITLE_LENGTH"

    body = _clean_body("## Sample Header\nText")
    assert body == "## Sample Header\nText"


def test_to_slug() -> None:
    """Slugs convert to lowercase alphanumeric hyphenated format."""
    assert _to_slug("My First Doc!", "doc") == "my-first-doc"
    assert _to_slug("   ", "default") == "default"


def test_compute_new_sort_rank() -> None:
    """Sort rank computation exercises after_id and before_id boundary branches."""
    u1 = uuid.uuid4()
    u2 = uuid.uuid4()
    u3 = uuid.uuid4()
    siblings = [(u1, "a0"), (u2, "b0"), (u3, "c0")]

    # After first sibling (has next)
    r1 = _compute_new_sort_rank(siblings, after_id=u1, before_id=None)
    assert "a0" < r1 < "b0"

    # After last sibling (no next)
    r2 = _compute_new_sort_rank(siblings, after_id=u3, before_id=None)
    assert r2 > "c0"

    # Before last sibling (has prev)
    r3 = _compute_new_sort_rank(siblings, after_id=None, before_id=u3)
    assert "b0" < r3 < "c0"

    # Before first sibling (no prev)
    r4 = _compute_new_sort_rank(siblings, after_id=None, before_id=u1)
    assert r4 < "a0"

    # Neither after nor before: appends after last
    r5 = _compute_new_sort_rank(siblings, after_id=None, before_id=None)
    assert r5 > "c0"

    # Empty siblings
    r6 = _compute_new_sort_rank([], after_id=None, before_id=None)
    assert r6 == "a0"

    # Unknown after_id / before_id falls back to default rank
    r7 = _compute_new_sort_rank(siblings, after_id=uuid.uuid4(), before_id=None)
    assert r7 == "a0"
    r8 = _compute_new_sort_rank(siblings, after_id=None, before_id=uuid.uuid4())
    assert r8 == "a0"
