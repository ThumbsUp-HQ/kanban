# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: SLF001, E501
"""Security tests for RunnerHub frame ownership and anti-forgery guards (KAN-339).

Verifies:
  1. Positive: Assigned runner submits tool events and job results matching assigned job_id.
  2. Forgery Block: Unassigned runner attempting to submit job.result for another runner's job
     raises CrossRunnerJobForgeryError and leaves the pending future uncompleted.
  3. Forgery Block: Unassigned runner attempting to submit job.tool_event raises
     CrossRunnerJobForgeryError and event is discarded.
  4. Non-Existent Job: Runner submitting results for unassigned job raises CrossRunnerJobForgeryError.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import Any

import pytest

from kanban.runners.hub import (
    ConnectedRunner,
    CrossRunnerJobForgeryError,
    RunnerWssHub,
)


class _MockWebSocket:
    """Mock WebSocket for RunnerWssHub registration."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        pass


@pytest.fixture
def hub_with_two_runners() -> tuple[RunnerWssHub, ConnectedRunner, ConnectedRunner]:
    """Fixture providing RunnerWssHub with two connected runners in the same workspace and pool."""
    hub = RunnerWssHub()
    ws_id = uuid.uuid4()

    r1_id = uuid.uuid4()
    ws1 = _MockWebSocket()
    runner_1 = hub.register_runner(
        runner_id=r1_id,
        workspace_id=ws_id,
        pool_slug="test-pool",
        hostname="runner-1.internal",
        websocket=ws1,  # type: ignore[arg-type]
        max_concurrency=4,
    )

    r2_id = uuid.uuid4()
    ws2 = _MockWebSocket()
    runner_2 = hub.register_runner(
        runner_id=r2_id,
        workspace_id=ws_id,
        pool_slug="test-pool",
        hostname="runner-2.internal",
        websocket=ws2,  # type: ignore[arg-type]
        max_concurrency=4,
    )

    return hub, runner_1, runner_2


@pytest.mark.asyncio
async def test_case_1_positive_job_dispatch_and_result(
    hub_with_two_runners: tuple[RunnerWssHub, ConnectedRunner, ConnectedRunner],
) -> None:
    """Case 1: Legitimate execution where assigned runner sends tool event and result."""
    hub, runner_1, _ = hub_with_two_runners
    job_id = "job-valid-101"

    # Assign job to runner_1
    runner_1.active_jobs.add(job_id)
    hub._job_to_runner[job_id] = runner_1.runner_id
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    hub._pending_jobs[job_id] = fut

    # Runner 1 sends tool event
    hub.handle_frame(
        runner_id=runner_1.runner_id,
        frame={
            "type": "job.tool_event",
            "job_id": job_id,
            "tool_name": "pytest",
            "duration_ms": 50,
            "status": "passed",
        },
    )
    assert len(hub._tool_events) == 1
    assert hub._tool_events[0]["job_id"] == job_id

    # Runner 1 sends result
    b64_out = base64.b64encode(b"success").decode("ascii")
    hub.handle_frame(
        runner_id=runner_1.runner_id,
        frame={
            "type": "job.result",
            "job_id": job_id,
            "exit_code": 0,
            "stdout_b64": b64_out,
        },
    )
    assert fut.done()
    res = fut.result()
    assert res["exit_code"] == 0
    assert res["stdout_b64"] == b64_out


def test_case_2_cross_runner_result_forgery_blocked(
    hub_with_two_runners: tuple[RunnerWssHub, ConnectedRunner, ConnectedRunner],
) -> None:
    """Case 2: Runner 2 attempting to submit job.result for Runner 1's job is blocked."""
    hub, runner_1, runner_2 = hub_with_two_runners
    job_id = "job-target-202"

    # Assign job to runner_1
    runner_1.active_jobs.add(job_id)
    hub._job_to_runner[job_id] = runner_1.runner_id
    loop = asyncio.new_event_loop()
    fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    hub._pending_jobs[job_id] = fut

    # Runner 2 attempts to send forged result for Runner 1's job
    with pytest.raises(CrossRunnerJobForgeryError) as exc_info:
        hub.handle_frame(
            runner_id=runner_2.runner_id,
            frame={
                "type": "job.result",
                "job_id": job_id,
                "exit_code": 0,
                "stdout_b64": base64.b64encode(b"forged").decode("ascii"),
            },
        )
    assert exc_info.value.code == "CROSS_RUNNER_FORGERY_DETECTED"
    assert not fut.done(), "Target job future must remain uncompleted after forgery attempt"


def test_case_3_cross_runner_tool_event_forgery_blocked(
    hub_with_two_runners: tuple[RunnerWssHub, ConnectedRunner, ConnectedRunner],
) -> None:
    """Case 3: Runner 2 attempting to submit job.tool_event for Runner 1's job is blocked."""
    hub, runner_1, runner_2 = hub_with_two_runners
    job_id = "job-target-303"

    runner_1.active_jobs.add(job_id)
    hub._job_to_runner[job_id] = runner_1.runner_id

    # Runner 2 attempts to send tool event for Runner 1's job
    with pytest.raises(CrossRunnerJobForgeryError) as exc_info:
        hub.handle_frame(
            runner_id=runner_2.runner_id,
            frame={
                "type": "job.tool_event",
                "job_id": job_id,
                "tool_name": "malicious_injection",
                "duration_ms": 10,
                "status": "forged",
            },
        )
    assert exc_info.value.code == "CROSS_RUNNER_FORGERY_DETECTED"
    assert len(hub._tool_events) == 0, "Forged tool events must not be recorded"


def test_case_4_unknown_job_id_forgery_blocked(
    hub_with_two_runners: tuple[RunnerWssHub, ConnectedRunner, ConnectedRunner],
) -> None:
    """Case 4: Submitting result for unassigned or non-existent job ID is blocked."""
    hub, runner_1, _ = hub_with_two_runners

    with pytest.raises(CrossRunnerJobForgeryError) as exc_info:
        hub.handle_frame(
            runner_id=runner_1.runner_id,
            frame={
                "type": "job.result",
                "job_id": "job-nonexistent-999",
                "exit_code": 0,
                "stdout_b64": "",
            },
        )
    assert exc_info.value.code == "CROSS_RUNNER_FORGERY_DETECTED"
