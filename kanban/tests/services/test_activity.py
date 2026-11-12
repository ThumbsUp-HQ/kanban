"""Tests for the shared activity helper (KB-P3-01a)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.services.activity import (
    EVENT_CATEGORY,
    MAX_PAYLOAD_BYTES,
    ActivityCategory,
    ActivityEnvelope,
    ActivityEventType,
    ActivityObjectNotFound,
    ActivityPayloadTooLarge,
    EphemeralEnvelope,
    clear_activity_listeners,
    emit_ephemeral_event,
    record_activity,
    register_activity_listener,
)
from kanban.tests.security.helpers import (
    create_project,
    create_user,
    create_workspace,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _isolated_listeners() -> Iterator[None]:
    """Guarantee each test starts and ends with an empty listener registry."""
    clear_activity_listeners()
    yield
    clear_activity_listeners()


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a workspace, actor and project object; return their ids."""
    ws = await create_workspace(session)
    actor = await create_user(session, ws, handle="@actor", display_name="Actor")
    project = await create_project(session, ws, identifier="ACT", created_by_id=actor)
    return ws, actor, project


async def _count(session: AsyncSession, object_id: uuid.UUID) -> int:
    row = await session.execute(
        text("SELECT count(*) FROM activity_records WHERE object_id = :o"), {"o": object_id}
    )
    return int(row.scalar_one())


@pytest.mark.asyncio
async def test_case_6a_payload_over_cap_raises(db_session: AsyncSession) -> None:
    """A payload over 16384 serialized bytes raises and writes nothing."""
    ws, actor, project = await _seed(db_session)
    with pytest.raises(ActivityPayloadTooLarge):
        await record_activity(
            db_session,
            workspace_id=ws,
            object_id=project,
            actor_principal_id=actor,
            event_type=ActivityEventType.PROJECT_UPDATED,
            payload={"blob": "x" * MAX_PAYLOAD_BYTES},
        )
    assert await _count(db_session, project) == 0

    # Just under the cap is accepted by both the helper and the DB CHECK constraint.
    activity_id = await record_activity(
        db_session,
        workspace_id=ws,
        object_id=project,
        actor_principal_id=actor,
        event_type=ActivityEventType.PROJECT_UPDATED,
        payload={"blob": "x" * (MAX_PAYLOAD_BYTES - 64)},
    )
    assert isinstance(activity_id, uuid.UUID)
    assert await _count(db_session, project) == 1


@pytest.mark.asyncio
async def test_case_6b_raising_listener_rolls_back_insert(db_session: AsyncSession) -> None:
    """A listener exception propagates and the activity insert is rolled back."""
    ws, actor, project = await _seed(db_session)
    seen: list[str] = []

    async def good(_session: AsyncSession, env: ActivityEnvelope | EphemeralEnvelope) -> None:
        seen.append(f"good:{env.event_type}")

    async def bad(_session: AsyncSession, _env: ActivityEnvelope | EphemeralEnvelope) -> None:
        msg = "listener failure"
        raise RuntimeError(msg)

    register_activity_listener(good)
    register_activity_listener(bad)
    with pytest.raises(RuntimeError, match="listener failure"):
        await record_activity(
            db_session,
            workspace_id=ws,
            object_id=project,
            actor_principal_id=actor,
            event_type=ActivityEventType.PROJECT_CREATED,
            payload={"identifier": "ACT"},
        )
    assert seen == ["good:PROJECT_CREATED"]
    assert await _count(db_session, project) == 0


@pytest.mark.asyncio
async def test_listeners_run_in_order_with_envelope(db_session: AsyncSession) -> None:
    """Listeners receive the persisted envelope in registration order."""
    ws, actor, project = await _seed(db_session)
    order: list[int] = []
    envelopes: list[ActivityEnvelope] = []

    async def first(_s: AsyncSession, env: ActivityEnvelope | EphemeralEnvelope) -> None:
        order.append(1)
        assert isinstance(env, ActivityEnvelope)
        envelopes.append(env)

    async def second(_s: AsyncSession, _env: ActivityEnvelope | EphemeralEnvelope) -> None:
        order.append(2)

    register_activity_listener(first)
    register_activity_listener(second)
    activity_id = await record_activity(
        db_session,
        workspace_id=ws,
        object_id=project,
        actor_principal_id=actor,
        event_type=ActivityEventType.MODULE_DEFAULTS_CHANGED,
        payload={"old_module_ids": [], "new_module_ids": []},
    )
    assert order == [1, 2]
    assert envelopes[0].activity_id == activity_id
    assert envelopes[0].category is ActivityCategory.HISTORY
    assert envelopes[0].object_id == project


@pytest.mark.asyncio
async def test_ephemeral_event_notifies_without_persisting(db_session: AsyncSession) -> None:
    """Ephemeral events reach listeners but never write ``activity_records``."""
    ws, actor, project = await _seed(db_session)
    received: list[EphemeralEnvelope] = []

    async def listener(_s: AsyncSession, env: ActivityEnvelope | EphemeralEnvelope) -> None:
        assert isinstance(env, EphemeralEnvelope)
        received.append(env)

    register_activity_listener(listener)
    envelope = EphemeralEnvelope(
        workspace_id=ws,
        object_id=project,
        actor_principal_id=actor,
        event_type="ISSUE_RANK_MOVED",
        payload={"rank": "a0"},
    )
    await emit_ephemeral_event(db_session, envelope)
    assert received == [envelope]
    assert await _count(db_session, project) == 0


@pytest.mark.asyncio
async def test_unknown_object_raises(db_session: AsyncSession) -> None:
    """Recording against an object invisible to the session raises ActivityObjectNotFound."""
    ws, actor, _project = await _seed(db_session)
    with pytest.raises(ActivityObjectNotFound):
        await record_activity(
            db_session,
            workspace_id=ws,
            object_id=uuid.uuid4(),
            actor_principal_id=actor,
            event_type=ActivityEventType.PROJECT_CREATED,
            payload={},
        )


def test_every_event_type_has_a_category() -> None:
    """Every ActivityEventType member must be registered in EVENT_CATEGORY."""
    assert set(EVENT_CATEGORY) == set(ActivityEventType)
    assert all(isinstance(c, ActivityCategory) for c in EVENT_CATEGORY.values())
    assert {c.value for c in ActivityCategory} == {"COMMENT", "HISTORY", "GATE", "SYSTEM"}
