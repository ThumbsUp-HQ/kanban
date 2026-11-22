# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Background sweeper deleting expired issue claim leases via SKIP LOCKED (KB-CONCURRENCY-01)."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from database.models.issue_lease import IssueLease
from database.session import RLSContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.session import RLSSessionFactory

logger = logging.getLogger(__name__)

__all__ = [
    "LeaseExpirySweeper",
]


class LeaseExpirySweeper:
    """Sweeper that detects and purges expired issue leases under concurrency locks."""

    def __init__(
        self,
        session_factory: RLSSessionFactory | None = None,
        sweep_interval_s: float = 5.0,
        batch_size: int = 100,
        workspace_id: uuid.UUID | None = None,
        admin_principal_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize sweeper with optional session factory and poll interval."""
        self.session_factory = session_factory
        self.sweep_interval_s = sweep_interval_s
        self.batch_size = batch_size
        self.workspace_id = workspace_id
        self.admin_principal_id = admin_principal_id

    async def sweep_once(self, session: AsyncSession) -> int:
        """Purge expired leases in current transaction using FOR UPDATE SKIP LOCKED."""
        now = dt.datetime.now(dt.UTC)
        stmt = (
            select(IssueLease)
            .where(IssueLease.expires_at <= now)
            .order_by(IssueLease.expires_at.asc())
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        res = await session.execute(stmt)
        expired_leases = list(res.scalars().all())

        if not expired_leases:
            return 0

        for lease in expired_leases:
            payload_str = json.dumps(
                {
                    "lease_id": str(lease.id),
                    "fencing_token": lease.fencing_token,
                    "expired_at": lease.expires_at.isoformat(),
                },
                ensure_ascii=False,
            )
            # Record activity ledger entry
            try:
                await session.execute(
                    text(
                        "SELECT append_activity("
                        "  :ws, :oid, CAST('issue' AS object_kind), :actor, 'ISSUE_LEASE_EXPIRED',"
                        "  CAST(:payload AS jsonb)"
                        ")"
                    ),
                    {
                        "ws": lease.workspace_id,
                        "oid": lease.issue_id,
                        "actor": lease.principal_id,
                        "payload": payload_str,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed appending ISSUE_LEASE_EXPIRED activity: %s", exc)

            await session.delete(lease)

        await session.flush()
        return len(expired_leases)

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run continuous sweeping loop until stop_event is signaled."""
        admin_ctx = RLSContext(
            principal_id=self.admin_principal_id or uuid.UUID(int=0),
            workspace_id=self.workspace_id or uuid.UUID(int=0),
            token_scopes=("admin",),
            aal_level=2,
        )
        while not stop_event.is_set():
            if self.session_factory is not None:
                try:
                    async with self.session_factory.session(admin_ctx) as session:
                        await self.sweep_once(session)
                        await session.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Lease expiry sweeper poll error: %s", exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=self.sweep_interval_s)
