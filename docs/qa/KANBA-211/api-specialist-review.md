# API Specialist Review: KANBA-211

**Ticket:** KANBA-211 ([KB-AUDIT-05] Fix Cycles and Modules End-to-End Persistence, Lifecycle Actions, Dates Display, and Light/Dark/Mobile Color Schemes)
**Reviewer:** API Specialist / Backend Architect
**Status:** APPROVED
**Date:** 2026-11-18

---

## 1. Schema & Contract Audits

- **Cycle & Module Summary Schemas:**
  - `IssueRead` in `kanban/api/v1/schemas/issues.py` and `IssueSummary` in `kanban/web/src/features/views/viewsApi.ts` now include typed `cycle?: CycleSummary | null` and `modules?: ModuleSummary[]`.
  - Backend services populate summary structures (`id`, `name`, `status`, `color_hex`) directly into responses, eliminating client N+1 roundtrips.

- **Human-Readable Date Validation:**
  - Client and backend validation for `start_date` vs `end_date` / `target_date` enforces clear user-facing messages:
    - `End date cannot be earlier than start date.`
    - `Target date cannot be earlier than start date.`
  - Raw internal field names (`end_date cannot be earlier than start_date`) are intercepted and converted to localized sentence copy before presentation.

- **Cycle Completion & Rollover:**
  - `POST /api/v1/projects/{project_id}/cycles/{cycle_id}/complete` accepts optional `rollover_cycle_id`.
  - Unfinished work items in the completed cycle are automatically migrated to the designated target cycle or unassigned (backlog) if omitted.

---

## 2. RBAC & Security Boundary Verification

- **Lifecycle Actions & Delete Restrictions:**
  - Delete endpoints (`DELETE /api/v1/projects/{project_id}/cycles/{cycle_id}` and `DELETE /api/v1/projects/{project_id}/modules/{module_id}`) enforce `PROJECT_ADMIN` or `WORKSPACE_ADMIN` authority.
  - In frontend `routes.tsx`, `canDelete` is strictly gated on `isProjectAdmin`:
    - `VIEWER` and `MEMBER` roles do NOT see the Delete button.
    - `PROJECT_ADMIN` and workspace administrators receive active Delete controls.

- **Project `modules_enabled` Toggle Enforcement:**
  - When `modules_enabled === false`, `Sidebar.tsx` hides the Modules navigation item.
  - Quick-create dialogs and `TableView.tsx` hide module selection pickers and columns when modules are disabled.

---

## 3. Cache Invalidation & Synchronous State Updates

- React Query client triggers synchronous query invalidations (`['project', projectKey, 'cycles']`, `['project', projectKey, 'modules']`, and `['project', projectKey, 'issues']`) upon mutation success.
- New cycles and modules appear instantly in UI lists without requiring manual browser reload (`F5`).
- Peek drawer and full screen issue detail views persist cycle and module assignments reliably across page reloads.

---

## 4. Specialist Recommendation

All API contracts, validation guards, RBAC permissions, and query cache lifecycles are hardened and verified. Approved with no reservations.
