# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S311
"""Unit tests for fractional indexing under COLLATE 'C' (KB-P2-10, KB-P3-12)."""

from __future__ import annotations

import random

import pytest

from kanban.util.fractional_rank import (
    BASE62_ALPHABET,
    MAX_RANK_LENGTH,
    initial_ranks,
    midpoint_rank,
    needs_rebalance,
    rebalance_ranks,
)


def test_base62_alphabet_properties() -> None:
    """Verify alphabet conforms to PostgreSQL COLLATE 'C' ASCII byte ordering."""
    assert len(BASE62_ALPHABET) == 62
    # Digits < Uppercase < Lowercase
    assert ord("0") < ord("9") < ord("A") < ord("Z") < ord("a") < ord("z")
    # Strict byte ordering check
    sorted_chars = "".join(sorted(BASE62_ALPHABET))
    assert sorted_chars == BASE62_ALPHABET
    # Distinct characters
    assert len(set(BASE62_ALPHABET)) == 62


def test_midpoint_rank_edge_cases() -> None:
    """Verify midpoint generation for boundary and initial conditions."""
    # Both None
    m_both = midpoint_rank(None, None)
    assert m_both == "V"
    assert not m_both.endswith("0")

    # Lower bound open (None, 'V')
    m_left = midpoint_rank(None, "V")
    assert "" < m_left < "V"
    assert not m_left.endswith("0")

    # Upper bound open ('V', None)
    m_right = midpoint_rank("V", None)
    assert m_right > "V"
    assert not m_right.endswith("0")

    # Midpoint between adjacent single chars
    m_ab = midpoint_rank("a", "b")
    assert "a" < m_ab < "b"
    assert not m_ab.endswith("0")

    # Midpoint when prefix matches and difference is minimal
    m_tight = midpoint_rank("a", "a1")
    assert "a" < m_tight < "a1"
    assert not m_tight.endswith("0")


def test_midpoint_rank_validation_errors() -> None:
    """Verify input validation rules and error conditions."""
    # Trailing '0' on prev
    with pytest.raises(ValueError, match="forbidden '0'"):
        midpoint_rank("a0", "b")

    # Trailing '0' on nxt
    with pytest.raises(ValueError, match="forbidden '0'"):
        midpoint_rank("a", "b0")

    # Empty string prev
    with pytest.raises(ValueError, match="empty string"):
        midpoint_rank("", "b")

    # Empty string nxt
    with pytest.raises(ValueError, match="empty string"):
        midpoint_rank("a", "")

    # Invalid chars
    with pytest.raises(ValueError, match="Invalid character"):
        midpoint_rank("a!", "b")

    with pytest.raises(ValueError, match="Invalid character"):
        midpoint_rank("a", "b?")

    # When prev >= nxt
    with pytest.raises(ValueError, match="strictly less"):
        midpoint_rank("b", "a")

    with pytest.raises(ValueError, match="strictly less"):
        midpoint_rank("a", "a")


def test_initial_ranks_and_rebalance() -> None:
    """Verify initial ranking generation and rebalance mechanics."""
    assert initial_ranks(0) == []
    assert initial_ranks(-5) == []

    ranks = initial_ranks(25, length=4)
    assert len(ranks) == 25
    assert ranks == sorted(ranks)
    for r in ranks:
        assert len(r) == 4
        assert not r.endswith("0")

    # needs_rebalance
    assert not needs_rebalance("a" * MAX_RANK_LENGTH)
    assert needs_rebalance("a" * (MAX_RANK_LENGTH + 1))

    # rebalance_ranks
    items = ["item_a", "item_b", "item_c"]
    rebalanced = rebalance_ranks(items)
    assert len(rebalanced) == 3
    assert [item for item, _ in rebalanced] == items
    assigned_ranks = [rank for _, rank in rebalanced]
    assert assigned_ranks == sorted(assigned_ranks)
    for r in assigned_ranks:
        assert len(r) == 4
        assert not r.endswith("0")


def test_random_insertions_sequence() -> None:
    """Perform 500 consecutive random midpoint insertions maintaining strict invariant."""
    ranks: list[str] = []
    rng = random.Random(42)

    for _ in range(500):
        if not ranks:
            ranks.append(midpoint_rank(None, None))
        else:
            idx = rng.randint(0, len(ranks))
            prev = ranks[idx - 1] if idx > 0 else None
            nxt = ranks[idx] if idx < len(ranks) else None
            mid = midpoint_rank(prev, nxt)
            assert not mid.endswith("0")
            if prev is not None:
                assert prev < mid
            if nxt is not None:
                assert mid < nxt
            ranks.insert(idx, mid)

    assert ranks == sorted(ranks)
