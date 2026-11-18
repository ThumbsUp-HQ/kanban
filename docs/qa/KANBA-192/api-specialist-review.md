# API Specialist Forensic QA Review: KANBA-192

## Metadata
- **Ticket ID:** KANBA-192
- **Title:** [KB-WS-PROJ] Fix Default Workspace Project Creation 403, Workspace Switch 403 & Live UI Sync, /objects/KAN/access 422 on Page Load, and Independent Sidebar Project Expand
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `ee2cd44` (merged into `main`)
- **Review Date:** 2026-11-17
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 Database Migration & Forward Chaining Standard (`database/GEMINI.md`)
- **Linear Migration Chain:** Adheres strictly to the Zero-Guesswork standard established in KANBA-189. Migration `p4_21_workspace_project_rbac_fix` chains linearly from `p4_20_user_personal_settings` as the single authoritative head.
- **SQL & Security Invariants:**
  - Up migration `sql/p4_21_workspace_project_rbac_fix.up.sql` updates `kb_auth.switch_workspace` and `kb_auth.list_user_workspaces` with security definer guarantees, explicitly preserving session authorization and RLS context.
  - Grants execute privileges on updated helper functions to `kanban_app`.
  - Reversible down migration `sql/p4_21_workspace_project_rbac_fix.down.sql` verified.
  - Validated by `database/tests/migrations/test_p4_21_workspace_project_rbac_fix_migration.py` and `uv run kanban-ctl db check-migrations --static-only` (60 migrations valid, single head: `p4_21_workspace_project_rbac_fix`).

### 1.2 Project Creation RBAC & Workspace Bootstrapping (`kanban/services/projects.py`)
- **Permission Check Resolution:** In `_require_project_creator`, users with `WORKSPACE_MEMBER` or `WORKSPACE_ADMIN` role in the active workspace are permitted to create projects within that workspace.
- **Elimination of False 403s:** Eliminates the defect where valid workspace members were blocked from bootstrapping their first project upon entering a newly created workspace.

### 1.3 Workspace Switch & CSRF Token Precedence (`kanban/api/v1/workspaces.py`, `kanban/auth/sessions/csrf.py`)
- **CSRF Extraction Precedence:** In `kanban/auth/sessions/csrf.py:extract_csrf_cookie`, the extraction logic now strictly prioritizes the secure prefix `__Host-kb_csrf` before falling back to plain `kb_csrf`, preventing stale CSRF cookie collisions when switching between HTTP/HTTPS or sessions.
- **Workspace Switch Endpoint (`POST /api/v1/workspaces/{workspace_id}/switch`):**
  - Switches active workspace in session storage cleanly under RLS (`FORCE RLS`).
  - Clears fallback plain-HTTP cookies if operating on a secure HTTPS connection.
  - Re-issues synchronized session and CSRF cookies, returning the updated `csrf_token` in the response payload.
  - Tested via `test_case_9_multi_workspace_switch_roundtrip_project_creation` in `kanban/tests/api/test_workspaces_api.py`, confirming complete A -> B -> A round-trip workspace switching and project creation under clean RLS isolation.

### 1.4 Object Access Endpoint Reference Resolution (`kanban/api/v1/objects_access.py`, `kanban/services/object_ref.py`)
- **Flexible Reference Resolution:** `resolve_object_ref` updated to accept `ref: str | uuid.UUID` and safely normalize via `str(ref).strip()`.
- **422 to 404 Transition:** In `kanban/api/v1/objects_access.py`, the path parameter is accepted as `object_id: str` and resolved via `resolve_object_ref`. Non-existent object keys (e.g. `/api/v1/objects/KAN/access`) now return a standard RFC 7807 404 Problem response protected by `TimingFloor` rather than failing route validation with a 422 Unprocessable Entity.

---

## 2. Test Suite & Proof Verification

### 2.1 Backend Unit & Integration Tests
- Executed `database/tests/migrations/test_p4_21_workspace_project_rbac_fix_migration.py`, `database/tests/test_migration_consistency_static.py`, `database/tests/test_p1_17_models.py`, `database/tests/test_p1_14_rls_catalog.py`, `kanban/tests/api/test_workspaces_api.py`, and `kanban/tests/api/test_objects_access_endpoint.py`:
  - **Result:** 23 passed in 6.53s, 0 failures, 0 regressions.
  - Verified:
    - Migration upgrade/downgrade round-trip and single-head chain integrity.
    - Workspace switch A -> B -> A round-trip and project creation under RLS.
    - Object access endpoint string key resolution, timing floor, and 404 handling.

### 2.2 Proof Artifacts Audit (`docs/qa/KANBA-192/`)
- `git-diff.patch`: Complete diff against `main` excluding `docs/qa/KANBA-192/`.
- `changed-files-manifest.txt`: 31 files cataloged with SHA-256 digests and line counts.
- `unit-test-results.txt`: Confirms 23 backend pytest tests and 178 frontend Vitest suites (1893 tests) passed.
- `build-check.txt`: Clean static analysis (`ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`, `check-migrations --static-only`, `check_no_dashes`).
- `contract-sample.json`: Valid JSON contract sample documenting `post_projects`, `workspace_switch_roundtrip`, and `get_object_access_by_key`.
- `message-to-reality-checker.md`: Accurate narrative detailing architecture, migration forward chaining, and DoD fulfillment.

---

## 3. Specialist Verdict

The implementation in commit `ee2cd44` satisfies all backend architectural requirements, database migration standards, workspace switching security controls, and object reference resolution contracts specified in KANBA-192.

**Verdict: APPROVED**
