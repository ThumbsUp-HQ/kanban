# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Realtime WebSocket and SSE subscription hub and RLS authorization filters."""

from __future__ import annotations

from kanban.realtime.hub import (
    MAX_CHANNELS_PER_CONNECTION,
    MAX_CONNECTIONS_PER_PRINCIPAL,
    MAX_INBOUND_FRAME_BYTES,
    WS_CLOSE_CONNECTION_LIMIT,
    WS_CLOSE_DRAINING,
    WS_CLOSE_FRAME_TOO_LARGE,
    WS_CLOSE_ORIGIN_MISMATCH,
    WS_CLOSE_UNAUTHENTICATED,
    RealtimeConnection,
    RealtimeHub,
    SSEConnection,
    WebSocketConnection,
)
from kanban.realtime.replay import (
    OutboxReplayer,
    ReplayedEvent,
    ReplayResult,
)
from kanban.realtime.rls_filter import (
    EXTERNAL_COLLABORATOR_REDACTED,
    OutboxEventLike,
    authorize_event_recipients,
    redact_event_payload,
)

__all__ = [
    "EXTERNAL_COLLABORATOR_REDACTED",
    "MAX_CHANNELS_PER_CONNECTION",
    "MAX_CONNECTIONS_PER_PRINCIPAL",
    "MAX_INBOUND_FRAME_BYTES",
    "WS_CLOSE_CONNECTION_LIMIT",
    "WS_CLOSE_DRAINING",
    "WS_CLOSE_FRAME_TOO_LARGE",
    "WS_CLOSE_ORIGIN_MISMATCH",
    "WS_CLOSE_UNAUTHENTICATED",
    "OutboxEventLike",
    "OutboxReplayer",
    "RealtimeConnection",
    "RealtimeHub",
    "ReplayResult",
    "ReplayedEvent",
    "SSEConnection",
    "WebSocketConnection",
    "authorize_event_recipients",
    "redact_event_payload",
]
