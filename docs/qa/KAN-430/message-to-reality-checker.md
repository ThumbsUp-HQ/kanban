# Message to Reality-Checker: KAN-430

## Ticket Scope & Deliverable Summary
- **Ticket ID:** `KAN-430` (`[BUG][AGENT-GATES] Fix Unbound RLS Session Crash in Async in_app_sdk Gate Runner and StructuredRequest 60s Timeout Cap`)
- **Branch:** `fix/KAN-430-agent-gate-rls-session-and-timeout`
- **Commit:** `3eab80ea`
- **Base:** `1bbc9981`
- **Visual Proof:** `N/A - Non-UI Ticket` (Zero UI code modified; backend gate runner, budget settlement, and provider protocol fix. Dual UI specialist review confirmed 300000ms parity with Admin UI).

## Root Cause & Architecture Fix Summary
1. **Unbound RLS Session Decoupling in Gate Worker and Budget Enforcer:**
   - **Root Cause:** In `agent/gates/runner.py`, `GateWorkerRunner._load_entities` previously initialized `BudgetEnforcer(session=session)` and `InAppSdkHarness(..., session=session)` within an `async with self.session_factory.session(admin_ctx) as session:` block. That block exited upon entity loading, unbinding and closing the session. When `GateWorker.handle_dispatch()` subsequently executed `live_harness.run()`, any budget reservation, settlement, or release query crashed with: `HARNESS_ERROR: Executing query on unbound RLS session is forbidden.`
   - **Resolution:**
     - Updated `agent/budget.py`: `BudgetEnforcer` now supports `session_factory` and `rls_context` parameters alongside backward-compatible `session`. The new `@asynccontextmanager async def _scoped_session(self, session, workspace_id)` provides short-lived atomic RLS transactions via `session_factory.session(rls_context)` when no external session is passed. Each of `reserve()`, `settle()`, and `release()` executes within its own short-lived RLS transaction, preventing DB connection exhaustion during slow LLM inference.
     - Updated `agent/harnesses/in_app_sdk.py`: Accepts `session_factory` and `rls_context`, attaching them to `budget_enforcer` when unassigned.
     - Updated `agent/gates/runner.py`: Passes `session_factory=self.session_factory` and `rls_context=admin_ctx` to both `BudgetEnforcer` and `InAppSdkHarness`, completely decoupling the entities loading transaction from the later async execution.

2. **Timeout Upper Bound Raised to 300000ms:**
   - **Root Cause:** In `agent/providers/base.py`, `CompletionRequest.ttft_deadline_ms` and `StructuredRequest.ttft_deadline_ms` capped timeouts at `le=60000`. When self-hosted models (such as Ollama `nemotron-3-super:latest`) were configured in Admin settings with timeouts up to 5 minutes (`300000ms`), Pydantic rejected the requests with `Input should be less than or equal to 60000`.
   - **Resolution:**
     - In `agent/providers/base.py`: Raised upper bound on `ttft_deadline_ms` to `300000` (`ge=1, le=300000`) on both `CompletionRequest` and `StructuredRequest`.
     - In `agent/harnesses/in_app_sdk.py`: Updated `ttft_deadline_ms=cutoff_ms` so values up to 300000ms pass through without artificial clamping to 60000ms.

## Verification Evidence & Quality Metrics
1. **Pytest Integration & Unit Test Suite:**
   - **Execution Command:** `KB_TEST_DB_PREFIX=kanban_test_kan430 PYTHONPATH=. uv run --no-sync pytest agent/tests/ --cov=agent.gates.runner --cov=agent.harnesses.in_app_sdk --cov=agent.budget --cov=agent.providers.base --cov-report=term-missing`
   - **Pass Rate:** 606 of 606 passed in 53.47s (0 failures, 4 benign warnings).
   - **Coverage Metrics (All Touched Modules >=95%):**
     * `agent/budget.py`: 100% (120/120 statements, 36/36 branches)
     * `agent/gates/runner.py`: 95% (272 statements, 80 branches)
     * `agent/harnesses/in_app_sdk.py`: 99% (184 statements, 44 branches)
     * `agent/providers/base.py`: 99% (119 statements, 14 branches)
     * **Total across touched modules:** 98% coverage.
   - **Verbatim Results Log:** Saved to `docs/qa/KAN-430/unit-test-results.txt`.

2. **Real-PG + Ephemeral Ollama Server Integration Tests:**
   - Located in `agent/tests/gates/test_gate_runner_rls_session.py`:
     * Positive E2E: Real PostgreSQL tables + ephemeral Ollama server running `nemotron-3-super:latest` with `timeout_ms=120000`. `BudgetEnforcer.reserve()` and `settle()` execute in independent RLS transactions. 0 unbound RLS session errors. Gate approval recorded.
     * Negative E2E: Incomplete ticket generates a reject decision without leaking token reservations.
     * Negative Rollback: Upstream 500 failure triggers `BudgetEnforcer.release()`, restoring `tokens_reserved` to 0 with 0 token leakage.
     * Boundary Validations: Deadlines of 120000ms and 300000ms validate cleanly; 300001ms and 0ms raise `ValidationError`.

3. **Static Analysis & Build Hygiene:**
   - Ruff: 0 errors (`All checks passed!`).
   - Mypy: 0 errors (`Success: no issues found in 136 source files`).
   - Character Hygiene: `python3 scripts/check_no_dashes.py --all` passed with 0 violations.
   - **Verbatim Build Log:** Saved to `docs/qa/KAN-430/build-check.txt`.

4. **Dual Specialist Reviews:**
   - API Specialist Review: `APPROVED` (`docs/qa/KAN-430/api-specialist-review.md`).
   - UI Specialist Review: `APPROVED - Non-UI Backend Gate Fix; verified 300000ms parity with Admin UI` (`docs/qa/KAN-430/ui-specialist-review.md`).

## Reality-Checker Verdict Request
All requirements for KAN-430 have been fulfilled with zero errors, >=95% unit test coverage across all touched modules, clean dual specialist sign-offs, and complete forensic proof. Requesting Grade-A READY certification.
