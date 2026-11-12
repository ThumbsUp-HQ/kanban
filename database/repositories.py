"""Base repository implementing strictly typed Universal Object Graph persistence."""

import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.base import Base
from database.session import UnboundRLSSessionError

TModel = TypeVar("TModel", bound=Base)

MIN_LIMIT = 1
MAX_LIMIT = 500


class BaseRepository(Generic[TModel]):  # noqa: UP046
    """Generic repository providing typed data access over an RLS-bound session."""

    def __init__(self, session: AsyncSession, model: type[TModel]) -> None:
        """Initialize repository with an active RLS-bound session and entity model."""
        if not session.info.get("rls_bound", False):
            msg = "BaseRepository requires an active RLS-bound session"
            raise UnboundRLSSessionError(msg)
        self._session = session
        self._model = model

    @property
    def session(self) -> AsyncSession:
        """The underlying RLS-bound session."""
        return self._session

    @property
    def model(self) -> type[TModel]:
        """The entity model class managed by this repository."""
        return self._model

    async def get_by_id(self, entity_id: uuid.UUID) -> TModel | None:
        """Fetch a single entity by its primary key."""
        return await self._session.get(self._model, entity_id)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[TModel]:
        """List entities with bounded pagination (limit between 1 and 500)."""
        if limit < MIN_LIMIT or limit > MAX_LIMIT:
            msg = f"Limit must be between {MIN_LIMIT} and {MAX_LIMIT} (got {limit})"
            raise ValueError(msg)
        if offset < 0:
            msg = f"Offset cannot be negative (got {offset})"
            raise ValueError(msg)

        stmt = select(self._model).limit(limit).offset(offset)
        result = await self._session.scalars(stmt)
        return result.all()

    def add(self, entity: TModel) -> TModel:
        """Add a new entity instance to the session."""
        self._session.add(entity)
        return entity

    async def delete(self, entity: TModel) -> None:
        """Delete an existing entity instance from the session."""
        await self._session.delete(entity)

    async def flush(self) -> None:
        """Flush pending changes to the database within the current transaction."""
        await self._session.flush()
