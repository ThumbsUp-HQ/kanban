# Clean-Room API Specialist Review: KAN-30 (R2 Live Full-Stack Verification)

**Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
**Date:** 2026-11-20  
**Target:** `main` (commit `07d04cde`)  
**Container Environment:** `http://127.0.0.1:18961` (container: `kanban-liveqa-1`)  
**Live Stack Status:** `LIVE_STACK_VERDICT: PASS`  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-30** (`[KB-P3-AUDIT-24] Add Workspace Admin Trash & Retention Studio, Enforce Per-Workspace Retention & RLS Boundaries, and Publish Visual Role & Permission Matrix`) on `main` at commit `07d04cde`.

The audit incorporates verified evidence from the zero-mock live container execution (`live-fullstack-proof.txt` run on `http://127.0.0.1:18961` with PostgreSQL 16 and `FORCE ROW LEVEL SECURITY`), all 10 live visual screenshots in `docs/qa/KAN-30/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

All requirements and reality-checker findings have been verified on the live stack:
1. `GET /api/v1/admin/trash` (`kanban/api/v1/admin/destructive.py`) enforces typed `limit` and `offset` query pagination with strict bounds checking.
2. Stage 2 permanent cryptographic purge enforces verbatim confirmation phrase input matching and an un-pre-filled audit reason of at least 8 characters, disabling the confirmation button until both conditions are met.
3. `PROJECT_ADMIN` scoped access to `/workspaces/settings#tab-trash` restricts the interface to project-level trash inspection and restoration, hiding workspace general/members/groups tabs, retention policy edit controls, and permanent purge actions.
4. Pluralization typo `Stickys` is completely eliminated from the DOM via `TRASH_FILTER_LABELS` mapping `sticky` to `Stickies`.
5. All 10 live visual screenshots across Desktop, Tablet, and Mobile viewports verify zero horizontal overflow, correct WCAG AA contrast, and layout bounds.
6. Zero console errors, zero page errors, and zero HTTP 5xx errors recorded during live execution.

---

## 2. Zero-Mock Live Full-Stack Execution Verification

### 2.1. Live Container Execution Telemetry (`live-fullstack-proof.txt`)
- Target: `http://127.0.0.1:18961` (container `kanban-liveqa-1`).
- Database: Embedded PostgreSQL 16 with active `FORCE ROW LEVEL SECURITY`.
- Mock Policy: Exactly 0 mocks or stubs (0 mockApi, 0 page.route, 0 context.route).
- Telemetry: Unexpected console errors: 0, Page errors: 0, HTTP 5xx server errors: 0.
- Verdict: `LIVE_STACK_VERDICT: PASS`.

### 2.2. Live Pagination API Validation
Executed against live PostgreSQL 16 with RLS:
- `GET /api/v1/admin/trash?limit=100&offset=0` -> HTTP 200 (`items=4, total=4`).
- `GET /api/v1/admin/trash?limit=2&offset=1` -> HTTP 200 (returns 2 items sliced correctly).
- `GET /api/v1/admin/trash?limit=0` -> HTTP 422 `VALIDATION_FAILED` (`Input should be greater than or equal to 1`).
- `GET /api/v1/admin/trash?limit=501` -> HTTP 422 `VALIDATION_FAILED` (`Input should be less than or equal to 500`).
- Confirms server-side validation rejecting invalid page sizes with HTTP 422.

### 2.3. Live Stage 2 Permanent Cryptographic Purge (KAN-3)
- Stage 1 Request: `POST /api/v1/admin/destructive:request` -> HTTP 200, `confirm_phrase="PURGE ISSUE KAN-3"`.
- Modal Default State Verified:
  * `permanent-purge-confirm-phrase-input` is empty (`""`).
  * `permanent-purge-reason-input` is empty (`""`).
  * `confirm-permanent-purge-btn` is disabled (`disabled=true`).
- Validation Gate: Incorrect confirmation phrase or short reason (<8 characters) keeps the button disabled.
- Valid Submission: Typing exact phrase `"PURGE ISSUE KAN-3"` and audit reason `"Live QA R2 permanent purge check for KAN-30"` enables the button with full danger styling (`backgroundColor="rgb(153, 27, 27)"` / `#991b1b`, `color="rgb(255, 255, 255)"`, `opacity="0.9984"`).
- Stage 2 Execution: `POST /api/v1/admin/destructive:execute` -> HTTP 200:
  ```json
  {
    "status": "executed",
    "target": "KAN-3",
    "target_kind": "issue",
    "target_id": "01a1faaf-02d8-7e31-8649-d221e377be18",
    "mode": "permanent_purge",
    "reason": "Live QA R2 permanent purge check for KAN-30",
    "blast_hash": "c8a468dddebcfd92cd0e3b7441637dc0639fdaec85a2e5e93c0c6083c7bec9c7"
  }
  ```
  Verified: KAN-3 permanently purged and removed from the trash table (`purgedRowCountAfter=0`).

### 2.4. Live PROJECT_ADMIN Isolation & Item Restore
- Authenticated as `@projadmin` (role: `WORKSPACE_MEMBER`, with `PROJECT_ADMIN` on `KAN` only):
  * Non-AAL2 access to `/api/v1/admin/trash` returns HTTP 403 `MFA_ENROLLMENT_REQUIRED`.
  * Post-AAL2 TOTP verification: Loaded `/workspaces/settings#tab-trash` (779ms).
  * Navigation Isolation: `visibleTabCount=1` (only `#tab-trash` visible; General & Policy, Workspace Members, Groups & Governance tabs are hidden).
  * Retention Policy Isolation: Retention policy input and save button are hidden (`saveRetentionBtnCount=0`; zero number inputs in DOM; read-only policy text displayed).
  * Action Isolation: Permanent purge buttons are hidden (`permanentPurgeBtnCount=0`).
  * Scoped Restoration: Clicked Restore on `KAN-2`: `POST /api/v1/admin/trash/...:restore` -> HTTP 200 (`status="restored"`), removing `KAN-2` from the trash table.

### 2.5. Verification of All 10 Live Visual Screenshots
The 10 live visual screenshots in `docs/qa/KAN-30/screenshots/` were inspected on disk:
1. `live-desktop-light.png` (1440x900 Light): Full-page capture showing `Stickies` pill, clean table rendering, zero horizontal overflow (`scrollWidth=1440`).
2. `live-desktop-dark.png` (1440x900 Dark): Dark mode theme token contrast compliant with WCAG AA.
3. `live-tablet.png` (768x1024 Light): Responsive tablet layout without horizontal clipping (`scrollWidth=768`).
4. `live-mobile.png` (390x844 Light): Responsive mobile layout with horizontal scroll container for wide table columns (`scrollWidth=390`).
5. `live-purge-modal.png`: Stage 2 Permanent Cryptographic Purge modal showing typed confirmation phrase, audit reason, and enabled `#991b1b` danger button.
6. `live-projadmin-trash-desktop-light.png`: Trash studio loaded under `@projadmin`, displaying only `#tab-trash`, read-only retention text, and restore actions.
7. `live-role-matrix-desktop-light.png`: Role and permission matrix documentation at `/docs/role-and-permission-matrix` showing glyphs (`● / ◐ / ○`).
8. `live-role-matrix-desktop-dark.png`: Role matrix dark mode contrast.
9. `live-role-matrix-tablet.png`: Role matrix tablet rendering (`scrollWidth=768`).
10. `live-role-matrix-mobile.png`: Role matrix mobile rendering (`scrollWidth=390`).

---

## 3. Technical & Architectural Audit

### 3.1. Trash Pagination Implementation (`kanban/api/v1/admin/destructive.py`)
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
- Query Statement: `.order_by(ObjectRecord.deleted_at.desc()).offset(offset).limit(limit)`.
- Enforces strict validation: `limit` bounds [1, 500] and `offset >= 0`. Out-of-bounds requests return HTTP 422.
- Verified by unit test `test_admin_trash_pagination_limit_and_offset` in `kanban/tests/api/test_admin_trash_api.py`.

### 3.2. Authorization & Invariant Compliance
- **Admin AAL2 Route Protection**: `Depends(require_admin_aal2)` enforced on all `/api/v1/admin/*` endpoints (`test_assert_admin_routes_protected_compliance` passed).
- **Capability Scoping**: `destructive.py:263-276` filters non-workspace admins to projects where they hold administrative capabilities.
- **Permanent Purge Restriction**: Permanent cryptographic purge requires `SERVER_ADMIN` authority and verified 2-stage token validation.
- **Pluralization Fix**: `TRASH_FILTER_LABELS` explicitly maps `sticky` to `Stickies`, preventing any appearance of `Stickys`.

---

## 4. Test Suite and Static Analysis Verification

### 4.1. Unit Test Coverage (`unit-test-results.txt`)
- **Backend Pytest**: 51/51 tests passed in 53.20s across 7 test suites.
  * `kanban/api/v1/admin/destructive.py`: 95% statement coverage.
  * `kanban/api/v1/admin/workspace_settings.py`: 94% statement coverage.
  * `kanban/api/v1/schemas/issue_delete.py`: 100% statement coverage.
  * `kanban/jobs/trash_purge.py`: 95% statement coverage.
  * `kanban/services/activity.py`: 96% statement coverage.
  * `kanban/services/destructive_lifecycle.py`: 95% statement coverage.
  * `kanban/services/issue_delete.py`: 95% statement coverage.
  * Overall touched module coverage: **95%** (1,432 statements, 33 missed).
- **Frontend Vitest**: 34/34 tests passed in 2.59s with 0 `act(...)` warnings.
  * `WorkspaceSettingsPage.tsx`: **99.78% statements, 95.11% branch, 100% functions, 100% lines**.
- **CSS Design Tokens**: `cssTokensAudit.test.ts` passed 4/4 (0 inline JSX style properties).

### 4.2. Static Gates (`build-or-typecheck.txt`)
- `kanban-ctl db check-migrations`: All 62 migrations valid, single head `p4_23_oidc_link_intent_fk`.
- `uv run ruff check .`: Clean (all checks passed).
- `uv run ruff format --check .`: Clean (1,966 files inspected, formatted).
- `uv run mypy`: Clean (Success: no issues found in 1,125 source files).
- `uv run lint-imports`: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint . --max-warnings 0`: Clean (0 warnings).
- `vite build`: Clean production build completed in 1.20s.
- `python3 -m scripts.check_no_dashes`: Clean (0 em-dashes and 0 en-dashes across codebase and wiki).

---

## 5. Security & Invariant Checklist

| Check / Requirement | Standard | Live Verification | Verdict |
| :--- | :--- | :--- | :--- |
| **Admin Route AAL2** | Route-level dependency | `require_admin_aal2` enforced | PASS |
| **Pagination API** | Limit (1-500) and offset (>=0) | Live 200 and 422 responses verified | PASS |
| **Stage 2 Purge Guard** | Verbatim confirm phrase + reason | Modal requires exact phrase + >=8-char reason | PASS |
| **PROJECT_ADMIN Scoping** | Trash tab access scoped to project | General/Members/Groups and retention edit hidden | PASS |
| **Spelling Hygiene** | Stickies pluralization in filter pills | Explicit mapping via `TRASH_FILTER_LABELS` | PASS |
| **Module Layering** | Unidirectional import boundaries | `agent -> mcp -> kanban -> database` maintained | PASS |
| **Code Style** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Certification Signoff

STATUS: APPROVED

All requirements, reality-checker remediations, live container execution telemetry, and visual proofs for KAN-30 have been audited and certified. All 10 live visual screenshots in `docs/qa/KAN-30/screenshots/` are verified. KAN-30 is certified ready for production.
