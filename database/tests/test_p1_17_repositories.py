"""Unit tests for BaseRepository (KANBA-55 / KB-P1-17)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Workspace
from database.repositories import BaseRepository
from database.session import RLSContext, UnboundRLSSessionError, bind_rls_context


@pytest.mark.asyncio
async def test_repository_unbound_session_guard(db_session: AsyncSession) -> None:
    """Verify instantiating BaseRepository with unbound session raises UnboundRLSSessionError."""
    # Ensure session has no rls_bound
    db_session.info.pop("rls_bound", None)

    with pytest.raises(
        UnboundRLSSessionError, match="BaseRepository requires an active RLS-bound session"
    ):
        BaseRepository(db_session, Workspace)


@pytest.mark.asyncio
async def test_repository_crud_operations(db_session: AsyncSession) -> None:
    """Verify get_by_id, list_all, add, delete, flush on BaseRepository."""
    ws_id = uuid.uuid4()
    u_id = uuid.uuid4()

    ctx = RLSContext(principal_id=u_id, workspace_id=ws_id)
    async with db_session.begin():
        # Bind RLS context to the test savepoint session
        await bind_rls_context(db_session, ctx)
        assert db_session.info.get("rls_bound") is True

        repo = BaseRepository(db_session, Workspace)
        assert repo.session is db_session
        assert repo.model is Workspace

        # 1. Add workspace
        ws = Workspace(id=ws_id, slug=f"repo-ws-{ws_id.hex[:8]}", name="Repo Workspace")
        added = repo.add(ws)
        assert added is ws
        await repo.flush()

        # 2. get_by_id existing
        fetched = await repo.get_by_id(ws_id)
        assert fetched is not None
        assert fetched.id == ws_id
        assert fetched.name == "Repo Workspace"

        # get_by_id non-existing
        non_existent = await repo.get_by_id(uuid.uuid4())
        assert non_existent is None

        # 3. list_all
        items = await repo.list_all(limit=10, offset=0)
        assert len(items) >= 1
        assert any(w.id == ws_id for w in items)

        # 4. delete
        await repo.delete(ws)
        await repo.flush()

        deleted = await repo.get_by_id(ws_id)
        assert deleted is None


@pytest.mark.asyncio
async def test_repository_pagination_bounds(db_session: AsyncSession) -> None:
    """Verify list_all enforces 1 <= limit <= 500 and offset >= 0."""
    ctx = RLSContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    async with db_session.begin():
        await bind_rls_context(db_session, ctx)

        repo = BaseRepository(db_session, Workspace)

        # limit = 0 raises ValueError
        with pytest.raises(ValueError, match=r"Limit must be between 1 and 500 \(got 0\)"):
            await repo.list_all(limit=0)

        # limit = 501 raises ValueError
        with pytest.raises(ValueError, match=r"Limit must be between 1 and 500 \(got 501\)"):
            await repo.list_all(limit=501)

        # limit = -5 raises ValueError
        with pytest.raises(ValueError, match=r"Limit must be between 1 and 500 \(got -5\)"):
            await repo.list_all(limit=-5)

        # offset = -1 raises ValueError
        with pytest.raises(ValueError, match=r"Offset cannot be negative \(got -1\)"):
            await repo.list_all(limit=100, offset=-1)

        # Valid boundaries: limit=1 and limit=500 succeed
        res1 = await repo.list_all(limit=1, offset=0)
        assert isinstance(res1, (list, tuple))

        res500 = await repo.list_all(limit=500, offset=0)
        assert isinstance(res500, (list, tuple))
