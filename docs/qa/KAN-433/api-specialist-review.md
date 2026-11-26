# API Specialist Review: KAN-433 (Persist system_instructions_md in Agent Definitions API and Stop Session Request Storm)

**Ticket:** KAN-433 (`[BUG][AGENTS] Persist system_instructions_md in Agent Definitions API and Stop Infinite /api/v1/auth/session Request Storm on /workspaces/settings/agents`)  
**Parent Project:** `👍kanban`  
**Auditor:** `backend-architect` (Backend Architect & API Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-26  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan433-943bd920`  
**Target Branch:** `fix/KAN-433-agent-instructions-and-session-storm`  
**Base Commit:** `7c5d632c`  

---

## 1. Executive Summary & Verdict

This API Specialist Review audits the backend API and HTTP client contract updates implemented for **KAN-433**.

Key Architectural & Protocol Invariants Audited:
1. **Explicit Commit Durability on Mutating Agent Definition Routes**:
   - `FastAPI 0.162.5` exits request handling and transmits HTTP response headers and body before exiting the dependency stack context manager (`get_rls_session`). In high-concurrency or immediate read-after-write flows, this causes client `GET` queries to race against uncommitted database transactions.
   - Explicit `await session.commit()` calls were added before return statements across all six mutating routes in `kanban/api/v1/agent_definitions.py`:
     - `create_agent_definition` (Workspace-scoped `POST`)
     - `patch_agent_definition` (Workspace-scoped `PATCH`)
     - `delete_agent_definition` (Workspace-scoped `DELETE`)
     - `admin_create_agent_definition` (Admin-scoped `POST /api/v1/admin/agent-definitions`)
     - `admin_patch_agent_definition` (Admin-scoped `PATCH /api/v1/admin/agent-definitions/{agent_id}`)
     - `admin_delete_agent_definition` (Admin-scoped `DELETE /api/v1/admin/agent-definitions/{agent_id}`)
   - Read-after-write consistency is now guaranteed before HTTP 200/201/204 responses are sent over the wire.
2. **Infinite Session Request Storm Suppression**:
   - `RequestIdMiddleware` emits `x-kb-aal2-expires-at` on every response when AAL2 is active, including responses to `GET /api/v1/auth/session`.
   - In `kanban/web/src/api/client.ts`, both initial and replayed fetch responses now explicitly check whether the resolved request URL is `/api/v1/auth/session`. If so, dispatching the `kb:aal2-expires-at` custom event is suppressed. This defense-in-depth measure eliminates self-triggering feedback loops where session polling triggers AAL2 extension events that trigger further session polling.

**Verdict: APPROVED.** All API contracts, commit durability guarantees, and request storm defenses function as designed.

---

## 2. Test Verification & Code Quality Metrics

- **Backend Pytest**: `kanban/tests/api/test_agent_definitions.py` passed (2/2 tests passed in 1.12s):
  - `test_create_agent_definition_persists_custom_system_instructions`: Verified custom `system_instructions_md` persists durably across workspace list, detail, and patch operations.
  - `test_admin_agent_definitions_commit_durability`: Verified `session.commit()` durability on admin routes under required AAL2 step-up session context.
- **Frontend API Tests**: `kanban/web/src/api/__tests__/websudoReplay.test.tsx` passed:
  - Verified that `/api/v1/auth/session` calls do not dispatch `kb:aal2-expires-at`.
  - Verified other authenticated endpoints continue to dispatch `kb:aal2-expires-at` normally.
- **Static Analysis & Types**:
  - Ruff: Clean (0 errors, 0 warnings).
  - Mypy: Clean (1373 source files checked, 0 type errors).

---

## 3. Security & Safety Invariants Sign-Off

- **AAL2 Step-Up Integrity:** APPROVED. Admin agent definitions endpoints continue to strictly enforce `Depends(require_admin_aal2)`.
- **Row-Level Security (RLS) Isolation:** APPROVED. Explicit session commits occur within active RLS tenancy boundaries.
- **Network Boundaries:** APPROVED. Pre-production instance `k.hackedyour.info` / `192.168.1.101` was not accessed or probed.
- **Zero Dash Invariant:** APPROVED. Verified zero Unicode em-dashes and en-dashes.
