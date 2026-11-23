# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for re-executing SET LOCAL GUC context on transaction re-begin (KAN-335)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from database.session import RLSContext, RLSSessionFactory


@pytest.mark.asyncio
async def test_rls_session_rebegin_preserves_guc_context(pg_worker_db: AsyncEngine) -> None:
    """Verify that committing a transaction and continuing in the same session re-binds GUCs."""
    factory = RLSSessionFactory(pg_worker_db)
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    ctx = RLSContext(
        principal_id=p_id,
        workspace_id=ws_id,
        token_scopes=("user", "read"),
        aal_level=2,
    )

    async with factory.session(ctx) as session:
        # Transaction 1
        ws1 = await session.scalar(text("SELECT current_setting('app.workspace_id', true)"))
        p1 = await session.scalar(text("SELECT current_setting('app.principal_id', true)"))
        aal1 = await session.scalar(text("SELECT current_setting('app.aal_level', true)"))
        assert ws1 == str(ws_id)
        assert p1 == str(p_id)
        assert aal1 == "2"

        # Commit Transaction 1
        await session.commit()

        # Transaction 2 (mid-session continuation)
        ws2 = await session.scalar(text("SELECT current_setting('app.workspace_id', true)"))
        p2 = await session.scalar(text("SELECT current_setting('app.principal_id', true)"))
        aal2 = await session.scalar(text("SELECT current_setting('app.aal_level', true)"))
        assert ws2 == str(ws_id), f"Expected {ws_id} in Tx 2, got {ws2!r}"
        assert p2 == str(p_id), f"Expected {p_id} in Tx 2, got {p2!r}"
        assert aal2 == "2", f"Expected '2' in Tx 2, got {aal2!r}"
