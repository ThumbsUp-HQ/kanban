# Forensic QA Submission: KANBA-175

**Ticket:** KANBA-175 ([KB-UX-05] Fix Standalone Status Topbar Notification Pill Click/Dismiss, Compose Export 403, and Multi-Workspace Switcher/Creation)
**Worker:** `worker-175`
**Date:** 2026-11-16
**Status:** READY FOR AUDIT

---

## 1. Executive Summary

KANBA-175 resolves critical UX, security, and multi-tenant ergonomics blockers across standalone notifications, compose export access, and multi-workspace lifecycle management:
1. **Interactive Topbar Notification Pill & Session Dismissal:** Fixed portal button blur unmounting in `EmojiHint.tsx` via `onMouseDown={(e) => { e.preventDefault(); }}` and auto-closing popups on action. Added interactive action support directly on pills with defined `onAction`, and implemented a session-persistent `✕` dismiss button on the Standalone warning pill in `HeaderPills.tsx`.
2. **Hardened Standalone Status & Compose Export API:** Allowed authenticated admins to query `/api/v1/admin/standalone/status` and `/api/v1/admin/standalone/compose-export` without 403 `INSUFFICIENT_CAPABILITY` errors, while preserving strict `assert_admin_routes_protected` compliance and scoping `require_server_admin` strictly to encrypted backup triggers. Updated `get_standalone_status()` and `run_pg_dump()` to respect `settings.deployment_mode` and `settings.database_url`.
3. **Multi-Workspace Creation & Instant Switching:** Implemented full REST lifecycle in `kanban/api/v1/workspaces.py` (`GET /api/v1/workspaces`, `POST /api/v1/workspaces`, `POST /api/v1/workspaces/{workspace_id}/switch`) with strict RLS isolation, auto-initialized workspace settings, and automatic role binding. Wired `.kb-workspace-switcher` in `Sidebar.tsx` with a keyboard-accessible dropdown menu, active workspace indicator, instant workspace switching, and a dedicated `CreateWorkspaceModal` adhering to strict CSP rules (zero inline styles).

---

## 2. Verification Artifacts & Deliverables

1. **Unit & Integration Test Execution Logs:**
   - [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-175/unit-test-results.txt):
     - **Backend:** 16/16 tests passed across `test_workspaces_api.py` and `test_system_status.py` in 4.91s (`pytest-9.2.0`, Python 3.12.7).
     - **Backend Coverage:** 97% statement coverage on `kanban/api/v1/workspaces.py` (156 statements, only 2 missed branches).
     - **Frontend:** 62/62 tests passed across `EmojiHint.test.tsx`, `HeaderPills.test.tsx`, `Sidebar.test.tsx`, `CreateWorkspaceModal.test.tsx`, and `StandaloneStatusPanel.test.tsx` in 2.44s.
2. **Build, Typecheck, and Lint Verification:**
   - [build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-175/build-check.txt):
     - **Python (Ruff):** Clean pass with 0 errors across all touched files.
     - **TypeScript Compiler (`tsc -b --noEmit`):** Clean pass with exit code 0.
     - **ESLint:** Clean pass with exit code 0 across all modified and created components.
3. **Changed Files Manifest & Git Patch:**
   - [changed-files-manifest.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-175/changed-files-manifest.txt): Exactly 14 files modified/added.
   - [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-175/git-diff.patch): 95 KB complete unified diff.
4. **Visual Playwright Screenshot Proof:**
   - [standalone-panel-and-workspace-switcher.png](file:///home/adamoutler/kanban/docs/qa/KANBA-175/screenshots/standalone-panel-and-workspace-switcher.png): High-resolution capture showing the topbar notification pill, dismiss control, and the opened multi-workspace switcher dropdown in the sidebar rail.
   - [standalone-panel-opened.png](file:///home/adamoutler/kanban/docs/qa/KANBA-175/screenshots/standalone-panel-opened.png): High-resolution capture showing the Standalone Status Panel with volume persistence details and Compose Export tab.

---

## 3. Detailed Implementation Breakdown

### 3.1 Topbar Notification Pill Click & Session Dismissal
- **`kanban/web/src/components/emoji/EmojiHint.tsx`**:
  - Added optional `onAction?: () => void` and `actionLabel?: string` props to `EmojiHintProps`.
  - Added `onMouseDown={(e) => { e.preventDefault(); }}` on `.emoji-hint-action-btn` to prevent portal unmounting before `onClick` fires.
  - Implemented `ctrl.close(popupId)` immediately after `onAction()` invocation.
  - Added direct click handling on the emoji pill itself when `onAction` is provided.
- **`kanban/web/src/app/HeaderPills.tsx`**:
  - Eliminated all inline `style={{...}}` usages to strictly comply with project CSP invariants.
  - Added session dismissal tracking via `sessionStorage` key `kb_dismiss_standalone_warning`.
  - Added an interactive `✕` dismiss button (`.header-pills__dismiss-btn`) on the Standalone warning pill allowing users to dismiss persistent warnings for their active session without losing click-through access to the status dialog.

### 3.2 Standalone Status & Compose Export Backend
- **`kanban/api/v1/system_status.py`**:
  - Mounted `GET /api/v1/admin/standalone/status` with `SystemStatusResponse` model.
  - Enforced `Depends(require_admin_aal2)` across the entire router to satisfy `assert_admin_routes_protected` security audit compliance.
  - Scoped `require_server_admin` specifically to `POST /backup`, allowing standard authenticated admins to read `/status` and `/compose-export` without 403 `INSUFFICIENT_CAPABILITY` rejections.
  - Passed application settings into `run_pg_dump` for dynamic database connection resolution.
- **`kanban/standalone/export_service.py`**:
  - Updated `get_standalone_status` to respect `settings.deployment_mode` when available.
  - Updated `run_pg_dump` to accept `settings` and `database_url`, parsing database credentials safely via `make_url` with zero shell interpolation.

### 3.3 Multi-Workspace Lifecycle & UI Switcher
- **`kanban/api/v1/workspaces.py`**:
  - `GET /api/v1/workspaces`: Lists all workspaces for `SERVER_ADMIN` principals, and resolves user workspaces by matching caller email or principal membership across tenants.
  - `POST /api/v1/workspaces`: Validates workspace name and kebab-case slug (`^[a-z0-9][a-z0-9-]{1,62}$`), provisions workspace object, auto-initializes `workspace_settings`, and binds the creator as `WORKSPACE_ADMIN`.
  - `POST /api/v1/workspaces/{workspace_id}/switch`: Verifies access, auto-provisions `WORKSPACE_ADMIN` binding if caller is `SERVER_ADMIN`, issues rotated session cookie and CSRF tokens, and returns updated session context.
- **`kanban/web/src/app/Sidebar.tsx` & `Sidebar.css`**:
  - Replaced static placeholder button with interactive `.kb-workspace-switcher` featuring dynamic current workspace name display.
  - Added accessible dropdown menu (`.kb-workspace-dropdown`) listing tenant workspaces with active indicator checkmark (`✓`).
  - Added "+ Create New Workspace" action button opening `CreateWorkspaceModal`.
  - Implemented keyboard navigation, outside click dismissal, and escape key handling.
  - Strictly enforced CSS-only styling with zero inline `style={{...}}`.
- **`kanban/web/src/features/workspaces/CreateWorkspaceModal.tsx` & `CreateWorkspaceModal.css`**:
  - Accessible modal dialog with focus trapping, backdrop scrim, and escape closing.
  - Automatic kebab-case slug generation from workspace display name.
  - Full error boundary rendering and CSRF token propagation.

---

## 4. Forensic Compliance & Invariants Checklist

- [x] **Zero Inline Styles (Strict CSP):** All styles located in `Sidebar.css`, `CreateWorkspaceModal.css`, and `HeaderPills.css`. Zero `style={{...}}` introduced.
- [x] **Zero Warnings / Safe Typing:** Clean `uv run ruff check` on Python; clean `tsc -b --noEmit` and `eslint` on TypeScript.
- [x] **Code Coverage Invariant (>= 95%):** Achieved 97% unit test coverage on `kanban/api/v1/workspaces.py` with 7 comprehensive integration test cases.
- [x] **Security Invariants:** `assert_admin_routes_protected` verified compliant; RLS session isolation verified across cross-workspace endpoints; secrets zeroized and redacted.
- [x] **Documentation Style Guide:** Plain ASCII hyphens utilized throughout QA and public documentation. Zero em-dashes or en-dashes.
