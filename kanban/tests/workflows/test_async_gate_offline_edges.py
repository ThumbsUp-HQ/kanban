# Copyright 2026 Kanban Platform Contributors
"""KAN-538: offline edge-path tests for async_gate helpers and GateCoordinator guards."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kanban.api.problems import ProblemException
from kanban.workflows.async_gate import GateCoordinator, compute_harness_label


def _agent(**kw: Any) -> Any:  # noqa: ANN401
    base = {
        "harness_kind": "in_app_sdk",
        "provider_kind": None,
        "model_id": None,
        "cli_binary_allowlist_id": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_harness_label_variants() -> None:
    """Labels cover provider-only, sdk-only, and model forms."""
    assert compute_harness_label(_agent(provider_kind="ollama")) == "in_app_sdk (ollama)"
    assert compute_harness_label(_agent()) == "in_app_sdk"
    assert compute_harness_label(_agent(provider_kind="ollama", model_id="m")) == (
        "in_app_sdk (ollama/m)"
    )
    assert compute_harness_label(
        _agent(harness_kind="cli_pipe", cli_binary_allowlist_id="agy")
    ) == ("cli: agy -p")


@pytest.mark.asyncio
async def test_record_decision_execution_not_found() -> None:
    """Unknown execution raises EXECUTION_NOT_FOUND."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    sess = AsyncMock()
    sess.execute.return_value = res
    with pytest.raises(ProblemException) as ei:
        await GateCoordinator.record_decision(sess, uuid.uuid4(), uuid.uuid4(), MagicMock())
    assert ei.value.code == "EXECUTION_NOT_FOUND"


@pytest.mark.asyncio
async def test_record_failure_guards() -> None:
    """record_failure validates its identifiers and invocation lookup."""
    with pytest.raises(ValueError, match="session must be provided"):
        await GateCoordinator.record_failure(None)
    sess = AsyncMock()
    sess.get.return_value = None
    with pytest.raises(ProblemException) as ei:
        await GateCoordinator.record_failure(sess, invocation_id=uuid.uuid4())
    assert ei.value.code == "INVOCATION_NOT_FOUND"
    with pytest.raises(ValueError, match="execution_id and hook_id"):
        await GateCoordinator.record_failure(sess)


@pytest.mark.asyncio
async def test_instance_record_failure_requires_session_and_delegates() -> None:
    """Bound coordinator forwards to the classmethod; unbound instance method raises."""
    sess = AsyncMock()
    coord = GateCoordinator(sess)
    with pytest.raises(ValueError, match="execution_id and hook_id"):
        await coord.record_failure()
    unbound = GateCoordinator()
    with pytest.raises(ValueError, match="session is required"):
        await unbound._record_failure_instance()  # noqa: SLF001
