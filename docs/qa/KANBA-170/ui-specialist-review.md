# UI Specialist Gate Review: KANBA-170 (KB-QA-02)

- **Ticket**: `KANBA-170` (`KB-QA-02`: Authentication route guard `/setup` & `/login` redirects, Workspace Home dashboard on `/`, and unified `AppShell` issue workspace with persistent background board on `?peek=`)
- **Reviewer**: `@ui-specialist` (UI Designer & UX Architect)
- **Scope**:
  - `kanban/web/src/App.tsx`
  - `kanban/web/src/app/routes.tsx`
  - `kanban/web/src/app/AppShell.tsx`
  - `kanban/web/src/app/AppShell.css`
  - `kanban/web/src/features/auth/useSessionGuard.ts`
- **Verdict**: **APPROVED**

---

## 1. Visual Proof Inspection (6 Viewport Screenshots Verified)

All 6 Playwright screenshots in `docs/qa/KANBA-170/screenshots/` were directly inspected via binary read:

| File | Viewport | Verified Visual & Layout State |
| :--- | :--- | :--- |
| `home-desktop.png` | `1440x900` | Full `AppShell` (`Sidebar` 256px + `Topbar` 52px + `WorkspaceHomeView` main canvas), `+ Create Project` and `+ New Work Item` header actions, responsive project cards (`KAN` and `SEC`) with quick links (`Work Items ->`, `Board`, `Stickies`, `Docs`, `Custom Fields`). |
| `home-tablet.png` | `834x1112` | Collapsible hamburger sidebar trigger in `Topbar`, 2-column project card grid with breathable padding (`var(--board-canvas-pad)`). |
| `home-mobile.png` | `390x844` | Single-column stacked header CTA buttons and project cards, zero horizontal overflow. |
| `issues-appshell-desktop.png` | `1440x900` | `/projects/KAN/issues` rendered inside `AppShell` with persistent left `Sidebar`, `Topbar` (`List` / `Board` / `Table` / `Calendar` / `Timeline` switcher), filter bar, and grouped work item rows. |
| `issues-appshell-tablet.png` | `834x1112` | Responsive `AppShell` header and issue list groups (`Backlog`, `Todo`, `In Progress`, `In Review`, `Done`, `Cancelled`). |
| `issues-appshell-mobile.png` | `390x844` | Compact mobile topbar and filter toolbar with full list accessibility. |

---

## 2. UI/UX Architecture & Security Invariants

1. **Strict CSP `style-src 'self'` Compliance**:
   - Verified zero `dangerouslySetInnerHTML` and zero inline `style={{...}}` attributes across `App.tsx`, `AppShell.tsx`, and `routes.tsx`.
   - All `WorkspaceHomeView` and `ProjectSavedViewsView` layout styles reside in `kanban/web/src/app/AppShell.css` using `tokens.css` variables.
2. **Pre-Session Route Guard (`useSessionGuard.ts`)**:
   - Unclaimed server redirects cleanly to `/setup` before rendering workspace placeholders.
   - Unauthenticated requests on claimed servers redirect cleanly to `/login`.
3. **Unified `AppShell` & Persistent Peek Drawer Context**:
   - `/projects/:projectKey/issues` now renders inside `AppShell` (`ProjectIssuesRoute` -> `IssuesWorkspaceRoute`), keeping the Sidebar, Topbar, and background List/Board mounted when `?peek=<KEY>` opens the right-hand `IssueSurface` drawer.
4. **Typography & Automated Verification**:
   - 102/102 unit tests passing (`unit-test-results.txt`), `typecheck` / `lint` / `vite build` exit 0 (`build-check.txt`), zero Unicode em/en-dashes.

Verdict: APPROVED
