# Verification Proof & Reality-Checker Submission: KANBA-209

## Metadata
- **Ticket ID:** `KANBA-209`
- **Ticket Title:** [KB-AUDIT-03] Enforce Strict RBAC Route Guards (/admin/standalone, Unauthorized Projects, Guest Dummy KAN) and Hide All Disallowed Controls for Viewer, Guest, and Member
- **Assignee:** `w2-rbac`
- **Worktree Branch:** `feat/w2-rbac`
- **Submission Date:** 2026-11-18

---

## 1. Scope & Verification Packet Inventory

The forensic QA proof packet is organized inside `docs/qa/KANBA-209/`:
- `git-diff.patch`: Complete unified diff against `origin/main` (commit 41a4d8d).
- `changed-files-manifest.txt`: SHA-256 cryptographic hashes and line counts for all 29 touched files.
- `unit-test-results.txt`: Vitest unit test suite run (183 of 183 test files passed, 2,066 of 2,066 tests passed).
- `build-or-typecheck.txt`: Clean `tsc -b` and `vite build` production build log with zero errors.
- `screenshots/`: 42 full-resolution annotated Playwright PNG screenshots covering Light, Dark, Desktop (1440x900), Tablet (1024x768), and Mobile (390x844) viewports.

---

## 2. Requirement Verification Matrix

| Requirement | Implementation Artifacts | Verification Method & Output | Status |
| :--- | :--- | :--- | :---: |
| 1. Admin Route Lockdown (`/admin/standalone`, `/admin/*`) | `kanban/web/src/app/routes.tsx` (`AdminRouteGuard`), `NotFoundView` | Playwright test `06-admin-standalone-guard`, renders exact "Not found or no access" for non-server-admin, 0 system UI leak | PASS |
| 2. Purge Synthetic Dummy `KAN` Fallback | `kanban/web/src/app/routes.tsx` (`WorkspaceHomeInner`), `kanban/web/src/app/Sidebar.tsx` | Playwright test `01-guest-empty-home`, 0 KAN cards rendered, exact "No accessible projects" text | PASS |
| 3. Direct URL Access to Unauthorized Projects | `kanban/web/src/app/routes.tsx` (`ProjectRouteContainer`) | Playwright test `07-unauthorized-project-guard`, renders exact "Not found or no access", 0 sidebar project links | PASS |
| 4. Fail-Closed Project Capabilities in Cycles & Modules | `kanban/web/src/app/routes.tsx` (`ProjectCyclesViewInner`, `ProjectModulesViewInner`) | Default capability fallback changed from fail-open `['EDIT', 'ADMIN']` to fail-closed `[]`. Playwright test `03-viewer-readonly-cycles` | PASS |
| 5. Hide All Disallowed Controls for `VIEWER` | `kanban/web/src/app/Sidebar.tsx`, `viewRegistry.tsx`, `ListRow.tsx`, `DocsTreeNav.tsx`, `StickyCard.tsx`, `IssueSurface.tsx` | Playwright test `02-viewer-readonly-board`: 0 `+ New work item`, 0 row checkboxes, 0 bulk bar, 0 quick-create shortcuts, 0 edit buttons | PASS |
| 6. Hide Disallowed Controls for `MEMBER` | `kanban/web/src/app/Sidebar.tsx`, `routes.tsx`, `ListView.tsx` | Playwright test `04-member-restricted-home` and `05-member-restricted-board`: 0 `+ Create Project`, 0 `+ Workflow` header, Modules hidden when disabled | PASS |
| 7. Deduplicate Default Workspace | `kanban/web/src/app/Sidebar.tsx` | Workspace switcher deduplicates Default Workspace and displays exact active workspace | PASS |
| 8. >=95% Unit/Branch Coverage | Touched files: `AppShell.tsx` (100%), `Sidebar.tsx` (97.18%), `routes.tsx` (95.68%), `viewRegistry.tsx` (97.92%) | Full unit test suite (183/183 passed, 2,066 passed) | PASS |
| 9. Zero Em/En-Dashes Rule | All codebase changes strictly ASCII hyphens `-` | Verified with `grep -P "[\x{2013}\x{2014}]"` (0 matches) | PASS |

---

## 3. Visual Screenshot Evidence

Directly inspected via `read_file`:
- `01-guest-empty-home-light-desktop.png`: Guest empty workspace home rendering exact "No accessible projects" and 0 dummy KAN cards.
- `01-guest-empty-home-dark-mobile.png`: Mobile (390x844) view of Guest empty state with 0 KAN project cards.
- `02-viewer-readonly-board-light-desktop.png`: Viewer read-only board with 0 `+ New work item` buttons, 0 row checkboxes, and 0 edit buttons.
- `03-viewer-readonly-cycles-dark-tablet.png`: Viewer read-only cycles view omitting `Create New Cycle` form.
- `04-member-restricted-home-light-desktop.png`: Member workspace home with 0 `+ Create Project` buttons and 0 Add Project in sidebar.
- `05-member-restricted-board-dark-mobile.png`: Member board with 0 `+ Workflow` management headers.
- `06-admin-standalone-guard-light-desktop.png`: Non-server-admin accessing `/admin/standalone` renders exact "Not found or no access".
- `07-unauthorized-project-guard-dark-mobile.png`: Direct URL access to unauthorized `/projects/QAADM/issues` renders exact "Not found or no access" with 0 sidebar links.

---

## 4. Request for Reality-Checker Forensic Audit

Please audit this verification packet against the requirements of `KANBA-209` and the project invariants defined in `GEMINI.md`.
