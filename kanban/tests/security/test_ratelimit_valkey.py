"""Unit and contract tests for Valkey sliding-window rate limiter (S2.4, KB-P2-18)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from kanban.security.ratelimit.base import RateLimiter, RateLimitPolicy, make_key
from kanban.security.ratelimit.pg import PgRateLimiter
from kanban.security.ratelimit.valkey import ValkeyRateLimiter
from kanban.tests.security.fakes import FakeValkey

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def fake_valkey() -> FakeValkey:
    """Fixture providing an isolated FakeValkey test double."""
    return FakeValkey()


@pytest.fixture
def valkey_limiter(fake_valkey: FakeValkey) -> ValkeyRateLimiter:
    """Fixture providing a ValkeyRateLimiter wired to FakeValkey."""
    return ValkeyRateLimiter(fake_valkey)


@pytest.mark.asyncio
async def test_case_02_valkey_positive_sliding_window(valkey_limiter: ValkeyRateLimiter) -> None:
    """Test Case 2: Valkey allows 5 hits and denies 6th with retry_after in [1, 60]."""
    policy = RateLimitPolicy(name="valkey_burst", limit=5, window_seconds=60)
    key = make_key(policy, "valkey_client_01", session_hmac_key=b"v" * 32)

    for i in range(5):
        decision = await valkey_limiter.hit(policy, key)
        assert decision.allowed is True
        assert decision.remaining == 4 - i
        assert decision.retry_after_seconds == 0

    # 6th hit must be denied
    denied = await valkey_limiter.hit(policy, key)
    assert denied.allowed is False
    assert denied.remaining == 0
    assert 1 <= denied.retry_after_seconds <= 60


@pytest.mark.asyncio
async def test_valkey_window_slide_overlap(
    fake_valkey: FakeValkey, valkey_limiter: ValkeyRateLimiter
) -> None:
    """Verify Valkey backend weights previous window count at 25%, 50%, and 99% overlap."""
    policy = RateLimitPolicy(name="valkey_slide", limit=100, window_seconds=100)
    session_k = b"z" * 32

    t0 = 1794480000.0  # clean 100-second multiple

    async def _test_overlap(scenario: str, elapsed: float, expected_remaining: int) -> None:
        key = make_key(policy, f"vslide_{scenario}", session_hmac_key=session_k)

        # Seed 100 hits in previous window [t0, t0 + 100)
        fake_valkey.set_time(t0 + 10.0)
        for _ in range(100):
            await valkey_limiter.hit(policy, key)

        # Move to current window [t0 + 100, t0 + 200) at elapsed offset
        now = t0 + 100.0 + elapsed
        fake_valkey.set_time(now)
        dec = await valkey_limiter.hit(policy, key)
        assert dec.allowed is True
        assert dec.remaining == expected_remaining

    # 25% overlap remaining -> 74 remaining
    await _test_overlap("ov25", 75.0, 74)

    # 50% overlap remaining -> 49 remaining
    await _test_overlap("ov50", 50.0, 49)

    # 99% overlap remaining -> 0 remaining
    await _test_overlap("ov99", 1.0, 0)


@pytest.mark.asyncio
async def test_valkey_reset_and_validation(valkey_limiter: ValkeyRateLimiter) -> None:
    """Verify Valkey reset clears rate limit state and key validation enforces 32 bytes."""
    policy = RateLimitPolicy(name="valkey_reset", limit=3, window_seconds=60)
    key = make_key(policy, "vreset_client", session_hmac_key=b"r" * 32)

    for _ in range(3):
        await valkey_limiter.hit(policy, key)
    denied = await valkey_limiter.hit(policy, key)
    assert denied.allowed is False

    await valkey_limiter.reset(policy, key)

    allowed = await valkey_limiter.hit(policy, key)
    assert allowed.allowed is True
    assert allowed.remaining == 2

    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        await valkey_limiter.hit(policy, b"short")

    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        await valkey_limiter.reset(policy, b"short")


@pytest.mark.asyncio
async def test_valkey_timestamp_parameter_types(valkey_limiter: ValkeyRateLimiter) -> None:
    """Verify Valkey hit and reset support float and datetime timestamp arguments."""
    policy = RateLimitPolicy(name="v_ts_types", limit=10, window_seconds=60)
    key = make_key(policy, "ts_user", session_hmac_key=b"t" * 32)

    # 1. float timestamp
    dec1 = await valkey_limiter.hit(policy, key, now=1794480000.0)
    assert dec1.allowed is True

    # 2. datetime timestamp
    dt = datetime(2026, 11, 12, 12, 0, 0, tzinfo=UTC)
    dec2 = await valkey_limiter.hit(policy, key, now=dt)
    assert dec2.allowed is True

    # 3. reset with float and datetime
    await valkey_limiter.reset(policy, key, now=1794480000.0)
    await valkey_limiter.reset(policy, key, now=dt)


@pytest.mark.asyncio
async def test_shared_contract_pg_and_valkey(
    db_session: AsyncSession, fake_valkey: FakeValkey
) -> None:
    """Verify both PG and Valkey backends satisfy identical rate limiting semantics."""
    pg_limiter = PgRateLimiter(session=db_session)
    valkey_lim = ValkeyRateLimiter(fake_valkey)

    policy = RateLimitPolicy(name="shared_contract", limit=4, window_seconds=60)
    key_pg = make_key(policy, "shared_pg", session_hmac_key=b"s" * 32)
    key_vk = make_key(policy, "shared_vk", session_hmac_key=b"s" * 32)

    targets: list[tuple[RateLimiter, bytes]] = [(pg_limiter, key_pg), (valkey_lim, key_vk)]
    for limiter, key in targets:
        # 4 allowed hits
        for expected_rem in [3, 2, 1, 0]:
            dec = await limiter.hit(policy, key)
            assert dec.allowed is True
            assert dec.remaining == expected_rem
            assert dec.retry_after_seconds == 0

        # Denied 5th hit
        denied = await limiter.hit(policy, key)
        assert denied.allowed is False
        assert denied.remaining == 0
        assert 1 <= denied.retry_after_seconds <= 60
