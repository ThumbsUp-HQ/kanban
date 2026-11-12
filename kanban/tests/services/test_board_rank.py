# Copyright 2026 Kanban Platform Contributors
"""Comprehensive unit and property tests for fractional Base-62 board rank engine (KB-P3-12)."""

from __future__ import annotations

import pytest

from kanban.services.board_rank import (
    DEFAULT_MIDPOINT_CHAR,
    MAX_RANK_LEN,
    RankOrderError,
    allocate_initial_board_rank,
    from_base62,
    generate_evenly_spaced_ranks,
    initial_rank,
    is_valid_rank,
    midpoint_rank,
    rank_between,
    rebalance_ranks,
    to_base62,
    validate_rank,
)


def test_base62_roundtrip_and_errors() -> None:
    """Verify Base-62 conversion and error conditions."""
    assert to_base62(0) == "0"
    assert to_base62(61) == "z"
    assert to_base62(62) == "10"
    assert to_base62(3843) == "zz"
    assert to_base62(3844) == "100"

    assert from_base62("0") == 0
    assert from_base62("z") == 61
    assert from_base62("10") == 62
    assert from_base62("zz") == 3843
    assert from_base62("100") == 3844

    for val in [0, 1, 42, 61, 62, 100, 1000, 999999, 123456789]:
        assert from_base62(to_base62(val)) == val

    with pytest.raises(ValueError, match="Negative integer not supported"):
        to_base62(-1)

    with pytest.raises(ValueError, match="Empty Base-62 string"):
        from_base62("")

    with pytest.raises(ValueError, match="Invalid Base-62 character"):
        from_base62("abc#123")


def test_is_valid_rank_and_validate_rank() -> None:
    """Verify rank canonical validation rules."""
    assert is_valid_rank("V") is True
    assert is_valid_rank("a00001V") is True
    assert is_valid_rank("z") is True

    # Trailing zero is invalid
    assert is_valid_rank("a00000") is False
    assert is_valid_rank("0") is False
    assert is_valid_rank("V0") is False

    # Empty or too long
    assert is_valid_rank("") is False
    assert is_valid_rank("a" * (MAX_RANK_LEN + 1)) is False

    # Non-alphanumeric
    assert is_valid_rank("a-b") is False
    assert is_valid_rank("a_b") is False
    assert is_valid_rank("a b") is False

    # validate_rank helper
    assert validate_rank("a00001V") == "a00001V"
    with pytest.raises(ValueError, match="Invalid board rank"):
        validate_rank("invalid0")


def test_initial_rank_allocations() -> None:
    """Verify initial rank generation guarantees non-zero termination."""
    r1 = allocate_initial_board_rank(1)
    assert is_valid_rank(r1)
    assert not r1.endswith("0")

    # Sequence id 0 produces all zeros in base62, so allocate_initial_board_rank appends 'V'
    r0 = allocate_initial_board_rank(0)
    assert is_valid_rank(r0)
    assert r0.endswith(DEFAULT_MIDPOINT_CHAR)

    # Check alias
    assert initial_rank(1) == r1


def test_midpoint_rank_order_error() -> None:
    """prev_rank >= next_rank raises RankOrderError."""
    with pytest.raises(RankOrderError, match="must be strictly less than"):
        midpoint_rank("b", "a")

    with pytest.raises(RankOrderError, match="must be strictly less than"):
        midpoint_rank("same", "same")

    # rank_between alias
    assert rank_between("a", "c") == "b"


def test_midpoint_rank_none_bounds() -> None:
    """None bounds produce valid midpoint, prepending and appending."""
    # Both None -> default midpoint
    assert midpoint_rank(None, None) == DEFAULT_MIDPOINT_CHAR

    # Next is None -> tail expansion
    after = midpoint_rank("a", None)
    assert after == "b"
    assert after.encode("ascii") > "a".encode("ascii")

    after_z = midpoint_rank("z", None)
    assert after_z == "z" + DEFAULT_MIDPOINT_CHAR
    assert after_z.encode("ascii") > "z".encode("ascii")

    # Prev is None -> head expansion
    before_v = midpoint_rank(None, DEFAULT_MIDPOINT_CHAR)
    assert before_v.encode("ascii") < DEFAULT_MIDPOINT_CHAR.encode("ascii")
    assert not before_v.endswith("0")

    # Prev is None with leading zeros in next
    before_zero = midpoint_rank(None, "001")
    assert before_zero.encode("ascii") < "001".encode("ascii")
    assert not before_zero.endswith("0")

    # Head expansion where character value < 2
    before_01 = midpoint_rank(None, "01")
    assert before_01.encode("ascii") < "01".encode("ascii")
    assert not before_01.endswith("0")


def test_midpoint_rank_between_cases() -> None:
    """Verify bisections between different prefixes and divergence patterns."""
    # Non-adjacent characters with gap
    mid_ac = midpoint_rank("a", "c")
    assert mid_ac == "b"

    # Adjacent characters
    mid_ab = midpoint_rank("a", "b")
    assert "a".encode("ascii") < mid_ab.encode("ascii") < "b".encode("ascii")
    assert not mid_ab.endswith("0")

    # Adjacent characters with rest in prev
    mid_rest = midpoint_rank("aZ", "b")
    assert "aZ".encode("ascii") < mid_rest.encode("ascii") < "b".encode("ascii")
    assert not mid_rest.endswith("0")

    # Prev is proper prefix of next
    mid_prefix = midpoint_rank("abc", "abcV")
    assert "abc".encode("ascii") < mid_prefix.encode("ascii") < "abcV".encode("ascii")
    assert not mid_prefix.endswith("0")


def test_property_200_bisections_collate_c_invariants() -> None:
    """Property test: 200 sequential head, tail, and adversarial bisections preserve ASCII order."""
    # 1. Sequential head insertions
    curr = "z"
    for _ in range(50):
        new_head = midpoint_rank(None, curr)
        assert new_head.encode("ascii") < curr.encode("ascii")
        assert not new_head.endswith("0")
        assert is_valid_rank(new_head)
        curr = new_head

    # 2. Sequential tail insertions
    curr = "01"
    for _ in range(50):
        new_tail = midpoint_rank(curr, None)
        assert curr.encode("ascii") < new_tail.encode("ascii")
        assert not new_tail.endswith("0")
        assert is_valid_rank(new_tail)
        curr = new_tail

    # 3. Adversarial bisection at same slot (between adjacent initial keys)
    lo = "a000001"
    hi = "a000002"
    chain = [lo, hi]
    for _ in range(100):
        # Always bisect slot 0 and 1
        mid = midpoint_rank(chain[0], chain[1])
        assert chain[0].encode("ascii") < mid.encode("ascii") < chain[1].encode("ascii")
        assert not mid.endswith("0")
        assert is_valid_rank(mid)
        chain.insert(1, mid)

    # Verify overall chain is strictly sorted in ASCII byte order
    for i in range(len(chain) - 1):
        assert chain[i].encode("ascii") < chain[i + 1].encode("ascii")


def test_generate_evenly_spaced_ranks() -> None:
    """Verify batch rank generation for rebalancing."""
    assert generate_evenly_spaced_ranks(0) == []
    assert generate_evenly_spaced_ranks(-5) == []

    one = generate_evenly_spaced_ranks(1)
    assert one == [DEFAULT_MIDPOINT_CHAR]

    count = 100
    ranks = generate_evenly_spaced_ranks(count)
    assert len(ranks) == count
    assert rebalance_ranks(count) == ranks

    for i, r in enumerate(ranks):
        assert len(r) <= 7
        assert not r.endswith("0")
        assert is_valid_rank(r)
        if i > 0:
            assert ranks[i - 1].encode("ascii") < r.encode("ascii")
