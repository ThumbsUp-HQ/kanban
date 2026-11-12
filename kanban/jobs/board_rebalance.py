"""Background column rebalancing service for fractional board ranks (KB-P3-12, S6.4)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from database.models.issues import Issue
from database.models.projects import Project
from database.models.spine import ObjectRecord
from database.outbox.broker import enqueue_outbox_event
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.board_rank import generate_evenly_spaced_ranks

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def rebalance_column(
    session: AsyncSession,
    project_id: uuid.UUID,
    state_id: uuid.UUID,
    *,
    actor_principal_id: uuid.UUID | None = None,
) -> int:
    """Rebalance board_rank for all active issues in a column under advisory lock.

    Returns the number of reindexed issue rows updated.
    """
    # 1. Acquire transaction-scoped advisory lock for the column
    lock_stmt = text(
        "SELECT pg_try_advisory_xact_lock(hashtext('kanban.rebalance.' || CAST(:state_id AS text)))"
    )
    locked = (await session.execute(lock_stmt, {"state_id": str(state_id)})).scalar_one()
    if not locked:
        logger.info(
            "Column rebalance skipped: advisory lock already held for state %s",
            state_id,
        )
        return 0

    # 2. Select all active issues in column ordered by board_rank COLLATE "C", id
    query = (
        select(Issue.id, Issue.board_rank)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.project_id == project_id,
            Issue.state_id == state_id,
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
        )
        .order_by(text('board_rank COLLATE "C" ASC'), Issue.id.asc())
    )
    result = await session.execute(query)
    rows = list(result.all())

    if len(rows) <= 1:
        return 0

    max_prev_len = max(len(r[1]) for r in rows)
    new_ranks = generate_evenly_spaced_ranks(len(rows))

    updates: list[tuple[uuid.UUID, str]] = []
    for (issue_id, old_rank), new_rank in zip(rows, new_ranks, strict=True):
        if old_rank != new_rank:
            updates.append((issue_id, new_rank))

    if not updates:
        return 0

    # 3. Bulk update changed issue board_rank values in current transaction
    for issue_id, new_rank in updates:
        await session.execute(
            text("UPDATE issues SET board_rank = :new_rank WHERE id = :id"),
            {"new_rank": new_rank, "id": issue_id},
        )

    # Lookup workspace_id and project creator for activity recording
    proj_row = (
        await session.execute(
            select(Project.workspace_id, ObjectRecord.created_by_id)
            .join(ObjectRecord, ObjectRecord.id == Project.id)
            .where(Project.id == project_id)
        )
    ).first()
    if proj_row is None:
        return 0
    workspace_id, default_actor_id = proj_row
    effective_actor = actor_principal_id or default_actor_id

    # 4. Emit single BOARD_COLUMN_REBALANCED activity record on the project
    await record_activity(
        session,
        workspace_id=workspace_id,
        object_id=project_id,
        actor_principal_id=effective_actor,
        event_type=ActivityEventType.BOARD_COLUMN_REBALANCED,
        payload={
            "state_id": str(state_id),
            "reindexed_count": len(updates),
            "max_prev_len": max_prev_len,
        },
    )

    # 5. Publish single column.rebalanced outbox event
    await enqueue_outbox_event(
        session,
        workspace_id=workspace_id,
        project_id=project_id,
        object_id=state_id,
        topic="column.rebalanced",
        payload={
            "state_id": str(state_id),
            "project_id": str(project_id),
            "reindexed_count": len(updates),
            "max_prev_len": max_prev_len,
        },
    )

    logger.info(
        "Rebalanced column %s in project %s: updated %d/%d cards (max prev len %d)",
        state_id,
        project_id,
        len(updates),
        len(rows),
        max_prev_len,
    )
    return len(updates)
