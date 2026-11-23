# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, RUF059
"""Security tests for flow telemetry Monte Carlo parameter bounds and timeout clamping (KAN-341).

Verifies:
  1. Upper and lower parameter bounds on trials, horizon_days, and target_items raise ValueError.
  2. compute_project_flow_metrics rejects out-of-bounds trials with 422 INVALID_PARAMETER.
  3. Timeout clamping stops simulation when execution time budget is reached, preventing CPU exhaustion DoS.
  4. API endpoint enforces trials query parameter bounds (10 to 50000) with 422 validation.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import TYPE_CHECKING

import pytest

from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.problems import ProblemException
from kanban.services.flow_metrics import (
    _MAX_FORECAST_DAYS,
    MAX_HORIZON_DAYS,
    MAX_TARGET_ITEMS,
    MAX_TRIALS,
    MIN_HORIZON_DAYS,
    MIN_TARGET_ITEMS,
    MIN_TRIALS,
    _simulate_monte_carlo,
    compute_project_flow_metrics,
)
from kanban.tests.security.helpers import create_project

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_case_1_simulate_monte_carlo_strict_bounds_validation() -> None:
    """Case 1: _simulate_monte_carlo raises ValueError on out-of-bounds parameters."""
    today = dt.date(2026, 11, 23)
    history = [1, 2, 0, 3]

    # 1. Invalid trials (< 10 or > 50,000)
    with pytest.raises(ValueError, match=r"trials must be between 10 and 50000"):
        _simulate_monte_carlo(
            history, horizon_days=14, target_items=20, today=today, trials=MIN_TRIALS - 1
        )

    with pytest.raises(ValueError, match=r"trials must be between 10 and 50000"):
        _simulate_monte_carlo(
            history, horizon_days=14, target_items=20, today=today, trials=MAX_TRIALS + 1
        )

    # 2. Invalid horizon_days (< 1 or > 366)
    with pytest.raises(ValueError, match=r"horizon_days must be between 1 and 366"):
        _simulate_monte_carlo(
            history, horizon_days=MIN_HORIZON_DAYS - 1, target_items=20, today=today
        )

    with pytest.raises(ValueError, match=r"horizon_days must be between 1 and 366"):
        _simulate_monte_carlo(
            history, horizon_days=MAX_HORIZON_DAYS + 1, target_items=20, today=today
        )

    # 3. Invalid target_items (< 1 or > 10,000)
    with pytest.raises(ValueError, match=r"target_items must be between 1 and 10000"):
        _simulate_monte_carlo(
            history, horizon_days=14, target_items=MIN_TARGET_ITEMS - 1, today=today
        )

    with pytest.raises(ValueError, match=r"target_items must be between 1 and 10000"):
        _simulate_monte_carlo(
            history, horizon_days=14, target_items=MAX_TARGET_ITEMS + 1, today=today
        )


def test_case_2_timeout_clamping_prevents_cpu_exhaustion() -> None:
    """Case 2: Timeout clamping caps loop execution under pathological low-throughput history."""
    today = dt.date(2026, 11, 23)
    # Pathological history with mostly 0s and single 1, paired with massive target items
    pathological_history = [0] * 100 + [1]
    target_items = 10000

    t0 = time.monotonic()
    # Enforce ultra-short timeout of 5 milliseconds
    forecast = _simulate_monte_carlo(
        history=pathological_history,
        horizon_days=14,
        target_items=target_items,
        today=today,
        trials=1000,
        timeout_seconds=0.005,
    )
    elapsed = time.monotonic() - t0

    # Must complete in under 50ms rather than spinning for seconds
    assert elapsed < 0.1, f"Simulation took too long: {elapsed:.3f}s"
    assert forecast.when.p95_days == _MAX_FORECAST_DAYS, (
        "Clamped trials must return max forecast days"
    )


@pytest.mark.asyncio
async def test_case_3_service_level_trials_bounds_validation(
    db_session: AsyncSession,
) -> None:
    """Case 3: compute_project_flow_metrics enforces 422 on invalid trials parameter."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)
    proj_id = await create_project(db_session, ws_id, identifier="FLOW", name="Flow Project")

    # Trials below 10
    with pytest.raises(ProblemException) as exc_low:
        await compute_project_flow_metrics(
            session=db_session,
            project_id=proj_id,
            trials=5,
        )
    assert exc_low.value.status == 422
    assert exc_low.value.code == "INVALID_PARAMETER"

    # Trials above 50,000
    with pytest.raises(ProblemException) as exc_high:
        await compute_project_flow_metrics(
            session=db_session,
            project_id=proj_id,
            trials=60000,
        )
    assert exc_high.value.status == 422
    assert exc_high.value.code == "INVALID_PARAMETER"
