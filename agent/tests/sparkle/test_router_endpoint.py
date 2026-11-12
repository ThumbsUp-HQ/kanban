# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Integration unit tests for Sparkle FIM router endpoint (Cases 8b, 9, and ASGI composition)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from starlette.requests import Request

from agent.asgi import create_agent_app
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sparkle.pipeline import SparkleRequest
from agent.sparkle.router import (
    _resolve_provider_router,
    complete_sparkle,
    verify_sparkle_access,
)
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from agent.tests.sparkle.test_retrieval import _MockAsyncSession
from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

_CASSETTES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "ai"


class _StaticPrincipalResolver:
    """Mock principal resolver for testing authenticated endpoint flows."""

    def __init__(self, principal: PrincipalContext) -> None:
        self.principal = principal

    async def resolve(self, request: object) -> PrincipalContext:
        del request
        return self.principal


def _setup_app_with_cassette(cassette_name: str, workspace_id: uuid.UUID) -> FastAPI:
    app = create_agent_app()
    principal_id = uuid.uuid4()
    principal = PrincipalContext(principal_id=principal_id, workspace_id=workspace_id)
    app.state.principal_resolver = _StaticPrincipalResolver(principal)

    cas = load_cassette(_CASSETTES_DIR / cassette_name)
    provider = FixtureLLMProvider([cas])
    candidate = RouteCandidate(
        provider_config_id=uuid.uuid4(),
        provider=provider,
        residency_tier="fixture",
        priority=1,
    )
    app.state.provider_router = ProviderRouter(
        workspace_id=workspace_id,
        candidates=[candidate],
        air_gap_mode=False,
    )
    return app


@pytest.mark.asyncio
async def test_csrf_validation_missing_and_mismatch() -> None:
    """Case 9a: Missing or mismatched CSRF token returns RFC 7807 403 Forbidden."""
    ws_id = uuid.uuid4()
    app = _setup_app_with_cassette("sparkle_fim_ok.yaml", ws_id)

    payload = {
        "project_id": str(uuid.uuid4()),
        "surface": "doc",
        "prefix": "def foo():\n    ",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Missing CSRF header and cookie
        res_no_csrf = await client.post("/api/v1/sparkle/complete", json=payload)
        assert res_no_csrf.status_code == 403
        problem = res_no_csrf.json()
        assert problem["code"] == "CSRF_TOKEN_MISSING"

        # 2. Missing cookie token
        res_no_cookie = await client.post(
            "/api/v1/sparkle/complete",
            json=payload,
            headers={"X-CSRF-Token": "test-token"},
        )
        assert res_no_cookie.status_code == 403
        assert res_no_cookie.json()["code"] == "CSRF_TOKEN_MISSING"

        # 3. Missing header token
        res_no_header = await client.post(
            "/api/v1/sparkle/complete",
            json=payload,
            cookies={"__Host-kb_csrf": "test-token"},
        )
        assert res_no_header.status_code == 403
        assert res_no_header.json()["code"] == "CSRF_TOKEN_MISSING"

        # 4. Token mismatch (constant-time check fails)
        res_mismatch = await client.post(
            "/api/v1/sparkle/complete",
            json=payload,
            headers={"X-CSRF-Token": "token-a"},
            cookies={"__Host-kb_csrf": "token-b"},
        )
        assert res_mismatch.status_code == 403
        assert res_mismatch.json()["code"] == "CSRF_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_body_size_cap_413() -> None:
    """Case 9b: Payload exceeding 16 KiB returns RFC 7807 413 Payload Too Large."""
    ws_id = uuid.uuid4()
    app = _setup_app_with_cassette("sparkle_fim_ok.yaml", ws_id)

    csrf = "valid-token"
    # Construct body slightly above 16 * 1024 bytes
    oversized_prefix = "x" * (17 * 1024)
    payload = {
        "project_id": str(uuid.uuid4()),
        "surface": "doc",
        "prefix": oversized_prefix,
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"__Host-kb_csrf": csrf},
    ) as client:
        res = await client.post(
            "/api/v1/sparkle/complete",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 413
        problem = res.json()
        assert problem["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_streaming_sse_headers_and_contract() -> None:
    """Case 9c: Valid request returns 200 text/event-stream with no-store and no-buffering."""
    ws_id = uuid.uuid4()
    app = _setup_app_with_cassette("sparkle_fim_ok.yaml", ws_id)

    csrf = "valid-token"
    payload = {
        "project_id": str(uuid.uuid4()),
        "surface": "doc",
        "prefix": "def add(a, b):\n    return ",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"__Host-kb_csrf": csrf},
    ) as client:
        res = await client.post(
            "/api/v1/sparkle/complete",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 200
        # Headers verification
        assert "text/event-stream" in res.headers["content-type"]
        assert "no-store" in res.headers["cache-control"]
        assert res.headers["x-accel-buffering"] == "no"

        # SSE body verification
        body = res.text
        assert "event: completion\n" in body
        assert "event: done\n" in body
        assert '"status": "ok"' in body


@pytest.mark.asyncio
async def test_streaming_sse_secret_scrubbed_terminal_done() -> None:
    """Case 9d: Secret detected yields 200 text/event-stream with done event only."""
    ws_id = uuid.uuid4()
    app = _setup_app_with_cassette("sparkle_fim_ok.yaml", ws_id)

    csrf = "valid-token"
    # Dynamically constructed secret token
    live_key = "sk-live-" + "X9z" * 10
    payload = {
        "project_id": str(uuid.uuid4()),
        "surface": "doc",
        "prefix": f"API_KEY = '{live_key}'",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"__Host-kb_csrf": csrf},
    ) as client:
        res = await client.post(
            "/api/v1/sparkle/complete",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 200
        body = res.text
        assert "event: completion\n" not in body
        assert "event: done\n" in body
        assert '"status": "secret_scrubbed"' in body


@pytest.mark.asyncio
async def test_case_08b_empty_and_timeout_sse_events() -> None:
    """Case 8b: Empty completion emits single done event; timeout emits single done event."""
    ws_id = uuid.uuid4()

    # 1. Empty completion (prompt override cassette drops all text)
    app_empty = _setup_app_with_cassette("sparkle_fim_prompt_override.yaml", ws_id)
    csrf = "valid-token"
    payload_empty = {
        "project_id": str(uuid.uuid4()),
        "surface": "doc",
        "prefix": "test prompt",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app_empty),
        base_url="http://test",
        cookies={"__Host-kb_csrf": csrf},
    ) as client:
        res_empty = await client.post(
            "/api/v1/sparkle/complete",
            json=payload_empty,
            headers={"X-CSRF-Token": csrf},
        )

        assert res_empty.status_code == 200
        body_empty = res_empty.text
        assert "event: completion\n" not in body_empty
        assert "event: done\n" in body_empty
        assert '"status": "empty"' in body_empty

    # 2. Timeout completion
    app_timeout = _setup_app_with_cassette("sparkle_fim_ttft_timeout.yaml", ws_id)
    payload_timeout = {
        "project_id": str(uuid.uuid4()),
        "surface": "doc",
        "prefix": "Delayed request...",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app_timeout),
        base_url="http://test",
        cookies={"__Host-kb_csrf": csrf},
    ) as client:
        res = await client.post(
            "/api/v1/sparkle/complete",
            json=payload_timeout,
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 200
        body = res.text
        assert "event: completion\n" not in body
        assert "event: done\n" in body
        assert '"status": "timeout"' in body


@pytest.mark.asyncio
async def test_unreadable_resource_returns_404(pg_worker_db: AsyncEngine) -> None:
    """Case 9e: Caller lacking EDIT on object_id or VIEW on project_id receives 404."""
    ws_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    session_factory = RLSSessionFactory(pg_worker_db)

    # Setup project in DB that Alice has NO permissions on
    sec_proj = uuid.uuid4()
    async with pg_worker_db.begin() as conn:
        await conn.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS')"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Alice')"
            ),
            {"id": alice_id, "ws_id": ws_id},
        )
        await conn.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'SEC', 'Secret', :creator, :sec_id"
                ")"
            ),
            {"ws_id": ws_id, "creator": alice_id, "sec_id": sec_proj},
        )
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws, 'SEC', 'Secret')"
            ),
            {"id": sec_proj, "ws": ws_id},
        )

    app = create_agent_app()
    app.state.session_factory = session_factory
    principal = PrincipalContext(principal_id=alice_id, workspace_id=ws_id)
    app.state.principal_resolver = _StaticPrincipalResolver(principal)

    csrf = "valid-token"
    payload = {
        "project_id": str(sec_proj),
        "surface": "doc",
        "prefix": "Attempting unreadable access...",
        "suffix": "",
        "client_request_id": str(uuid.uuid4()),
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"__Host-kb_csrf": csrf},
    ) as client:
        res = await client.post(
            "/api/v1/sparkle/complete",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 404
        assert res.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_readable_and_editable_resources_and_object_id_discipline(
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify RLS permission verification with object_id EDIT and project VIEW capability."""
    ws_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    session_factory = RLSSessionFactory(pg_worker_db)

    pub_proj = uuid.uuid4()
    sticky_obj_id = uuid.uuid4()

    async with pg_worker_db.begin() as conn:
        await conn.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS-PERM')"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
        )
        await conn.execute(
            text(
                "SELECT register_object("
                "  'user'::object_kind, :ws_id, NULL, :ckey, 'Alice', :user_id, :user_id"
                ")"
            ),
            {"ws_id": ws_id, "ckey": f"user-{alice_id.hex[:8]}", "user_id": alice_id},
        )
        await conn.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Alice')"
            ),
            {"id": alice_id, "ws_id": ws_id},
        )
        await conn.execute(
            text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
            {"id": alice_id, "ws_id": ws_id, "email": f"alice-{alice_id.hex[:6]}@test.com"},
        )

        await conn.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'PUBP', "
                "  'Public Project', :creator, :proj_id"
                ")"
            ),
            {"ws_id": ws_id, "creator": alice_id, "proj_id": pub_proj},
        )
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws, 'PUBP', 'Public')"
            ),
            {"id": pub_proj, "ws": ws_id},
        )

        await conn.execute(
            text(
                "SELECT register_object("
                "  'sticky'::object_kind, :ws_id, :proj_id, 'PUBP-STK', "
                "  'Sticky', :creator, :sticky_id"
                ")"
            ),
            {"ws_id": ws_id, "proj_id": pub_proj, "creator": alice_id, "sticky_id": sticky_obj_id},
        )
        await conn.execute(
            text(
                "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
                "VALUES (:id, :ws, :proj, 'Valid sticky')"
            ),
            {"id": sticky_obj_id, "ws": ws_id, "proj": pub_proj},
        )

        await conn.execute(
            text(
                "INSERT INTO role_bindings "
                "(workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:ws_id, :p_id, 'MEMBER', 'project', :proj_id)"
            ),
            {"ws_id": ws_id, "p_id": alice_id, "proj_id": pub_proj},
        )
        await conn.execute(
            text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
            {"ws_id": ws_id},
        )

    app = _setup_app_with_cassette("sparkle_fim_ok.yaml", ws_id)
    app.state.session_factory = session_factory
    principal = PrincipalContext(principal_id=alice_id, workspace_id=ws_id)
    app.state.principal_resolver = _StaticPrincipalResolver(principal)

    csrf = "valid-token"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"__Host-kb_csrf": csrf},
    ) as client:
        # 1. Project VIEW capability granted (object_id is None)
        res_view = await client.post(
            "/api/v1/sparkle/complete",
            json={
                "project_id": str(pub_proj),
                "surface": "doc",
                "prefix": "test view prefix",
                "suffix": "",
                "client_request_id": str(uuid.uuid4()),
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert res_view.status_code == 200
        assert "event: completion\n" in res_view.text

        # 2. Object EDIT capability granted (object_id is sticky_obj_id)
        res_edit = await client.post(
            "/api/v1/sparkle/complete",
            json={
                "project_id": str(pub_proj),
                "object_id": str(sticky_obj_id),
                "surface": "sticky",
                "prefix": "test edit prefix",
                "suffix": "",
                "client_request_id": str(uuid.uuid4()),
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert res_edit.status_code == 200
        assert "event: completion\n" in res_edit.text

        # 3. Object EDIT capability denied (random non-existent object_id in project)
        res_denied = await client.post(
            "/api/v1/sparkle/complete",
            json={
                "project_id": str(pub_proj),
                "object_id": str(uuid.uuid4()),
                "surface": "sticky",
                "prefix": "test non-existent object",
                "suffix": "",
                "client_request_id": str(uuid.uuid4()),
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert res_denied.status_code == 404


@pytest.mark.asyncio
async def test_resolve_provider_router_fallback_and_session_factory_flavors() -> None:
    """Verify _resolve_provider_router fallback and session_factory callable/direct flavors."""
    ws_id = uuid.uuid4()
    p_ctx = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="prefix",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    mock_app = MagicMock()
    mock_app.state.provider_router = None
    mock_app.state.sparkle_route_candidates = []
    mock_app.state.air_gap_mode = True
    scope = {"type": "http", "app": mock_app}
    http_req = Request(scope)
    router = _resolve_provider_router(http_req, ws_id)
    assert isinstance(router, ProviderRouter)
    assert router.workspace_id == ws_id
    assert router.air_gap_mode is True

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = 1
    dummy_sess = _MockAsyncSession(execute_return_value=mock_res)

    # 1. Callable factory
    await verify_sparkle_access(
        session_factory=lambda: dummy_sess,
        principal=p_ctx,
        req=req,
    )

    # 2. Direct session
    await verify_sparkle_access(
        session_factory=dummy_sess,
        principal=p_ctx,
        req=req,
    )


@pytest.mark.asyncio
async def test_complete_sparkle_disconnect_and_cancellation() -> None:
    """Verify complete_sparkle generator handles client disconnects and pipeline cancellation."""
    ws_id = uuid.uuid4()
    p_ctx = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)

    # 1. Disconnect before completion event
    mock_req_disc = MagicMock(spec=Request)
    mock_req_disc.app.state.session_factory = None
    mock_req_disc.app.state.provider_router = None
    mock_req_disc.app.state.sparkle_route_candidates = []
    mock_req_disc.app.state.air_gap_mode = False
    mock_req_disc.is_disconnected = AsyncMock(side_effect=[True, True])
    body_data = (
        b'{"project_id":"' + str(uuid.uuid4()).encode() + b'",'
        b'"surface":"doc","prefix":"hi","suffix":"","client_request_id":"'
        + str(uuid.uuid4()).encode()
        + b'"}'
    )
    mock_req_disc.body = AsyncMock(return_value=body_data)

    resp = await complete_sparkle(mock_req_disc, principal=p_ctx, _=None)
    items = [chunk async for chunk in resp.body_iterator]
    assert items == []

    # 2. Disconnect before done event
    mock_req_disc2 = MagicMock(spec=Request)
    mock_req_disc2.app.state.session_factory = None
    mock_req_disc2.app.state.provider_router = None
    mock_req_disc2.app.state.sparkle_route_candidates = []
    mock_req_disc2.app.state.air_gap_mode = False
    mock_req_disc2.is_disconnected = AsyncMock(side_effect=[False, True])
    mock_req_disc2.body = AsyncMock(return_value=body_data)

    resp2 = await complete_sparkle(mock_req_disc2, principal=p_ctx, _=None)
    items2 = [chunk async for chunk in resp2.body_iterator]
    assert len(items2) == 0 or (len(items2) == 1 and "event: completion\n" in items2[0])

    # 3. Pipeline task cancelled
    mock_req_canc = MagicMock(spec=Request)
    mock_req_canc.app.state.session_factory = None
    mock_req_canc.app.state.provider_router = None
    mock_req_canc.app.state.sparkle_route_candidates = []
    mock_req_canc.app.state.air_gap_mode = False
    mock_req_canc.body = AsyncMock(return_value=body_data)

    with patch("agent.sparkle.router.run_sparkle_pipeline", side_effect=asyncio.CancelledError):
        resp3 = await complete_sparkle(mock_req_canc, principal=p_ctx, _=None)
        with pytest.raises(asyncio.CancelledError):
            async for _ in resp3.body_iterator:
                pass


@pytest.mark.asyncio
async def test_asgi_fallback_idx_none() -> None:
    """Verify create_agent_app handles FastAPI app without catch-all route gracefully."""
    with patch("agent.asgi.create_app") as mock_create_app:
        raw_app = FastAPI()
        mock_create_app.return_value = raw_app
        composed_app = create_agent_app()
        assert composed_app is raw_app


@pytest.mark.asyncio
async def test_asgi_routing_parity() -> None:
    """Verify ASGI route composition keeps v1 healthz and fallback 404 handling intact."""
    app = create_agent_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Healthz endpoint remains reachable
        res_health = await client.get("/api/v1/healthz")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "ok"}

        # 2. Non-existent API route falls back to RFC 7807 404
        res_unknown = await client.get("/api/v1/non_existent_route")
        assert res_unknown.status_code == 404
        assert res_unknown.json()["status"] == 404
