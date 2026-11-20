# API Specialist Review: KAN-30 (KB-P3-AUDIT-24)

- Ticket: KAN-30
- Title: [KB-P3-AUDIT-24] Add Workspace Admin Trash & Retention Studio, Enforce Per-Workspace Retention & RLS Boundaries, and Publish Visual Role & Permission Matrix (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-30`
- Branch: `main`
- Commit: `837f657d079ebcb8ee88eec86ad2f6df41c1eb33` (short: `837f657d`)
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-30 on `main` at commit `837f657d`, incorporating verified evidence from the zero-mock live container execution (`live-fullstack-proof.txt` run on `http://127.0.0.1:18961`, container `kanban-liveqa-1`), all 6 live visual screenshots in `docs/qa/KAN-30/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves four primary problems across data retention, trash lifecycle, role-based access control, and visual permissions:
1. Per-Workspace Retention Enforcement & Multi-Object Expired Trash Sweep:
   - Enforces per-workspace `workspaces.trash_retention_days` (`7..365` days) across `workspace_settings.py`, `issue_delete.py`, and `destructive_lifecycle.py`.
   - Requires fresh AAL2 step-up verification (`<= 900s`) when updating workspace retention settings, and records `ActivityEventType.TRASH_RETENTION_SHORTENED_WARN` in the immutable audit ledger if retention days are shortened.
   - Strengthens `destructive_lifecycle.py` with defense-in-depth tenant boundary check `.where(Issue.id == parsed_uuid, Issue.workspace_id == caller.workspace_id)`.
   - Expands `kanban/jobs/trash_purge.py` to sweep all expired trashed object types (`issues`, `docs`, `pages`, `stickies`, `cycles`, `modules`, `views`, `projects`), clean invalid links via Link Auditor/Purger, cascade page deletions to `page_versions`, and clean project dependencies under `SET LOCAL kanban.allow_project_delete = 'on'`.
2. Workspace Trash Listing & Restore API with Strict RLS + ACL DENY Isolation:
   - Implemented `GET /api/v1/admin/trash` (`Depends(require_admin_aal2)`) supporting filtering by `kind`, `project_id`, and `q`. Scopes items to `caller.workspace_id` and filters every candidate through `evaluate_capabilities(session, caller, obj.id)`, ensuring private items with an explicit ACL `DENY` are never leaked to Workspace Admins. Restricts Project Admins strictly to their administered projects.
   - Implemented `POST /api/v1/admin/trash/{target_id}:restore` allowing Workspace Admins and Server Admins with fresh AAL2 to restore soft-trashed items.
   - Preserves 2-stage permanent purge exclusively for `SERVER_ADMIN` + fresh AAL2 + `DestructiveConfirmationToken` + `blast_hash` + reason (`403 FORBIDDEN` for `WORKSPACE_ADMIN`).
3. Workspace Trash & Retention Studio UI:
   - Integrated `#tab-trash` (`id="tab-trash"`) into `WorkspaceSettingsPage.tsx` with bidirectional URL hash sync (`#tab-trash`, `#tab-general`, `#tab-members`, `#tab-groups`).
   - Provided retention policy setting card (`7..365` days), multi-kind filter pills, real-time search, responsive data table, and Restore / Permanent Purge actions with zero inline CSS styles.
4. Published Visual Role & Permission Matrix:
   - Authored `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Role-and-Permission-Matrix.md` and integrated `/docs/role-and-permission-matrix`.
   - Documented fine-grained capabilities across all 7 principal tiers using standardized visual indicators (`●` Allowed by role, `◐` Conditional, `○` Never allowed).

All API contracts, security invariants, tenant boundaries, administrative AAL2 step-up protections, and test coverage requirements are verified and approved:
- Exact problem response structure and capability enforcement: Callers lacking AAL2 or with stale sessions (`> 900s`) receive HTTP 403 `AAL2_REQUIRED` or `AAL2_STALE`.
- High test coverage: 50/50 Pytest tests pass in 50.50s with 95% overall statement coverage across touched backend files (`destructive.py` 95%, `workspace_settings.py` 95%, `issue_delete.py` 100% schemas / 95% services, `trash_purge.py` 95%, `activity.py` 96%, `destructive_lifecycle.py` 95%). 31/31 Vitest tests pass in 3.76s with 99.77% statement / 95.68% branch coverage on `WorkspaceSettingsPage.tsx`.
- Zero external runtime packages added (`Apache-2.0` compliant).
- Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation (`check_no_dashes` clean).

---

## 2. Detailed Contract & Security Verification

### 2.1 Retention Settings & Fresh AAL2 Step-Up (`kanban/api/v1/admin/workspace_settings.py`)
- Source: `kanban/api/v1/admin/workspace_settings.py` (`update_workspace_settings`)
- Validation:
  - `WorkspaceSettingsUpdate.trash_retention_days`: `int | None = Field(default=None, ge=7, le=365)`.
  - Fresh AAL2 requirement: If `body.trash_retention_days` is updated:
    - Enforces `caller.aal_level >= 2` (HTTP 403 `AAL2_REQUIRED`).
    - Enforces `caller.aal2_verified_at` freshness: `(now_utc - verified_at).total_seconds() <= 900` (HTTP 403 `AAL2_STALE`).
  - Shortening Warning Audit:
    - If `new_retention_days < before["trash_retention_days"]`, logs warning and records `ActivityEventType.TRASH_RETENTION_SHORTENED_WARN` with previous and new retention days.

### 2.2 Workspace Trash Listing Endpoint (`kanban/api/v1/admin/destructive.py`)
- Source: `kanban/api/v1/admin/destructive.py` (`api_admin_list_trash`)
- Route: `GET /api/v1/admin/trash`
- Security Protection: `Depends(require_admin_aal2)`
- Request Query Parameters:
  - `kind: str = "all"` (`all`, `project`, `issue`, `doc`, `page`, `sticky`, `cycle`, `module`, `view`)
  - `project_id: uuid.UUID | None = None`
  - `q: str | None = None` (searches `canonical_key` and `display_title`)
- Tenant & Capability Isolation Invariants:
  1. Scoped strictly to `ObjectRecord.workspace_id == caller.workspace_id` and `ObjectRecord.deleted_at.is_not(None)`.
  2. Role differentiation:
     - `SERVER_ADMIN` and `WORKSPACE_ADMIN`: See all workspace items permitted by capability evaluation.
     - `PROJECT_ADMIN`: Constrained strictly to `admin_project_ids` (projects where principal holds `PROJECT_ADMIN` role).
  3. Absolute ACL DENY Precedence:
     - Every candidate row is evaluated via `await evaluate_capabilities(session, caller, obj.id)`.
     - Requires `Capability.VIEW` and (`Capability.DELETE` or `Capability.ADMIN`).
     - If an explicit `DENY` entry exists on the entity, `Capability.VIEW` is stripped, completely excluding the object from the response.
  4. Days Remaining Computation:
     - Dynamically calculates `purge_after = obj.deleted_at + timedelta(days=retention_days)`.
     - Computes `remaining_days = max(0, int((purge_after - now_ts).total_seconds() // 86400))`.

### 2.3 Workspace Trash Restore Endpoint (`kanban/api/v1/admin/destructive.py`)
- Source: `kanban/api/v1/admin/destructive.py` (`api_admin_restore_by_id`)
- Route: `POST /api/v1/admin/trash/{target_id}:restore`
- Protection: `Depends(require_admin_aal2)`
- Parameters: `target_id: uuid.UUID`, `reason: str = Query(min_length=10, max_length=500)`
- Implementation:
  - Resolves target object kind from `ObjectRecord.object_type`.
  - Invokes `restore_object()` in `kanban/services/destructive_lifecycle.py`.
  - Restores object row and clears `deleted_at = None` across primary table and `objects` spine within a clean transaction.

### 2.4 Multi-Object Trash Purge Daemon (`kanban/jobs/trash_purge.py`)
- Source: `kanban/jobs/trash_purge.py` (`_process_trash_purge_batch`, `_run_pass_with_session`)
- Per-Workspace Threshold:
  - Identifies expired entities where `ObjectRecord.deleted_at + func.make_interval(0, 0, 0, func.coalesce(Workspace.trash_retention_days, 30)) <= now`.
- Multi-Entity Sweep:
  - Sweeps `issues`, `docs`, `pages`, `stickies`, `cycles`, `modules`, `views`, and `projects`.
  - Invokes `InvalidLinkAuditor` and `LinkPurger` to audit and purge broken object links.
  - Handles project cascades under `SET LOCAL kanban.allow_project_delete = 'on'`, safely removing project priorities, workflow states, and module defaults.
  - Cascades `pages` deletion to `page_versions` respecting database immutability triggers.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt`)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-30/live-fullstack-proof.txt` on target container `kanban-liveqa-1` (`http://127.0.0.1:18961`) at commit `837f657d`:
1. Test Data Provisioning & Soft-Trash Setup:
   - Provisioned disposable issues as `@admin` (`SERVER_ADMIN`, AAL2):
     * `pubIssue`: KAN-7 (`01a1fa5c-8c3e-7a6c-b21f-7b9f1b684777`) -> HTTP 201
     * `secIssue`: KAN-8 (`01a1fa5c-8c7f-76ac-9da4-c22524fe2692`) -> HTTP 201
     * `restoreIssue`: KAN-9 (`01a1fa5c-8cba-7acc-9c3a-b2aadd625ae4`) -> HTTP 201
   - Granted explicit ACL DENY for `@wsadmin` (`WORKSPACE_ADMIN`) on KAN-8 via `POST /api/v1/admin/acl-entries` -> HTTP 200.
   - Soft-trashed KAN-7, KAN-8, KAN-9 (GET /delete-preview + DELETE /api/v1/issues/{key} with Kb-Blast-Hash) -> HTTP 200 each.
2. Workspace Admin Trash & Retention Studio UI:
   - Loaded `/workspaces/settings#tab-trash` as `@admin` (795ms).
   - Viewport checks confirm zero horizontal overflow across Desktop (1440x900 Light/Dark), Tablet (768x1024, scrollWidth=768), and Mobile (390x844, scrollWidth=390).
   - Retention policy setting:
     * Invalid (<7 days): `PATCH /api/v1/admin/workspace-settings {trash_retention_days: 3}` -> HTTP 422.
     * Valid update via UI (21 days): `PATCH /api/v1/admin/workspace-settings` -> HTTP 200 (55ms).
   - UI Restore action: Clicked Restore on KAN-9 -> `POST /api/v1/admin/trash/01a1fa5c-8cba-7acc-9c3a-b2aadd625ae4:restore` -> HTTP 200 (89ms).
3. Full Live 2-Stage Permanent Purge UI Modal E2E:
   - Stage 1: Clicked `[data-testid="permanent-purge-btn-01a1fa5c-8c3e-7a6c-b21f-7b9f1b684777"]` on KAN-7:
     * `POST /api/v1/admin/destructive:request` -> HTTP 200 (57ms).
     * Returned `confirm_phrase="PURGE ISSUE KAN-7"`.
     * Confirmation dialog rendered with exact confirm phrase. Screenshot: `screenshots/live-purge-modal.png`.
   - Stage 2: Entered reason ("Live QA permanent purge verification for KAN-30") and confirmed:
     * `POST /api/v1/admin/destructive:execute` -> HTTP 200 (65ms).
     * Body: `{"status":"executed","target":"KAN-7","target_kind":"issue","target_id":"01a1fa5c-8c3e-7a6c-b21f-7b9f1b684777","mode":"permanent_purge","blast_hash":"192640f97a9d700f5bce38727e5c86f3d4f9ca98da9287ce495df76e93a420f5"}`.
     * KAN-7 disappeared immediately from the trash items table.
4. RLS & Role Isolation (@member and @wsadmin):
   - `@member_r4` (`WORKSPACE_MEMBER`, non-admin):
     * `GET /api/v1/admin/trash` -> HTTP 403.
     * `POST /api/v1/admin/destructive:request` -> HTTP 403.
     * UI renders access-denied message.
   - `@wsadmin` (`WORKSPACE_ADMIN`, AAL2):
     * `GET /api/v1/admin/trash` -> HTTP 200, secret ACL-DENY issue KAN-8 excluded (`secretHidden=true`).
     * `POST /api/v1/admin/destructive:request` -> HTTP 403 `SERVER_ADMIN_REQUIRED`.
     * UI permanently hides purge buttons (`count = 0`).
5. Visual Role & Permission Matrix:
   - Loaded `/docs/role-and-permission-matrix` (843ms).
   - Verified glyphs rendered in DOM: filled circle (`●`), half circle (`◐`), and empty circle (`○`).
   - Desktop 1440x900 Light: `scrollWidth=1440`, `innerWidth=1440` (zero horizontal overflow). Screenshot: `live-role-matrix-desktop-light.png`.
6. All 6 Live Screenshots Verified on Disk:
   - `live-desktop-dark.png`
   - `live-desktop-light.png`
   - `live-mobile.png`
   - `live-purge-modal.png`
   - `live-role-matrix-desktop-light.png`
   - `live-tablet.png`
7. Telemetry & Stability: Unexpected console errors: 0, Page errors: 0, HTTP 5xx server errors: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/api/test_admin_trash_api.py`: 5 passed.
  - `kanban/tests/api/test_workspace_settings.py`: 13 passed.
  - `kanban/tests/jobs/test_trash_purge.py`: 9 passed.
  - `kanban/tests/auth/test_aal2_policy.py`: 3 passed.
  - `kanban/tests/api/test_destructive_lifecycle.py`: 6 passed.
  - `kanban/tests/api/test_destructive_lifecycle_coverage.py`: 6 passed.
  - `kanban/tests/api/test_issue_delete.py`: 8 passed.
  - Total: 50 passed in 50.50s.
  - Statement coverage across touched files:
    - `kanban/api/v1/admin/destructive.py`: 95%
    - `kanban/api/v1/admin/workspace_settings.py`: 95%
    - `kanban/api/v1/schemas/issue_delete.py`: 100%
    - `kanban/jobs/trash_purge.py`: 95%
    - `kanban/services/activity.py`: 96%
    - `kanban/services/destructive_lifecycle.py`: 95%
    - `kanban/services/issue_delete.py`: 95%
    - Combined coverage: 95% (1431 stmts, 33 miss).
  - Admin Routes Compliance: `kanban/tests/api/test_system_status.py::test_assert_admin_routes_protected_compliance` PASSED (0.66s).
- Frontend Vitest Suite (`unit-test-results.txt`):
  - `src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`: 31 passed in 2346ms.
  - Coverage: 99.77% statements, 95.68% branch, 100% funcs, 100% lines on `WorkspaceSettingsPage.tsx`.
  - Design tokens: `cssTokensAudit.test.ts` passed 4/4 in 14ms (0 inline JSX style props).
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check .`: Clean (All checks passed).
  - `uv run ruff format --check .`: Clean (1942 files already formatted).
  - `uv run mypy`: Clean (Success: no issues found in 1115 source files).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean (0 errors).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Per-Workspace Retention | `7..365` days range validation | Enforced via Pydantic validator | PASS |
| AAL2 Step-Up Protection | Retention update requires fresh AAL2 (<= 900s) | Checked against `caller.aal2_verified_at` | PASS |
| Shortened Retention Warning | Warning event recorded on retention reduction | `TRASH_RETENTION_SHORTENED_WARN` emitted | PASS |
| Multi-Object Sweep | Purges all expired trashed entity types | Sweeps issues, docs, stickies, cycles, views, etc. | PASS |
| ACL DENY Trash Isolation | Trashed items with explicit DENY hidden from UI | `evaluate_capabilities` excludes DENY entities | PASS |
| Project Admin Scope | Project Admin sees only items in their projects | Scoped to `admin_project_ids` | PASS |
| 2-Stage Permanent Purge | `SERVER_ADMIN` + token + phrase + reason | Enforced in Stage 1 & Stage 2 | PASS |
| Confirm Phrase Match | Exact phrase `"PURGE ISSUE KAN-7"` | Validated in live proof and test suite | PASS |
| Visual Permission Matrix | Visual ●/◐/○ representation published | Rendered at `/docs/role-and-permission-matrix` | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, retention validators, trash sweep daemon logic, ACL DENY isolation guards, 2-stage permanent purge flows, and unit test suites for KAN-30 on `main` at commit `837f657d` have been thoroughly audited, verified against live container `kanban-liveqa-1`, and certified. All 6 live visual screenshots in `docs/qa/KAN-30/screenshots/` are verified. Ready for Clean-Room Reality-Checker QA.
