"""Unit tests for RLS dependency, identity isolation, and connection pool safety (S3.3)."""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from database.session import RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import (
    DenyAllResolver,
    PrincipalContext,
    PrincipalResolver,
    get_principal,
    get_rls_session,
)
from kanban.api.problems import (
    PROBLEM_MEDIA_TYPE,
    ProblemException,
    problem_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware


class _StubResolver:
    """Configurable resolver returning a fixed PrincipalContext or None."""

    def __init__(self, principal: PrincipalContext | None = None) -> None:
        self.principal = principal

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        del request
        return self.principal


def _build_test_api(
    resolver: PrincipalResolver | None = None,
    session_factory: RLSSessionFactory | None = None,
) -> FastAPI:
    """Create test FastAPI application wired with RLS dependencies."""
    app = FastAPI(title="RLS Test App")
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    app.state.principal_resolver = resolver if resolver is not None else DenyAllResolver()
    app.state.session_factory = session_factory

    router = APIRouter(prefix="/api/v1/test")

    @router.get("/whoami")
    async def whoami(
        principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> dict[str, str]:
        return {
            "principal_id": str(principal.principal_id),
            "workspace_id": str(principal.workspace_id),
        }

    @router.get("/inspect-db-principal")
    async def inspect_db_principal(
        session: Annotated[AsyncSession, Depends(get_rls_session)],
    ) -> dict[str, Any]:
        result = await session.execute(text("SELECT current_setting('app.principal_id', true)"))
        val = result.scalar_one_or_none()
        return {"current_setting_principal_id": val}

    @router.get("/error-rollback")
    async def error_rollback(
        session: Annotated[AsyncSession, Depends(get_rls_session)],
    ) -> None:
        del session
        err_msg = "Forced error inside transaction"
        raise RuntimeError(err_msg)

    app.include_router(router)
    return app


def test_principal_context_validation() -> None:
    """Test PrincipalContext bounds checking for aal_level and scope iteration."""
    p_id = uuid.uuid4()
    w_id = uuid.uuid4()

    # Valid
    ctx = PrincipalContext(principal_id=p_id, workspace_id=w_id, aal_level=1)
    assert ctx.aal_level == 1
    assert ctx.token_scopes == ()

    # Iterable conversion
    ctx_scopes = PrincipalContext(
        principal_id=p_id,
        workspace_id=w_id,
        token_scopes=["read:issues", "write:issues"],  # type: ignore[arg-type]
    )
    assert isinstance(ctx_scopes.token_scopes, tuple)
    assert ctx_scopes.token_scopes == ("read:issues", "write:issues")

    # Invalid AAL
    with pytest.raises(ValueError, match="Invalid aal_level"):
        PrincipalContext(principal_id=p_id, workspace_id=w_id, aal_level=3)

    # Non-iterable token_scopes
    with pytest.raises(TypeError, match="Token scopes must be an iterable"):
        PrincipalContext(principal_id=p_id, workspace_id=w_id, token_scopes=123)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_rls_session_missing_factory() -> None:
    """Test get_rls_session raises RuntimeError when session_factory is not configured."""
    p_id = uuid.uuid4()
    w_id = uuid.uuid4()
    stub_principal = PrincipalContext(principal_id=p_id, workspace_id=w_id)
    app = _build_test_api(resolver=_StubResolver(stub_principal), session_factory=None)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(RuntimeError, match="RLS session factory is not configured"):
            await client.get("/api/v1/test/inspect-db-principal")


@pytest.mark.asyncio
async def test_case_3_security_header_spoofing_denied() -> None:
    """Test Case 3: Inbound request with client identity headers/query returns 401.

    Ensures the database session factory is never touched.
    """
    mock_factory = AsyncMock(spec=RLSSessionFactory)
    app = _build_test_api(resolver=DenyAllResolver(), session_factory=mock_factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Spoofed headers and query param
        response = await client.get(
            "/api/v1/test/inspect-db-principal?principal_id=00000000-0000-0000-0000-000000000001",
            headers={
                "X-Principal-Id": str(uuid.uuid4()),
                "X-Workspace-Id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 401
        assert response.headers.get("content-type") == PROBLEM_MEDIA_TYPE

        data = response.json()
        assert data["code"] == "AUTHENTICATION_REQUIRED"
        assert data["status"] == 401
        assert data["title"] == "Authentication Required"
        # WWW-Authenticate header must be omitted
        assert "www-authenticate" not in response.headers

        # Verify DB factory was NEVER called
        assert mock_factory.session.call_count == 0


@pytest.mark.asyncio
async def test_case_2_positive_rls_session_context_binding(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 2: Route using get_rls_session observes current_setting('app.principal_id')."""
    p_id = uuid.uuid4()
    w_id = uuid.uuid4()
    stub_principal = PrincipalContext(principal_id=p_id, workspace_id=w_id)
    factory = RLSSessionFactory(pg_worker_db)

    app = _build_test_api(resolver=_StubResolver(stub_principal), session_factory=factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/test/inspect-db-principal")
        assert response.status_code == 200
        data = response.json()
        assert data["current_setting_principal_id"] == str(p_id)


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_4_security_context_leak_and_pool_isolation(
    request: pytest.FixtureRequest,
) -> None:
    """Test Case 4: Sequential requests with different principals on pooled connection.

    Second request sees only its own principal; pool connection has app.principal_id cleared.
    """
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    db_name = f"kanban_test_{worker_id}"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    dsn = build_dsn(database=db_name, host=socket_dir, user=user)

    # Single-connection pool to guarantee sequential reuse of the exact same physical connection
    single_conn_engine = create_async_engine(dsn, pool_size=1, max_overflow=0)
    factory = RLSSessionFactory(single_conn_engine)

    try:
        p1 = uuid.uuid4()
        w1 = uuid.uuid4()
        ctx1 = PrincipalContext(principal_id=p1, workspace_id=w1)

        p2 = uuid.uuid4()
        w2 = uuid.uuid4()
        ctx2 = PrincipalContext(principal_id=p2, workspace_id=w2)

        dynamic_resolver = _StubResolver(ctx1)
        app = _build_test_api(resolver=dynamic_resolver, session_factory=factory)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # First request with Principal 1
            res1 = await client.get("/api/v1/test/inspect-db-principal")
            assert res1.status_code == 200
            assert res1.json()["current_setting_principal_id"] == str(p1)

            # Switch resolver to Principal 2
            dynamic_resolver.principal = ctx2

            # Second request with Principal 2 on the exact same connection
            res2 = await client.get("/api/v1/test/inspect-db-principal")
            assert res2.status_code == 200
            assert res2.json()["current_setting_principal_id"] == str(p2)

        # After the requests, inspect connection returned to the pool: setting must be empty or NULL
        async with single_conn_engine.connect() as check_conn:
            result = await check_conn.execute(
                text("SELECT current_setting('app.principal_id', true)")
            )
            val = result.scalar_one_or_none()
            assert val is None or val == ""
    finally:
        await single_conn_engine.dispose()
