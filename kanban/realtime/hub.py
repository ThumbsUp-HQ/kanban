# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Realtime WebSocket & SSE connection hub with delivery-time RLS filtering (KB-P3-16)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from sqlalchemy import text

from database.session import RLSContext
from kanban.realtime.replay import OutboxReplayer
from kanban.realtime.rls_filter import (
    NOTIFICATION_TOPICS,
    authorize_event_recipients,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import WebSocket
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.outbox.broker import OutboxEnvelope, RealtimeBroker
    from database.session import RLSSessionFactory
    from kanban.auth.sessions.service import SessionService

logger = logging.getLogger("kanban.realtime.hub")

MAX_CONNECTIONS_PER_PRINCIPAL: Final[int] = 16
MAX_CHANNELS_PER_CONNECTION: Final[int] = 64
MAX_INBOUND_FRAME_BYTES: Final[int] = 4096
DEFAULT_PING_INTERVAL_S: Final[float] = 25.0
DEFAULT_SESSION_CHECK_INTERVAL_S: Final[float] = 60.0

WS_CLOSE_UNAUTHENTICATED: Final[int] = 4401
WS_CLOSE_ORIGIN_MISMATCH: Final[int] = 4403
WS_CLOSE_FRAME_TOO_LARGE: Final[int] = 4413
WS_CLOSE_CONNECTION_LIMIT: Final[int] = 4429
WS_CLOSE_DRAINING: Final[int] = 1001

_CHANNEL_REGEX = re.compile(
    r"^(?:(?P<kind>workspace|project|issue|doc|user):(?P<id>[0-9a-fA-F-]{36}|[0-9a-fA-F]{32})|notifications:self)$"
)


@runtime_checkable
class RealtimeConnection(Protocol):
    """Abstract protocol for active realtime connections (WebSocket or SSE)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    session_id: uuid.UUID
    token_sha256: bytes | None
    subscribed_channels: set[str]
    mcp_session_id: str | None

    async def send_json(self, data: dict[str, Any]) -> None:
        """Send JSON payload to the client."""
        ...

    async def send_event(self, envelope: OutboxEnvelope, channel: str) -> None:
        """Deliver domain event frame to the client."""
        ...

    async def close(self, code: int, reason: str = "") -> None:
        """Close connection with code and reason."""
        ...


@dataclass(slots=True)
class WebSocketConnection:
    """Manages an active WebSocket client session."""

    id: uuid.UUID
    websocket: WebSocket
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    session_id: uuid.UUID
    token_sha256: bytes | None = None
    mcp_session_id: str | None = None
    subscribed_channels: set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_pong_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    async def send_json(self, data: dict[str, Any]) -> None:
        """Send serialized JSON message frame over WebSocket."""
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True)
        await self.websocket.send_text(raw)

    async def send_event(self, envelope: OutboxEnvelope, channel: str) -> None:
        """Format and send domain event frame."""
        frame = {
            "channel": channel,
            "created_at": envelope.created_at.isoformat(),
            "event_id": str(envelope.seq),
            "object_id": str(envelope.object_id) if envelope.object_id is not None else None,
            "payload": envelope.payload,
            "project_id": str(envelope.project_id) if envelope.project_id is not None else None,
            "topic": envelope.topic,
            "type": "event",
            "workspace_id": str(envelope.workspace_id),
        }
        await self.send_json(frame)

    async def close(self, code: int, reason: str = "") -> None:
        """Close underlying WebSocket."""
        with contextlib.suppress(Exception):
            await self.websocket.close(code=code, reason=reason)


@dataclass(slots=True)
class SSEConnection:
    """Manages an active Server-Sent Events client stream."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    session_id: uuid.UUID
    token_sha256: bytes | None = None
    mcp_session_id: str | None = None
    subscribed_channels: set[str] = field(default_factory=set)
    queue: asyncio.Queue[str | None] = field(default_factory=lambda: asyncio.Queue(maxsize=1024))
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    async def send_json(self, data: dict[str, Any]) -> None:
        """Format arbitrary JSON as an SSE event message frame."""
        msg_type = data.get("type", "message")
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True)
        frame = f"event: {msg_type}\ndata: {raw}\n\n"
        with contextlib.suppress(asyncio.QueueFull):
            self.queue.put_nowait(frame)

    async def send_event(self, envelope: OutboxEnvelope, channel: str) -> None:
        """Format OutboxEnvelope as canonical SSE message frame."""
        body = {
            "channel": channel,
            "created_at": envelope.created_at.isoformat(),
            "event_id": str(envelope.seq),
            "object_id": str(envelope.object_id) if envelope.object_id is not None else None,
            "payload": envelope.payload,
            "project_id": str(envelope.project_id) if envelope.project_id is not None else None,
            "topic": envelope.topic,
            "type": "event",
            "workspace_id": str(envelope.workspace_id),
        }
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True)
        frame = f"id: {envelope.seq}\nevent: {envelope.topic}\ndata: {raw}\n\n"
        with contextlib.suppress(asyncio.QueueFull):
            self.queue.put_nowait(frame)

    async def send_heartbeat(self) -> None:
        """Send SSE heartbeat comment."""
        with contextlib.suppress(asyncio.QueueFull):
            self.queue.put_nowait(": heartbeat\n\n")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Signal end of SSE event stream."""
        del code, reason
        with contextlib.suppress(asyncio.QueueFull):
            self.queue.put_nowait(None)


class RealtimeHub:
    """Subscription manager and fanout hub coordinating WebSocket and SSE connections."""

    def __init__(
        self,
        broker: RealtimeBroker | None = None,
        session_factory: RLSSessionFactory | None = None,
        session_service: SessionService | None = None,
        *,
        ping_interval_s: float = DEFAULT_PING_INTERVAL_S,
        session_check_interval_s: float = DEFAULT_SESSION_CHECK_INTERVAL_S,
    ) -> None:
        """Initialize realtime hub with broker, session dependencies, and interval timers."""
        self._broker = broker
        self._session_factory = session_factory
        self._session_service = session_service
        self._ping_interval_s = ping_interval_s
        self._session_check_interval_s = session_check_interval_s

        self._connections: dict[uuid.UUID, RealtimeConnection] = {}
        self._user_connections: dict[tuple[uuid.UUID, uuid.UUID], set[uuid.UUID]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._replayer = OutboxReplayer()

        self._listener_task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._session_check_task: asyncio.Task[None] | None = None

        self._running = False
        self._draining = False

    @property
    def replayer(self) -> OutboxReplayer:
        """The underlying outbox replayer service."""
        return self._replayer

    @property
    def active_connection_count(self) -> int:
        """Current number of active registered connections."""
        return len(self._connections)

    def get_diagnostics_snapshot(self) -> dict[str, Any]:
        """Return diagnostic snapshot of realtime hub connections, broker, and tasks."""
        ws_count = sum(1 for c in self._connections.values() if isinstance(c, WebSocketConnection))
        sse_count = sum(1 for c in self._connections.values() if isinstance(c, SSEConnection))

        ws_by_workspace: dict[str, int] = defaultdict(int)
        for (w_id, _), conn_ids in self._user_connections.items():
            ws_by_workspace[str(w_id)] += len(conn_ids)

        broker_kind = "none"
        broker_listener_connected = False
        broker_publisher_connected = False
        if self._broker is not None:
            broker_kind = getattr(self._broker, "kind", "pg_notify")
            if hasattr(self._broker, "get_diagnostics_snapshot"):
                b_snap = self._broker.get_diagnostics_snapshot()
                broker_listener_connected = b_snap.get("listener_connected", False)
                broker_publisher_connected = b_snap.get("publisher_connected", False)

        return {
            "hub_running": self._running,
            "hub_draining": self._draining,
            "broker_kind": broker_kind,
            "broker_listener_connected": broker_listener_connected,
            "broker_publisher_connected": broker_publisher_connected,
            "active_connections_total": len(self._connections),
            "ws_connections": ws_count,
            "sse_connections": sse_count,
            "workspace_connections": dict(ws_by_workspace),
            "heartbeat_interval_s": self._ping_interval_s,
            "session_recheck_interval_s": self._session_check_interval_s,
            "replay_retention_minutes": 60,
            "background_tasks": {
                "listener_alive": (
                    self._listener_task is not None and not self._listener_task.done()
                ),
                "ping_alive": self._ping_task is not None and not self._ping_task.done(),
                "session_check_alive": (
                    self._session_check_task is not None and not self._session_check_task.done()
                ),
            },
        }

    def get_status(self) -> dict[str, Any]:
        """Alias for get_diagnostics_snapshot."""
        return self.get_diagnostics_snapshot()

    async def start(self) -> None:
        """Start background listener, heartbeat ping, and session expiration loops."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._draining = False

            if self._broker is not None:
                self._listener_task = asyncio.create_task(
                    self._broker_listener_loop(), name="realtime-broker-listener"
                )
            self._ping_task = asyncio.create_task(self._heartbeat_loop(), name="realtime-heartbeat")
            self._session_check_task = asyncio.create_task(
                self._session_recheck_loop(), name="realtime-session-recheck"
            )

    async def drain(self, timeout_seconds: float = 3.0) -> None:
        """Gracefully notify and disconnect all clients within timeout ceiling."""
        async with self._lock:
            self._draining = True
            self._running = False

            tasks_to_cancel = [
                t
                for t in (self._listener_task, self._ping_task, self._session_check_task)
                if t is not None
            ]
            for t in tasks_to_cancel:
                t.cancel()

            # Broadcast server.draining frame to all active connections
            active_conns = list(self._connections.values())

        draining_payload = {"type": "server.draining", "retry_ms": 1000}
        for conn in active_conns:
            with contextlib.suppress(Exception):
                await conn.send_json(draining_payload)
                await conn.close(code=WS_CLOSE_DRAINING, reason="server.draining")

        try:
            async with asyncio.timeout(timeout_seconds):
                for t in tasks_to_cancel:
                    with contextlib.suppress(asyncio.CancelledError):
                        await t
        except TimeoutError:
            logger.warning("RealtimeHub drain timed out after %.1fs", timeout_seconds)

        async with self._lock:
            self._connections.clear()
            self._user_connections.clear()

    async def register_connection(self, conn: RealtimeConnection) -> bool:
        """Register active connection. Returns False if concurrent connection cap is reached."""
        async with self._lock:
            if self._draining:
                return False

            key = (conn.workspace_id, conn.principal_id)
            current_user_conns = self._user_connections[key]
            if len(current_user_conns) >= MAX_CONNECTIONS_PER_PRINCIPAL:
                return False

            self._connections[conn.id] = conn
            current_user_conns.add(conn.id)
            return True

    async def unregister_connection(self, conn_id: uuid.UUID) -> None:
        """Remove connection and release capacity slot."""
        async with self._lock:
            conn = self._connections.pop(conn_id, None)
            if conn is not None:
                key = (conn.workspace_id, conn.principal_id)
                self._user_connections[key].discard(conn_id)
                if not self._user_connections[key]:
                    self._user_connections.pop(key, None)

    def get_connection(self, conn_id: uuid.UUID) -> RealtimeConnection | None:
        """Lookup active connection by ID."""
        return self._connections.get(conn_id)

    def get_user_connections(
        self, workspace_id: uuid.UUID, principal_id: uuid.UUID
    ) -> list[RealtimeConnection]:
        """Lookup all active connections belonging to a principal."""
        conn_ids = self._user_connections.get((workspace_id, principal_id), set())
        return [self._connections[cid] for cid in conn_ids if cid in self._connections]

    async def _check_object_view(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        target_uuid: uuid.UUID,
    ) -> bool:
        await session.execute(
            text(
                "SELECT set_config('app.workspace_id', :ws_id, true), "
                "       set_config('app.principal_id', :pid, true)"
            ),
            {"ws_id": str(workspace_id), "pid": str(principal_id)},
        )
        return bool(
            await session.scalar(
                text("SELECT app_has_object_capability(:obj_id, 1)"),
                {"obj_id": target_uuid},
            )
        )

    async def _resolve_workspace_channel(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        raw_id: str,
    ) -> tuple[str, uuid.UUID, str] | None:
        if raw_id == "stickies":
            return ("workspace:stickies", workspace_id, "workspace")

        try:
            target_uuid = uuid.UUID(raw_id)
        except ValueError:
            stmt = text("SELECT id FROM workspaces WHERE slug = :slug")
            row = (await session.execute(stmt, {"slug": raw_id})).first()
            if row is None:
                return None
            target_uuid = uuid.UUID(str(row[0]))

        if target_uuid != workspace_id:
            return None
        return (f"workspace:{target_uuid}", target_uuid, "workspace")

    async def _resolve_project_channel(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        raw_id: str,
    ) -> tuple[str, uuid.UUID, str] | None:
        try:
            target_uuid = uuid.UUID(raw_id)
        except ValueError:
            stmt = text(
                "SELECT p.id FROM projects p "
                "JOIN objects o ON o.id = p.id "
                "WHERE p.workspace_id = :ws_id "
                "  AND p.identifier = :ident "
                "  AND o.deleted_at IS NULL"
            )
            row = (
                await session.execute(stmt, {"ws_id": workspace_id, "ident": raw_id.upper()})
            ).first()
            if row is None:
                return None
            target_uuid = uuid.UUID(str(row[0]))

        if not await self._check_object_view(session, workspace_id, principal_id, target_uuid):
            return None
        return (f"project:{target_uuid}", target_uuid, "project")

    async def _resolve_issue_channel(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        raw_id: str,
    ) -> tuple[str, uuid.UUID, str] | None:
        target_uuid: uuid.UUID | None = None
        try:
            target_uuid = uuid.UUID(raw_id)
        except ValueError:
            if "-" in raw_id:
                ident, seq_str = raw_id.rsplit("-", 1)
                if seq_str.isdigit():
                    stmt = text(
                        "SELECT i.id FROM issues i "
                        "JOIN projects p ON p.id = i.project_id "
                        "JOIN objects o ON o.id = i.id "
                        "WHERE p.identifier = :ident AND i.sequence_id = :seq_id "
                        "  AND i.workspace_id = :ws_id AND o.deleted_at IS NULL"
                    )
                    row = (
                        await session.execute(
                            stmt,
                            {
                                "ws_id": workspace_id,
                                "ident": ident.upper(),
                                "seq_id": int(seq_str),
                            },
                        )
                    ).first()
                    if row is not None:
                        target_uuid = uuid.UUID(str(row[0]))
            if target_uuid is None:
                stmt = text(
                    "SELECT id FROM objects "
                    "WHERE workspace_id = :ws_id "
                    "  AND (canonical_key = :raw_id OR display_title = :raw_id) "
                    "  AND object_type = 'issue' AND deleted_at IS NULL"
                )
                row = (
                    await session.execute(
                        stmt,
                        {"ws_id": workspace_id, "raw_id": raw_id},
                    )
                ).first()
                if row is not None:
                    target_uuid = uuid.UUID(str(row[0]))

        if target_uuid is None:
            return None

        if not await self._check_object_view(session, workspace_id, principal_id, target_uuid):
            return None
        return (f"issue:{target_uuid}", target_uuid, "issue")

    async def _resolve_doc_channel(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        raw_id: str,
    ) -> tuple[str, uuid.UUID, str] | None:
        try:
            target_uuid = uuid.UUID(raw_id)
        except ValueError:
            return None

        if not await self._check_object_view(session, workspace_id, principal_id, target_uuid):
            return None
        return (f"doc:{target_uuid}", target_uuid, "doc")

    @staticmethod
    def _resolve_user_channel(
        principal_id: uuid.UUID,
        kind: str,
        raw_id: str,
    ) -> tuple[str, uuid.UUID, str] | None:
        if kind == "notifications":
            if raw_id == "self":
                return (f"user:{principal_id}", principal_id, "user")
            return None

        try:
            target_uuid = uuid.UUID(raw_id)
        except ValueError:
            return None

        if target_uuid != principal_id:
            return None
        return (f"user:{principal_id}", principal_id, "user")

    async def resolve_channel(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        channel: str,
    ) -> tuple[str, uuid.UUID, str] | None:
        """Resolve channel identifier to (canonical_channel, target_uuid, kind).

        Supports:
        - workspace:<UUID> or workspace:<SLUG> or workspace:stickies
        - project:<UUID> or project:<KEY>
        - issue:<UUID> or issue:<KEY>
        - doc:<UUID>
        - notifications:self or user:<SELF_UUID>

        Returns None if channel format is invalid, target does not exist, or principal lacks VIEW.
        """
        if ":" not in channel:
            return None

        kind, raw_id = channel.split(":", 1)
        raw_id = raw_id.strip()
        if not raw_id:
            return None

        result: tuple[str, uuid.UUID, str] | None = None
        if kind == "workspace":
            result = await self._resolve_workspace_channel(session, workspace_id, raw_id)
        elif kind == "project":
            result = await self._resolve_project_channel(
                session, workspace_id, principal_id, raw_id
            )
        elif kind == "issue":
            result = await self._resolve_issue_channel(session, workspace_id, principal_id, raw_id)
        elif kind == "doc":
            result = await self._resolve_doc_channel(session, workspace_id, principal_id, raw_id)
        elif kind in ("notifications", "user"):
            result = self._resolve_user_channel(principal_id, kind, raw_id)
        return result

    async def check_channel_viewable(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        channel: str,
    ) -> bool:
        """Evaluate VIEW permission on target channel, preventing enumeration."""
        resolved = await self.resolve_channel(session, workspace_id, principal_id, channel)
        return resolved is not None

    async def _resolve_channel_taint(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        kind: str,
        target_uuid: uuid.UUID,
    ) -> tuple[uuid.UUID | None, bool]:
        """Resolve parent project ID and untrusted content flag for a channel target."""
        if kind == "project":
            return target_uuid, False
        if kind == "issue":
            stmt = text(
                "SELECT project_id, is_untrusted_content "
                "FROM issues WHERE id = :id AND workspace_id = :ws_id"
            )
        elif kind == "doc":
            stmt = text(
                "SELECT project_id, is_untrusted_content "
                "FROM docs WHERE id = :id AND workspace_id = :ws_id"
            )
        else:
            return None, False

        row = (await session.execute(stmt, {"id": target_uuid, "ws_id": workspace_id})).first()
        if row is not None and row[0] is not None:
            return uuid.UUID(str(row[0])), bool(row[1])
        return None, False

    async def _propagate_subscription_read_taint(
        self,
        session: AsyncSession,
        conn: RealtimeConnection,
        resolved_targets: Sequence[tuple[str, uuid.UUID]],
    ) -> None:
        """Propagate read-taint for subscribed projects, issues, and docs to mcp_read_taint."""
        import hashlib  # noqa: PLC0415

        from kanban.security.read_taint import record_read_taint  # noqa: PLC0415

        taint_project_ids: set[uuid.UUID] = set()
        untrusted_entries: list[tuple[uuid.UUID, uuid.UUID]] = []

        for kind, target_uuid in resolved_targets:
            p_id, is_untrusted = await self._resolve_channel_taint(
                session, conn.workspace_id, kind, target_uuid
            )
            if p_id is not None:
                taint_project_ids.add(p_id)
                if is_untrusted:
                    untrusted_entries.append((p_id, target_uuid))

        if not taint_project_ids:
            return

        mcp_sess = getattr(conn, "mcp_session_id", None)
        mcp_key = hashlib.sha256(mcp_sess.encode("utf-8")).digest() if mcp_sess else None

        await record_read_taint(
            session=session,
            workspace_id=conn.workspace_id,
            project_ids=taint_project_ids,
            session_id=conn.session_id,
            credential_key=conn.token_sha256,
        )
        if mcp_key is not None:
            await record_read_taint(
                session=session,
                workspace_id=conn.workspace_id,
                project_ids=taint_project_ids,
                session_key=mcp_key,
            )

        for p_id, src_id in untrusted_entries:
            await record_read_taint(
                session=session,
                workspace_id=conn.workspace_id,
                project_ids=[p_id],
                session_id=conn.session_id,
                credential_key=conn.token_sha256,
                untrusted_source_object_id=src_id,
                contains_untrusted_content=True,
            )
            if mcp_key is not None:
                await record_read_taint(
                    session=session,
                    workspace_id=conn.workspace_id,
                    project_ids=[p_id],
                    session_key=mcp_key,
                    untrusted_source_object_id=src_id,
                    contains_untrusted_content=True,
                )

    async def handle_subscribe(
        self,
        session: AsyncSession,
        conn: RealtimeConnection,
        req_id: str,
        channels: Sequence[str],
        last_event_id: str | None = None,
    ) -> None:
        """Handle client subscribe request, validating limits and anti-enumeration permissions."""
        successful_channels: list[str] = []
        resolved_targets: list[tuple[str, uuid.UUID]] = []

        for ch in channels:
            if len(conn.subscribed_channels) >= MAX_CHANNELS_PER_CONNECTION:
                await conn.send_json(
                    {
                        "code": "CHANNEL_LIMIT_EXCEEDED",
                        "channel": ch,
                        "req_id": req_id,
                        "type": "subscribe_error",
                    }
                )
                continue

            resolved = await self.resolve_channel(session, conn.workspace_id, conn.principal_id, ch)
            if resolved is None:
                await conn.send_json(
                    {
                        "code": "NOT_FOUND",
                        "channel": ch,
                        "req_id": req_id,
                        "type": "subscribe_error",
                    }
                )
                continue

            canonical_ch, target_uuid, kind = resolved
            conn.subscribed_channels.add(ch)
            conn.subscribed_channels.add(canonical_ch)
            successful_channels.append(ch)
            resolved_targets.append((kind, target_uuid))

        if successful_channels:
            await self._propagate_subscription_read_taint(session, conn, resolved_targets)
            await conn.send_json(
                {
                    "channels": successful_channels,
                    "req_id": req_id,
                    "type": "subscribe_ack",
                }
            )

        if last_event_id is not None and successful_channels:
            replay_res = await self._replayer.replay_events(
                session,
                workspace_id=conn.workspace_id,
                principal_id=conn.principal_id,
                channels=list(conn.subscribed_channels),
                last_event_id=last_event_id,
            )
            if replay_res.resync_required:
                await conn.send_json(
                    {
                        "latest_event_id": replay_res.latest_event_id,
                        "type": "resync_required",
                    }
                )
            else:
                for event in replay_res.events:
                    await conn.send_json(event.to_dict())

    async def handle_unsubscribe(
        self,
        conn: RealtimeConnection,
        req_id: str,
        channels: Sequence[str],
    ) -> None:
        """Handle client unsubscribe request."""
        unsubscribed: list[str] = []
        user_chan = f"user:{conn.principal_id}"
        for ch in channels:
            if ch in ("notifications:self", user_chan):
                if (
                    ch in conn.subscribed_channels
                    or "notifications:self" in conn.subscribed_channels
                    or user_chan in conn.subscribed_channels
                ):
                    conn.subscribed_channels.discard("notifications:self")
                    conn.subscribed_channels.discard(user_chan)
                    unsubscribed.append(ch)
            elif ch in conn.subscribed_channels:
                conn.subscribed_channels.remove(ch)
                unsubscribed.append(ch)

        await conn.send_json(
            {
                "channels": unsubscribed,
                "req_id": req_id,
                "type": "unsubscribe_ack",
            }
        )

    async def handle_security_event(self, envelope: OutboxEnvelope) -> None:
        """Close matching connections within <= 250ms on security revocation events."""
        target_session_id_raw = envelope.payload.get("session_id")
        target_principal_id_raw = envelope.payload.get("principal_id")

        target_session_id = uuid.UUID(str(target_session_id_raw)) if target_session_id_raw else None
        target_principal_id = (
            uuid.UUID(str(target_principal_id_raw)) if target_principal_id_raw else None
        )

        async with self._lock:
            matched_conns: list[RealtimeConnection] = [
                conn
                for conn in self._connections.values()
                if (target_session_id is not None and conn.session_id == target_session_id)
                or (target_principal_id is not None and conn.principal_id == target_principal_id)
            ]

        for conn in matched_conns:
            await conn.close(code=WS_CLOSE_UNAUTHENTICATED, reason="SESSION_REVOKED")
            await self.unregister_connection(conn.id)

    @staticmethod
    def _match_channel(
        conn: RealtimeConnection,
        channels: tuple[str | None, ...],
        ws_chan: str,
        *,
        is_sticky: bool = False,
    ) -> str | None:
        for chan in channels:
            if chan and chan in conn.subscribed_channels:
                return chan
        if is_sticky and "workspace:stickies" in conn.subscribed_channels:
            return "workspace:stickies"
        if ws_chan in conn.subscribed_channels:
            return ws_chan
        return None

    async def _resolve_notification_candidates(
        self, envelope: OutboxEnvelope
    ) -> list[tuple[RealtimeConnection, str]]:
        """Resolve recipient-only connections subscribed to notifications:self or user:<uuid>."""
        raw_payload = envelope.payload or {}
        recipient_raw = raw_payload.get("recipient_principal_id")
        if not recipient_raw:
            return []
        try:
            recipient_uuid = uuid.UUID(str(recipient_raw))
        except (ValueError, TypeError, AttributeError):
            return []

        user_chan = f"user:{recipient_uuid}"
        notif_candidates: list[tuple[RealtimeConnection, str]] = []
        async with self._lock:
            user_conns = self.get_user_connections(envelope.workspace_id, recipient_uuid)

        for conn in user_conns:
            if conn.workspace_id != envelope.workspace_id or conn.principal_id != recipient_uuid:
                continue
            if "notifications:self" in conn.subscribed_channels:
                notif_candidates.append((conn, "notifications:self"))
            elif user_chan in conn.subscribed_channels:
                notif_candidates.append((conn, user_chan))
        return notif_candidates

    async def _resolve_candidate_connections(
        self, envelope: OutboxEnvelope
    ) -> list[tuple[RealtimeConnection, str]]:
        """Identify active connections subscribed to matching channels for this envelope."""
        if envelope.topic in NOTIFICATION_TOPICS or envelope.topic.startswith("notification."):
            return await self._resolve_notification_candidates(envelope)

        ws_chan = f"workspace:{envelope.workspace_id}"
        proj_chan = f"project:{envelope.project_id}" if envelope.project_id is not None else None
        issue_chan = f"issue:{envelope.object_id}" if envelope.object_id is not None else None
        doc_chan = f"doc:{envelope.object_id}" if envelope.object_id is not None else None

        raw_payload = envelope.payload or {}
        issue_key = str(raw_payload.get("key") or raw_payload.get("issue_key") or "")
        proj_key = str(
            raw_payload.get("project_key")
            or (issue_key.split("-", 1)[0] if "-" in issue_key else "")
        )

        proj_key_chan = f"project:{proj_key}" if proj_key else None
        issue_key_chan = f"issue:{issue_key}" if issue_key else None

        candidates: list[tuple[RealtimeConnection, str]] = []
        async with self._lock:
            all_conns = list(self._connections.values())

        is_sticky = envelope.topic.startswith("sticky.")
        channel_priority = (issue_key_chan, issue_chan, doc_chan, proj_key_chan, proj_chan)

        for conn in all_conns:
            if conn.workspace_id != envelope.workspace_id:
                continue

            matching_chan = self._match_channel(
                conn, channel_priority, ws_chan, is_sticky=is_sticky
            )
            if matching_chan is not None:
                candidates.append((conn, matching_chan))

        return candidates

    @staticmethod
    async def _dispatch_notification_candidates(
        envelope: OutboxEnvelope,
        candidates: list[tuple[RealtimeConnection, str]],
        authorized_principals: set[uuid.UUID],
    ) -> None:
        recipient_raw = (envelope.payload or {}).get("recipient_principal_id")
        try:
            recipient_uuid = uuid.UUID(str(recipient_raw))
        except (ValueError, TypeError, AttributeError):
            return
        for conn, matching_chan in candidates:
            if (
                conn.principal_id == recipient_uuid
                and conn.workspace_id == envelope.workspace_id
                and conn.principal_id in authorized_principals
            ):
                await conn.send_event(envelope, matching_chan)

    async def dispatch_envelope(self, session: AsyncSession, envelope: OutboxEnvelope) -> None:
        """Route outbox envelope through delivery-time RLS filter to subscribed connections."""
        if envelope.topic in ("security.session_revoked", "security.principal_deactivated"):
            await self.handle_security_event(envelope)
            return

        candidates = await self._resolve_candidate_connections(envelope)
        if not candidates:
            return

        candidate_principals = {conn.principal_id for conn, _ in candidates}
        authorized_principals = await authorize_event_recipients(
            session, envelope, candidate_principals
        )

        if envelope.topic in NOTIFICATION_TOPICS or envelope.topic.startswith("notification."):
            await self._dispatch_notification_candidates(
                envelope, candidates, authorized_principals
            )
            return

        issue_chan = f"issue:{envelope.object_id}" if envelope.object_id is not None else None
        doc_chan = f"doc:{envelope.object_id}" if envelope.object_id is not None else None

        for conn, matching_chan in candidates:
            if conn.principal_id in authorized_principals:
                # Recipient holds active VIEW permission on target object
                await conn.send_event(envelope, matching_chan)
            # Recipient lost VIEW permission (mid-session revocation)
            # If subscribed directly to object, revoke subscription and notify with zero payload
            elif issue_chan and issue_chan in conn.subscribed_channels:
                conn.subscribed_channels.remove(issue_chan)
                await conn.send_json({"type": "channel.revoked", "channel": issue_chan})
            elif doc_chan and doc_chan in conn.subscribed_channels:
                conn.subscribed_channels.remove(doc_chan)
                await conn.send_json({"type": "channel.revoked", "channel": doc_chan})
                # If subscribed to project channel, silently omit delivery (do not drop project)

    async def _broker_listener_loop(self) -> None:
        """Background loop reading from RealtimeBroker and dispatching envelopes."""
        if self._broker is None:
            return

        while self._running and not self._draining:
            try:
                async for envelope in self._broker.subscribe("*"):
                    if self._session_factory is not None:
                        ctx = RLSContext(
                            principal_id=uuid.UUID(int=0),
                            workspace_id=envelope.workspace_id,
                            token_scopes=("realtime",),
                            aal_level=1,
                        )
                        async with self._session_factory.session(ctx) as session:
                            await self.dispatch_envelope(session, envelope)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in realtime broker listener loop; reconnecting...")
                await asyncio.sleep(0.5)

    async def _heartbeat_loop(self) -> None:
        """Periodic server heartbeat ping (25s)."""
        while self._running and not self._draining:
            try:
                await asyncio.sleep(self._ping_interval_s)
                async with self._lock:
                    active_conns = list(self._connections.values())

                for conn in active_conns:
                    if isinstance(conn, WebSocketConnection):
                        with contextlib.suppress(Exception):
                            await conn.send_json({"type": "ping"})
                    elif isinstance(conn, SSEConnection):
                        with contextlib.suppress(Exception):
                            await conn.send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in realtime heartbeat loop")

    async def _session_recheck_loop(self) -> None:
        """Periodic session idle and absolute expiration recheck (60s)."""
        while self._running and not self._draining:
            try:
                await asyncio.sleep(self._session_check_interval_s)
                if self._session_factory is None or self._session_service is None:
                    continue

                async with self._lock:
                    active_conns = list(self._connections.values())

                # Recheck sessions via SessionService
                for conn in active_conns:
                    if conn.token_sha256 is None:
                        continue

                    ctx = RLSContext(
                        principal_id=conn.principal_id,
                        workspace_id=conn.workspace_id,
                        token_scopes=("session",),
                        aal_level=1,
                    )
                    async with self._session_factory.session(ctx) as session:
                        user_session = await self._session_service.resolve_session(
                            session, conn.token_sha256
                        )

                    if user_session is None or user_session.mfa_pending:
                        await conn.close(code=WS_CLOSE_UNAUTHENTICATED, reason="SESSION_EXPIRED")
                        await self.unregister_connection(conn.id)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in realtime session recheck loop")
