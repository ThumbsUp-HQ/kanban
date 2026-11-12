"""Concurrency stress test for activity_records hash chain serialization."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.committed_db
async def test_05_chain_concurrency_stress(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Test Case 5: 16 workers append 5 events each (80 total) without gaps/deadlocks."""
    ws_slug = f"ws-conc-{uuid.uuid4().hex[:12]}"
    row = await committed_db_session.execute(
        text(
            "INSERT INTO workspaces (slug, name) "
            "VALUES (:slug, 'Concurrency Workspace') RETURNING id"
        ),
        {"slug": ws_slug},
    )
    ws_id = row.scalar_one()
    await committed_db_session.commit()

    async def worker(worker_num: int) -> None:
        async with AsyncSession(pg_worker_db, expire_on_commit=False) as session:
            for step in range(1, 6):
                await session.execute(
                    text(
                        "SELECT append_activity("
                        "  :ws_id, NULL, NULL, NULL, 'CONCURRENT_STRESS', :payload"
                        ")"
                    ),
                    {
                        "ws_id": ws_id,
                        "payload": json.dumps({"worker": worker_num, "step": step}),
                    },
                )
                await session.commit()

    # Execute 16 concurrent workers appending 5 events each
    await asyncio.gather(*[worker(i) for i in range(16)])

    # Verify unbroken chain of 80 events
    res = await committed_db_session.execute(
        text(
            "SELECT is_valid, checked_rows, first_broken_seq, first_broken_id, failure_reason "
            "FROM verify_activity_chain(:ws_id)"
        ),
        {"ws_id": ws_id},
    )
    report = res.mappings().one()
    assert report["is_valid"] is True
    assert report["checked_rows"] == 80
    assert report["first_broken_seq"] is None
    assert report["first_broken_id"] is None
    assert report["failure_reason"] is None
