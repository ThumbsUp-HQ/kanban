"""Fractional Base-62 (COLLATE "C") board rank indexing engine (KB-P3-12, S6.4)."""

from __future__ import annotations

import re
from typing import Final

# Strict ASCII byte order: '0'-'9' (48-57) < 'A'-'Z' (65-90) < 'a'-'z' (97-122).
# This matches PostgreSQL COLLATE "C" exactly.
ALPHABET: Final[str] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE62_ASCII: Final[str] = ALPHABET
BASE62_LEN: Final[int] = 62
MAX_RANK_LEN: Final[int] = 256
REBALANCE_THRESHOLD_LEN: Final[int] = 32
DEFAULT_MIDPOINT_CHAR: Final[str] = "V"  # ALPHABET[31]
_MIN_DIVISIBLE_VAL: Final[int] = 2

_VAL_MAP: Final[dict[str, int]] = {char: idx for idx, char in enumerate(ALPHABET)}
_RANK_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Za-z]{1,256}$")


class RankOrderError(ValueError):
    """Raised when prev_rank >= next_rank in midpoint calculation."""


def is_valid_rank(rank: str) -> bool:
    """Check whether rank matches canonical regex and ends in a non-zero character."""
    if not rank or len(rank) > MAX_RANK_LEN:
        return False
    if rank.endswith("0"):
        return False
    return bool(_RANK_REGEX.fullmatch(rank))


def validate_rank(rank: str) -> str:
    """Validate that rank is canonical; raise ValueError if invalid."""
    if not is_valid_rank(rank):
        msg = (
            f"Invalid board rank '{rank}': must be 1..256 alphanumeric characters not ending in '0'"
        )
        raise ValueError(msg)
    return rank


def to_base62(n: int) -> str:
    """Encode a non-negative integer into a Base-62 string."""
    if n < 0:
        msg = f"Negative integer not supported: {n}"
        raise ValueError(msg)
    if n == 0:
        return ALPHABET[0]
    digits: list[str] = []
    curr = n
    while curr > 0:
        digits.append(ALPHABET[curr % BASE62_LEN])
        curr //= BASE62_LEN
    return "".join(reversed(digits))


def from_base62(s: str) -> int:
    """Decode a Base-62 string into an integer."""
    if not s:
        msg = "Empty Base-62 string"
        raise ValueError(msg)
    total = 0
    for char in s:
        if char not in _VAL_MAP:
            msg = f"Invalid Base-62 character: {char}"
            raise ValueError(msg)
        total = total * BASE62_LEN + _VAL_MAP[char]
    return total


def allocate_initial_board_rank(sequence_id: int) -> str:
    """Compute the initial deterministic board rank token for sequence_id."""
    raw = "a" + to_base62(sequence_id).rjust(6, "0")
    if raw.endswith("0"):
        return raw + DEFAULT_MIDPOINT_CHAR
    return raw


def initial_rank(sequence_id: int = 1) -> str:
    """Alias for allocate_initial_board_rank."""
    return allocate_initial_board_rank(sequence_id)


def _midpoint_head(next_rank: str) -> str:
    """Compute midpoint when prepending before next_rank."""
    k = 0
    while k < len(next_rank) and next_rank[k] == "0":
        k += 1
    c = next_rank[k]
    val = _VAL_MAP[c]
    if val >= _MIN_DIVISIBLE_VAL:
        return "0" * k + ALPHABET[val // 2]
    return "0" * (k + 1) + DEFAULT_MIDPOINT_CHAR


def _midpoint_tail(prev_rank: str) -> str:
    """Compute midpoint when appending after prev_rank."""
    if prev_rank[-1] < "z":
        return prev_rank[:-1] + ALPHABET[_VAL_MAP[prev_rank[-1]] + 1]
    return prev_rank + DEFAULT_MIDPOINT_CHAR


def _midpoint_between(prev_rank: str, next_rank: str) -> str:
    """Compute midpoint between two non-None ranks where prev_rank < next_rank."""
    prefix_len = 0
    while (
        prefix_len < len(prev_rank)
        and prefix_len < len(next_rank)
        and prev_rank[prefix_len] == next_rank[prefix_len]
    ):
        prefix_len += 1

    prefix = prev_rank[:prefix_len]

    if prefix_len < len(prev_rank) and prefix_len < len(next_rank):
        p_val = _VAL_MAP[prev_rank[prefix_len]]
        n_val = _VAL_MAP[next_rank[prefix_len]]
        diff = n_val - p_val
        if diff > 1:
            mid = (p_val + n_val) // 2
            return prefix + ALPHABET[mid]
        # Adjacent characters at divergence index (e.g. 'a' and 'b')
        p_rest = prev_rank[prefix_len + 1 :]
        if not p_rest:
            return prev_rank + DEFAULT_MIDPOINT_CHAR
        return prefix + prev_rank[prefix_len] + _midpoint_tail(p_rest)

    # prev_rank is a proper prefix of next_rank
    n_rest = next_rank[prefix_len:]
    return prefix + _midpoint_head(n_rest)


def midpoint_rank(prev_rank: str | None, next_rank: str | None) -> str:
    """Compute shortest Base-62 rank satisfying prev_rank < midpoint < next_rank in COLLATE "C".

    Raises:
        RankOrderError: If prev_rank is not None and next_rank is not None
            and prev_rank >= next_rank.

    """
    if prev_rank is not None and next_rank is not None and prev_rank >= next_rank:
        msg = f"prev_rank '{prev_rank}' must be strictly less than next_rank '{next_rank}'"
        raise RankOrderError(msg)

    if prev_rank is None:
        if next_rank is None:
            return DEFAULT_MIDPOINT_CHAR
        return _midpoint_head(next_rank)
    if next_rank is None:
        return _midpoint_tail(prev_rank)
    return _midpoint_between(prev_rank, next_rank)


def rank_between(before: str | None, after: str | None) -> str:
    """Compute rank between before and after (alias for midpoint_rank)."""
    return midpoint_rank(before, after)


def _int_to_base62_fixed(n: int, width: int) -> str:
    """Convert integer to fixed-width Base-62 string."""
    digits: list[str] = []
    curr = n
    for _ in range(width):
        digits.append(ALPHABET[curr % BASE62_LEN])
        curr //= BASE62_LEN
    return "".join(reversed(digits))


def generate_evenly_spaced_ranks(count: int) -> list[str]:
    """Generate count strictly increasing Base-62 ranks of width <= 7 with rank[-1] != '0'."""
    if count <= 0:
        return []
    if count == 1:
        return [DEFAULT_MIDPOINT_CHAR]

    width = 6
    total = BASE62_LEN**width
    step = total // (count + 1)
    ranks: list[str] = []
    last_val = 0
    for i in range(1, count + 1):
        val = max(last_val + 1, i * step)
        s = _int_to_base62_fixed(val, width)
        if s.endswith("0"):
            val += 1
            s = _int_to_base62_fixed(val, width)
        last_val = val
        ranks.append(s)
    return ranks


def rebalance_ranks(n: int) -> list[str]:
    """Generate n evenly spaced ranks for column rebalancing."""
    return generate_evenly_spaced_ranks(n)
