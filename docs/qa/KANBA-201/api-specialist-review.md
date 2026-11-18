# API Specialist Review: KANBA-201

**Ticket:** KANBA-201 ([KB-CAL-CYCLES])
**Auditor:** API Specialist
**Date:** 2026-11-18
**Verdict:** APPROVED (PASS)

---

## 1. Scope of API & Security Changes
1. **CSRF & Credential Protection on Schedule Mutations:**
   - Modified `patchIssueSchedule()` in `kanban/web/src/features/timeline/scheduleMutation.ts`.
   - All `PATCH /api/v1/issues/{issue_ref}` calls now attach:
     - `credentials: 'same-origin'` (securing cookie handling across same-origin requests)
     - `X-CSRF-Token` header retrieved via `ensureCsrfToken()` from `api/client.ts`.
   - Verified pre-mutation date capture (`originalStartDate`, `originalDueDate`) preventing rollback data loss on server failure.
   - Dispatches `window.dispatchEvent(new CustomEvent('kb:issue-updated', ...))` on successful updates to keep parallel layouts synchronized.

2. **Backend Capability Precision & RBAC:**
   - Updated `kanban/security/permissions.py`:
     - Populated `ProblemException.detail` with descriptive missing capability text and explicit role requirements hint (e.g. `"Missing required capability: EDIT (requires Project Member, Project Admin, Workspace Admin, or Server Admin role)."`).
   - Aligned `kanban/services/cycles.py` & `kanban/services/modules.py`:
     - Changed create and update operations to require `Capability.EDIT` instead of `Capability.ADMIN`, allowing standard Project Members to create and manage cycles/modules.
     - Preserved strict `Capability.ADMIN` requirement for cycle/module deletions.

---

## 2. API Contract & Regression Testing
1. **Automated Unit & Integration Coverage:**
   - `kanban/tests/api/test_cycles.py`: 9/9 tests pass (verifying member create/patch with `EDIT` capability and admin-only deletion with `ADMIN` capability).
   - `kanban/tests/api/test_modules.py`: 6/6 tests pass (verifying member creation, boundary validation, and role hint details).
   - `kanban/web/src/features/timeline/scheduleMutation.test.tsx`: 7/7 tests pass (verifying CSRF header attachment, same-origin credentials, optimistic updates, and rollback).
   - `kanban/web/src/features/timeline/TimelineView.test.tsx`: 19/19 tests pass (verifying milestone dragging, range calculations, keyboard adjustments, and error banner display).
   - `kanban/web/src/features/calendar/CalendarView.test.tsx`: 16/16 tests pass (verifying 2-week navigation, drag-and-drop reschedule, keyboard range shifts, and error banners).
   - `kanban/web/src/app/routes.test.tsx`: 19/19 tests pass (verifying cycle and module creation forms, capability gating, and error banner handling).

2. **Schema & Contract Parity:**
   - All request/response contracts conform to OpenAPI specifications with zero type errors in `mypy --strict kanban` and `tsc -b --noEmit`.

**Review Status:** Approved without reservations.
