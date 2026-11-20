# API Specialist Review: KAN-30 (KB-P3-AUDIT-24)

- Ticket: KAN-30
- Title: [KB-P3-AUDIT-24] Add Workspace Admin Trash & Retention Studio, Enforce Per-Workspace Retention & RLS Boundaries, and Publish Visual Role & Permission Matrix (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan30-112e571f`
- Target Branch: `feat/KAN-30`
- Commit: `29fa13e88dcc058d8fa3d20206ba13e8cf13f3ae`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-30 on branch `feat/KAN-30` (commit `29fa13e8`) and wiki repository (commit `899dec9`).

The ticket resolves four primary problems:
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
   - Authored `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Role-and-Permission-Matrix.md` (commit `899dec9`), linked in `_Sidebar.md`.
   - Documented fine-grained capabilities across all 7 principal tiers using standardized visual indicators (`●` Allowed by role, `◐` Conditional, `○` Never allowed).

All API contracts, security invariants, tenant boundaries, administrative AAL2 step-up protections, and test coverage requirements are verified and approved:
- Exact problem response structure and capability enforcement: Callers lacking AAL2 or with stale sessions (`> 900s`) receive HTTP 403 `AAL2_REQUIRED` or `AAL2_STALE`.
- High test coverage: 50/50 Pytest tests pass in 52.04s with 95% overall statement coverage across touched backend files (`destructive.py` 95%, `workspace_settings.py` 95%, `issue_delete.py` 100% schemas / 95% services, `trash_purge.py` 95%, `activity.py` 96%, `destructive_lifecycle.py` 95%). 31/31 Vitest tests pass in 3.80s with 99.76% statement / 95.79% branch coverage on `WorkspaceSettingsPage.tsx`.
- Zero external runtime packages added (`Apache-2.0` compliant).
- Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Linear migration chain: 62 valid migrations, single head `p4_23_oidc_link_intent_fk`.
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

### 2.5 Published Role and Permission Matrix (`Role-and-Permission-Matrix.md`)
- File: `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Role-and-Permission-Matrix.md` (commit `899dec9`), linked in `_Sidebar.md`.
- Content Verification:
  - Defines the 7 principal tiers: `Guest`, `Viewer`, `Member`, `Project Admin`, `Workspace Admin`, `Server Admin`, and `Scoped MCP Agent`.
  - Visual status symbols: `●` (Allowed by role), `◐` (Conditional), `○` (Never allowed).
  - Explicit documentation of:
    - Absolute `DENY` precedence (effective bitmask collapse).
    - Fresh AAL2 step-up requirement (`<= 900s`).
    - 2-stage cryptographic confirmation tokens for permanent purge.
    - Scoped MCP agent token narrowing and tool permission filters.
    - Immutable audit ledger protection (no UPDATE/DELETE grants).
  - Strictly 0 em-dashes and 0 en-dashes (`check_no_dashes` passed cleanly).

### 2.6 Test Suites and Coverage Verification
- Backend Pytest Suite:
  - `kanban/tests/api/test_admin_trash_api.py`: 5/5 passed (listing, kind filtering, search, project scope, and ACL DENY isolation).
  - `kanban/tests/api/test_workspace_settings.py`: 13/13 passed (retention bounds, fresh AAL2 step-up <= 900s, and warning audit emission).
  - `kanban/tests/jobs/test_trash_purge.py`: 9/9 passed (multi-object sweep, cascade handling, and link purging).
  - `kanban/tests/api/test_destructive_lifecycle.py` & `test_destructive_lifecycle_coverage.py`: 12/12 passed.
  - `kanban/tests/api/test_issue_delete.py`: 8/8 passed.
  - `kanban/tests/auth/test_aal2_policy.py`: 3/3 passed.
  - Total: 50/50 tests passed in 52.04s.
  - Statement coverage across touched files:
    - `kanban/api/v1/admin/destructive.py`: 95%
    - `kanban/api/v1/admin/workspace_settings.py`: 95%
    - `kanban/api/v1/schemas/issue_delete.py`: 100%
    - `kanban/jobs/trash_purge.py`: 95%
    - `kanban/services/activity.py`: 96%
    - `kanban/services/destructive_lifecycle.py`: 95%
    - `kanban/services/issue_delete.py`: 95%
    - Combined coverage: 95% (1431 stmts, 33 miss).
- Frontend Vitest Suite:
  - `src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`: 31/31 passed in 3.80s.
  - Coverage: 99.76% statements, 95.79% branch, 100% funcs, 100% lines on `WorkspaceSettingsPage.tsx`.
  - Design tokens: `cssTokensAudit.test.ts` passed 4/4 (0 inline JSX style props).

### 2.7 Security, Architectural Boundary, and Code Style Compliance
- Dependency Invariant: Zero external runtime packages added (`Apache-2.0` compliant).
- Boundary Invariant: `lint-imports` confirms strict unidirectional layering (`agent -> mcp -> kanban -> database`), 2 kept, 0 broken.
- Database Invariant: `kanban-ctl db check-migrations` validates all 62 migrations with single head `p4_23_oidc_link_intent_fk`.
- Static Typecheck: `mypy` passed with zero errors across 1107 source files; `tsc -b --noEmit` passed with zero diagnostics.
- Linter: `ruff check` and `ruff format --check` clean; `eslint` passed with zero warnings.
- Punctuation Standard: Zero em-dashes and zero en-dashes across all code, tests, and documentation (`check_no_dashes` clean).

---

## 3. Specialist Checklist

1. [x] `workspaces.trash_retention_days` validated between 7 and 365 days
2. [x] Modifying retention days enforces fresh AAL2 step-up (`<= 900s`)
3. [x] Shortening retention days records `ActivityEventType.TRASH_RETENTION_SHORTENED_WARN`
4. [x] `destructive_lifecycle.py` enforces tenant boundary clause `.where(..., Issue.workspace_id == caller.workspace_id)`
5. [x] `trash_purge.py` sweeps all expired trashed object types (`issues`, `docs`, `pages`, `stickies`, `cycles`, `modules`, `views`, `projects`)
6. [x] Project dependencies purged under `SET LOCAL kanban.allow_project_delete = 'on'`
7. [x] `GET /api/v1/admin/trash` protected by `Depends(require_admin_aal2)`
8. [x] Filter by `kind`, `project_id`, and `q` supported
9. [x] Evaluates `evaluate_capabilities(session, caller, obj.id)` so explicit ACL `DENY` items never leak
10. [x] Project Admins restricted to items in projects they administer
11. [x] `POST /api/v1/admin/trash/{target_id}:restore` allows Workspace and Server Admins to restore items
12. [x] Permanent purge remains strictly restricted to `SERVER_ADMIN` + fresh AAL2 + 2-stage tokens
13. [x] `#tab-trash` integrated in `WorkspaceSettingsPage.tsx` with bidirectional URL hash sync
14. [x] Visual Role and Permission Matrix published on wiki (`Role-and-Permission-Matrix.md`)
15. [x] 50/50 Pytest tests pass with 95% coverage on touched backend files
16. [x] 31/31 Vitest tests pass with 99.76% statement coverage on `WorkspaceSettingsPage.tsx`
17. [x] Zero em-dashes or en-dashes across all code, tests, and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

Ticket KAN-30 is verified and approved on branch `feat/KAN-30` (commit `29fa13e8`) and wiki repository (commit `899dec9`). The implementation enforces per-workspace retention boundaries, protects against ACL DENY data leaks in the trash studio, sweeps all expired trashed object types, and provides a clear, authoritative Visual Role & Permission Matrix. Ready for dual specialist signoff and merge into `main`.
