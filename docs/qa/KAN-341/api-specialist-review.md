# API and Security Specialist Review: KAN-341

- **Ticket:** KAN-341 ([KB-REDTEAM-10]) - Enforce Strict Upper Bounds and Timeout Clamping on Monte Carlo Simulation Parameters in Flow Telemetry
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-23
- **Branch:** `feat/KAN-337-341`
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan337-341-814e49d3`
- **Status:** APPROVED

---

## 1. Executive Security Evaluation

Ticket KAN-341 remediates red-team vulnerability GSF-035 (and KAN-79) by eliminating CPU exhaustion DoS risks in project flow telemetry:
1. **Strict Parameter Bounds:** In `kanban/services/flow_metrics.py`, defined strict limits:
   - `MIN_TRIALS = 10`, `MAX_TRIALS = 50000`
   - `MIN_HORIZON_DAYS = 1`, `MAX_HORIZON_DAYS = 366`
   - `MIN_TARGET_ITEMS = 1`, `MAX_TARGET_ITEMS = 10000`
2. **Service & API Layer Rejection:** `compute_project_flow_metrics` rejects out-of-bounds parameters with `ProblemException(status=422, code="INVALID_PARAMETER")`. In `kanban/api/v1/flow_metrics.py`, `trials` query parameter enforces `Annotated[int, Query(ge=10, le=50000)] = 10000`.
3. **Execution Timeout Clamping:** `_simulate_monte_carlo` accepts `timeout_seconds: float = 2.0`. A periodic monotonic timer check (every 256 iterations) clamps execution if the time budget expires, returning safe fallback percentiles (`_MAX_FORECAST_DAYS = 365`) and logging a warning.

---

## 2. API Contract & Coverage Metrics

- **Unit Test Suite:** `kanban/tests/security/test_flow_metrics_dos_bounds.py`
  - `test_case_1_simulate_monte_carlo_strict_bounds_validation`: PASSED
  - `test_case_2_timeout_clamping_prevents_cpu_exhaustion`: PASSED
  - `test_case_3_service_level_trials_bounds_validation`: PASSED
- **Existing Regression Suite:** `kanban/tests/services/test_flow_metrics.py` (6 passed) and `kanban/tests/api/test_flow_metrics_api.py` (3 passed) remain 100% green.
- **Coverage:** `>=95%` unit test coverage on parameter validation and timeout clamping logic.
- **Dashes & Linter Invariants:** Zero em-dashes and zero en-dashes; `make check` passes with 0 errors.

**Recommendation:** APPROVED for merge.
