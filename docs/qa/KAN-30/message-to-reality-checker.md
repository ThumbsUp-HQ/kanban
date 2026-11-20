# Forensic Verification Packet for KAN-30

**Ticket:** KAN-30 ([KB-P3-AUDIT-24] Add Workspace Admin Trash & Retention Studio, Enforce Per-Workspace Retention & RLS Boundaries, and Publish Visual Role & Permission Matrix)
**Branch:** `feat/KAN-30`
**Base Commit:** `23ae056d`
**Wiki Commit:** `899dec9` (branch `main` in `/home/adamoutler/kanban/thumbs-up-kanban.wiki`)

---

## 1. Problem Implementation Summary

### Problem 1: Per-Workspace Retention Enforcement & Multi-Object Trash Purge Sweep
- **Per-Workspace Retention Config:**
  - In `kanban/api/v1/admin/workspace_settings.py`, updated `WorkspaceSettingsUpdate.trash_retention_days` validator to require `ge=7, le=365`.
  - Added strict requirement for fresh AAL2 step-up (`<= 900s`) when updating workspace settings.
  - Added emission of audit warning event `ActivityEventType.TRASH_RETENTION_SHORTENED_WARN` (`"TRASH_RETENTION_SHORTENED_WARN"`) under `ActivityCategory.SYSTEM` when shortening retention days.
  - In `kanban/services/issue_delete.py`, replaced fallback to global settings with direct read of `workspaces.trash_retention_days`.
  - In `kanban/services/destructive_lifecycle.py`, added per-workspace retention window check reading `workspaces.trash_retention_days` and added defense-in-depth clause `.where(Issue.id == parsed_uuid, Issue.workspace_id == caller.workspace_id)`.
- **Multi-Object Expired Trash Sweep:**
  - Extended `kanban/jobs/trash_purge.py` to sweep all expired trashed entity types: `issues`, `docs`, `pages`, `stickies`, `cycles`, `modules`, `views`, and `projects`.
  - Cleaned associated invalid object links via `InvalidLinkAuditor` / `LinkPurger`.
  - Cleaned project dependencies (`workflow_states`, `project_priorities`, `project_labels`, `project_module_defaults`) under `SET LOCAL kanban.allow_project_delete = 'on'` to satisfy cascade invariants.
  - Allowed `pages` deletion to cascade to `page_versions` (preserving `page_versions_immutable_bud()` trigger semantics at trigger depth 2).

### Problem 2: Workspace Trash Listing & Restore API with Strict RLS + ACL DENY Isolation
- **Trash Listing Endpoint (`GET /api/v1/admin/trash`):**
  - Protected with `Depends(require_admin_aal2)`.
  - Accepts parameters: `kind` (`all`, `project`, `issue`, `doc`, `page`, `sticky`, `cycle`, `module`, `view`), `project_id`, `q`, `limit`, `offset`.
  - Enforces strict tenant scoping to `caller.workspace_id`.
  - Filters all candidates through `evaluate_capabilities(session, caller, obj.id)` requiring `Capability.VIEW` and (`Capability.DELETE` or `Capability.ADMIN`).
  - Completely excludes private entities with an explicit ACL `DENY` from leaking to Workspace Admins.
  - Restricts Project Admins to items residing in projects they administer.
- **Trash Restore Endpoint (`POST /api/v1/admin/trash/{target_id}:restore`):**
  - Allows `WORKSPACE_ADMIN` and `SERVER_ADMIN` with fresh AAL2 to restore soft-trashed items and projects.
- **Permanent Purge Security Gate:**
  - Kept `mode="permanent_purge"` strictly gated to `SERVER_ADMIN` + fresh AAL2 + 2-stage `DestructiveConfirmationToken` + `blast_hash` + `reason` (`403 FORBIDDEN` for `WORKSPACE_ADMIN`).

### Problem 3: Workspace Trash & Retention Studio UI
- **Tab Navigation & URL Hash Sync:**
  - Updated `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx` with `#tab-trash` (`id="tab-trash"`, `data-testid="tab-trash"`, `aria-selected={activeTab === 'trash'}`).
  - Synchronized tab state bidirectionally with URL hash (`#tab-trash`, `#tab-general`, `#tab-members`, `#tab-groups`).
- **Studio Interface:**
  - Retention policy card exposing Trash Retention Days (`7..365` days) with save action.
  - Filter pills for `all`, `project`, `issue`, `doc`, `page`, `sticky`, `cycle`, `module`, `view`.
  - Live search input filterable by key or title.
  - Data table displaying Type badge, Item key/title, Deleted At timestamp, Days Remaining, and `[Restore]` button.
  - `SERVER_ADMIN`-only 2-stage `[Permanent Purge]` with confirmation dialog invoking `/api/v1/admin/destructive:request` and `/api/v1/admin/destructive:execute`.
  - Zero inline JSX `style={...}` props; all styles defined using canonical CSS tokens in `ProjectSettingsPage.css` (`.kb-trash-toolbar`, `.kb-trash-search-box`, `.kb-retention-settings-card`, `.kb-visually-hidden`).

### Problem 4: Role and Permission Matrix
- Published `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Role-and-Permission-Matrix.md` and linked in `_Sidebar.md`.
- Structured matrix using visual indicators:
  - `●` (Allowed by role)
  - `◐` (Conditional on ACL share, token scope, or AAL2 step-up)
  - `○` (Never allowed)
- Covered all 7 principal tiers (`Guest`, `Viewer`, `Member`, `Project Admin`, `Workspace Admin`, `Server Admin`, `Scoped MCP Agent`).
- Covered functional domains: Viewing, Authoring, Sharing/ACLs (`Explicit DENY` precedence), Project Studios, Soft-Trash, Restore, Retention Policy, Permanent Cryptographic Purge, Auth/User Governance, MCP Key Minting, and Immutable Audit Ledger protection.

---

## 2. Test Execution & Coverage Audit

### Backend Unit Tests & Coverage (`pytest --cov`)
- 50 passed in 52.04 seconds.
- Test files executed:
  - `kanban/tests/api/test_admin_trash_api.py` (5 passed)
  - `kanban/tests/api/test_workspace_settings.py` (13 passed)
  - `kanban/tests/jobs/test_trash_purge.py` (9 passed)
  - `kanban/tests/auth/test_aal2_policy.py` (3 passed)
  - `kanban/tests/api/test_destructive_lifecycle.py` (6 passed)
  - `kanban/tests/api/test_destructive_lifecycle_coverage.py` (6 passed)
  - `kanban/tests/api/test_issue_delete.py` (8 passed)
  - `kanban/tests/api/test_system_status.py` (`assert_admin_routes_protected` compliance passed)
- Coverage on touched backend modules:
  - `kanban/api/v1/admin/destructive.py`: 95%
  - `kanban/api/v1/admin/workspace_settings.py`: 95%
  - `kanban/api/v1/schemas/issue_delete.py`: 100%
  - `kanban/jobs/trash_purge.py`: 95%
  - `kanban/services/activity.py`: 96%
  - `kanban/services/destructive_lifecycle.py`: 95%
  - `kanban/services/issue_delete.py`: 95%
  - **Overall Touched Coverage:** 95% (1431 statements, 33 missed)

### Frontend Unit Tests & Coverage (`vitest --coverage`)
- `kanban/web/src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`:
  - 31 passed in 3.80s.
  - Coverage: **99.76% Stmts, 95.79% Branch, 100% Funcs, 100% Lines**.
- `kanban/web/src/styles/__tests__/cssTokensAudit.test.ts`:
  - 4 passed in 0.97s (100% canonical CSS tokens, 0 undefined tokens).

### Static Analysis & Linters
- `kanban-ctl db check-migrations`: OK (62 migrations valid, single head).
- `ruff check .`: Clean (0 errors).
- `ruff format --check .`: Clean (1918 files inspected, formatted).
- `mypy`: Clean (Success: no issues found in 1107 source files).
- `lint-imports`: Clean (2 contracts kept, 0 broken).
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint . --max-warnings 0`: Clean (0 warnings, 0 errors).
- `pnpm --dir kanban/web build`: Clean production build (dist output generated).
- `scripts.check_no_dashes`: Clean (0 em-dashes or en-dashes across codebase and wiki).

---

## 3. Artifact Manifest

- `docs/qa/KAN-30/unit-test-results.txt`: Verbatim Pytest and Vitest test outputs and coverage tables.
- `docs/qa/KAN-30/build-or-typecheck.txt`: Verbatim migration check, Ruff, Mypy, lint-imports, TSC, ESLint, Vite build, and check_no_dashes logs.
- `docs/qa/KAN-30/git-diff.patch`: Full unified git patch against base commit `23ae056d`.
- `docs/qa/KAN-30/wiki-diff.patch`: Unified diff of wiki commit `899dec9`.
- `docs/qa/KAN-30/changed-files-manifest.txt`: List of all changed files.
- `docs/qa/KAN-30/message-to-reality-checker.md`: This forensic summary.
