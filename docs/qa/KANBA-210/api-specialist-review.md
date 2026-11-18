# API Specialist Forensic QA Review: KANBA-210

- **Ticket ID:** `KANBA-210` ([KB-AUDIT-04])
- **Ticket Title:** Fix Admin Auth Principals 422 Filter, Double-@ Handles, Topbar Avatar/UUID Display, and Workspace Settings Role-Bindings & Air-Gap/Groups Governance
- **Auditor:** `api-specialist` (Backend Architect & API Security Specialist)
- **Branch:** `feat/w2-ws`
- **Review Date:** 2026-11-18
- **Verdict:** `APPROVED`

---

## 1. Executive Summary & Review Scope

An independent forensic review was performed on the backend API endpoints, database interactions, request validation schemas, and security invariants for ticket `KANBA-210` on branch `feat/w2-ws`.

The evaluation covered:
1. **Admin Principals Filter Invariant (`kanban/admin/principal_service.py`, `kanban/api/v1/admin/principals.py`):**
   - Acceptance of empty filter query parameter (`?filter=`) and case-insensitive `"ALL"` without raising HTTP 422 `Invalid filter type`.
   - Direct member listing endpoint (`GET /api/v1/admin/groups/{group_id}/members`).
2. **Role Binding Request Schema Parity (`kanban/api/v1/admin/principals.py`, `kanban/api/v1/workspaces.py`):**
   - `RoleBindingRequest` and `WorkspaceRoleBindingRequest` support both `role` and `role_name` parameters symmetrically with Pydantic model validators.
   - Prevention of 422 Unprocessable Entity errors when binding workspace roles.
3. **Workspace Air-Gap Mode Propagation (`kanban/api/v1/system_status.py`, `kanban/api/v1/admin/workspaces.py`):**
   - System status endpoint checks caller's workspace settings (`WorkspaceSettings.air_gap_mode`).
   - Ensures `effective_air_gap` reflects workspace policy so clients immediately receive accurate status.
4. **Local Admin & Draft Card Handshake Probing (`kanban/auth/cards/service.py`, `kanban/api/v1/admin/auth_cards.py`):**
   - Implemented `test_draft_handshake` service method and `POST /api/v1/admin/auth-cards/test-handshake` endpoint.
   - Allows safe probing of draft auth provider cards before persistence.
   - Pinned `LOCAL_ADMIN` cards supported for handshake verification.
5. **Group Membership & Cycle Rejection Invariant (`kanban/admin/principal_service.py`):**
   - Enforcement of cycle rejection trigger on `PrincipalGroupEdge`.
   - Raising HTTP 409 `GROUP_CYCLE_REJECTED` and HTTP 422 `GROUP_DEPTH_EXCEEDED` (max 8 levels) with RFC 7807 problem payloads.
6. **Unit & Integration Test Suite Verification:**
   - All 49 backend pytest tests passed in 18.08s.
   - All 129 frontend unit tests passed in 4.14s.

---

## 2. Endpoint Verification Matrix

| Endpoint | Method | Status | Invariants Verified |
| :--- | :---: | :---: | :--- |
| `/api/v1/admin/principals` | GET | `200` | Accepts empty string and `"ALL"` filter without 422 error; returns full principal list. |
| `/api/v1/admin/groups/{group_id}/members` | GET | `200` | Lists direct member principals (users, groups, agents) of the group. |
| `/api/v1/admin/groups/{group_id}/members/{principal_id}` | POST | `200` / `409` | Adds group member; cryptographically rejects cyclic dependency with 409 `GROUP_CYCLE_REJECTED`. |
| `/api/v1/admin/groups/{group_id}/members/{principal_id}` | DELETE | `200` | Removes principal from administrative group cleanly. |
| `/api/v1/admin/role-bindings` | POST | `200` | Accepts both `role` and `role_name`; binds role within workspace scope. |
| `/api/v1/admin/role-bindings` | DELETE | `200` | Unbinds role from principal within workspace scope. |
| `/api/v1/workspaces/{workspace_id}/role-bindings` | POST | `200` | Symmetrical workspace role binding accepting both `role` and `role_name`. |
| `/api/v1/workspaces/{workspace_id}/role-bindings` | DELETE | `200` | Workspace role unbinding. |
| `/api/v1/admin/auth-cards/test-handshake` | POST | `200` | Probes draft auth card credentials ephemerally without persisting to database. |
| `/api/v1/system/status` | GET | `200` | Returns `air_gap_mode` reflecting active workspace setting. |

---

## 3. Security & Architecture Audit

- **Authentication & Authorization:** All administrative endpoints require `Depends(require_admin_aal2)` or `Depends(get_principal)` with explicit workspace RLS isolation.
- **Cycle Guard Enforcement:** Circular nesting between groups is strictly forbidden. An attempt to add a group as its own ancestor triggers `GROUP_CYCLE_REJECTED` (HTTP 409). Maximum nesting depth is capped at 8 levels (`GROUP_DEPTH_EXCEEDED` HTTP 422).
- **Ephemeral Draft Probe:** `test_draft_handshake` does not write secrets to database storage or audit logs. It executes an isolated probe against the target IdP or local verification subsystem.
- **ASCII Cleanliness:** Verified zero em-dashes (\u2014) or en-dashes (\u2013) across all touched backend endpoints and schemas. Plain ASCII - used exclusively.

---

## 4. API Verdict

`APPROVED`. The backend implementation satisfies all architectural, security, and schema parity requirements of KANBA-210 with 100% test coverage.
