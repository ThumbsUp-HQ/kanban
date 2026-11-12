# Copyright 2026 Kanban Platform Contributors
"""Tests for background column board rank rebalancing (KB-P3-12, S6.4)."""

from __future__ import annotations

import argparse
import os
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from database.models import Issue, WorkflowState
from kanban.cli.jobs import _handle_board_rebalance, _run_board_rebalance
from kanban.jobs.board_rebalance import rebalance_column
from kanban.services.activity import ActivityEventType
from kanban.services.board_rank import REBALANCE_THRESHOLD_LEN, midpoint_rank
from kanban.tests.security.helpers import (
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.committed_db


async def _create_test_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    proj_ident: str,
    state_id: uuid.UUID,
    creator_id: uuid.UUID,
    rank: str,
    title: str = "Test Issue",
) -> uuid.UUID:
    """Allocate sequence, register object, and insert issue."""
    seq = await session.scalar(
        text("SELECT allocate_issue_sequence(:p)"),
        {"p": proj_id},
    )
    key = f"{proj_ident}-{seq}"
    iss_id = await create_registered_object(
        session,
        ws_id,
        kind="issue",
        key=key,
        title=title,
        project_id=proj_id,
        created_by_id=creator_id,
    )
    prio_id = await session.scalar(
        text("SELECT id FROM project_priorities WHERE project_id = :p ORDER BY sort_order LIMIT 1"),
        {"p": proj_id},
    )
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, state_id, "
            "  priority_id, board_rank, created_by_id, original_created_by_id"
            ") VALUES (:id, :ws, :proj, :seq, :summary, :state, :prio, :rank, :creator, :creator)"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "summary": title,
            "state": state_id,
            "prio": prio_id,
            "rank": rank,
            "creator": creator_id,
        },
    )
    return iss_id


async def test_rebalance_boundary_logic() -> None:
    """Bisecting adjacent ranks produces ranks exceeding threshold of 32 chars."""
    lo = "a000001"
    hi = "a000002"
    step = 0
    while len(hi) <= REBALANCE_THRESHOLD_LEN and step < 200:
        hi = midpoint_rank(lo, hi)
        step += 1

    assert len(hi) >= 33
    rebalance_scheduled = bool(len(hi) > REBALANCE_THRESHOLD_LEN)
    assert rebalance_scheduled is True


async def test_rebalance_column_empty_and_single(
    committed_db_session: AsyncSession,
) -> None:
    """Rebalance on empty or single-card column returns 0."""
    ws_id = await create_workspace(committed_db_session, name="RebalanceWs")
    admin_id = await create_user(committed_db_session, ws_id, handle="@admin", display_name="Admin")
    proj_id = await create_project(
        committed_db_session, ws_id, identifier="REB1", created_by_id=admin_id
    )
    await committed_db_session.commit()

    states = (
        (
            await committed_db_session.execute(
                select(WorkflowState).where(WorkflowState.project_id == proj_id)
            )
        )
        .scalars()
        .all()
    )
    target_state = states[0]

    # 0 issues -> returns 0
    updated_0 = await rebalance_column(committed_db_session, proj_id, target_state.id)
    assert updated_0 == 0

    # Non-existent project -> returns 0
    updated_nonexistent = await rebalance_column(
        committed_db_session, uuid.uuid4(), target_state.id
    )
    assert updated_nonexistent == 0

    # 1 issue -> returns 0
    await _create_test_issue(
        committed_db_session,
        ws_id,
        proj_id,
        "REB1",
        target_state.id,
        admin_id,
        "a000001V",
    )
    await committed_db_session.commit()

    updated_1 = await rebalance_column(
        committed_db_session, proj_id, target_state.id, actor_principal_id=admin_id
    )
    assert updated_1 == 0


async def test_rebalance_column_multi_card_and_activity_and_outbox(
    committed_db_session: AsyncSession,
) -> None:
    """Rebalancing multi-card column updates ranks, writes activity, and enqueues outbox."""
    ws_id = await create_workspace(committed_db_session, name="RebalanceWs2")
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@admin2", display_name="Admin2"
    )
    proj_id = await create_project(
        committed_db_session, ws_id, identifier="REB2", created_by_id=admin_id
    )
    await committed_db_session.commit()

    state = (
        (
            await committed_db_session.execute(
                select(WorkflowState).where(WorkflowState.project_id == proj_id)
            )
        )
        .scalars()
        .first()
    )
    assert state is not None

    # Insert 4 cards: 2 with normal ranks, 1 with a very long rank (33 chars), 1 normal
    # Strictly increasing in ASCII: 'a000001V' < 'a000002V' < 'm000...1V' < 'z000001V'
    deep_rank = "m" + "0" * 30 + "1V"  # 33 chars
    initial_ranks = ["a000001V", "a000002V", deep_rank, "z000001V"]

    issue_ids: list[uuid.UUID] = []
    for r in initial_ranks:
        iss_id = await _create_test_issue(
            committed_db_session,
            ws_id,
            proj_id,
            "REB2",
            state.id,
            admin_id,
            r,
        )
        issue_ids.append(iss_id)

    await committed_db_session.commit()

    # Execute rebalance_column
    updated_count = await rebalance_column(committed_db_session, proj_id, state.id)
    await committed_db_session.commit()
    assert updated_count > 0

    # Query issues after rebalance
    post_issues = (
        await committed_db_session.execute(
            select(Issue.id, Issue.board_rank)
            .where(Issue.project_id == proj_id, Issue.state_id == state.id)
            .order_by(text('board_rank COLLATE "C" ASC'), Issue.id.asc())
        )
    ).all()

    # Original order is preserved
    post_ids = [row[0] for row in post_issues]
    assert post_ids == issue_ids

    # All ranks are <= 7 chars and non-zero terminated
    for _, rank in post_issues:
        assert len(rank) <= 7
        assert not rank.endswith("0")

    # Verify BOARD_COLUMN_REBALANCED activity record on project
    activity_rows = (
        await committed_db_session.execute(
            text(
                "SELECT event_type, payload FROM activity_records "
                "WHERE object_id = :proj_id AND event_type = :event"
            ),
            {
                "proj_id": proj_id,
                "event": ActivityEventType.BOARD_COLUMN_REBALANCED.value,
            },
        )
    ).all()
    assert len(activity_rows) == 1
    act_event, act_payload = activity_rows[0]
    assert act_event == ActivityEventType.BOARD_COLUMN_REBALANCED.value
    assert act_payload["state_id"] == str(state.id)
    assert act_payload["reindexed_count"] == updated_count
    assert act_payload["max_prev_len"] == len(deep_rank)

    # Verify column.rebalanced outbox event
    outbox_rows = (
        await committed_db_session.execute(
            text(
                "SELECT topic, payload FROM outbox_events "
                "WHERE project_id = :proj_id AND topic = 'column.rebalanced'"
            ),
            {"proj_id": proj_id},
        )
    ).all()
    assert len(outbox_rows) == 1
    topic, out_payload = outbox_rows[0]
    assert topic == "column.rebalanced"
    assert out_payload["state_id"] == str(state.id)
    assert out_payload["reindexed_count"] == updated_count

    # Second run should find ranks already balanced and return 0
    updated_again = await rebalance_column(committed_db_session, proj_id, state.id)
    assert updated_again == 0


async def test_rebalance_column_advisory_lock_contention(
    committed_db_session: AsyncSession,
) -> None:
    """When advisory lock is already held, rebalance_column returns 0 immediately."""
    ws_id = await create_workspace(committed_db_session, name="LockWs")
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@admin3", display_name="Admin3"
    )
    proj_id = await create_project(
        committed_db_session, ws_id, identifier="LOCK1", created_by_id=admin_id
    )
    await committed_db_session.commit()

    state = (
        (
            await committed_db_session.execute(
                select(WorkflowState).where(WorkflowState.project_id == proj_id)
            )
        )
        .scalars()
        .first()
    )
    assert state is not None

    # Insert 2 cards
    for i in (1, 2):
        await _create_test_issue(
            committed_db_session,
            ws_id,
            proj_id,
            "LOCK1",
            state.id,
            admin_id,
            f"a0{i}V",
        )
    await committed_db_session.commit()

    # Mock execute result for advisory lock check to simulate lock contention
    orig_execute = committed_db_session.execute

    async def mock_execute(statement: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        if "pg_try_advisory_xact_lock" in str(statement):
            mock_res = AsyncMock()
            mock_res.scalar_one = lambda: False
            return mock_res
        return await orig_execute(statement, *args, **kwargs)

    with patch.object(committed_db_session, "execute", side_effect=mock_execute):
        res = await rebalance_column(committed_db_session, proj_id, state.id)
        assert res == 0


async def test_cli_board_rebalance_command(
    committed_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI board-rebalance runner executes across projects and filters."""
    ws_id = await create_workspace(committed_db_session, name="CliWs")
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@cliadmin", display_name="CliAdmin"
    )
    proj_id = await create_project(
        committed_db_session, ws_id, identifier="CLIP", created_by_id=admin_id
    )
    await committed_db_session.commit()

    state = (
        (
            await committed_db_session.execute(
                select(WorkflowState).where(WorkflowState.project_id == proj_id)
            )
        )
        .scalars()
        .first()
    )
    assert state is not None

    # Insert 2 cards with long ranks
    for i in (1, 2):
        await _create_test_issue(
            committed_db_session,
            ws_id,
            proj_id,
            "CLIP",
            state.id,
            admin_id,
            "a" * (30 + i) + "V",
        )
    await committed_db_session.commit()

    # Configure environment for CLI
    assert isinstance(committed_db_session.bind, AsyncEngine)
    db_name = committed_db_session.bind.url.database or "postgres"
    monkeypatch.setenv("KB_DB_NAME", db_name)
    raw_sock = committed_db_session.bind.url.query.get("host")
    if isinstance(raw_sock, tuple):
        raw_sock = raw_sock[0] if raw_sock else None
    sock = str(raw_sock or os.environ.get("KB_TEST_PGHOST") or "/tmp/kb-pgsock")
    monkeypatch.setenv("KB_TEST_PGHOST", sock)

    # Run CLI with matching project filter
    rc = await _run_board_rebalance("CLIP")
    assert rc == 0

    # Run CLI with non-matching project filter
    rc_none = await _run_board_rebalance("NONEXISTENT")
    assert rc_none == 0

    # Test parser handler function
    args = argparse.Namespace(project="CLIP")
    sync_rc = _handle_board_rebalance(args)
    assert sync_rc == 0
