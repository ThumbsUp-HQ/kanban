# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Delivery-time Row-Level Security (RLS) authorization and redaction filter (KB-P3-16)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from sqlalchemy import text

from kanban.security.permissions import Capability

if TYPE_CHECKING:
    from collections.abc import Sequence
    from collections.abc import Set as AbstractSet

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "EXTERNAL_COLLABORATOR_REDACTED",
    "OutboxEventLike",
    "authorize_event_recipients",
    "redact_event_payload",
]

EXTERNAL_COLLABORATOR_REDACTED: Final[dict[str, Any]] = {
    "redacted": True,
    "label": "1 External Collaborator",
}


@runtime_checkable
class OutboxEventLike(Protocol):
    """Protocol matching domain outbox events and envelopes."""

    workspace_id: uuid.UUID
    object_id: uuid.UUID | None
    project_id: uuid.UUID | None


def redact_event_payload(payload: dict[str, Any], *, is_visible: bool = True) -> dict[str, Any]:
    """Redact actor metadata in outbox event payload when outside recipient visibility boundary.

    Spec S3.4: Replaces actor object with standard {"redacted": True, "label": "1 External
    Collaborator"} placeholder and eliminates actor identifiers from the top level.
    """
    if is_visible:
        return dict(payload)

    redacted = dict(payload)
    if "actor" in redacted:
        redacted["actor"] = dict(EXTERNAL_COLLABORATOR_REDACTED)

    # Cleanse any direct actor identifier leakage
    for sensitive_key in (
        "actor_principal_id",
        "actor_id",
        "actor_email",
        "actor_handle",
        "actor_name",
    ):
        redacted.pop(sensitive_key, None)

    return redacted


async def authorize_event_recipients(
    session: AsyncSession,
    event: OutboxEventLike | object,
    candidate_principals: Sequence[uuid.UUID] | AbstractSet[uuid.UUID],
) -> set[uuid.UUID]:
    """Verify delivery-time VIEW access for candidate principals on an event's target object.

    Spec S3.3 / KB-P3-16: Runs one batched query against effective_resource_access evaluating
    (allow_mask & 1) = 1 AND (deny_mask & 1) = 0 on event.object_id (or project_id) for the
    event's workspace.
    """
    if not candidate_principals:
        return set()

    object_id: uuid.UUID | None = getattr(event, "object_id", None)
    workspace_id: uuid.UUID | None = getattr(event, "workspace_id", None)
    project_id: uuid.UUID | None = getattr(event, "project_id", None)

    target_id = object_id if object_id is not None else project_id
    if target_id is None:
        # Event is not bound to a specific object or project; all candidate principals in the
        # workspace are authorized recipients.
        return set(candidate_principals)

    candidate_list = list(candidate_principals)
    params: dict[str, Any] = {
        "obj_id": target_id,
        "candidate_ids": candidate_list,
    }

    if workspace_id is not None:
        stmt = text(
            "SELECT principal_id, allow_mask, deny_mask "
            "FROM effective_resource_access "
            "WHERE object_id = :obj_id "
            "  AND workspace_id = :ws_id "
            "  AND principal_id = ANY(CAST(:candidate_ids AS uuid[]))"
        )
        params["ws_id"] = workspace_id
    else:
        stmt = text(
            "SELECT principal_id, allow_mask, deny_mask "
            "FROM effective_resource_access "
            "WHERE object_id = :obj_id "
            "  AND principal_id = ANY(CAST(:candidate_ids AS uuid[]))"
        )

    result = await session.execute(stmt, params)
    rows = result.mappings().all()

    authorized: set[uuid.UUID] = set()
    view_bit = Capability.VIEW.value
    for row in rows:
        allow = int(row["allow_mask"])
        deny = int(row["deny_mask"])
        if (allow & view_bit) == view_bit and (deny & view_bit) == 0:
            authorized.add(uuid.UUID(str(row["principal_id"])))

    return authorized
