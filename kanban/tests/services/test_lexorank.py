# Copyright 2026 Kanban Platform Contributors
"""Unit tests for Base-62 Lexorank service (S8.1, S12.2)."""

from __future__ import annotations

import pytest

from kanban.services.lexorank import (
    _int_to_base62,
    midpoint_rank,
)


def test_int_to_base62_zero() -> None:
    """Zero value maps to alphabet zero."""
    assert _int_to_base62(0) == "0"
    assert _int_to_base62(62) == "10"


def test_midpoint_rank_invalid_bounds() -> None:
    """Prev rank >= next rank raises ValueError."""
    with pytest.raises(ValueError, match="must be lexicographically less"):
        midpoint_rank("b", "a")

    with pytest.raises(ValueError, match="must be lexicographically less"):
        midpoint_rank("same", "same")


def test_midpoint_rank_none_bounds() -> None:
    """None bounds produce valid default or bounded ranks."""
    default_rank = midpoint_rank(None, None)
    assert default_rank == "a0"

    after_rank = midpoint_rank("a0", None)
    assert after_rank > "a0"

    before_rank = midpoint_rank(None, "a0")
    assert "0" < before_rank < "a0"


def test_midpoint_rank_adjacent_strings() -> None:
    """Adjacent characters expand precision deterministically."""
    rank = midpoint_rank("a", "b")
    assert "a" < rank < "b"

    rank_deep = midpoint_rank("a0", "a1")
    assert "a0" < rank_deep < "a1"

    rank_tight = midpoint_rank("00", "01")
    assert "00" < rank_tight < "01"


def test_midpoint_rank_monotone_sequence() -> None:
    """Repeatedly inserting between items maintains strict monotonic order."""
    lo = "0"
    hi = "z"
    sequence: list[str] = [lo, hi]
    for _ in range(25):
        mid = midpoint_rank(sequence[0], sequence[1])
        assert sequence[0] < mid < sequence[1]
        sequence.insert(1, mid)

    assert sequence == sorted(sequence)
