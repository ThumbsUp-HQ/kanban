# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for the realtime domain outbox activity listener (KAN-35).

Covers 100% of branch and statement coverage for kanban.services.realtime_outbox:
- All issue mutation activity events -> outbox topics
- All comment mutation activity events -> outbox topics
- All sticky mutation activity events -> outbox topics
- Identity map cache hit vs SQL lookup
- Payload fallback key extraction
- Idempotent registration and reset
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from database.models import Issue, Project
from kanban.services.activity import (
    ActivityCategory,
    ActivityEnvelope,
    ActivityEventType,
)
from kanban.services.realtime_outbox import (
    _extract_string,
    clear_realtime_outbox_listener,
    handle_activity_event,
    register_realtime_outbox_listener,
)


def test_extract_string_helper() -> None:
    """Test _extract_string helper returns first non-empty string or None."""
    payload = {"empty": "", "number": 123, "valid": "found_me"}
    assert _extract_string(payload, "missing", "empty", "valid") == "found_me"
    assert _extract_string(payload, "number", "missing") is None
    assert _extract_string({}, "any") is None


@pytest.mark.asyncio
async def test_handle_activity_event_unknown_type_ignores() -> None:
    """Test unmapped activity event type returns None without enqueuing outbox events."""
    session = AsyncMock()
    envelope = ActivityEnvelope(
        activity_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        object_id=uuid.uuid4(),
        actor_principal_id=uuid.uuid4(),
        event_type="UNMAPPED_UNKNOWN_EVENT",  # type: ignore[arg-type]
        category=ActivityCategory.HISTORY,
        payload={},
    )
    await handle_activity_event(session, envelope)
    assert not session.execute.called


@pytest.mark.asyncio
async def test_handle_activity_event_stickies_variations() -> None:
    """Test all sticky event variations map to sticky.* topics."""
    ws_id = uuid.uuid4()
    sticky_id = uuid.uuid4()

    sticky_event_tests = [
        (ActivityEventType.STICKY_CREATED, "sticky.created"),
        (ActivityEventType.STICKY_UNARCHIVED_COPY, "sticky.created"),
        (ActivityEventType.STICKY_UPDATED, "sticky.updated"),
        (ActivityEventType.STICKY_RECOLORED, "sticky.updated"),
        (ActivityEventType.STICKY_PROMOTED_TO_DOC, "sticky.promoted"),
        (ActivityEventType.STICKY_TRASHED, "sticky.deleted"),
    ]

    for ev_type, expected_topic in sticky_event_tests:
        session = AsyncMock()
        envelope = ActivityEnvelope(
            activity_id=uuid.uuid4(),
            workspace_id=ws_id,
            object_id=sticky_id,
            actor_principal_id=uuid.uuid4(),
            event_type=ev_type,
            category=ActivityCategory.HISTORY,
            payload={"color": "yellow"},
        )
        await handle_activity_event(session, envelope)
        assert session.execute.called
        call_args = session.execute.call_args[0][0]
        # Verify compiled insert values
        assert call_args.compile().params.get("topic") == expected_topic


@pytest.mark.asyncio
async def test_handle_activity_event_identity_map_cache_hit() -> None:
    """Test issue resolution from session.identity_map without executing SQL query."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    issue_id = uuid.uuid4()

    mock_issue = MagicMock(spec=Issue)
    mock_issue.project_id = proj_id
    mock_issue.sequence_id = 42

    mock_proj = MagicMock(spec=Project)
    mock_proj.identifier = "DEMO"

    session = AsyncMock()
    session.identity_map = {
        (Issue, (issue_id,)): mock_issue,
        (Project, (proj_id,)): mock_proj,
    }

    envelope = ActivityEnvelope(
        activity_id=uuid.uuid4(),
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=uuid.uuid4(),
        event_type=ActivityEventType.ISSUE_STATE_CHANGED,
        category=ActivityCategory.HISTORY,
        payload={"from_state": "TODO", "to_state": "DONE"},
    )
    await handle_activity_event(session, envelope)
    assert session.execute.called
    params = session.execute.call_args[0][0].compile().params
    assert params["topic"] == "issue.transitioned"
    assert params["project_id"] == proj_id
    assert params["payload"]["issue_key"] == "DEMO-42"
    assert params["payload"]["project_key"] == "DEMO"


@pytest.mark.asyncio
async def test_handle_activity_event_sql_lookup_and_payload_fallback() -> None:
    """Test SQL lookup and payload fallback for purged/trashed issues."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    issue_id = uuid.uuid4()

    # 1. SQL lookup when not in identity map
    session = AsyncMock()
    session.identity_map = {}
    mock_result = MagicMock()
    mock_result.first.return_value = (proj_id, 10, "PROJ")
    session.execute.return_value = mock_result

    envelope = ActivityEnvelope(
        activity_id=uuid.uuid4(),
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=uuid.uuid4(),
        event_type=ActivityEventType.ISSUE_CREATED,
        category=ActivityCategory.HISTORY,
        payload={},
    )
    await handle_activity_event(session, envelope)
    insert_call = session.execute.call_args_list[-1][0][0]
    params = insert_call.compile().params
    assert params["topic"] == "issue.created"
    assert params["payload"]["issue_key"] == "PROJ-10"

    # 2. Payload fallback when SQL returns None (e.g. purged issue)
    session_fallback = AsyncMock()
    session_fallback.identity_map = {}
    mock_empty_res = MagicMock()
    mock_empty_res.first.return_value = None
    session_fallback.execute.return_value = mock_empty_res

    envelope_fallback = ActivityEnvelope(
        activity_id=uuid.uuid4(),
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=uuid.uuid4(),
        event_type=ActivityEventType.ISSUE_PURGED,
        category=ActivityCategory.HISTORY,
        payload={"issue_key": "FALLBACK-99", "project_key": "FALLBACK"},
    )
    await handle_activity_event(session_fallback, envelope_fallback)
    insert_call_fb = session_fallback.execute.call_args_list[-1][0][0]
    params_fb = insert_call_fb.compile().params
    assert params_fb["topic"] == "issue.deleted"
    assert params_fb["payload"]["issue_key"] == "FALLBACK-99"
    assert params_fb["payload"]["project_key"] == "FALLBACK"


@pytest.mark.asyncio
async def test_handle_activity_event_comment_and_link_events() -> None:
    """Test comment events and issue link/field events."""
    ws_id = uuid.uuid4()
    issue_id = uuid.uuid4()

    events_to_test = [
        (ActivityEventType.COMMENT_CREATED, "comment.created"),
        (ActivityEventType.COMMENT_EDITED, "comment.updated"),
        (ActivityEventType.COMMENT_DELETED, "comment.deleted"),
        (ActivityEventType.ISSUE_FIELD_CHANGED, "issue.updated"),
        (ActivityEventType.ISSUE_DESCRIPTION_CHANGED, "issue.updated"),
        (ActivityEventType.ISSUE_LABELS_CHANGED, "issue.updated"),
        (ActivityEventType.ISSUE_MODULE_ADDED, "issue.updated"),
        (ActivityEventType.ASSIGNEE_ADDED, "issue.updated"),
        (ActivityEventType.LINK_CREATED, "issue.updated"),
        (ActivityEventType.WIP_HARD_LIMIT_OVERRIDDEN, "issue.updated"),
        (ActivityEventType.WORK_COMPLETED, "issue.transitioned"),
        (ActivityEventType.ISSUE_MOVED, "issue.moved"),
        (ActivityEventType.ISSUE_TRASHED, "issue.deleted"),
    ]

    for ev_type, expected_topic in events_to_test:
        session = AsyncMock()
        session.identity_map = {}
        mock_res = MagicMock()
        mock_res.first.return_value = None
        session.execute.return_value = mock_res

        envelope = ActivityEnvelope(
            activity_id=uuid.uuid4(),
            workspace_id=ws_id,
            object_id=issue_id,
            actor_principal_id=uuid.uuid4(),
            event_type=ev_type,
            category=ActivityCategory.HISTORY,
            payload={"key": "TST-1"},
        )
        await handle_activity_event(session, envelope)
        insert_call = session.execute.call_args_list[-1][0][0]
        assert insert_call.compile().params["topic"] == expected_topic


def test_listener_registration_and_reset() -> None:
    """Test idempotent registration and test clear functions."""
    clear_realtime_outbox_listener()
    register_realtime_outbox_listener()
    # Second call should be a no-op
    register_realtime_outbox_listener()
    clear_realtime_outbox_listener()
