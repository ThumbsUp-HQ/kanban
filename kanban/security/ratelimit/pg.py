"""PostgreSQL sliding-window rate limiter implementation (S2.2, S2.4)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from kanban.security.ratelimit.base import RateLimitDecision, RateLimitPolicy

if TYPE_CHECKING:
    from datetime import datetime


_KEY_LENGTH = 32


class PgRateLimiter:
    """PostgreSQL-backed rate limiter executing kb_infra.rate_limit_hit."""

    def __init__(
        self,
        engine_or_session: AsyncEngine | AsyncConnection | AsyncSession | str | None = None,
        *,
        engine: AsyncEngine | AsyncConnection | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        """Initialize PostgreSQL rate limiter with engine, session, or connection string."""
        self._engine: AsyncEngine | AsyncConnection | None = None
        self._session: AsyncSession | None = None

        if isinstance(engine_or_session, (AsyncEngine, AsyncConnection)):
            self._engine = engine_or_session
        elif isinstance(engine_or_session, AsyncSession):
            self._session = engine_or_session
        elif isinstance(engine_or_session, str):
            self._engine = create_async_engine(engine_or_session)

        if engine is not None:
            self._engine = engine
        if session is not None:
            self._session = session

    def _get_engine(self) -> AsyncEngine:
        """Resolve or lazily initialize the AsyncEngine."""
        if isinstance(self._engine, AsyncEngine):
            return self._engine

        dsn = os.environ.get("KANBAN_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if dsn:
            new_eng = create_async_engine(dsn)
            self._engine = new_eng
            return new_eng

        socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")  # noqa: S108
        user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
        default_dsn = f"postgresql+asyncpg://{user}@/postgres?host={socket_dir}"
        new_eng = create_async_engine(default_dsn)
        self._engine = new_eng
        return new_eng

    async def hit(
        self,
        policy: RateLimitPolicy,
        key: bytes,
        now: datetime | None = None,
    ) -> RateLimitDecision:
        """Record hit against PostgreSQL bucket and return decision."""
        if len(key) != _KEY_LENGTH:
            msg = f"Rate limit key must be exactly {_KEY_LENGTH} bytes (got {len(key)})"
            raise ValueError(msg)

        if now is not None:
            stmt = text(
                "SELECT allowed, remaining, retry_after "
                "FROM kb_infra.rate_limit_hit(:policy, :key, :limit, :window_s, :now)"
            )
            params = {
                "policy": policy.name,
                "key": key,
                "limit": policy.limit,
                "window_s": policy.window_seconds,
                "now": now,
            }
        else:
            stmt = text(
                "SELECT allowed, remaining, retry_after "
                "FROM kb_infra.rate_limit_hit(:policy, :key, :limit, :window_s)"
            )
            params = {
                "policy": policy.name,
                "key": key,
                "limit": policy.limit,
                "window_s": policy.window_seconds,
            }

        if self._session is not None:
            res = await self._session.execute(stmt, params)
        elif isinstance(self._engine, AsyncConnection):
            res = await self._engine.execute(stmt, params)
        else:
            eng = self._get_engine()
            async with eng.begin() as conn:
                res = await conn.execute(stmt, params)

        row = res.one()
        return RateLimitDecision(
            allowed=bool(row[0]),
            remaining=int(row[1]),
            retry_after_seconds=int(row[2]),
        )

    async def reset(self, policy: RateLimitPolicy, key: bytes) -> None:
        """Reset rate limit bucket in PostgreSQL."""
        if len(key) != _KEY_LENGTH:
            msg = f"Rate limit key must be exactly {_KEY_LENGTH} bytes (got {len(key)})"
            raise ValueError(msg)

        stmt = text("SELECT kb_infra.rate_limit_reset(:policy, :key)")
        params = {"policy": policy.name, "key": key}

        if self._session is not None:
            await self._session.execute(stmt, params)
        elif isinstance(self._engine, AsyncConnection):
            await self._engine.execute(stmt, params)
        else:
            eng = self._get_engine()
            async with eng.begin() as conn:
                await conn.execute(stmt, params)
