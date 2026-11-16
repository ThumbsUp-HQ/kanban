# Backend Architect / API Specialist Review: KANBA-175

- **Reviewer:** Backend Architect / API Specialist (`arch-reviewer`)
- **Date:** 2026-11-16
- **Ticket:** KANBA-175 ([KB-UX-05] Fix Standalone Status Topbar Notification Pill Click/Dismiss, Compose Export 403, and Multi-Workspace Switcher/Creation)
- **Scope Inspected:**
  - `kanban/api/v1/system_status.py`
  - `kanban/standalone/export_service.py`
  - `kanban/api/v1/workspaces.py`
  - `kanban/api/v1/__init__.py`
  - `kanban/tests/api/test_workspaces_api.py`
  - `docs/qa/KANBA-175/changed-files-manifest.txt`
  - `docs/qa/KANBA-175/git-diff.patch`
  - `docs/qa/KANBA-175/unit-test-results.txt`
  - `docs/qa/KANBA-175/build-check.txt`
  - `docs/qa/KANBA-175/message-to-reality-checker.md`

---

## 1. Architectural & Security Evaluation

### A. Multi-Workspace REST API Architecture (`kanban/api/v1/workspaces.py`)
- **Tenant Isolation & Anti-Enumeration:**
  - `GET /api/v1/workspaces`: Only `SERVER_ADMIN` principals can enumerate all workspaces across the system. For regular users, membership is resolved strictly by matching the caller's verified email and active user principals, guaranteeing cross-tenant isolation and zero unauthenticated tenant enumeration.
- **Strict Validation & Provisioning:**
  - `POST /api/v1/workspaces`: Validates workspace display name (1 to 200 trimmed characters) and enforces strict lowercase URL-safe slug format matching `^[a-z0-9][a-z0-9-]{1,62}$`.
  - Duplicate slug collisions return standard RFC 7807 problem responses with HTTP 409 `WORKSPACE_SLUG_CONFLICT`.
  - Provisioning atomically registers the user object, creates the workspace principal and user record, and grants `WORKSPACE_ADMIN` in the new tenant.
- **Session & CSRF Lifecycle Management:**
  - `POST /api/v1/workspaces/{workspace_id}/switch`: Verifies membership (or `SERVER_ADMIN` authority) before permitting context switching; unauthorized switches are rejected with HTTP 403 `FORBIDDEN_WORKSPACE_SWITCH`.
  - Upon switching, `session_service.create_after_login` issues fresh, rotated session and CSRF cookies, including fallback cookies for non-HTTPS local environments.

### B. Standalone Status & Compose Export Security (`kanban/api/v1/system_status.py`)
- **Admin AAL2 Protection & Route Integrity:**
  - The `admin_standalone_router` strictly enforces `Depends(require_admin_aal2)` across all `/api/v1/admin/standalone/*` routes, maintaining 100% compliance with `assert_admin_routes_protected`.
  - Scoped `require_server_admin` specifically to the destructive/sensitive `POST /admin/standalone/backup` endpoint, allowing authenticated administrators with AAL2 to view status and download the sanitized Docker Compose export without 403 `INSUFFICIENT_CAPABILITY` errors.
- **Zero-Shell Execution & Secret Sanitization:**
  - `run_pg_dump()` safely extracts host, port, user, and database name via SQLAlchemy's `make_url`, passing credentials strictly through subprocess environment variables (`PGPASSWORD`) with zero shell interpolation.
  - Backup exports are encrypted using AES-256-GCM with either a PBKDF2-derived key (minimum 16-character passphrase) or server master KEK, and each backup event is recorded to the immutable `activity_records` ledger.

### C. Import Boundaries & Code Hygiene
- `uv run lint-imports` confirmed that all unidirectional layer contracts are kept (2 kept, 0 broken).
- `uv run ruff check` confirmed zero lint or formatting errors across all backend and test files.
- `scripts.check_no_dashes` confirmed strict adherence to plain ASCII hyphens.

---

## 2. Test Suite & Coverage Verification
- Executed `uv run pytest kanban/tests/api/test_workspaces_api.py kanban/tests/api/test_system_status.py -v`:
  - 16/16 backend tests passed in 5.54s with zero failures.
  - Verified `test_assert_admin_routes_protected_compliance` passes.
- Unit test coverage:
  - `kanban/api/v1/workspaces.py` achieved **97% statement coverage** (156 statements, only 2 missed branch cases), exceeding the project's >= 95% coverage requirement.
- Vitest frontend tests:
  - 62/62 tests passed across `EmojiHint.test.tsx`, `HeaderPills.test.tsx`, `Sidebar.test.tsx`, `CreateWorkspaceModal.test.tsx`, and `StandaloneStatusPanel.test.tsx`.

---

## 3. Findings & Defect Summary
- **Critical Defects:** 0
- **Security Vulnerabilities:** 0
- **Schema / Invariant Violations:** 0
- **Regressions:** 0

All backend, API, session security, and RLS requirements for KANBA-175 are satisfied.

---

**Verdict:** APPROVED
