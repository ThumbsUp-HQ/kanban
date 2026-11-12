# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Test fixtures and setup helpers for realtime WebSocket and SSE test suites."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING, Any, Self, cast

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from database.session import RLSContext, RLSSessionFactory
from kanban.app import create_app
from kanban.auth.sessions.service import IssuedSession, SessionService
from kanban.realtime.hub import RealtimeHub
from kanban.settings import Settings
from kanban.tests.contract import ContractRecorder

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from fastapi import FastAPI

    from database.outbox.pg_broker import PgNotifyBroker

__all__ = [
    "AsyncSSETestClient",
    "AsyncWebSocketTestClient",
    "build_realtime_test_app",
    "contract_recorder",
    "create_auth_session",
    "create_realtime_test_fixtures",
]


class AsyncWebSocketTestClient:
    """In-process ASGI WebSocket test client running on the active asyncio event loop."""

    def __init__(
        self,
        app: Any,  # noqa: ANN401
        path: str = "/ws",
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize in-process client with target app and headers."""
        self.app = app
        self.path = path
        self.headers: list[tuple[bytes, bytes]] = [
            (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
        ]
        self.in_q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.out_q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None

    async def connect(self) -> dict[str, Any]:
        """Initiate WebSocket handshake and return accept message, or raise WebSocketDisconnect."""
        scope = {
            "client": ("127.0.0.1", 50000),
            "headers": self.headers,
            "path": self.path,
            "query_string": b"",
            "raw_path": self.path.encode("ascii"),
            "root_path": "",
            "scheme": "ws",
            "server": ("testserver", 80),
            "type": "websocket",
        }
        self.task = asyncio.create_task(self.app(scope, self.in_q.get, self.out_q.put))
        await self.in_q.put({"type": "websocket.connect"})
        msg = await self.out_q.get()
        if msg["type"] == "websocket.close":
            raise WebSocketDisconnect(code=msg.get("code", 1000), reason=msg.get("reason", ""))
        return msg

    async def send_text(self, text_payload: str) -> None:
        """Send text frame to WebSocket server."""
        await self.in_q.put({"text": text_payload, "type": "websocket.receive"})

    async def receive_json(self, timeout_seconds: float = 3.0) -> dict[str, Any]:
        """Receive next JSON message frame, or raise WebSocketDisconnect on close."""
        async with asyncio.timeout(timeout_seconds):
            msg = await self.out_q.get()
        if msg["type"] == "websocket.close":
            raise WebSocketDisconnect(code=msg.get("code", 1000), reason=msg.get("reason", ""))
        return cast("dict[str, Any]", json.loads(msg["text"]))

    async def close(self) -> None:
        """Send disconnect and cleanly await ASGI task completion."""
        await self.in_q.put({"code": 1000, "type": "websocket.disconnect"})
        if self.task:
            try:
                async with asyncio.timeout(1.0):
                    await self.task
            except (TimeoutError, asyncio.CancelledError):
                self.task.cancel()

    async def __aenter__(self) -> Self:
        """Enter async context manager, establishing connection."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager, closing connection."""
        await self.close()


class AsyncSSETestClient:
    """In-process ASGI SSE test client running directly on the test asyncio event loop."""

    def __init__(
        self,
        app: Any,  # noqa: ANN401
        path: str = "/sse",
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize in-process SSE client with target app and headers."""
        self.app = app
        raw_path, _, query_string = path.partition("?")
        self.path = raw_path
        self.query_string = query_string.encode("ascii")
        self.headers: list[tuple[bytes, bytes]] = [
            (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
        ]
        if not any(k == b"host" for k, _ in self.headers):
            self.headers.append((b"host", b"kanban.example"))

        self.status_code: int = 0
        self.response_headers: dict[str, str] = {}
        self.body_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.disconnect_event = asyncio.Event()
        self.started_event = asyncio.Event()
        self.task: asyncio.Task[None] | None = None
        self._buffer: str = ""

    async def _receive(self) -> dict[str, Any]:
        await self.disconnect_event.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status_code = message["status"]
            self.response_headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in message.get("headers", [])
            }
            self.started_event.set()
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            if body:
                await self.body_queue.put(body)
            if not message.get("more_body", False):
                await self.body_queue.put(None)

    async def connect(self, timeout_seconds: float = 3.0) -> Self:
        """Initiate HTTP GET request and wait for response headers."""
        scope = {
            "client": ("127.0.0.1", 50000),
            "headers": self.headers,
            "http_version": "1.1",
            "method": "GET",
            "path": self.path,
            "query_string": self.query_string,
            "raw_path": self.path.encode("ascii"),
            "root_path": "",
            "scheme": "https",
            "server": ("testserver", 443),
            "type": "http",
        }
        self.task = asyncio.create_task(self.app(scope, self._receive, self._send))
        async with asyncio.timeout(timeout_seconds):
            await self.started_event.wait()
        return self

    async def read_event(self, timeout_seconds: float = 3.0) -> dict[str, str]:
        """Read and parse the next SSE event frame from the stream."""
        async with asyncio.timeout(timeout_seconds):
            while True:
                if "\n\n" in self._buffer:
                    frame, self._buffer = self._buffer.split("\n\n", 1)
                    parsed = self._parse_frame(frame)
                    if parsed:
                        return parsed

                chunk = await self.body_queue.get()
                if chunk is None:
                    if self._buffer:
                        parsed = self._parse_frame(self._buffer)
                        self._buffer = ""
                        if parsed:
                            return parsed
                    return {}
                self._buffer += chunk.decode("utf-8")

    @staticmethod
    def _parse_frame(frame: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for line in frame.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(":"):
                continue
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                parsed[k.strip()] = v.lstrip()
        return parsed

    async def read_json_body(self, timeout_seconds: float = 3.0) -> dict[str, Any]:
        """Read full JSON response body (for 4xx/5xx non-streaming error responses)."""
        chunks: list[bytes] = []
        async with asyncio.timeout(timeout_seconds):
            while True:
                chunk = await self.body_queue.get()
                if chunk is None:
                    break
                chunks.append(chunk)
        return cast("dict[str, Any]", json.loads(b"".join(chunks).decode("utf-8")))

    async def close(self) -> None:
        """Signal client disconnect and await task completion."""
        self.disconnect_event.set()
        if self.task:
            try:
                async with asyncio.timeout(1.0):
                    await self.task
            except (TimeoutError, asyncio.CancelledError):
                self.task.cancel()

    async def __aenter__(self) -> Self:
        """Enter async context manager, establishing connection."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager, closing connection."""
        await self.close()


@pytest.fixture(scope="session")
def contract_recorder() -> Iterator[ContractRecorder]:
    """Capture contract exchanges and write KB_CONTRACT_OUT if configured."""
    recorder = ContractRecorder()
    yield recorder
    recorder.write_if_configured()


@pytest.fixture
def hmac_key() -> bytes:
    """Provide fixed 32-byte HMAC key for test session cookies."""
    return b"k" * 32


@pytest.fixture
def session_service(hmac_key: bytes) -> SessionService:
    """Provide SessionService bound to test HMAC key."""
    return SessionService(hmac_key)


def build_realtime_test_app(
    factory: RLSSessionFactory,
    service: SessionService,
    broker: PgNotifyBroker | None = None,
    hub: RealtimeHub | None = None,
) -> tuple[FastAPI, RealtimeHub]:
    """Create FastAPI test application with configured session factory, broker, and hub."""
    settings = Settings(
        deployment_mode="production",
        public_base_url="https://kanban.example",
        standalone_cleartext_hosts=frozenset({"localhost", "127.0.0.1", "testserver"}),
    )
    app = create_app(settings)
    app.state.session_factory = factory
    app.state.session_service = service
    app.state.broker = broker

    realtime_hub = hub or RealtimeHub(
        broker=broker,
        session_factory=factory,
        session_service=service,
        ping_interval_s=1.0,
    )
    app.state.realtime_hub = realtime_hub
    return app, realtime_hub


async def create_auth_session(
    factory: RLSSessionFactory,
    service: SessionService,
    *,
    principal_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> IssuedSession:
    """Create active session in database and return issued cookie credentials."""
    ctx = RLSContext(principal_id=principal_id, workspace_id=workspace_id, aal_level=1)
    async with factory.session(ctx) as session:
        return await service.create_after_login(
            session,
            principal_id=principal_id,
            workspace_id=workspace_id,
            aal_level=1,
        )


async def create_realtime_test_fixtures(  # noqa: PLR0913
    factory: RLSSessionFactory,
    *,
    ws_id: uuid.UUID | None = None,
    admin_id: uuid.UUID | None = None,
    maya_id: uuid.UUID | None = None,
    other_id: uuid.UUID | None = None,
    proj_id: uuid.UUID | None = None,
    issue_id: uuid.UUID | None = None,
) -> dict[str, uuid.UUID]:
    """Provision workspace, users, project, issue, and grant initial VIEW access."""
    ws_id = ws_id or uuid.uuid4()
    admin_id = admin_id or uuid.uuid4()
    maya_id = maya_id or uuid.uuid4()
    other_id = other_id or uuid.uuid4()
    proj_id = proj_id or uuid.uuid4()
    issue_id = issue_id or uuid.uuid4()

    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        # 1. Create Workspace
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "name": "Realtime Test Workspace", "slug": f"rt-{ws_id.hex[:8]}"},
        )

        # 2. Provision Principals and Users
        for uid, name, email in (
            (admin_id, "Admin User", "admin@example.com"),
            (maya_id, "Maya Tester", "maya@example.com"),
            (other_id, "Other Collaborator", "other@example.com"),
        ):
            await session.execute(
                text(
                    "INSERT INTO principals "
                    "(id, principal_type, workspace_id, display_name, status) "
                    "VALUES (:id, 'USER', :ws_id, :name, 'ACTIVE')"
                ),
                {"id": uid, "name": name, "ws_id": ws_id},
            )
            await session.execute(
                text(
                    "SELECT register_object("
                    "'user'::object_kind, :ws_id, NULL, :ckey, :title, :uid, :uid"
                    ")"
                ),
                {"ckey": f"usr-{uid.hex}", "title": name, "uid": uid, "ws_id": ws_id},
            )
            await session.execute(
                text(
                    "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                    "VALUES (:id, 'user', 'USER', :ws_id, :email)"
                ),
                {"email": email, "id": uid, "ws_id": ws_id},
            )

        # 3. Create Project
        await session.execute(
            text(
                "SELECT register_object("
                "'project'::object_kind, :ws_id, NULL, 'KAN', 'KAN Project', :aid, :pid"
                ")"
            ),
            {"aid": admin_id, "pid": proj_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO projects (id, object_type, workspace_id, identifier, name) "
                "VALUES (:id, 'project', :ws_id, 'KAN', 'Kanban Project')"
            ),
            {"id": proj_id, "ws_id": ws_id},
        )

        # 4. Create Issue KAN-1 in objects
        await session.execute(
            text(
                "SELECT register_object("
                "'issue'::object_kind, :ws_id, :pid, :ckey, 'Issue 1', :aid, :iid"
                ")"
            ),
            {
                "aid": admin_id,
                "ckey": f"iss-{issue_id.hex}",
                "iid": issue_id,
                "pid": proj_id,
                "ws_id": ws_id,
            },
        )

        # 5. Populate initial role_bindings (populates effective_resource_access)
        rb_stmt = text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :pid, CAST(:role AS rbac_role), :scope, :proj_id)"
        )
        await session.execute(
            rb_stmt,
            {
                "id": uuid.uuid4(),
                "pid": admin_id,
                "proj_id": None,
                "role": "WORKSPACE_ADMIN",
                "scope": "workspace",
                "ws_id": ws_id,
            },
        )
        await session.execute(
            rb_stmt,
            {
                "id": uuid.uuid4(),
                "pid": maya_id,
                "proj_id": proj_id,
                "role": "PROJECT_ADMIN",
                "scope": "project",
                "ws_id": ws_id,
            },
        )
        await session.execute(
            rb_stmt,
            {
                "id": uuid.uuid4(),
                "pid": other_id,
                "proj_id": proj_id,
                "role": "MEMBER",
                "scope": "project",
                "ws_id": ws_id,
            },
        )

    return {
        "admin_id": admin_id,
        "issue_id": issue_id,
        "maya_id": maya_id,
        "other_id": other_id,
        "proj_id": proj_id,
        "ws_id": ws_id,
    }
