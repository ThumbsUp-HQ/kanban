# Forensic Verification Packet for KAN-30 (RC2 Remediation)

**Ticket:** KAN-30 ([KB-P3-AUDIT-24] Add Workspace Admin Trash & Retention Studio, Enforce Per-Workspace Retention & RLS Boundaries, and Publish Visual Role & Permission Matrix)
**Branch:** `fix/KAN-30-rc2`
**Base Commit:** `93301a8f`
**Wiki Commit:** `899dec9` (branch `main` in `/home/adamoutler/kanban/thumbs-up-kanban.wiki`)

---

## 1. Remediation of Reality-Checker Findings (RC2)

Every finding in `docs/qa/KAN-30/reality-checker-report.md` has been completely resolved:

### 1. Fix `Stickys` Pluralization Typo (`WorkspaceSettingsPage.tsx`)
- Replaced naive string concatenation (`${k}s`) with an explicit dictionary mapping (`TRASH_FILTER_LABELS`):
  - `all: 'All Items'`
  - `project: 'Projects'`
  - `issue: 'Issues'`
  - `doc: 'Docs'`
  - `page: 'Pages'`
  - `sticky: 'Stickies'`
  - `cycle: 'Cycles'`
  - `module: 'Modules'`
  - `view: 'Views'`
- Guaranteed that `Stickys` never renders anywhere in the UI or DOM.
- Verified by unit tests in `WorkspaceSettingsPage.test.tsx` asserting the presence of the `Stickies` pill and the absence of `Stickys`.

### 2. Require Explicit Typed Confirmation Phrase in Stage 2 Permanent Purge Modal (`WorkspaceSettingsPage.tsx`)
- Added explicit text input (`data-testid="permanent-purge-confirm-phrase-input"`) requiring the `SERVER_ADMIN` to type the exact `confirm_phrase` returned by Stage 1 (`typedConfirmPhrase.trim() === pendingPurge.confirmPhrase`).
- Set initial `purgeReason` state to `''` with an empty placeholder (`Enter audit reason for permanent purge (min 8 chars)...`), rather than pre-filling `'Permanent cryptographic purge'`.
- Disabled the `Confirm Permanent Purge` button (`data-testid="confirm-permanent-purge-btn"`) until:
  `typedConfirmPhrase.trim() === pendingPurge.confirmPhrase && purgeReason.trim().length >= 8`
- When enabled, the danger button renders in full-opacity `#991b1b` / `var(--danger)`. (Disabled state is styled via `.kb-btn-purge:disabled` with opacity 0.6 and not-allowed cursor in `ProjectSettingsPage.css`).
- Verified by unit tests in `WorkspaceSettingsPage.test.tsx`.

### 3. Resolve `PROJECT_ADMIN` Trash Studio Access Mismatch (`WorkspaceSettingsPage.tsx`, `destructive.py`, `Role-and-Permission-Matrix.md`)
- `WorkspaceSettingsPage.tsx` now evaluates whether the caller holds `PROJECT_ADMIN` authority (via `/api/v1/auth/me` `is_project_admin` flag or by probing `GET /api/v1/admin/trash` when opening `/workspaces/settings#tab-trash`).
- When a `PROJECT_ADMIN` without workspace admin rights opens `/workspaces/settings#tab-trash` (`isProjectAdminOnly = true`):
  - Sets `activeTab = 'trash'` and renders the Trash Studio tab.
  - Hides Workspace General, Members, and Groups navigation tabs.
  - Hides the Retention Policy edit form and input while continuing to display the read-only policy text (`Soft-deleted items are retained for X days per workspace policy.`).
  - Allows `PROJECT_ADMIN` users to inspect and restore soft-trashed items belonging to their administered projects (matching `destructive.py:263-276` and `Role-and-Permission-Matrix.md` Note 7 100%).
  - Retains strict `403` lockout and `access-denied-message` for standard members without project admin authority.
  - Retains strict `SERVER_ADMIN`-only restriction for permanent purge buttons and actions.

### 4. Implement `limit` and `offset` Pagination on `GET /api/v1/admin/trash` (`kanban/api/v1/admin/destructive.py`)
- Added explicit query parameters to `api_admin_list_trash`:
  - `limit: Annotated[int, Query(ge=1, le=500, description="Page size limit (1-500)")] = 100`
  - `offset: Annotated[int, Query(ge=0, description="Page offset")] = 0`
- Applied `.offset(offset).limit(limit)` to the `ObjectRecord` query statement.
- Added comprehensive unit test `test_admin_trash_pagination_limit_and_offset` in `kanban/tests/api/test_admin_trash_api.py` validating:
  - First page: `limit=2&offset=0` returns 2 newest items.
  - Second page: `limit=2&offset=2` returns the next 2 older items with zero overlap.
  - Validation rejections: `limit=0` (422), `limit=501` (422), `offset=-1` (422).

### 5. Accurate Filenames, Manifest, and Metrics
- Canonical filenames referenced accurately throughout all documentation:
  - `kanban/web/src/features/settings/ProjectSettingsPage.css` (not `WorkspaceSettingsPage.css`)
  - `kanban/api/v1/admin/destructive.py` (not `trash.py`)
  - `kanban/api/v1/admin/workspace_settings.py` (not `workspace_settings.py`)
- Updated `docs/qa/KAN-30/changed-files-manifest.txt` to include `docs/qa/KAN-30/screenshots/live-role-matrix-desktop-light.png`.
- Stored exact verbatim test and build logs in `docs/qa/KAN-30/unit-test-results.txt` and `docs/qa/KAN-30/build-or-typecheck.txt`.

---

## 2. Test Execution & Coverage Audit

### Backend Unit Tests & Coverage (`pytest --cov`)
- 51 passed in 53.20 seconds.
- Test files executed:
  - `kanban/tests/api/test_admin_trash_api.py` (6 passed, including pagination test)
  - `kanban/tests/api/test_workspace_settings.py` (13 passed)
  - `kanban/tests/jobs/test_trash_purge.py` (9 passed)
  - `kanban/tests/auth/test_aal2_policy.py` (3 passed)
  - `kanban/tests/api/test_destructive_lifecycle.py` (6 passed)
  - `kanban/tests/api/test_destructive_lifecycle_coverage.py` (6 passed)
  - `kanban/tests/api/test_issue_delete.py` (8 passed)
  - `kanban/tests/api/test_system_status.py` (`assert_admin_routes_protected` compliance passed)
- Coverage on touched backend modules:
  - `kanban/api/v1/admin/destructive.py`: 95%
  - `kanban/api/v1/admin/workspace_settings.py`: 94%
  - `kanban/api/v1/schemas/issue_delete.py`: 100%
  - `kanban/jobs/trash_purge.py`: 95%
  - `kanban/services/activity.py`: 96%
  - `kanban/services/destructive_lifecycle.py`: 95%
  - `kanban/services/issue_delete.py`: 95%
  - **Overall Touched Coverage:** 95% (1,432 statements, 33 missed)

### Frontend Unit Tests & Coverage (`vitest --coverage`)
- `kanban/web/src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`:
  - 34 passed in 2.59s, 0 `act(...)` warnings.
  - Coverage: **99.78% Stmts, 95.11% Branch, 100% Funcs, 100% Lines** (all `>= 95%`).
- `kanban/web/src/styles/__tests__/cssTokensAudit.test.ts`:
  - 4 passed in 13ms (100% canonical CSS tokens, 0 inline JSX style attributes).

### Static Analysis & Linters
- `kanban-ctl db check-migrations`: OK (62 migrations valid, single head `p4_23_oidc_link_intent_fk`).
- `ruff check .`: Clean (all checks passed).
- `ruff format --check .`: Clean (1,966 files inspected, formatted).
- `mypy`: Clean (Success: no issues found in 1,125 source files).
- `lint-imports`: Clean (2 contracts kept, 0 broken).
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint . --max-warnings 0`: Clean (0 warnings, 0 errors).
- `pnpm --dir kanban/web run build`: Clean production build (dist output generated in 1.20s).
- `python3 -m scripts.check_no_dashes`: Clean (0 em-dashes or en-dashes across codebase and wiki).

---

## 3. Artifact Manifest

- `docs/qa/KAN-30/unit-test-results.txt`: Verbatim Pytest and Vitest test outputs and coverage tables.
- `docs/qa/KAN-30/build-or-typecheck.txt`: Verbatim migration check, Ruff, Mypy, lint-imports, TSC, ESLint, Vite build, and check_no_dashes logs.
- `docs/qa/KAN-30/git-diff.patch`: Full unified git patch against base commit.
- `docs/qa/KAN-30/wiki-diff.patch`: Unified diff of wiki commit `899dec9`.
- `docs/qa/KAN-30/changed-files-manifest.txt`: List of all changed files including `live-role-matrix-desktop-light.png`.
- `docs/qa/KAN-30/message-to-reality-checker.md`: This forensic summary.
