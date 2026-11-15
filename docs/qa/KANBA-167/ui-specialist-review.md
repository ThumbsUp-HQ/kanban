# UI Specialist Gate Review: KANBA-167 (KB-QA-06)

- **Ticket**: `KANBA-167` (`KB-QA-06`: Topbar user menu with Logout & Admin/Settings navigation, `StandaloneStatusPanel` route `/admin/standalone`, Sidebar `Custom Fields` link, and clean workspace/project sub-routes)
- **Reviewer**: `@ui-specialist` (UI Designer & UX Architect)
- **Scope**:
  - `kanban/web/src/app/Topbar.tsx`
  - `kanban/web/src/app/Topbar.css`
  - `kanban/web/src/app/Sidebar.tsx`
  - `kanban/web/src/app/Sidebar.css`
  - `kanban/web/src/app/routes.tsx`
  - `kanban/web/src/app/AppShell.css`
- **Verdict**: **APPROVED**

---

## 1. Visual Proof Inspection (6 Viewport Screenshots Verified)

All 6 Playwright screenshots in `docs/qa/KANBA-167/screenshots/` were directly inspected via binary read:

| File | Viewport | Verified Visual & Layout State |
| :--- | :--- | :--- |
| `topbar-user-menu-desktop.png` | `1440x900` | Open Topbar avatar menu (`role="menu"`, `aria-label="User settings"`) showing `THEME` (`Light`, `Dark`, `System`), divider, `SETTINGS & ADMIN` links (`Personal MCP Keys`, `Workspace MCP Keys`, `Admin Auth Studio`, `Admin MCP Keys`, `Standalone Status & Backup`), divider, and accessible `Log out` action. Left `Sidebar` displays `Custom Fields` under project sub-items. |
| `topbar-user-menu-tablet.png` | `834x1112` | Properly anchored right-aligned popover menu over tablet layout switcher and issue list. |
| `topbar-user-menu-mobile.png` | `390x844` | Clean popover alignment within mobile viewport without horizontal overflow. |
| `standalone-status-desktop.png` | `1440x900` | `/admin/standalone` rendering `StandaloneStatusPanel` inside `AppShell` with `Persistent Volume Mounted /var/lib/kanban/data (ext4)` green status badge, `Tier A Wasmtime: Active`, `Tier B nsjaill CLI Sandbox: Active`, `Encrypted Database Backup` passphrase form, and `Production Compose Export & Promotion` actions + PostgreSQL 16 runbook. |
| `standalone-status-tablet.png` | `834x1112` | Centered standalone status card on tablet viewport with full form and runbook legibility. |
| `standalone-status-mobile.png` | `390x844` | Responsive stacked action buttons (`Download docker-compose.yml`, `Copy .env.example`) and runbook on mobile viewport. |

---

## 2. UI/UX Architecture & Security Invariants

1. **Strict CSP `style-src 'self'` Compliance**:
   - Verified zero `dangerouslySetInnerHTML` and zero inline `style={{...}}` attributes in `Topbar.tsx`, `Sidebar.tsx`, and `routes.tsx`.
   - All avatar menu, divider, link, and `.kb-avatar-logout` rules reside in `kanban/web/src/app/Topbar.css` using `tokens.css` variables.
2. **Light & Dark Theme Contrast**:
   - `.kb-avatar-logout` uses `var(--danger-fg, #dc2626)` in light theme and `#fca5a5` under `[data-theme="dark"]`, ensuring WCAG AA contrast across themes.
3. **Complete Sidebar & Admin Route Coverage**:
   - Mounted `<StandaloneStatusPanel />` at `/admin/standalone` and dedicated workspace/project views at `/drafts`, `/your-work`, `/projects/:projectKey/cycles`, `/projects/:projectKey/modules`, and `/projects/:projectKey/views`.
4. **Typography & Automated Verification**:
   - 102/102 unit tests passing (`unit-test-results.txt`), `typecheck` / `lint` / `vite build` exit 0 (`build-check.txt`), zero Unicode em/en-dashes.

Verdict: APPROVED
