"""Timing equalization engine and 404 anti-enumeration helpers (S3.4)."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Self

from kanban.api.problems import not_found

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Executable


class TimingFloor:
    """Async context manager ensuring a code block executes with a consistent timing floor."""

    def __init__(
        self,
        floor_ms: float = 25.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Initialize timing floor with threshold in milliseconds and custom clock/sleep."""
        self.floor_ms = floor_ms
        self.clock = clock
        self.sleep = sleep
        self._start: float = 0.0

    async def __aenter__(self) -> Self:
        """Record start time on block entry."""
        self._start = self.clock()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Sleep remaining time to enforce the floor duration, even on exception."""
        del exc_type, exc_val, exc_tb
        elapsed_ms = (self.clock() - self._start) * 1000.0
        remaining_s = max(0.0, (self.floor_ms - elapsed_ms) / 1000.0)
        if remaining_s > 0.0:
            await self.sleep(remaining_s)


def timing_floor(
    floor_ms: float = 25.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> TimingFloor:
    """Create a TimingFloor async context manager."""
    return TimingFloor(floor_ms=floor_ms, clock=clock, sleep=sleep)


async def load_or_404(session: AsyncSession, stmt: Executable) -> Any:  # noqa: ANN401
    """Execute an RLS-filtered SELECT and return the scalar result or raise 404.

    S3.4: Unreadable objects and non-existent objects follow the identical execution path
    and branch to ensure indistinguishable behavior and prevent enumeration attacks.
    """
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        not_found()
    return row
