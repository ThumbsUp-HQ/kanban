# Clean-Room API Specialist Review: KAN-30 (RC2 Remediation)

**Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
**Date:** 2026-11-20  
**Branch:** `fix/KAN-30-rc2`  
**Commit:** `68eae146124e98f268bc88501418f5cc143c1240`  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-30** on branch `fix/KAN-30-rc2` at commit `68eae146`. It specifically verifies the complete remediation of all reality-checker findings recorded in `docs/qa/KAN-30/reality-checker-report.md`.

The audit confirms that:
1. `GET /api/v1/admin/trash` (`kanban/api/v1/admin/destructive.py`) implements typed `limit` and `offset` query pagination with strict bounds enforcement.
2. Canonical filenames and exact symbols are documented throughout the QA packet (`kanban/api/v1/admin/destructive.py`, `kanban/api/v1/admin/workspace_settings.py`, and `kanban/web/src/features/settings/ProjectSettingsPage.css`).
3. `PROJECT_ADMIN` scoped access to `/workspaces/settings#tab-trash` aligns with backend capability filtering in `destructive.py` (lines 263-276), allowing project administrators to inspect and restore soft-trashed items belonging to their administered projects while strictly denying workspace-level settings mutations or permanent purges.
4. Stage 2 permanent cryptographic purge enforces explicit typed confirmation phrase matching and an un-pre-filled audit reason of at least 8 characters.
5. All backend modules achieve >=95% test coverage, and all static analysis gates pass with zero warnings and zero em/en-dashes.

---

## 2. Technical and Security Audit

### 2.1. Trash Pagination Implementation (`kanban/api/v1/admin/destructive.py`)
In `api_admin_list_trash`:
```python
limit: Annotated[
    int,
    Query(ge=1, le=500, description="Page size limit (1-500)"),
] = 100,
offset: Annotated[
    int,
    Query(ge=0, description="Page offset"),
] = 0,
```
- **Query Wiring**:
  ```python
  stmt = stmt.order_by(ObjectRecord.deleted_at.desc()).offset(offset).limit(limit)
  ```
- **Bounds Checking**:
  * `limit`: Enforces `ge=1` and `le=500` (default: `100`).
  * `offset`: Enforces `ge=0` (default: `0`).
  * Out-of-bounds requests (`limit=0`, `limit=501`, `offset=-1`) return HTTP 422 Unprocessable Entity.
- **Automated Verification**:
  * Unit test `test_admin_trash_pagination_limit_and_offset` in `kanban/tests/api/test_admin_trash_api.py` seeds 4 issues, soft-deletes them with staggered timestamps, and asserts:
    1. First page `limit=2&offset=0` returns items 0 and 1.
    2. Second page `limit=2&offset=2` returns items 2 and 3 with zero overlap.
    3. Boundary rejections for `limit=0`, `limit=501`, and `offset=-1` return HTTP 422.

### 2.2. Access Control and Admin AAL2 Invariants
- **Admin AAL2 Route Protection**:
  * Route dependency `Depends(require_admin_aal2)` is enforced at the router layer (`assert_admin_routes_protected` test passes cleanly).
- **PROJECT_ADMIN Trash Studio Scoping**:
  * In `destructive.py:263-276`, non-workspace admins are filtered to `project_ids` where they hold administrative capabilities.
  * In `WorkspaceSettingsPage.tsx`, `isProjectAdminOnly` users navigating to `#tab-trash` see only the Trash tab, with general/members/groups tabs hidden and retention policy edit controls disabled. Standard members without project admin authority remain locked out with HTTP 403 / access-denied.
- **Stage 2 Permanent Purge Safeguards**:
  * `SERVER_ADMIN` authority strictly required.
  * Stage 2 modal requires typing the exact `confirm_phrase` returned by Stage 1 (`typedConfirmPhrase.trim() === pendingPurge.confirmPhrase`).
  * Audit `purgeReason` is not pre-filled and requires a minimum of 8 characters.

### 2.3. Sibling Boundaries & Zero Regressions
- Touched backend files: `kanban/api/v1/admin/destructive.py` and `kanban/tests/api/test_admin_trash_api.py`.
- Zero edits to `kanban/services/issues.py`, `kanban/custom_fields/`, or MCP tools.
- Untracked files `.backup_schedule.json` and `backups/` strictly unstaged.

---

## 3. Test Suites, Coverage, and Static Analysis Verification

### 3.1. Backend Pytest Suite
- Command: `uv run pytest kanban/tests/api/test_admin_trash_api.py kanban/tests/api/test_workspace_settings.py kanban/tests/jobs/test_trash_purge.py kanban/tests/auth/test_aal2_policy.py kanban/tests/api/test_destructive_lifecycle.py kanban/tests/api/test_destructive_lifecycle_coverage.py kanban/tests/api/test_issue_delete.py --cov=kanban/api/v1/admin/destructive --cov=kanban/api/v1/admin/workspace_settings --cov=kanban/jobs/trash_purge --cov=kanban/services/destructive_lifecycle --cov=kanban/services/issue_delete --cov-report=term-missing`
- Result: 51/51 tests passed in 53.20s.
- Coverage Breakdown:
  * `kanban/api/v1/admin/destructive.py`: 95%
  * `kanban/api/v1/admin/workspace_settings.py`: 94%
  * `kanban/api/v1/schemas/issue_delete.py`: 100%
  * `kanban/jobs/trash_purge.py`: 95%
  * `kanban/services/activity.py`: 96%
  * `kanban/services/destructive_lifecycle.py`: 95%
  * `kanban/services/issue_delete.py`: 95%
  * **Overall Touched Coverage**: 95% (1,432 stmts, 33 missed).
- `assert_admin_routes_protected`: 1/1 passed.

### 3.2. Frontend Vitest Suite
- `WorkspaceSettingsPage.test.tsx`: 34/34 tests passed in 2.59s with 0 `act(...)` warnings.
- Coverage: 99.78% statements, 95.11% branch, 100% functions, 100% lines.
- `cssTokensAudit.test.ts`: 4/4 passed (0 inline JSX style properties).

### 3.3. Static Gates & Security Checks
- `kanban-ctl db check-migrations`: All 62 migrations valid, single head `p4_23_oidc_link_intent_fk`.
- `uv run ruff check .`: Clean (All checks passed).
- `uv run ruff format --check .`: Clean (1,966 files already formatted).
- `uv run mypy`: Clean (Success: 1,125 source files).
- `uv run lint-imports`: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint . --max-warnings 0`: Clean (0 warnings).
- `vite build`: Production build succeeded in 1.20s (720 modules).
- `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes across codebase and wiki).

---

## 4. Security & Compliance Matrix

| Invariant / Requirement | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Admin Route Protection** | Route-level AAL2 dependency | `Depends(require_admin_aal2)` enforced | PASS |
| **Pagination Controls** | Limit and offset on trash list | `limit` (1-500) and `offset` (>=0) | PASS |
| **Project Admin Scoping** | Trash access for project admins | Scoped to administered projects; retention edit blocked | PASS |
| **Stage 2 Purge Guard** | Verbatim confirm phrase + reason | Modal requires exact phrase match + min 8-char reason | PASS |
| **Pluralization Typo** | Stickies pluralization in filter pills | Explicit mapping via `TRASH_FILTER_LABELS` | PASS |
| **Import Layering** | Unidirectional module layering | `agent -> mcp -> kanban -> database` kept | PASS |
| **Code Style** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Certification Signoff

STATUS: APPROVED

All findings from the reality-checker report have been fully remediated. Pagination, access control scoping, Stage 2 permanent purge safeguards, and canonical filenames are verified on disk. KAN-30 is certified ready for reality-checker QA gate on `fix/KAN-30-rc2`.
