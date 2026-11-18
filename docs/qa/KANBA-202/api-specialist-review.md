# QA API Specialist Review: KANBA-202

## Review Metadata
- **Ticket ID:** KANBA-202 ([KB-RBAC-SETTINGS] Enforce RBAC Across Administrative Surfaces, Views Removal, Project & Workspace Settings Studio)
- **Reviewer:** api-specialist (Independent API & Security Architecture Swarm Reviewer)
- **Review Date:** 2026-11-18
- **Target Surfaces:** Backend REST APIs (`/api/v1/auth/me`, `/api/v1/projects`, `/api/v1/projects/{ref}/members`, `/api/v1/workspaces/{id}`, `/api/v1/admin/workspace-settings`), schemas, and Principal Service
- **Status:** APPROVED

---

## 1. Executive Summary
This review independently audits the backend and API enhancements implemented under KANBA-202. The ticket enforces explicit role-based access control (RBAC), expands `/api/v1/auth/me` with principal capabilities and admin flags, extends `ProjectResponse` with caller admin status and project-scoped role, introduces complete member role binding endpoints for projects, restricts privilege escalation in `bind_role`, and adds workspace metadata updates with strict conflict checking.

All backend unit tests (`kanban/tests/auth/test_standard_user_rbac_matrix.py`) pass in 1.40s. Static checks (`ruff`, `mypy`, `check_no_dashes`) pass with zero errors, warnings, or unhandled exceptions.

---

## 2. API Contract & Architectural Audit

### 2.1 GET /api/v1/auth/me
- **Extended Contract:** Now returns `is_server_admin` (bool), `is_workspace_admin` (bool), `workspace_role` (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `WORKSPACE_MEMBER`, or `WORKSPACE_GUEST`), and `workspace_capabilities` (list of strings).
- **Security & Capability Precision:**
  - `SERVER_ADMIN` receives full administrative capabilities including `MANAGE_SERVER_ADMIN`, `ADMIN_AUTH_STUDIO`, `ADMIN_MCP_KEYS`, and `SYSTEM_STORAGE`.
  - `WORKSPACE_ADMIN` receives `CREATE_PROJECT`, `MANAGE_WORKSPACE_SETTINGS`, and `MANAGE_WORKSPACE_MCP_KEYS`. They are strictly excluded from server-level capabilities.
  - `WORKSPACE_MEMBER` receives `CREATE_PROJECT`.
  - `WORKSPACE_GUEST` receives an empty list of capabilities (`[]`).

### 2.2 Project Role Binding Endpoints (/api/v1/projects/{ref}/members)
- **Endpoints:**
  - `GET /api/v1/projects/{ref}/members`: Lists bindings (`id`, `principal_id`, `project_id`, `role`, `display_name`, `handle`, `email`, `created_at`). Requires `Capability.VIEW`.
  - `POST /api/v1/projects/{ref}/members`: Adds or updates a binding (`PROJECT_ADMIN`, `MEMBER`, `VIEWER`). Requires `Capability.ADMIN` on the project.
  - `DELETE /api/v1/projects/{ref}/members/{principal_id}`: Removes a member binding from the project. Requires `Capability.ADMIN` on the project.
- **Privilege Escalation Prevention:** Non-admin callers (such as `MEMBER` or `VIEWER`) attempting to add or delete project members are rejected with HTTP 403 `INSUFFICIENT_CAPABILITY`.

### 2.3 ProjectResponse Extension
- **Fields:** `is_project_admin` (bool) and `project_role` (`PROJECT_ADMIN`, `MEMBER`, `VIEWER`, or null).
- **Resolution:** Derived accurately from project-level `Capability.ADMIN` or explicit `role_bindings` row, allowing frontend clients to conditionally render administrative controls without redundant permission probes.

### 2.4 Server Admin Escalation Block in bind_role
- **Invariant:** Non-`SERVER_ADMIN` actors are prevented from granting the `SERVER_ADMIN` role in `kanban.admin.principal_service.bind_role`.
- **Validation:** Attempts by `WORKSPACE_ADMIN` or standard members to grant `SERVER_ADMIN` fail immediately with HTTP 403 `INSUFFICIENT_CAPABILITY`.

### 2.5 Workspace Name and Slug Updates
- **Endpoints:** `PATCH /api/v1/admin/workspace-settings` and `PATCH /api/v1/workspaces/{workspace_id}`.
- **Validation & Conflict Handling:**
  - Slugs are validated against `^[a-z0-9][a-z0-9-]{1,62}$`.
  - Slug collisions with existing workspaces return HTTP 409 `WORKSPACE_SLUG_CONFLICT`.
  - Non-administrators attempting updates return HTTP 403 `INSUFFICIENT_CAPABILITY`.

---

## 3. Hostile Input, Sanitization & Secret Handling
- **UUID & Slug Validation:** Strict regex and Pydantic models forbid extraneous attributes.
- **Timing & Enumeration Resistance:** Project lookups continue to operate behind `timing_floor(floor_ms=25.0)`.
- **Formatting Compliance:** Zero em-dashes and en-dashes across all files.

---

## 4. Verification Proof Summary
- **Backend Matrix Tests:** `kanban/tests/auth/test_standard_user_rbac_matrix.py` (5 passed in 1.40s).
- **Frontend Unit Tests:** 51 unit tests passed across settings and navigation suites in 3.04s.
- **Static Analysis:** Strict typing, ruff lint, and check_no_dashes pass cleanly.

---

## 5. Specialist Verdict
The RBAC API contract extensions, privilege boundaries, and project member management implementation adhere to all security invariants. **APPROVED** without reservations.
