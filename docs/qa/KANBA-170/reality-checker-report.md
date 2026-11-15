# Integration Agent Reality-Based Report - KANBA-170 (`KB-QA-02`)

- **Ticket:** `KANBA-170` (`KB-QA-02`: Authentication route guard `/setup` & `/login` redirects, Workspace Home dashboard on `/`, and unified `AppShell` issue workspace with persistent background board on `?peek=`)
- **Specialist Gate Approvals Verified:**
  - `docs/qa/KANBA-170/api-specialist-review.md` (`@arch-reviewer`: **APPROVED, Grade A**)
  - `docs/qa/KANBA-170/ui-specialist-review.md` (`@ui-specialist`: **APPROVED**)
- **Visual Proof Inspected:** 6 Playwright screenshots (`home-desktop.png`, `home-tablet.png`, `home-mobile.png`, `issues-appshell-desktop.png`, `issues-appshell-tablet.png`, `issues-appshell-mobile.png`) in `docs/qa/KANBA-170/screenshots/`.

## Forensic Verification Matrix

| DoD & Security Criterion | Evidence Verified | Result |
| :--- | :--- | :---: |
| **Pre-Session Initialization & Auth Route Guard (`useSessionGuard.ts`)** | Queries `GET /api/v1/setup/status` (`initialized === false` -> `/setup`) and `GET /api/v1/auth/session` (`authenticated === false` -> `/login`, `mfa_pending === true` -> `/setup`), caching `kb_csrf` cookie. | **PASS** |
| **Workspace Home View on `/` (`routes.tsx`)** | Replaces bare `<RoutePlaceholder route="/" />` with `WorkspaceHomeView`, loading live projects from `GET /api/v1/projects` with `+ Create Project` and `+ New Work Item` CTAs. | **PASS** |
| **Unified `AppShell` & Zero-Remount Peek Drawer (`App.tsx`, `routes.tsx`)** | Removes `AppRoutes()` bypass in `App.tsx`; `/projects/:projectKey/issues` renders inside `ProjectRouteContainer` (`<AppShell>`) and keeps `<IssuesWorkspaceRoute>` mounted when `?peek=` opens `<IssueSurface>`. | **PASS** |
| **Strict CSP `style-src 'self'` & Anti-Enumeration** | Zero `dangerouslySetInnerHTML` and zero inline `style={{...}}` in modified files (`AppShell.css` classes used); pre-fetch `PROJECT_KEY_REGEX` / `ISSUE_KEY_REGEX` validation renders uniform `NotFoundView`. | **PASS** |
| **Unit Tests, Typecheck, Build & No-Dashes Gate** | `unit-test-results.txt` (`13` files, `102/102 passed`), `build-check.txt` (`tsc -b --noEmit` & `vite build` exit `0`), `check_no_dashes` exit `0`. | **PASS** |

## Verdict
- **Overall Quality Rating:** **Grade A**
- **Production Readiness:** **READY**
