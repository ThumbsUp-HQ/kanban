"""Regression: record_failure with invocation_id must pass a session to the classmethod."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.gates import runner as runner_mod

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.mark.asyncio
async def test_record_failure_with_invocation_id_passes_session() -> None:
    """Previously GateCoordinator(session).record_failure ran with session=None."""
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _sess(_ctx: object) -> AsyncIterator[MagicMock]:
        yield session

    factory = MagicMock()
    factory.session = _sess
    r = runner_mod.GateWorkerRunner.__new__(runner_mod.GateWorkerRunner)
    r.session_factory = factory
    r._execution_contexts = {}  # noqa: SLF001
    r.workspace_id = None
    r.admin_principal_id = None
    with patch.object(runner_mod.GateCoordinator, "record_failure", new=AsyncMock()) as m:
        inv = uuid.uuid4()
        await r.record_failure(uuid.uuid4(), uuid.uuid4(), "GATE_TIMEOUT", invocation_id=inv)
    assert m.await_args.kwargs["session"] is session
    assert m.await_args.kwargs["invocation_id"] == inv
    session.commit.assert_awaited_once()
