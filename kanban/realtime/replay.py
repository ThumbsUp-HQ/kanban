# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Outbox replay service for Last-Event-ID resumption and anti-harvesting RLS checks (KB-P3-16)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from kanban.realtime.rls_filter import OutboxEventLike, authorize_event_recipients

if TYPE_CHECKING:
    from collections.abc import Sequence
    from collections.abc import Set as AbstractSet
    from datetime import datetime

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "OutboxReplayer",
    "ReplayResult",
    "ReplayedEvent",
]

DEFAULT_MAX_REPLAY_EVENTS = 500
DEFAULT_RETENTION_MINUTES = 15


@dataclass(frozen=True, slots=True)
class ReplayedEvent:
    """Historical domain event retrieved from outbox_events during connection resume."""

    event_id: str
    channel: str
    topic: str
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    object_id: uuid.UUID | None
    payload: dict[str, Any]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert replayed event to canonical wire dictionary."""
        return {
            "channel": self.channel,
            "created_at": self.created_at.isoformat(),
            "event_id": self.event_id,
            "object_id": str(self.object_id) if self.object_id is not None else None,
            "payload": self.payload,
            "project_id": str(self.project_id) if self.project_id is not None else None,
            "topic": self.topic,
            "type": "event",
            "workspace_id": str(self.workspace_id),
        }

    def to_sse_frame(self) -> str:
        """Format as Server-Sent Event message frame."""
        data_json = json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)
        return f"id: {self.event_id}\nevent: {self.topic}\ndata: {data_json}\n\n"


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Result of an outbox replay request."""

    resync_required: bool
    latest_event_id: str
    events: list[ReplayedEvent]


class OutboxReplayer:
    """Service querying transactional outbox history with anti-harvesting RLS checks."""

    def __init__(
        self,
        *,
        max_events: int = DEFAULT_MAX_REPLAY_EVENTS,
        retention_minutes: int = DEFAULT_RETENTION_MINUTES,
    ) -> None:
        """Initialize replayer with maximum batch size and retention window in minutes."""
        self._max_events = max_events
        self._retention_minutes = retention_minutes

    async def _check_retention(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        last_seq: int,
    ) -> tuple[bool, int]:
        """Check if last_seq is valid or expired. Returns (resync_required, latest_seq)."""
        stats_stmt = text(
            "SELECT coalesce(min(seq), 0) AS min_seq, "
            "       coalesce(max(seq), 0) AS max_seq "
            "FROM outbox_events "
            "WHERE workspace_id = :ws_id "
            "  AND created_at >= clock_timestamp() - (make_interval(mins => :retention_minutes))"
        )
        stats_res = await session.execute(
            stats_stmt,
            {
                "ws_id": workspace_id,
                "retention_minutes": self._retention_minutes,
            },
        )
        row = stats_res.mappings().first()
        min_seq = int(row["min_seq"]) if row else 0
        max_seq = int(row["max_seq"]) if row else 0

        if min_seq > 0 and last_seq < min_seq:
            return True, max_seq

        if min_seq == 0 and max_seq == 0:
            overall_stmt = text(
                "SELECT coalesce(max(seq), 0) AS overall_max "
                "FROM outbox_events "
                "WHERE workspace_id = :ws_id"
            )
            overall_res = await session.execute(overall_stmt, {"ws_id": workspace_id})
            overall_max = int(overall_res.scalar_one())
            if overall_max > 0 and last_seq < overall_max:
                return True, overall_max
            return False, last_seq

        return False, max_seq

    @staticmethod
    def _match_channel(
        channel_set: AbstractSet[str],
        ws_id: uuid.UUID,
        proj_id: uuid.UUID | None,
        obj_id: uuid.UUID | None,
    ) -> str | None:
        """Determine matching subscribed channel pattern for event."""
        if obj_id is not None:
            issue_chan = f"issue:{obj_id}"
            if issue_chan in channel_set:
                return issue_chan
            doc_chan = f"doc:{obj_id}"
            if doc_chan in channel_set:
                return doc_chan

        if proj_id is not None:
            proj_chan = f"project:{proj_id}"
            if proj_chan in channel_set:
                return proj_chan

        ws_chan = f"workspace:{ws_id}"
        if ws_chan in channel_set:
            return ws_chan

        return None

    async def _fetch_and_filter_events(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        channel_set: AbstractSet[str],
        last_seq: int,
    ) -> list[ReplayedEvent]:
        """Fetch candidate rows and filter each against delivery-time RLS."""
        events_stmt = text(
            "SELECT id, seq, workspace_id, project_id, object_id, topic, payload, created_at "
            "FROM outbox_events "
            "WHERE workspace_id = :ws_id "
            "  AND seq > :last_seq "
            "  AND created_at >= clock_timestamp() - (make_interval(mins => :retention_minutes)) "
            "ORDER BY seq ASC "
            "LIMIT :limit"
        )
        events_res = await session.execute(
            events_stmt,
            {
                "ws_id": workspace_id,
                "last_seq": last_seq,
                "retention_minutes": self._retention_minutes,
                "limit": self._max_events,
            },
        )
        rows: Sequence[RowMapping] = events_res.mappings().all()

        replayed: list[ReplayedEvent] = []
        for row in rows:
            row_ws_id = uuid.UUID(str(row["workspace_id"]))
            row_proj_id = uuid.UUID(str(row["project_id"])) if row["project_id"] else None
            row_obj_id = uuid.UUID(str(row["object_id"])) if row["object_id"] else None

            matching_channel = self._match_channel(channel_set, row_ws_id, row_proj_id, row_obj_id)
            if matching_channel is None:
                continue

            envelope = _SimpleEnvelope(
                workspace_id=row_ws_id,
                object_id=row_obj_id,
                project_id=row_proj_id,
            )
            authorized = await authorize_event_recipients(session, envelope, [principal_id])
            if principal_id not in authorized:
                continue

            replayed.append(
                ReplayedEvent(
                    event_id=str(row["seq"]),
                    channel=matching_channel,
                    topic=str(row["topic"]),
                    workspace_id=row_ws_id,
                    project_id=row_proj_id,
                    object_id=row_obj_id,
                    payload=dict(row["payload"]),
                    created_at=row["created_at"],
                )
            )

        return replayed

    async def replay_events(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        channels: Sequence[str] | AbstractSet[str],
        last_event_id: str | int,
    ) -> ReplayResult:
        """Replay missed events for channels, filtering each event through current RLS."""
        try:
            last_seq = int(str(last_event_id).strip())
        except (ValueError, TypeError):
            return ReplayResult(resync_required=True, latest_event_id="0", events=[])

        if last_seq < 0:
            return ReplayResult(resync_required=True, latest_event_id="0", events=[])

        channel_set = set(channels)
        if not channel_set:
            return ReplayResult(resync_required=False, latest_event_id=str(last_seq), events=[])

        resync_required, latest_seq = await self._check_retention(session, workspace_id, last_seq)
        if resync_required:
            return ReplayResult(resync_required=True, latest_event_id=str(latest_seq), events=[])

        # Verify missed row count ceiling
        count_stmt = text(
            "SELECT count(*) "
            "FROM outbox_events "
            "WHERE workspace_id = :ws_id "
            "  AND seq > :last_seq "
            "  AND created_at >= clock_timestamp() - (make_interval(mins => :retention_minutes))"
        )
        count_res = await session.execute(
            count_stmt,
            {
                "ws_id": workspace_id,
                "last_seq": last_seq,
                "retention_minutes": self._retention_minutes,
            },
        )
        if int(count_res.scalar_one()) > self._max_events:
            return ReplayResult(resync_required=True, latest_event_id=str(latest_seq), events=[])

        events = await self._fetch_and_filter_events(
            session, workspace_id, principal_id, channel_set, last_seq
        )
        return ReplayResult(
            resync_required=False,
            latest_event_id=str(latest_seq or last_seq),
            events=events,
        )


@dataclass(frozen=True, slots=True)
class _SimpleEnvelope(OutboxEventLike):
    workspace_id: uuid.UUID
    object_id: uuid.UUID | None
    project_id: uuid.UUID | None
