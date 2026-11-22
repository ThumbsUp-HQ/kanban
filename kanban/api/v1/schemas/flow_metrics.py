# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Pydantic v2 schemas for statistical flow telemetry metrics (KAN-79, KB-FLOW-METRICS-01)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

STATE_GROUPS: Final[tuple[str, ...]] = (
    "backlog",
    "unstarted",
    "started",
    "completed",
    "cancelled",
)


class CfdStateMeta(BaseModel):
    """Metadata for a project workflow state in the CFD."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    state_group: str
    color_hex: str
    sort_order: int


class CfdPoint(BaseModel):
    """Daily cumulative flow diagram metrics point."""

    model_config = ConfigDict(extra="forbid")

    date: str
    backlog: int = 0
    unstarted: int = 0
    started: int = 0
    completed: int = 0
    cancelled: int = 0
    total: int = 0
    counts_by_state: dict[str, int] = Field(default_factory=dict)


class CfdSeries(BaseModel):
    """CFD data series and metadata."""

    model_config = ConfigDict(extra="forbid")

    points: list[CfdPoint]
    states: list[CfdStateMeta]
    state_groups: list[str] = list(STATE_GROUPS)


class PercentileValues(BaseModel):
    """Percentile thresholds (p50, p85, p95)."""

    model_config = ConfigDict(extra="forbid")

    p50: float
    p85: float
    p95: float


class CycleLeadTimePoint(BaseModel):
    """Cycle time and lead time measurement point for a completed work item."""

    model_config = ConfigDict(extra="forbid")

    issue_id: uuid.UUID
    issue_key: str
    title: str
    completed_at: str
    cycle_time_days: float
    lead_time_days: float


class CycleLeadTimeMetrics(BaseModel):
    """Scatterplot data and percentiles for cycle time and lead time."""

    model_config = ConfigDict(extra="forbid")

    points: list[CycleLeadTimePoint]
    cycle_time_percentiles: PercentileValues
    lead_time_percentiles: PercentileValues
    total_completed_in_window: int


class AgingWipIssue(BaseModel):
    """Active WIP item and aging telemetry."""

    model_config = ConfigDict(extra="forbid")

    issue_id: uuid.UUID
    issue_key: str
    title: str
    state_id: uuid.UUID
    state_name: str
    state_color_hex: str
    age_in_current_state_hours: float
    total_wip_hours: float
    state_entered_at: str
    first_started_at: str


class ColumnAgingThresholds(BaseModel):
    """Historical duration percentiles for a workflow column."""

    model_config = ConfigDict(extra="forbid")

    state_id: uuid.UUID
    state_name: str
    p50_hours: float
    p85_hours: float
    p95_hours: float


class AgingWipMetrics(BaseModel):
    """Aging WIP active items and column threshold guides."""

    model_config = ConfigDict(extra="forbid")

    active_issues: list[AgingWipIssue]
    column_thresholds: dict[str, ColumnAgingThresholds]
    total_active_wip: int


class MonteCarloHowMany(BaseModel):
    """Monte Carlo throughput forecast for 'How Many items in horizon_days?'."""

    model_config = ConfigDict(extra="forbid")

    horizon_days: int
    p50: int
    p85: int
    p95: int
    distribution: dict[int, int]


class MonteCarloWhen(BaseModel):
    """Monte Carlo throughput forecast for 'When will target_items be done?'."""

    model_config = ConfigDict(extra="forbid")

    target_items: int
    p50_days: int | None
    p85_days: int | None
    p95_days: int | None
    p50_date: str | None
    p85_date: str | None
    p95_date: str | None
    distribution: dict[int, int]


class MonteCarloForecast(BaseModel):
    """10,000-trial Monte Carlo throughput forecast simulation results."""

    model_config = ConfigDict(extra="forbid")

    trials: int
    historical_daily_throughput: list[int]
    average_daily_throughput: float
    how_many: MonteCarloHowMany
    when: MonteCarloWhen


class ProjectFlowMetricsResponse(BaseModel):
    """Comprehensive flow telemetry studio response for a project."""

    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    project_key: str
    window_days: int
    cfd: CfdSeries
    cycle_lead_time: CycleLeadTimeMetrics
    aging_wip: AgingWipMetrics
    monte_carlo: MonteCarloForecast
