# API Specialist Review: KANBA-202 (KB-RBAC-SETTINGS)

## Review Metadata
- **Ticket:** KANBA-202
- **Module:** `kanban` backend REST routes, authentication session, project & workspace services, schemas, and admin services
- **Reviewer:** Backend Architect Specialist
- **Status:** APPROVED

---

## 1. Architectural & Specification Verification

### Endpoint Schema & Contract Alignment
1. `GET /api/v1/auth/me`:
   - Returns extended RBAC fields: `is_server_admin: bool`, `is_workspace_admin: bool`, `workspace_role: Literal["SERVER_ADMIN", "WORKSPACE_ADMIN", "WORKSPACE_MEMBER", "WORKSPACE_GUEST"]`, and `workspace_capabilities: list[str]`.
   - Properly resolves active workspace role and capabilities from the underlying object graph and database role bindings without leaking unauthorized cross-tenant data.

2. `ProjectResponse` & `GET /api/v1/projects/{ref}`:
   - Exposes `is_project_admin: bool` (`"ADMIN" in capabilities`) and `project_role: str | None`.
   - Verified that project serialization dynamically maps principal role bindings (`PROJECT_ADMIN`, `MEMBER`, `VIEWER`).

3. Project Membership Endpoints:
   - `GET /api/v1/projects/{project_ref}/members`: Lists explicit role bindings for project principals.
   - `POST /api/v1/projects/{project_ref}/members`: Grants project roles (`PROJECT_ADMIN`, `MEMBER`, `VIEWER`). Requires `Capability.ADMIN` on the target project.
   - `DELETE /api/v1/projects/{project_ref}/members/{principal_id}`: Revokes project role bindings. Requires `Capability.ADMIN` on the target project.

4. Privilege Escalation Prevention in `PrincipalAdminService`:
   - In `kanban/admin/principal_service.py` (`bind_role`), non-`SERVER_ADMIN` callers attempting to grant `role="SERVER_ADMIN"` are strictly blocked with `403 INSUFFICIENT_CAPABILITY`.

5. Workspace Settings & Slug Updates:
   - `kanban/api/v1/admin/workspace_settings.py` and `kanban/api/v1/workspaces.py` support updating `name` and `slug`.
   - Enforces unique slug checks via `resolve_workspace_by_slug_or_id` returning `409 WORKSPACE_SLUG_CONFLICT` on collision.

---

## 2. Test Verification & Code Quality
- All backend RBAC test cases in `kanban/tests/auth/test_standard_user_rbac_matrix.py` pass cleanly in 1.39 seconds.
- Ruff linting and Mypy strict type checking pass with 0 errors across all 8 modified backend modules.
- Zero em-dashes and zero en-dashes present.

---

## 3. Verdict
The API endpoints and service boundaries are secure, fail-closed, and strictly comply with all KANBA-202 specifications.
