# API Specialist Review: KAN-430 (Fix Unbound RLS Session Crash in Async in_app_sdk Gate Runner & StructuredRequest 60s Timeout Cap)

**Ticket:** KAN-430 (`[BUG][AGENT-GATES]`)  
**Auditor:** `api-spec` (Backend Architect & API Tester)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan430-2812030e`  
**Target Branch:** `fix/KAN-430-agent-gate-rls-session-and-timeout`  
**Target Commit:** `bd65b7d7` (base: `1bbc9981`)  

---

## 1. Executive Summary & Verdict

This API & Security Specialist Review audits the backend architecture, session lifecycle management, Row-Level Security (RLS) context scoping, and Pydantic request protocol validations implemented for **KAN-430**.

### Core Problems Resolved:
1. **Unbound AsyncSession Crash in Agent Gate Workflows**:
   In long-lived agent gate runner operations (`GateWorkerRunner` and `InAppSdkHarness`), database sessions previously risked escaping their transaction bounds during lengthy inference calls. When `BudgetEnforcer.reserve()`, `settle()`, or `release()` was called without an active session, or after a parent transaction closed, the runner threw runtime exceptions (`ValueError: BudgetEnforcer requires an active AsyncSession...` or SQLAlchemy closed transaction errors).
   - **Resolution**: Implemented `BudgetEnforcer._scoped_session()`, which dynamically acquires short-lived, RLS-scoped sessions via `session_factory.session(rls_context)` when no outer session is passed. `GateWorkerRunner` and `InAppSdkHarness` now cleanly propagate `session_factory` and `rls_context` down to tool invocations, ensuring atomic transactions and deterministic isolation under `FORCE ROW LEVEL SECURITY`.
2. **Artificial 60-Second Timeout Constraint on StructuredRequest Protocol**:
   The `StructuredRequest.ttft_deadline_ms` field was hardcoded to `le=60000`, causing valid 5-minute timeout configurations (up to `300000` ms) configured for large local Ollama models (e.g. `nemotron-3-super:latest`) to fail with Pydantic `ValidationError`.
   - **Resolution**: Updated `agent/providers/base.py` to raise `ttft_deadline_ms` upper bound to `300000` ms across both `CompletionRequest` and `StructuredRequest`, maintaining strict positive lower bound `ge=1`.

**Verdict: APPROVED.** All architectural, security, and coverage invariants are fully satisfied.

---

## 2. Protocol & Architecture Audit Details

### 2.1 Budget Enforcer Scoped Session Lifecycle (`agent/budget.py`)
- **Session Factory & RLS Context Propagation**:
  - `BudgetEnforcer.__init__` accepts optional `session_factory` and `rls_context`.
  - Added `attach_session_factory(session_factory, rls_context)` to allow late binding when enforcers are instantiated prior to tenant resolution.
  - Implemented `_scoped_session(session, workspace_id)` async context manager:
    - Yields explicit `session` or bound `self._session` if provided.
    - If `session_factory` is present, resolves `rls_context` (defaulting safely to workspace admin context if unconfigured) and yields an isolated `async with session_cm(ctx) as sess:`.
    - Fails fast with `ValueError` if neither session nor factory is available.
- **Transactional Atomicity in Ledger Updates**:
  - Wrapped `reserve()`, `settle()`, and `release()` in `_scoped_session()`.
  - Nested transactions use explicit database savepoints (`async with sess.begin_nested():`) to guarantee ledger consistency without holding connections during network inference.

### 2.2 Gate Runner & InAppSdk Harness Decoupling (`agent/gates/runner.py`, `agent/harnesses/in_app_sdk.py`)
- `GateWorkerRunner._load_entities` supplies `session_factory=self.session_factory` and `rls_context=self.rls_context` to `BudgetEnforcer` and `InAppSdkHarness`.
- `InAppSdkHarness` attaches `session_factory` and `rls_context` to the budget enforcer and injects them into repo toolkits and tool executions.

### 2.3 Provider Base Protocol Bounds (`agent/providers/base.py`)
- `CompletionRequest.ttft_deadline_ms: int = Field(default=30000, ge=1, le=300000)`
- `StructuredRequest.ttft_deadline_ms: int = Field(default=30000, ge=1, le=300000)`
- Protocol models correctly reject invalid values (`0`, `-1`, `300001`) and accept valid boundaries (`1`, `60000`, `120000`, `300000`).

---

## 3. Verification & Test Metrics

### 3.1 Unit Test Execution
- Executed full test suite: `uv run pytest agent/tests/`
- **Result:** 606 passed in 53.47s (0 failures, 4 warnings)
- Recorded in `docs/qa/KAN-430/unit-test-results.txt`

### 3.2 Coverage Analysis (Touched Modules)
- `agent/budget.py`: **100%**
- `agent/gates/runner.py`: **95%**
- `agent/harnesses/in_app_sdk.py`: **99%**
- `agent/providers/base.py`: **99%**
- **Overall Module Coverage:** **98%** (exceeds mandatory `>=95%` standard)

### 3.3 Static Analysis & Hygiene
- **Ruff:** Clean (0 errors)
- **Mypy:** Clean across 136 source files (0 type errors)
- **Unicode Dash Check:** Passed with 0 em/en-dashes (`python3 scripts/check_no_dashes.py`)

---

## 4. Final Verdict

- **API & Protocol Conformance:** APPROVED
- **Security & RLS Isolation:** APPROVED
- **Coverage & Test Rigor:** APPROVED
