# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Test fixtures for /mcp/docs surface integration tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from database.session import RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.app import create_app
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    generate_csrf_token,
)
from kanban.tests.security.helpers import (
    add_role_binding,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class SeededUser:
    """A user principal created by make_user fixture."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    handle: str


class _MutableResolver:
    """Principal resolver whose active principal is switched by as_principal fixture."""

    def __init__(self) -> None:
        self.principal: PrincipalContext | None = None

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        del request
        return self.principal


@dataclass(slots=True)
class ApiEnv:
    """Running app, HTTP client, seed session and active-principal switch."""

    client: httpx.AsyncClient
    resolver: _MutableResolver
    seed: AsyncSession
    workspace_id: uuid.UUID


@pytest.fixture
async def api_env(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> AsyncIterator[ApiEnv]:
    """Provide running FastAPI app, client, and seed session bound to fresh workspace."""
    workspace_id = await create_workspace(committed_db_session, name="Engineering Docs")
    await committed_db_session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    resolver = _MutableResolver()
    app = create_app()
    app.state.session_factory = RLSSessionFactory(app_engine)
    app.state.principal_resolver = resolver
    transport = httpx.ASGITransport(app=app)
    csrf_token = generate_csrf_token(PRE_SESSION_ID, b"\x00" * 32)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={CSRF_HEADER_NAME: csrf_token},
            cookies={CSRF_COOKIE_NAME: csrf_token},
        ) as client:
            yield ApiEnv(client, resolver, committed_db_session, workspace_id)
    finally:
        await app_engine.dispose()


@pytest.fixture
def make_user(api_env: ApiEnv) -> Callable[..., Awaitable[SeededUser]]:
    """Return a factory that creates a user, optionally with a workspace-level role."""

    async def _make(handle: str, *, workspace_role: str | None = None) -> SeededUser:
        user_id = await create_user(
            api_env.seed, api_env.workspace_id, handle=f"@{handle}", display_name=handle.title()
        )
        if workspace_role is not None:
            await add_role_binding(
                api_env.seed,
                api_env.workspace_id,
                user_id,
                role=workspace_role,
                scope_type="workspace",
            )
        await rebuild_era(api_env.seed, api_env.workspace_id)
        await api_env.seed.commit()
        return SeededUser(id=user_id, workspace_id=api_env.workspace_id, handle=handle)

    return _make


@pytest.fixture
def as_principal(api_env: ApiEnv) -> Callable[..., httpx.AsyncClient]:
    """Switch the authenticated principal and return the shared HTTP client."""

    def _switch(
        user: SeededUser,
        *,
        scopes: tuple[str, ...] = ("session", "docs:read", "docs:write"),
        aal_level: int = 1,
        agent_principal_id: uuid.UUID | None = None,
    ) -> httpx.AsyncClient:
        api_env.resolver.principal = PrincipalContext(
            principal_id=user.id,
            workspace_id=user.workspace_id,
            token_scopes=scopes,
            aal_level=aal_level,
            agent_principal_id=agent_principal_id,
        )
        return api_env.client

    return _switch
