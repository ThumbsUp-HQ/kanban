# Copyright 2026 Kanban Platform Contributors
"""Base-62 LexoRank sorting helper (S8.1, S12.2)."""

from __future__ import annotations

from typing import Final

__all__ = [
    "BASE62_ALPHABET",
    "midpoint_rank",
]

BASE62_ALPHABET: Final[str] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_CHAR_TO_VAL: Final[dict[str, int]] = {c: i for i, c in enumerate(BASE62_ALPHABET)}
_MIN_RANK_LEN: Final[int] = 2
_BASE: Final[int] = 62
_MID_STEP: Final[int] = 31


def _digits_to_int(digits: list[int]) -> int:
    """Convert base-62 digit list to integer."""
    val = 0
    for d in digits:
        val = val * _BASE + d
    return val


def _int_to_base62(val: int) -> str:
    """Convert positive integer to Base-62 string."""
    if val == 0:
        return BASE62_ALPHABET[0]
    digits: list[int] = []
    v = val
    while v > 0:
        digits.append(v % _BASE)
        v //= _BASE
    digits.reverse()
    return "".join(BASE62_ALPHABET[d] for d in digits)


def midpoint_rank(prev: str | None, next_: str | None) -> str:
    """Compute a deterministic Base-62 sort_rank strictly between prev and next in C collation.

    If prev is None and next_ is None, returns standard default rank 'a0'.
    If prev is None, returns a rank strictly less than next_.
    If next_ is None, returns a rank strictly greater than prev.
    If both are provided, returns a rank strictly between prev and next_ (prev < rank < next_).

    Raises:
        ValueError: If prev is lexicographically greater than or equal to next_.

    """
    if not prev and not next_:
        return "a0"

    p = prev if prev is not None else "0"
    n = next_ if next_ is not None else ("z" * (len(p) + 1) if prev else "a0")

    if p >= n:
        msg = f"prev rank ({p!r}) must be lexicographically less than next rank ({n!r})"
        raise ValueError(msg)

    # Pad representation to compare with fractional digits
    max_len = max(len(p), len(n)) + 1
    p_digits = [_CHAR_TO_VAL[c] for c in p] + [0] * (max_len - len(p))
    n_digits = [_CHAR_TO_VAL[c] for c in n] + [0] * (max_len - len(n))

    p_val = _digits_to_int(p_digits)
    n_val = _digits_to_int(n_digits)

    mid_val = (p_val + n_val) // 2

    res_digits: list[int] = []
    v = mid_val
    while v > 0:
        res_digits.append(v % _BASE)
        v //= _BASE
    res_digits.reverse()
    if len(res_digits) < max_len:
        res_digits = [0] * (max_len - len(res_digits)) + res_digits
    result = "".join(BASE62_ALPHABET[d] for d in res_digits)

    # Trim trailing zeros if result remains strictly greater than p
    while len(result) > _MIN_RANK_LEN and result.endswith("0") and result > p:
        result = result[:-1]

    return result
