"""Shared API test fixtures: seeded principals, projects, principal switching, contract capture.

Fixtures here run the real ASGI app over ``httpx.ASGITransport`` against a PostgreSQL database
connected as the non-bypass ``kanban_app`` role, while seeding happens through the committed
migrator session. Tests using ``api_env`` must be marked ``committed_db`` (module-level
``pytestmark`` is sufficient).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

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
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit.decorator import build_rate_limiter
from kanban.tests.contract import ContractRecorder
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@dataclass(frozen=True, slots=True)
class SeededUser:
    """A user principal created by the ``make_user`` fixture."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    handle: str


class _MutableResolver:
    """Principal resolver whose active principal is switched by the ``as_principal`` fixture."""

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


@pytest.fixture(scope="session")
def contract_recorder() -> Iterator[ContractRecorder]:
    """Session-wide recorder; writes ``KB_CONTRACT_OUT`` at session end when configured."""
    recorder = ContractRecorder()
    yield recorder
    recorder.write_if_configured()


@pytest.fixture
async def api_env(
    committed_db_session: AsyncSession, pg_worker_db: AsyncEngine
) -> AsyncIterator[ApiEnv]:
    """Provide the running app, client and seed session bound to a fresh workspace."""
    workspace_id = await create_workspace(committed_db_session, name="Engineering")
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
    app.state.key_material = KeyMaterial(
        master_kek=b"m" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"\x00" * 32,
    )
    app.state.session_factory = RLSSessionFactory(app_engine)
    app.state.rate_limiter = build_rate_limiter(engine=app_engine)
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
            scope_type = "server" if workspace_role == "SERVER_ADMIN" else "workspace"
            await add_role_binding(
                api_env.seed,
                api_env.workspace_id,
                user_id,
                role=workspace_role,
                scope_type=scope_type,
            )
        await rebuild_era(api_env.seed, api_env.workspace_id)
        await api_env.seed.commit()
        return SeededUser(id=user_id, workspace_id=api_env.workspace_id, handle=handle)

    return _make


@pytest.fixture
def make_project(api_env: ApiEnv) -> Callable[..., Awaitable[uuid.UUID]]:
    """Return a factory that creates a project plus per-user project roles (bypasses the API)."""

    async def _make(
        identifier: str,
        *,
        created_by: SeededUser,
        roles: Mapping[SeededUser, str] | None = None,
        modules_enabled: bool = False,
    ) -> uuid.UUID:
        project_id = await create_project(
            api_env.seed,
            api_env.workspace_id,
            identifier=identifier,
            name=f"{identifier} project",
            created_by_id=created_by.id,
            modules_enabled=modules_enabled,
        )
        for user, role in (roles or {}).items():
            await add_role_binding(
                api_env.seed,
                api_env.workspace_id,
                user.id,
                role=role,
                scope_type="project",
                project_id=project_id,
            )
        await rebuild_era(api_env.seed, api_env.workspace_id)
        await api_env.seed.commit()
        return project_id

    return _make


@pytest.fixture
def make_module(api_env: ApiEnv) -> Callable[..., Awaitable[uuid.UUID]]:
    """Return a factory that inserts a module row and its spine object for a project."""

    async def _make(project_id: uuid.UUID, name: str, *, created_by: SeededUser) -> uuid.UUID:
        module_id = await create_registered_object(
            api_env.seed,
            api_env.workspace_id,
            kind="module",
            key=name,
            title=name,
            project_id=project_id,
            created_by_id=created_by.id,
        )
        await api_env.seed.execute(
            text(
                "INSERT INTO modules (id, workspace_id, project_id, name)"
                " VALUES (:id, :ws, :proj, :name)"
            ),
            {"id": module_id, "ws": api_env.workspace_id, "proj": project_id, "name": name},
        )
        await rebuild_era(api_env.seed, api_env.workspace_id)
        await api_env.seed.commit()
        return module_id

    return _make


@pytest.fixture
def as_principal(api_env: ApiEnv) -> Callable[..., httpx.AsyncClient]:
    """Switch the authenticated principal and return the shared HTTP client."""

    def _switch(
        user: SeededUser,
        *,
        scopes: tuple[str, ...] = ("session",),
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
