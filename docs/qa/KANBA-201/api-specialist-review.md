# API Specialist Forensic QA Review: KANBA-201

## Metadata
- **Ticket ID:** KANBA-201
- **Title:** [KB-CAL-CYCLES] Calendar & Timeline 14-day scoping, CSRF-secured scheduling mutations, rollback error banners, and accessible Cycles/Modules form controls
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `4af8c16` (merged into `main`)
- **Review Date:** 2026-11-18
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 Backend Capability Precision & Descriptive RBAC (`kanban/security/permissions.py`)
- **Descriptive Error Detail:** Updated `require_capability` in `kanban/security/permissions.py`:
  - When a capability check fails, `ProblemException.detail` is populated with specific missing capabilities and explicit role hints.
  - For admin/delete/share operations (`Capability.ADMIN | Capability.DELETE | Capability.SHARE`): reports `"requires Project Admin, Workspace Admin, or Server Admin role"`.
  - For edit/comment/transition/link operations (`Capability.EDIT | Capability.COMMENT | Capability.TRANSITION | Capability.LINK`): reports `"requires Project Member, Project Admin, Workspace Admin, or Server Admin role"`.
  - Provides actionable diagnostics to API and MCP consumers without leaking sensitive tenant enumeration data.

### 1.2 Cycles & Modules Service RBAC Alignment (`kanban/services/cycles.py`, `kanban/services/modules.py`)
- **Project Member Creation & Management:**
  - Create and update routines (`create_cycle`, `update_cycle`, `create_module`, `update_module`) now verify `Capability.EDIT` rather than requiring `Capability.ADMIN`.
  - Allows standard Project Members to create sprints, cycles, and feature modules.
  - Strict deletion policy preserved: delete routines (`delete_cycle`, `delete_module`) remain strictly gated by `Capability.ADMIN`.

### 1.3 CSRF & Client Security on Scheduling Mutations (`kanban/web/src/features/timeline/scheduleMutation.ts`)
- **Same-Origin & CSRF Token Injection:**
  - `patchIssueSchedule()` retrieves the active CSRF token via `ensureCsrfToken()` from `api/client.ts` and attaches it via `X-CSRF-Token`.
  - Emits `credentials: 'same-origin'` to enforce safe cookie handling for same-origin mutation requests.
- **Rollback Invariant:**
  - `useRescheduleIssue` captures `originalStartDate` and `originalDueDate` before optimistic updates, guaranteeing accurate date rollback if the server rejects the patch.
  - Dispatches `kb:issue-updated` custom event on successful mutations to ensure synchronized state across parallel layouts.

---

## 2. Test Suite & Proof Verification

### 2.1 Backend Unit & Integration Tests
- Executed `kanban/tests/api/test_cycles.py` and `kanban/tests/api/test_modules.py`:
  - 15 passed in 8.68s, 0 failures, 0 regressions.
  - Verified:
    - Non-member 404/403 with descriptive role requirement hints.
    - Project member cycle and module creation/updates with `Capability.EDIT`.
    - Deletion operations fail with 403 for members and succeed strictly for admins with `Capability.ADMIN`.

### 2.2 Proof Artifacts Audit (`docs/qa/KANBA-201/`)
- `git-diff.patch`: Complete diff from `7c370b1`.
- `changed-files-manifest.txt`: 18 modified files cataloged with line counts.
- `unit-test-results.txt`: Confirms backend pytest and frontend vitest suites passed cleanly.
- `build-check.txt`: Clean static analysis (`ruff check .`, `mypy --strict kanban`, `pnpm run typecheck`, `pnpm run lint`, `pnpm run build`, `check_no_dashes`).
- `contract-sample.json`: Valid JSON contract sample documenting `patch_issue_schedule_request`, `patch_issue_schedule_response`, `missing_capability_403_response`, `create_cycle_request`, and `create_module_request`.
- `message-to-reality-checker.md`: Accurate narrative detailing architectural changes and DoD fulfillment.

---

## 3. Specialist Verdict

The implementation in commit `4af8c16` satisfies all backend architectural requirements, capability precision standards, CSRF scheduling security invariants, and cycle/module RBAC rules specified in KANBA-201.

**Verdict: APPROVED**
