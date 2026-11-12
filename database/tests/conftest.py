"""Database test configuration and role-bound fixtures."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def bind_ctx(
    session: AsyncSession,
    principal_id: UUID | str | None,
    workspace_id: UUID | str | None,
) -> None:
    """Set transaction-local principal and workspace context (Section 3.3)."""
    p_str = str(principal_id) if principal_id is not None else ""
    w_str = str(workspace_id) if workspace_id is not None else ""
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": p_str, "w_id": w_str},
    )


@pytest.fixture
def superuser_session(db_session: AsyncSession) -> AsyncSession:
    """Provide session with default superuser / maintenance privileges."""
    return db_session


@pytest.fixture
async def app_session(db_session: AsyncSession) -> AsyncSession:
    """Provide session switched to least-privilege kanban_app role."""
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    return db_session
