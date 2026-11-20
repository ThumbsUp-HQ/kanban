# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for project config service (get_state_audit_impact lifecycle protections)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database.models import WorkflowState
from kanban.services.project_config import get_state_audit_impact


def _create_mock_session(state: WorkflowState, group_count: int) -> AsyncMock:
    """Build a mock database session returning preconfigured counts and queries."""
    session = AsyncMock()

    async def execute_impl(statement: object, *args: object, **kwargs: object) -> MagicMock:
        del args, kwargs
        res = MagicMock()
        stmt_str = str(statement).lower()
        if "from workflow_states" in stmt_str and (
            "workflow_states.id ==" in stmt_str or "workflow_states.id =" in stmt_str
        ):
            res.scalar_one_or_none.return_value = state
        elif "from workflow_states" in stmt_str and "count" in stmt_str:
            res.scalar_one.return_value = group_count
        elif "from workflow_transition_executions" in stmt_str:
            res.scalar_one.return_value = 0
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    session.execute.side_effect = execute_impl
    return session


@pytest.mark.asyncio
async def test_get_state_audit_impact_flags_last_started_state() -> None:
    """Verify get_state_audit_impact flags the last state in started group with blocking reason."""
    caller = MagicMock()
    project_id = uuid.uuid4()
    state_id = uuid.uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.identifier = "KAN"

    mock_state = MagicMock(spec=WorkflowState)
    mock_state.id = state_id
    mock_state.project_id = project_id
    mock_state.name = "In Progress"
    mock_state.state_group = "started"
    mock_state.is_default = False

    session = _create_mock_session(mock_state, group_count=1)

    with (
        patch(
            "kanban.services.project_config.get_project_or_404",
            AsyncMock(return_value=mock_project),
        ),
        patch("kanban.services.project_config.require_capability", AsyncMock()),
        patch("kanban.services.project_config.list_states", AsyncMock(return_value=[])),
    ):
        result = await get_state_audit_impact(session, caller, "KAN", state_id)

    assert "Last State in Group: Cannot delete the last state in group." in result.blocking_reasons


@pytest.mark.asyncio
async def test_get_state_audit_impact_does_not_flag_started_when_multiple_states() -> None:
    """Verify get_state_audit_impact does NOT flag started when multiple states exist."""
    caller = MagicMock()
    project_id = uuid.uuid4()
    state_id = uuid.uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.identifier = "KAN"

    mock_state = MagicMock(spec=WorkflowState)
    mock_state.id = state_id
    mock_state.project_id = project_id
    mock_state.name = "In Progress"
    mock_state.state_group = "started"
    mock_state.is_default = False

    session = _create_mock_session(mock_state, group_count=2)

    with (
        patch(
            "kanban.services.project_config.get_project_or_404",
            AsyncMock(return_value=mock_project),
        ),
        patch("kanban.services.project_config.require_capability", AsyncMock()),
        patch("kanban.services.project_config.list_states", AsyncMock(return_value=[])),
    ):
        result = await get_state_audit_impact(session, caller, "KAN", state_id)

    assert (
        "Last State in Group: Cannot delete the last state in group." not in result.blocking_reasons
    )


@pytest.mark.asyncio
async def test_get_state_audit_impact_does_not_flag_unstarted_state() -> None:
    """Verify get_state_audit_impact does NOT flag unstarted state as last state in group."""
    caller = MagicMock()
    project_id = uuid.uuid4()
    state_id = uuid.uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.identifier = "KAN"

    mock_state = MagicMock(spec=WorkflowState)
    mock_state.id = state_id
    mock_state.project_id = project_id
    mock_state.name = "Todo"
    mock_state.state_group = "unstarted"
    mock_state.is_default = False

    session = _create_mock_session(mock_state, group_count=1)

    with (
        patch(
            "kanban.services.project_config.get_project_or_404",
            AsyncMock(return_value=mock_project),
        ),
        patch("kanban.services.project_config.require_capability", AsyncMock()),
        patch("kanban.services.project_config.list_states", AsyncMock(return_value=[])),
    ):
        result = await get_state_audit_impact(session, caller, "KAN", state_id)

    assert (
        "Last State in Group: Cannot delete the last state in group." not in result.blocking_reasons
    )
