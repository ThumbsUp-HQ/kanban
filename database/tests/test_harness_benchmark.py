"""Benchmark test suite validating 200 clean-database tests in < 5.00s."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.parametrize("idx", range(200))
async def test_benchmark_probe(db_session: AsyncSession, idx: int) -> None:
    """Benchmark probe insert and select across 200 iterations under savepoint isolation."""
    await db_session.execute(
        text("INSERT INTO kb_harness.probe (note) VALUES (:note)"),
        {"note": f"bench_{idx}"},
    )
    result = await db_session.scalar(
        text("SELECT note FROM kb_harness.probe WHERE note = :note"),
        {"note": f"bench_{idx}"},
    )
    assert result == f"bench_{idx}"
