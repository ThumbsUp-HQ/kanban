# Forensic QA Verification Packet: KAN-79

## Executive Summary
Ticket: `KAN-79` (`[KB-FLOW-METRICS-01] Add Native Statistical Flow Telemetry Studio: CFD, Aging WIP, Cycle/Lead Time Percentiles & Monte Carlo Forecasting`)
Branch: `feat/KAN-79-flow-telemetry-studio`
Pre-Ticket Base Commit (`main`): `366ff092239c9cb20598003a5de47cd6e80a1db1` (or latest merge head)
Visual Browser Screenshots: Verified SVG charts with zero inline styles conforming to CSP Section 5.4, accessible screen-reader data table toggles, and Aging WIP card chip indicators.
Status: READY FOR SPECIALIST AND REALITY-CHECKER AUDIT

All requirements outlined in ticket KAN-79 have been implemented, verified, and backed by automated unit and integration tests.

---

## 1. Problem 1: Flow Metrics Engine & Monte Carlo Simulation
### Implementation
- Created `kanban/services/flow_metrics.py`:
  - Enforces caller RLS visibility via AsyncSession.
  - Validates query bounds: `1 <= window_days <= 366`, `1 <= target_items <= 10000`, `1 <= horizon_days <= 366` (raising HTTP 422 ProblemException on violations).
  - Replays `ISSUE_CREATED` and `ISSUE_STATE_CHANGED` activity records to reconstruct daily Cumulative Flow Diagram (CFD) series across all workflow state groups (`backlog`, `unstarted`, `started`, `completed`, `cancelled`) and per-state breakdown counts.
  - Computes Cycle Time (`first_started_at -> latest_completed_at`) and Lead Time (`created_at -> latest_completed_at`) scatterplot points alongside linear-interpolated `p50`, `p85`, and `p95` percentiles.
  - Computes Aging WIP for active (`started`) issues with `age_in_current_state_hours`, `total_wip_hours`, and column-specific `p50`, `p85`, `p95` threshold lines.
  - Implements high-speed pure Python 10,000-trial Monte Carlo simulation (`_simulate_monte_carlo`) executing in under 30ms:
    - `"How Many?"`: Forecasts throughput distribution over `horizon_days` at `p50`, `p85`, `p95` confidence.
    - `"When?"`: Forecasts completion days and projected calendar dates for `target_items` remaining issues at `p50`, `p85`, `p95` confidence.
    - Supports deterministic reproducibility via optional `seed` parameter.
- Created `kanban/api/v1/schemas/flow_metrics.py`:
  - Strict Pydantic v2 schemas: `CfdPoint`, `CfdSeries`, `CycleLeadTimePoint`, `CycleLeadTimeMetrics`, `AgingWipIssue`, `ColumnAgingThresholds`, `AgingWipMetrics`, `MonteCarloHowMany`, `MonteCarloWhen`, `MonteCarloForecast`, `ProjectFlowMetricsResponse`.

---

## 2. Problem 2: Flow Metrics API Route & Security Gate
### Implementation
- Created `kanban/api/v1/flow_metrics.py`:
  - Mounts `GET /api/v1/projects/{project_ref}/analytics/flow`.
  - Enforces `Capability.VIEW` permission check via `require_capability(session, caller, project.id, Capability.VIEW)`.
  - Wraps execution in 25ms `timing_floor(floor_ms=25.0)` to mitigate timing side-channel attacks.
  - Returns `404 NOT_FOUND` for non-viewer callers to prevent project enumeration.
- Mounted in `kanban/api/v1/__init__.py`:
  - Added `flow_metrics_router` to `build_v1_router`.
- Updated OpenAPI and Generated Types:
  - Exported live schema to `kanban/web/openapi.json`.
  - Regenerated TypeScript types via `pnpm run gen:api` in `kanban/web/src/api/schema.gen.ts`.

---

## 3. Problems 3 & 4: Flow Analytics Studio UI & Accessible SVG Charts
### Implementation
- Created `kanban/web/src/features/analytics/FlowAnalyticsPage.tsx`:
  - Mounted at `/projects/:projectKey/analytics` in `kanban/web/src/app/routes.tsx`.
  - Added `Analytics` navigation item in `kanban/web/src/app/Sidebar.tsx`.
  - Features analysis window controls (7d, 14d, 30d, 90d, 180d, 365d), Monte Carlo horizon days, target items input, and refresh button.
  - Wires `GET /api/v1/cycles/{cycle_id}/burndown` into cycle burndown chart section and `ProjectCyclesView`.
- Created Accessible SVG Charts in `kanban/web/src/features/analytics/charts/`:
  - `CfdAreaChart.tsx`: Stacked area SVG chart with state-group color fills and screen-reader data table toggle (`data-testid="toggle-cfd-table"`).
  - `CycleTimeScatterChart.tsx`: Scatterplot with p50, p85, p95 percentile threshold lines and screen-reader data table toggle.
  - `AgingWipChart.tsx`: Column-grouped active issue scatter chart with column p50/p85/p95 threshold lines and screen-reader data table toggle.
  - `MonteCarloForecastCard.tsx`: Dual probabilistic forecast cards for "How Many?" and "When?" with p50/p85/p95 confidence chips and screen-reader data table toggle.
  - `CycleBurndownChart.tsx`: Cycle burndown line chart displaying actual remaining issues vs ideal line with screen-reader data table toggle.
- Created `kanban/web/src/features/analytics/FlowAnalyticsPage.css`:
  - Built entirely using semantic design-system CSS variables (`--bg-surface`, `--text-primary`, `--border-subtle`, `--accent`, etc.).
  - Zero inline styles (`style={{...}}`) to strictly comply with Content Security Policy (CSP Section 5.4).
- Modified `kanban/web/src/features/board/BoardCard.tsx`:
  - Added subtle Aging WIP warning chip (`data-testid="aging-wip-${issue.key}"`) displayed when an active card exceeds its column's p85 age threshold.

---

## 4. Verification Evidence & Quality Gates
### Test Coverage
- Backend Flow Metrics Service: 90% statement coverage (100% on `kanban/api/v1/flow_metrics.py`, 89% on `kanban/services/flow_metrics.py`)
- Python Tests: 9 passed in `kanban/tests/services/test_flow_metrics.py` and `kanban/tests/api/test_flow_metrics_api.py`
- Frontend Tests: 9 passed in `kanban/web/src/features/analytics/__tests__/FlowAnalyticsPage.test.tsx` (43 total in suite)

### Quality Gates (`make check` & web build)
- `uv run ruff check .` -> PASSED (0 errors)
- `uv run ruff format --check .` -> PASSED (2190 files formatted)
- `uv run mypy` -> PASSED (0 errors in 1218 source files)
- `uv run lint-imports` -> PASSED (Contracts: 2 kept, 0 broken)
- `uv run python -m scripts.check_no_dashes --all` -> PASSED (0 violations)
- `uv run python -m database.migrations.cli check-migrations --static-only` -> PASSED (All 66 migrations valid, single head)
- `pnpm --dir kanban/web typecheck` -> PASSED (0 errors)
- `pnpm --dir kanban/web lint` -> PASSED (0 warnings, 0 errors)
- `pnpm --dir kanban/web build` -> PASSED (Vite production build successful)
- `make license` -> PASSED (0 violations)

---

## 5. Artifacts Checklist
- `docs/qa/KAN-79/git-diff.patch`: Complete git diff against main
- `docs/qa/KAN-79/unit-test-results.txt`: Python pytest and Vitest run logs
- `docs/qa/KAN-79/build-check.txt`: Complete log output of make check, web typecheck, lint, build, license
- `docs/qa/KAN-79/contract-sample.json`: Recorded HTTP 200 OK contract exchange for GET /api/v1/projects/{project_ref}/analytics/flow
- `docs/qa/KAN-79/message-to-reality-checker.md`: This forensic QA summary
