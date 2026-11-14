# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Fractional indexing using base-62 ASCII characters under COLLATE 'C' (KB-P2-10, KB-P3-12)."""

from __future__ import annotations

from typing import Final

__all__ = [
    "BASE62_ALPHABET",
    "MAX_RANK_LENGTH",
    "initial_ranks",
    "midpoint_rank",
    "needs_rebalance",
    "rebalance_ranks",
]

# 62 ASCII chars in strict byte order: digits (48-57) < uppercase (65-90) < lowercase (97-122).
BASE62_ALPHABET: Final[str] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_BASE: Final[int] = len(BASE62_ALPHABET)
_CHAR_TO_VAL: Final[dict[str, int]] = {c: i for i, c in enumerate(BASE62_ALPHABET)}
MAX_RANK_LENGTH: Final[int] = 32


def _int_to_base62(val: int, length: int) -> str:
    """Convert non-negative integer to fixed-length base-62 string."""
    digits: list[str] = []
    rem = val
    for _ in range(length):
        digits.append(BASE62_ALPHABET[rem % _BASE])
        rem //= _BASE
    return "".join(reversed(digits))


def midpoint_rank(prev: str | None, nxt: str | None) -> str:  # noqa: C901, PLR0912, PLR0915
    """Compute a lexicographic midpoint between prev and nxt without trailing '0's.

    Ranks represent fractional values in [0, 1) expressed in base 62.
    Trailing '0' characters are forbidden so that infinite subdivisions remain possible.
    """
    if prev is not None:
        if not prev:
            msg = "prev rank must not be empty string"
            raise ValueError(msg)
        if prev.endswith("0"):
            msg = f"prev rank {prev!r} ends with forbidden '0'"
            raise ValueError(msg)
        for c in prev:
            if c not in _CHAR_TO_VAL:
                msg = f"Invalid character {c!r} in prev rank"
                raise ValueError(msg)

    if nxt is not None:
        if not nxt:
            msg = "nxt rank must not be empty string"
            raise ValueError(msg)
        if nxt.endswith("0"):
            msg = f"nxt rank {nxt!r} ends with forbidden '0'"
            raise ValueError(msg)
        for c in nxt:
            if c not in _CHAR_TO_VAL:
                msg = f"Invalid character {c!r} in nxt rank"
                raise ValueError(msg)

    if prev is not None and nxt is not None and prev >= nxt:
        msg = f"prev rank {prev!r} must be strictly less than nxt rank {nxt!r}"
        raise ValueError(msg)

    if prev is None and nxt is None:
        # Default middle of the base-62 alphabet
        return BASE62_ALPHABET[_BASE // 2]

    p_str = prev if prev is not None else ""

    if nxt is None:
        # Midpoint between prev and 1.0 (the upper bound)
        k = len(p_str) + 1
        p_val = 0
        for c in p_str:
            p_val = p_val * _BASE + _CHAR_TO_VAL[c]
        p_val *= _BASE
        top_val = _BASE**k
        mid = (p_val + top_val) // 2
    else:
        k = max(len(p_str), len(nxt))
        p_val = 0
        for c in p_str:
            p_val = p_val * _BASE + _CHAR_TO_VAL[c]
        p_val *= _BASE ** (k - len(p_str))

        n_val = 0
        for c in nxt:
            n_val = n_val * _BASE + _CHAR_TO_VAL[c]
        n_val *= _BASE ** (k - len(nxt))

        while n_val - p_val <= 1:
            p_val *= _BASE
            n_val *= _BASE
            k += 1

        mid = (p_val + n_val) // 2

    digits: list[str] = []
    rem = mid
    for _ in range(k):
        digits.append(BASE62_ALPHABET[rem % _BASE])
        rem //= _BASE

    res = "".join(reversed(digits)).rstrip("0")
    if not res:
        # Fallback if mid was 0 (should not happen with positive intervals)
        res = BASE62_ALPHABET[1]
    return res


def initial_ranks(count: int, length: int = 4) -> list[str]:
    """Generate evenly spaced ranks of fixed length without trailing '0's."""
    if count <= 0:
        return []

    total = _BASE**length
    step = total // (count + 1)
    ranks: list[str] = []

    for i in range(1, count + 1):
        v = i * step
        if v % _BASE == 0:
            v += 1
        r = _int_to_base62(v, length)
        if r.endswith("0"):
            r = r[:-1] + "1"
        ranks.append(r)

    return ranks


def needs_rebalance(rank: str, max_length: int = MAX_RANK_LENGTH) -> bool:
    """Return True if rank length exceeds the rebalance threshold."""
    return len(rank) > max_length


def rebalance_ranks[T](cards: list[T]) -> list[tuple[T, str]]:
    """Assign evenly spaced 4-character ranks to existing items preserving order."""
    new_ranks = initial_ranks(len(cards), length=4)
    return list(zip(cards, new_ranks, strict=True))
