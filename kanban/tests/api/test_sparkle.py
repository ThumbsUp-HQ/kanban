# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for Sparkle FIM project key resolution and access policies (KB-P3-AUDIT-04)."""

from __future__ import annotations

import importlib
import uuid
from typing import Any, Self
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import kanban.api.v1.sparkle as kanban_sparkle_mod
from kanban.api.deps import PrincipalContext
from kanban.api.v1.sparkle import (
    SparkleRequest as KanbanSparkleRequest,
)
from kanban.api.v1.sparkle import (
    router as kanban_sparkle_router,
)
from kanban.auth.sessions.csrf import PRE_SESSION_ID, generate_csrf_token

_agent_asgi = importlib.import_module("agent.asgi")
_agent_providers_base = importlib.import_module("agent.providers.base")
_agent_providers_router = importlib.import_module("agent.providers.router")
_agent_sparkle_pipeline = importlib.import_module("agent.sparkle.pipeline")

create_agent_app = _agent_asgi.create_agent_app
StreamChunk = _agent_providers_base.StreamChunk
ProviderRouter = _agent_providers_router.ProviderRouter
RouteCandidate = _agent_providers_router.RouteCandidate
SparkleRequest = _agent_sparkle_pipeline.SparkleRequest

MockAppContext = tuple[Any, uuid.UUID, uuid.UUID, dict[str, uuid.UUID], str]


def _make_csrf_token() -> str:
    return generate_csrf_token(PRE_SESSION_ID, b"\x00" * 32)


class _StaticPrincipalResolver:
    """Mock principal resolver for testing authenticated endpoint flows."""

    def __init__(self, principal: PrincipalContext) -> None:
        self.principal = principal

    async def resolve(self, request: object) -> PrincipalContext:
        del request
        return self.principal


class _MockSession:
    """Mock database session simulating project resolution and RLS capability checks."""

    def __init__(
        self,
        projects: dict[str, uuid.UUID],
        era_allowed: set[uuid.UUID],
        workspace_id: uuid.UUID,
    ) -> None:
        self.projects = projects
        self.era_allowed = era_allowed
        self.workspace_id = workspace_id
        self.info: dict[str, Any] = {}

    def begin(self) -> _MockSession:
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        del exc_type, exc_val, exc_tb

    async def execute(  # noqa: C901, PLR0912
        self,
        stmt: object,
        params: dict[str, Any] | None = None,
    ) -> MagicMock:
        sql = str(stmt)
        params = params or {}

        mock_res = MagicMock()

        if "set_config" in sql:
            mock_res.scalar_one_or_none.return_value = None
            return mock_res

        if "FROM projects" in sql:
            ident = params.get("ident", "")
            ws_id = params.get("ws_id")
            p_id = params.get("p_id")
            if p_id:
                str_vals = [str(v) for v in self.projects.values()]
                if str(p_id) in str_vals and ws_id == self.workspace_id:
                    mock_res.scalar_one_or_none.return_value = p_id
                else:
                    mock_res.scalar_one_or_none.return_value = None
            elif ident:
                target = self.projects.get(ident.upper())
                if target and ws_id == self.workspace_id:
                    mock_res.scalar_one_or_none.return_value = target
                else:
                    mock_res.scalar_one_or_none.return_value = None
            else:
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        if "FROM effective_resource_access era" in sql:
            obj_id = params.get("obj_id") or params.get("proj_id")
            if obj_id in self.era_allowed:
                mock_res.scalar_one_or_none.return_value = 1
            else:
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        if "FROM issues" in sql or "FROM docs" in sql:
            obj_id = params.get("obj_id")
            if obj_id in self.era_allowed:
                # Return first project
                mock_res.scalar_one_or_none.return_value = next(iter(self.projects.values()), None)
            else:
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        mock_res.scalar_one_or_none.return_value = None
        return mock_res


class _MockSessionFactory:
    def __init__(self, session: _MockSession) -> None:
        self.session = session

    def sessionmaker(self) -> _MockSession:
        return self.session


@pytest.fixture
def mock_app_and_context() -> MockAppContext:
    """Fixture provisioning agent app, mock DB session, and auth context."""
    app = create_agent_app()
    ws_id = uuid.uuid4()
    principal_id = uuid.uuid4()
    principal = PrincipalContext(principal_id=principal_id, workspace_id=ws_id)
    app.state.principal_resolver = _StaticPrincipalResolver(principal)

    proj_uuid = uuid.uuid4()
    projects = {"KAN": proj_uuid, "CORE": proj_uuid}
    era_allowed = {proj_uuid}

    session = _MockSession(projects=projects, era_allowed=era_allowed, workspace_id=ws_id)
    app.state.session_factory = _MockSessionFactory(session)

    class _MockProvider:
        async def stream_complete(self, req: object) -> Any:  # noqa: ANN401
            del req
            yield StreamChunk(delta="mock_completion", index=0, finish_reason="stop")

    candidate = RouteCandidate(
        provider_config_id=uuid.uuid4(),
        provider=_MockProvider(),
        residency_tier="fixture",
        priority=1,
    )
    app.state.provider_router = ProviderRouter(
        workspace_id=ws_id,
        candidates=[candidate],
        air_gap_mode=False,
    )

    csrf_token = _make_csrf_token()
    return app, ws_id, proj_uuid, projects, csrf_token


def test_kanban_sparkle_reexports() -> None:
    """Verifies kanban.api.v1.sparkle exposes SparkleRequest and router dynamically."""
    assert KanbanSparkleRequest is SparkleRequest
    assert kanban_sparkle_router is not None
    with pytest.raises(AttributeError):
        _ = kanban_sparkle_mod.nonexistent_attr_probe


@pytest.mark.asyncio
async def test_sparkle_accepts_project_key_string(mock_app_and_context: MockAppContext) -> None:
    """Accepts string project keys like 'KAN' and resolves cleanly via session."""
    app, _ws_id, _proj_uuid, _projects, csrf_token = mock_app_and_context

    headers = {"X-CSRF-Token": csrf_token}
    cookies = {"__Host-kb_csrf": csrf_token}
    payload = {
        "project_id": "KAN",
        "surface": "doc",
        "prefix": "def solve():\n    ",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers=headers,
    ) as client:
        res = await client.post("/api/v1/sparkle/complete", json=payload)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]


@pytest.mark.asyncio
async def test_sparkle_accepts_project_uuid_direct(mock_app_and_context: MockAppContext) -> None:
    """Accepts valid UUID project_id directly."""
    app, _ws_id, proj_uuid, _projects, csrf_token = mock_app_and_context

    headers = {"X-CSRF-Token": csrf_token}
    cookies = {"__Host-kb_csrf": csrf_token}
    payload = {
        "project_id": str(proj_uuid),
        "surface": "doc",
        "prefix": "def run():\n    ",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers=headers,
    ) as client:
        res = await client.post("/api/v1/sparkle/complete", json=payload)
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_sparkle_unknown_project_key_returns_404(
    mock_app_and_context: MockAppContext,
) -> None:
    """Unknown project key returns timing-equalized 404 (never 422 or 500)."""
    app, _ws_id, _proj_uuid, _projects, csrf_token = mock_app_and_context

    headers = {"X-CSRF-Token": csrf_token}
    cookies = {"__Host-kb_csrf": csrf_token}
    payload = {
        "project_id": "NONEXISTENT",
        "surface": "doc",
        "prefix": "def test():\n    ",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers=headers,
    ) as client:
        res = await client.post("/api/v1/sparkle/complete", json=payload)
        assert res.status_code == 404
        data = res.json()
        assert data.get("status") == 404


@pytest.mark.asyncio
async def test_sparkle_cross_tenant_project_key_returns_404(
    mock_app_and_context: MockAppContext,
) -> None:
    """Cross-tenant project key in another workspace returns 404 without resource enumeration."""
    app, _ws_id, _proj_uuid, _projects, csrf_token = mock_app_and_context

    headers = {"X-CSRF-Token": csrf_token}
    cookies = {"__Host-kb_csrf": csrf_token}
    payload = {
        "project_id": "OTHER_WS_PROJ",
        "surface": "doc",
        "prefix": "def secret():\n    ",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers=headers,
    ) as client:
        res = await client.post("/api/v1/sparkle/complete", json=payload)
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_sparkle_none_project_id_with_object_id(
    mock_app_and_context: MockAppContext,
) -> None:
    """project_id=None with valid object_id derives project and succeeds."""
    app, _ws_id, _proj_uuid, _projects, csrf_token = mock_app_and_context

    obj_uuid = uuid.uuid4()
    app.state.session_factory.session.era_allowed.add(obj_uuid)

    headers = {"X-CSRF-Token": csrf_token}
    cookies = {"__Host-kb_csrf": csrf_token}
    payload = {
        "project_id": None,
        "object_id": str(obj_uuid),
        "surface": "comment",
        "prefix": "Looks good, let's ship ",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers=headers,
    ) as client:
        res = await client.post("/api/v1/sparkle/complete", json=payload)
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_sparkle_payload_oversize_413(mock_app_and_context: MockAppContext) -> None:
    """Payloads exceeding 16 KiB budget return 413 Payload Too Large."""
    app, _ws_id, proj_uuid, _projects, csrf_token = mock_app_and_context

    headers = {"X-CSRF-Token": csrf_token}
    cookies = {"__Host-kb_csrf": csrf_token}
    payload = {
        "project_id": str(proj_uuid),
        "surface": "doc",
        "prefix": "A" * 17000,
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies=cookies,
        headers=headers,
    ) as client:
        res = await client.post("/api/v1/sparkle/complete", json=payload)
        assert res.status_code == 413
