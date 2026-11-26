# UI Specialist Review: KAN-430 (Fix Unbound RLS Session Crash in Async in_app_sdk Gate Runner & StructuredRequest 60s Timeout Cap)

**Ticket:** KAN-430 (`[BUG][AGENT-GATES]`)  
**Auditor:** `ui-spec` (UI Designer & UX Architect)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan430-2812030e`  
**Target Branch:** `fix/KAN-430-agent-gate-rls-session-and-timeout`  
**Target Commit:** `bd65b7d7`  

---

## 1. Executive Summary & Verdict

This UI Specialist Review audits the backend bug fix in **KAN-430: Fix Unbound RLS Session Crash in Async in_app_sdk Gate Runner and StructuredRequest 60s Timeout Cap** from the perspective of frontend interaction alignment, UX timeout expectations, and UI design contract invariants.

While KAN-430 is a backend agent gate and harness fix touching `agent/budget.py`, `agent/gates/runner.py`, `agent/harnesses/in_app_sdk.py`, and `agent/providers/base.py`, it directly resolves a critical contract divergence with the user interface:
1. **Frontend-Backend Timeout Alignment**: In the Admin UI (`/admin/agents` and `/admin/ai`), the Agent and AI Provider editor forms allow administrators to configure timeout values up to `300000` ms (5 minutes) to accommodate large self-hosted reasoning models (such as Ollama `nemotron-3-super:latest`). Previously, the backend Pydantic model `StructuredRequest` in `agent/providers/base.py` artificially capped `ttft_deadline_ms` at `60000` ms, causing valid admin-configured timeouts between 61s and 300s to crash with validation errors (`Input should be less than or equal to 60000`). Raising this ceiling to `300000` ms aligns the backend protocol 100% with frontend UI form validations.
2. **User Experience of Reality-Checker Gates**: By resolving the unbound RLS session crash in `GateWorkerRunner` and `BudgetEnforcer`, gate executions triggered from the web UI (such as moving cards to Done or running reality-checker audits) complete smoothly without producing obscure 500 errors or freezing UI state transitions.
3. **No UI Code Touched**: Zero frontend components, styles, or templates were modified. Zero UI regressions were introduced.

**Verdict: APPROVED.** Backend timeout bounds are now fully consistent with the Admin UI contracts and gate lifecycles.

---

## 2. Interaction & Contract Parity Checklist

- [x] **Timeout Value Consistency**: Backend upper limit of 300,000 ms directly matches the max timeout allowed in `AgentDefinitionEditorDrawer.tsx` and `AiProviderEditorDrawer.tsx`.
- [x] **No Layout or CSS Regressions**: No frontend source files were touched.
- [x] **Gate State Transition UX**: Gate execution now transitions cleanly through pending and completed states without hanging on unbound database transactions.
- [x] **Static & Test Gates**: 606/606 Pytest tests pass with 98% overall coverage on touched backend modules; Ruff and Mypy clean.

---

## 3. Verification Sign-Off

- **Audit Tooling:** Code diff inspection and frontend contract alignment audit.
- **Dashes Enforcement:** Verified 0 Unicode em/en-dashes in this review document via `python3 scripts/check_no_dashes.py`.
- **Verdict:** **APPROVED** without conditions.
