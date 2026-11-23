# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Native statistical flow telemetry endpoints (KAN-79, KB-FLOW-METRICS-01).

Mounts:
    GET /api/v1/projects/{project_ref}/analytics/flow
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.flow_metrics import ProjectFlowMetricsResponse
from kanban.security.permissions import Capability, require_capability
from kanban.services.flow_metrics import compute_project_flow_metrics
from kanban.services.projects import get_project_or_404

router = APIRouter(tags=["analytics"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/projects/{project_ref}/analytics/flow",
    response_model=ProjectFlowMetricsResponse,
    summary="Compute project flow telemetry metrics",
    description=(
        "Compute native statistical flow telemetry metrics including Cumulative "
        "Flow Diagram (CFD), Cycle Time / Lead Time scatterplot with p50/p85/p95 "
        "percentiles, Aging WIP active items with column thresholds, and "
        "10,000-trial Monte Carlo throughput forecasting."
    ),
)
async def get_project_flow_metrics(  # noqa: PLR0913, PLR0917
    project_ref: str,
    caller: Caller,
    session: Session,
    window_days: Annotated[
        int,
        Query(
            ge=1,
            le=366,
            description="Analysis window in calendar days (1 to 366)",
        ),
    ] = 90,
    horizon_days: Annotated[
        int,
        Query(
            ge=1,
            le=366,
            description="Forecasting horizon for 'How Many?' Monte Carlo in days (1 to 366)",
        ),
    ] = 14,
    target_items: Annotated[
        int,
        Query(
            ge=1,
            le=10000,
            description="Remaining items count for 'When?' Monte Carlo simulation (1 to 10000)",
        ),
    ] = 20,
    trials: Annotated[
        int,
        Query(
            ge=10,
            le=50000,
            description="Monte Carlo simulation trials (10 to 50000)",
        ),
    ] = 10000,
    seed: Annotated[
        int | None,
        Query(
            description="Optional random seed for deterministic simulation and reproducibility",
        ),
    ] = None,
) -> ProjectFlowMetricsResponse:
    """Retrieve statistical flow metrics and probabilistic forecasts for a project."""
    async with timing_floor(floor_ms=25.0):
        project = await get_project_or_404(session, caller, project_ref)
        await require_capability(session, caller, project.id, Capability.VIEW)

        return await compute_project_flow_metrics(
            session=session,
            project_id=project.id,
            window_days=window_days,
            horizon_days=horizon_days,
            target_items=target_items,
            seed=seed,
            trials=trials,
        )
