# API and Security Specialist Review: KAN-79

- **Ticket:** KAN-79 ([KB-FLOW-METRICS-01]) - Add Native Statistical Flow Telemetry Studio: CFD, Aging WIP, Cycle/Lead Time Percentiles & Monte Carlo Forecasting
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `main` (merged from `feat/KAN-79-flow-telemetry-studio`)
- **Commit Under Audit (`HEAD`):** `7f9e74d706a147d9e9c7d217dc7a55d06382d492` (`7f9e74d7`)
- **Base Commit (`main`):** `c6d3d99b6b80a02a91199451423617a297e7c6f2` (`c6d3d99b`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan79-e66cdab7`
- **Status:** APPROVED

---

## 1. Executive API & Security Architecture Evaluation

Ticket KAN-79 delivers native statistical flow analytics and telemetry, integrating Cumulative Flow Diagrams (CFD), Cycle/Lead Time percentiles, Aging WIP tracking, and 10,000-trial Monte Carlo forecasting.

Key API, computational, and security elements audited:
1. **Statistical Flow Telemetry Service (`kanban/services/flow_metrics.py`):**
   - Strictly enforces caller Row-Level Security visibility via session boundaries.
   - Rigorously validates query input parameters: `1 <= window_days <= 366`, `1 <= horizon_days <= 366`, `1 <= target_items <= 10000`, rejecting out-of-range inputs with HTTP 422 ProblemException.
   - Reconstructs historical state progression by replaying `ISSUE_CREATED` and `ISSUE_STATE_CHANGED` activity ledger events into daily CFD series across state groups (`backlog`, `unstarted`, `started`, `completed`, `cancelled`) and per-state breakdowns.
   - Computes Cycle Time and Lead Time durations alongside linear-interpolated `p50`, `p85`, and `p95` percentiles.
   - Identifies active WIP items, computing current-state age and total WIP hours alongside column threshold lines.
   - Monte Carlo engine executes 10,000 trials in pure Python in under 30ms, providing deterministic simulations with optional `seed` parameters for both "How Many?" and "When?" forecasts.
2. **REST Endpoint & Security Invariants (`kanban/api/v1/flow_metrics.py`):**
   - Mounts `GET /api/v1/projects/{project_ref}/analytics/flow`.
   - Protects route with explicit capability check: `require_capability(session, caller, project.id, Capability.VIEW)`.
   - Wraps responses in 25ms execution timing floor (`timing_floor(floor_ms=25.0)`) to defend against side-channel timing attacks and principal enumeration.
   - Emits HTTP 404 for callers lacking project visibility, preventing project existence leakage.
3. **Frontend Integration & CSP Compliance:**
   - Accessible SVG charts built with zero inline styles (`style={{...}}`) complying with Content Security Policy (CSP Section 5.4).
   - Data table toggles on all chart components support accessibility and automated test verification.

---

## 2. Wire Contracts & Security Invariants

### A. HTTP Wire Contract & Schemas
- `GET /api/v1/projects/{project_ref}/analytics/flow` returns structured `ProjectFlowMetricsResponse` including `cfd`, `cycle_lead_time`, `aging_wip`, and `monte_carlo`.
- Input validation failures return standard RFC 7807 422 ProblemException responses.

### B. Tenancy & Anti-Enumeration
- Caller cannot access metrics for projects outside their authorized workspace and project scopes.
- All database queries filter issues through the caller's active RLS context.

---

## 3. Unit Test Coverage & Verification Metrics

- **Backend Pytest Results:** 9 passed in 3.80s (`kanban/tests/services/test_flow_metrics.py`, `kanban/tests/api/test_flow_metrics_api.py`).
- **Frontend Vitest Results:** 43 passed (including 9 in `FlowAnalyticsPage.test.tsx`).
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2190 files formatted.
  - `mypy`: 0 issues found in 1218 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.
  - `check-migrations`: Valid single head.
  - `check_no_dashes`: Clean across all repository files (0 violations).
  - `make license`: 0 license violations.
  - `pnpm typecheck`, `lint`, and `build`: Clean production build.

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
