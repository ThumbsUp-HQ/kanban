"""Unit and concurrency tests for PostgreSQL sliding-window rate limiter (S2.4, KB-P2-18)."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from kanban.security.ratelimit.base import RateLimitPolicy, make_key
from kanban.security.ratelimit.pg import PgRateLimiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.mark.asyncio
async def test_case_01_pg_positive_sliding_window(db_session: AsyncSession) -> None:
    """Test Case 1: Policy 5/60s allows 5 hits and denies 6th with retry_after in [1, 60]."""
    limiter = PgRateLimiter(session=db_session)
    policy = RateLimitPolicy(name="auth_login_test", limit=5, window_seconds=60)
    key = make_key(policy, "test_client_01", session_hmac_key=b"k" * 32)

    for i in range(5):
        decision = await limiter.hit(policy, key)
        assert decision.allowed is True
        assert decision.remaining == 4 - i
        assert decision.retry_after_seconds == 0

    # 6th hit must be denied with retry_after_seconds in [1, 60]
    denied = await limiter.hit(policy, key)
    assert denied.allowed is False
    assert denied.remaining == 0
    assert 1 <= denied.retry_after_seconds <= 60


@pytest.mark.asyncio
async def test_case_03_credential_stuffing_prevention(db_session: AsyncSession) -> None:
    """Test Case 3: 1000 hits over 1000 distinct account keys from one IP throttled after 20."""
    limiter = PgRateLimiter(session=db_session)
    ip_policy = RateLimitPolicy(name="auth_login_ip", limit=20, window_seconds=900)
    acct_policy = RateLimitPolicy(name="auth_login_account", limit=5, window_seconds=900)

    session_k = b"m" * 32
    ip_key = make_key(ip_policy, "198.51.100.88", session_hmac_key=session_k)

    # Simulate 50 hits (representative subset of 1000) from distinct account identifiers
    for idx in range(50):
        acct_key = make_key(acct_policy, f"victim_{idx}@example.com", session_hmac_key=session_k)

        # Account policy allows initial hit
        acct_dec = await limiter.hit(acct_policy, acct_key)
        assert acct_dec.allowed is True

        # IP policy tracks aggregate requests from peer
        ip_dec = await limiter.hit(ip_policy, ip_key)
        if idx < 20:
            assert ip_dec.allowed is True
            assert ip_dec.remaining == 19 - idx
        else:
            assert ip_dec.allowed is False
            assert ip_dec.remaining == 0
            assert 1 <= ip_dec.retry_after_seconds <= 900


@pytest.mark.asyncio
async def test_case_06_privacy_pseudonymization(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Test Case 6: Sensitive strings (alice@example.com, IP) never appear in DB or logs."""
    limiter = PgRateLimiter(session=db_session)
    policy = RateLimitPolicy(name="privacy_guard", limit=50, window_seconds=60)

    sensitive_email = "alice@example.com"
    sensitive_ip = "198.51.100.7"
    key = make_key(policy, sensitive_email, sensitive_ip, session_hmac_key=b"p" * 32)

    for _ in range(10):
        await limiter.hit(policy, key)

    # Inspect raw table contents
    rows = (
        await db_session.execute(
            text("SELECT policy, key_hash, window_start, count FROM rate_limit_buckets")
        )
    ).fetchall()

    assert len(rows) >= 1
    for row in rows:
        row_str = str(row)
        assert sensitive_email not in row_str
        assert sensitive_ip not in row_str
        # Verify raw bytes in key_hash do not contain UTF-8 sensitive strings
        key_bytes = bytes(row[1])
        assert sensitive_email.encode("utf-8") not in key_bytes
        assert sensitive_ip.encode("utf-8") not in key_bytes

    # Assert caplog contains neither string
    assert sensitive_email not in caplog.text
    assert sensitive_ip not in caplog.text


@pytest.mark.asyncio
async def test_case_07_window_slide_overlap_weighting(db_session: AsyncSession) -> None:
    """Test Case 7: Sliding window weights previous window count at 25%, 50%, and 99% overlap."""
    limiter = PgRateLimiter(session=db_session)
    policy = RateLimitPolicy(name="slide_test", limit=100, window_seconds=100)
    session_k = b"w" * 32

    # Fixed base timestamp aligned to window boundary (100s multiple)
    t0_epoch = 1794480000.0  # clean 100-second multiple
    t0 = datetime.fromtimestamp(t0_epoch, tz=UTC)

    # Helper to test specific overlap percentage
    async def _test_overlap(
        scenario_id: str, elapsed_seconds: float, expected_remaining: int
    ) -> None:
        key = make_key(policy, f"slide_{scenario_id}", session_hmac_key=session_k)

        # Seed 100 hits in previous window [t0, t0 + 100)
        # Directly update bucket count to 100 for test speed
        await db_session.execute(
            text(
                "INSERT INTO rate_limit_buckets (policy, key_hash, window_start, count) "
                "VALUES (:policy, :key, :win, 100)"
            ),
            {"policy": policy.name, "key": key, "win": t0},
        )

        # Current window is [t0 + 100, t0 + 200). Current time is t0 + 100 + elapsed_seconds.
        now_ts = t0 + timedelta(seconds=100 + elapsed_seconds)
        decision = await limiter.hit(policy, key, now=now_ts)

        assert decision.allowed is True
        assert decision.remaining == expected_remaining

    # 1. 25% overlap remaining -> 75s elapsed in current window -> weight 0.25 -> 100 * 0.25 = 25.
    # Total = 25 + 1 = 26 -> remaining 100 - 26 = 74.
    await _test_overlap("overlap_25", 75.0, 74)

    # 2. 50% overlap remaining -> 50s elapsed in current window -> weight 0.50 -> 100 * 0.50 = 50.
    # Total = 50 + 1 = 51 -> remaining 100 - 51 = 49.
    await _test_overlap("overlap_50", 50.0, 49)

    # 3. 99% overlap remaining -> 1s elapsed in current window -> weight 0.99 -> 100 * 0.99 = 99.
    # Total = 99 + 1 = 100 -> remaining 100 - 100 = 0.
    await _test_overlap("overlap_99", 1.0, 0)


@pytest.mark.committed_db
@pytest.mark.usefixtures("committed_db_session")
@pytest.mark.asyncio
async def test_case_10_pg_concurrency(pg_worker_db: AsyncEngine) -> None:
    """Test Case 10: 50 concurrent hit calls on limit 10 yields exactly 10 allowed."""
    policy = RateLimitPolicy(name="concurrent_burst", limit=10, window_seconds=60)
    key = make_key(policy, "concurrent_target", session_hmac_key=b"c" * 32)

    concurrency_engine = create_async_engine(pg_worker_db.url, poolclass=NullPool)
    limiter = PgRateLimiter(engine=concurrency_engine)

    # Launch 50 parallel hit operations
    tasks = [limiter.hit(policy, key) for _ in range(50)]
    decisions = await asyncio.gather(*tasks)
    await concurrency_engine.dispose()

    allowed_hits = sum(1 for d in decisions if d.allowed)
    denied_hits = sum(1 for d in decisions if not d.allowed)

    assert allowed_hits == 10
    assert denied_hits == 40


@pytest.mark.asyncio
async def test_pg_reset_and_validation(db_session: AsyncSession) -> None:
    """Verify reset function removes bucket and key length validation raises ValueError."""
    limiter = PgRateLimiter(session=db_session)
    policy = RateLimitPolicy(name="reset_policy", limit=5, window_seconds=60)
    key = make_key(policy, "reset_client", session_hmac_key=b"r" * 32)

    # Exhaust limit
    for _ in range(5):
        await limiter.hit(policy, key)
    denied = await limiter.hit(policy, key)
    assert denied.allowed is False

    # Reset bucket
    await limiter.reset(policy, key)

    # Immediately allowed again
    allowed = await limiter.hit(policy, key)
    assert allowed.allowed is True
    assert allowed.remaining == 4

    # Invalid key length must raise ValueError
    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        await limiter.hit(policy, b"short_key")

    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        await limiter.reset(policy, b"short_key")


@pytest.mark.asyncio
async def test_pg_constructor_and_engine_paths(db_session: AsyncSession) -> None:
    """Verify PgRateLimiter constructor variants and engine-based execution paths."""
    policy = RateLimitPolicy(name="ctor_test", limit=2, window_seconds=60)

    # 1. Constructor with session as first argument
    lim1 = PgRateLimiter(db_session)
    key1 = make_key(policy, "ctor_user_1", session_hmac_key=b"1" * 32)
    dec1 = await lim1.hit(policy, key1)
    assert dec1.allowed is True

    # 2. Connection-backed execution
    conn = await db_session.connection()
    lim2 = PgRateLimiter(conn)
    key2 = make_key(policy, "ctor_user_2", session_hmac_key=b"2" * 32)
    dec2 = await lim2.hit(policy, key2)
    assert dec2.allowed is True
    await lim2.reset(policy, key2)

    # 3. Connection-string constructor with independent key
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock-24")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    db_name = str(conn.engine.url.database) if hasattr(conn, "engine") else "postgres"
    dsn = f"postgresql+asyncpg://{user}@/{db_name}?host={socket_dir}"
    lim3 = PgRateLimiter(dsn)
    key3 = make_key(policy, "ctor_user_3", session_hmac_key=b"3" * 32)
    dec3 = await lim3.hit(policy, key3)
    assert dec3.allowed is True
    await lim3.reset(policy, key3)


def test_pg_rate_limiter_get_engine_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify _get_engine resolution with and without DATABASE_URL."""
    # 1. With KANBAN_DATABASE_URL
    dsn = "postgresql+asyncpg://kanban_test@/postgres?host=/tmp"
    monkeypatch.setenv("KANBAN_DATABASE_URL", dsn)
    lim1 = PgRateLimiter()
    eng1 = lim1._get_engine()  # noqa: SLF001
    assert eng1 is not None

    # 2. Without env var (defaults to socket_dir)
    monkeypatch.delenv("KANBAN_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    lim2 = PgRateLimiter()
    eng2 = lim2._get_engine()  # noqa: SLF001
    assert eng2 is not None
