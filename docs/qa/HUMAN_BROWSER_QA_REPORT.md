# 👍kanban Human Browser QA Report (Suites 1-8 Forensic Re-Test Audit)

- **Auditor:** `qa-argon-2` (Independent Black-Box Human Browser QA Engineer)
- **Date:** 2026-11-15
- **Container Image Tested:** `adamoutler/thumbs-up-kanban:latest` (`sha256:5f00ccdb787f96d70a2f00fc4d24ace2be2c7ae321b66`, Standalone mode, embedded PostgreSQL 16 + Uvicorn on port `18923`)
- **Test Origin:** `http://localhost:18923` (`KB_PUBLIC_ORIGIN=http://localhost:18923`, `KB_RP_ID=localhost`, `KB_STANDALONE_ALLOW_CLEARTEXT=true`)
- **Browser Harness:** Headless Chromium (`1440x900`, `768x1024`, and `375x812` viewports) via Playwright browser automation driving real DOM interactions (`click`, `fill`, `keyboard.press`, `reload`) with zero backend, CLI, or database shortcuts
- **Screenshot Evidence Directory:** `docs/qa/human-browser-qa-screenshots/` (38 fresh full-page PNG screenshots captured across Suites 1-8 against the unmodified standalone container)

---

## 1. Executive Summary & Self-Hosting Readiness Verdict

**Self-Hosting Readiness Verdict: `READY FOR SELF-HOSTING (ALL 8 SUITES & ALL 7 REMEDIATION TICKETS KANBA-164..KANBA-170 PASS END-TO-END IN CHROMIUM)`**

This black-box human browser QA audit verified the standalone `adamoutler/thumbs-up-kanban:latest` image (`sha256:5f00ccdb787f96d70a2f00fc4d24ace2be2c7ae321b66`) on port `18923` from a completely empty volume (`kb-qa-retest-data`) through full administrative setup, MFA enrollment, logout/re-login, project creation, issue creation/persistence across all 5 views, peek drawer editing (Markdown + Mermaid + workflow transitions + comments), stickies, project docs, custom fields, MCP key minting, Auth Studio, Standalone Status & Backup/Compose export, security headers, and responsive viewports.

### Remediation Verification Summary (`KANBA-164`..`KANBA-170`)

| Remediation Ticket | Scope | Re-Test Status | Summary of Browser Verification |
| :--- | :--- | :---: | :--- |
| **`KANBA-164`** | Peek Drawer background preservation (`?peek=...`), Markdown/Mermaid save, workflow state change, comments | **PASS** | Clicking `SELF-1` on the Board opens `.surface--drawer` while keeping the background Board (`SELF-2`, `SELF-3`), Sidebar, and Topbar visible behind it. Editing and saving Markdown + Mermaid persists (`PATCH /api/v1/issues/SELF-1` -> `200 OK`) and renders `[data-testid="issue-mermaid-diagram"]` SVG. Changing state to `In Progress` persists (`200 OK`). Posting a comment via `CommentComposer` sends `X-CSRF-Token` (`POST /api/v1/issues/SELF-1/comments` -> `201 Created`) and persists across `F5` reload. |
| **`KANBA-165`** | `/setup` CSRF bootstrap (`__Host-kb_csrf` / `kb_csrf`), `#setup-email` field, 3-step Setup -> MFA -> Recovery Codes | **PASS** | Step 1 (`/setup?token=...`) renders `#setup-email`, bootstraps CSRF via `GET /api/v1/auth/session` (`200 OK`), and submits `POST /api/v1/setup/claim` (`200 OK`). Step 2 TOTP enrollment (`POST /api/v1/auth/mfa/totp/enroll` -> `200 OK` and `POST /api/v1/auth/mfa/totp/confirm` -> `200 OK`) succeeds under the non-superuser `kanban_app` role. Step 3 displays 10 single-use recovery codes and redirects to `/` upon acknowledgment. |
| **`KANBA-166`** | Project creation UI (`CreateProjectModal`), live PostgreSQL issues on `/projects/:key/issues`, `F5` persistence, Board state matching | **PASS** | `+ Create Project` opens `CreateProjectModal`, creates project `SELF` (`Self Host QA`) via `POST /api/v1/projects` (`201 Created`), and updates both the Sidebar and `/` Workspace Home. Pressing `c` / clicking `+ New work item` creates live PostgreSQL issues (`SELF-1`, `SELF-2`, `SELF-3` via `POST /api/v1/projects/SELF/issues` -> `201 Created`), which survive `F5` reload and render inside the `Todo` column on `?layout=board` (`Todo 3`) as well as `List`, `Table`, `Calendar`, and `Timeline` views. |
| **`KANBA-167`** | `/stickies` `+ New Sticky` button & `/projects/:key/docs` tree endpoint (`zero 404 /api/v1/docs/.../tree`) | **PASS** | `/stickies` renders `+ New Sticky` (`[data-testid="new-sticky-btn"]`), creates a sticky in PostgreSQL, autosaves Markdown edits (`200 OK`), triggers the >400-char smart Doc promotion suggestion, and persists across `F5`. `/projects/SELF/docs` calls `GET /api/v1/projects/SELF/docs/tree` (`200 OK` - zero 404 tree errors) and persists created/edited pages across `F5` reload. |
| **`KANBA-168`** | CSRF header wiring on Custom Fields, MCP Key Minting, Admin Auth Studio, Standalone Status | **PASS** | Creating Custom Field `CVSS Score` (`cvss-score`, `NUMBER`) on `/projects/SELF/settings/custom-fields` succeeds (`201 Created`). Minting an MCP key on `/settings/mcp` succeeds (`201 Created`) and displays the one-time secret modal + table row. `/admin/auth` (`GET /api/v1/auth/me` -> `200 OK`, `GET /api/v1/admin/auth/cards` -> `200 OK`) and `/admin/standalone` (`StandaloneStatusPanel` with Encrypted Database Backup and Production Compose Export) load and operate cleanly. |
| **`KANBA-169`** | `Content-Security-Policy` `img-src` directive syntax (`img-src 'self' blob: data:;`) & column-scoped `local_admin_credentials` privilege | **PASS** | `Content-Security-Policy` emits valid `img-src 'self' blob: data:;` with zero CSP console errors across all routes, and `kanban_app` has column-scoped `SELECT (principal_id, username)` + RLS access on `local_admin_credentials` without exposing `password_hash`. |
| **`KANBA-170`** | Uninitialized guard (`GET /` -> `/setup`), Topbar Avatar menu (Logout, MCP, Admin, Standalone, Theme), Sidebar navigation | **PASS** | Uninitialized `GET /` redirects immediately to `/setup`. Topbar Avatar menu exposes user identity, Theme switcher, `Personal MCP Keys`, `Workspace MCP Keys`, `Admin MCP Keys`, `Admin Auth Studio`, `Standalone Status & Backup`, and `Log out`. All Sidebar project links (`Work Items`, `Cycles`, `Modules`, `Views`, `Docs (Pages)`, `Custom Fields`) render functional pages inside `AppShell`. |

---

## 2. Suite-by-Suite Pass/Fail Matrix

| Suite & Test Case | Status | URL(s) Tested | Network Calls Observed | Console / HTTP Findings | Screenshot Evidence |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **1.1 Uninitialized Guard (`GET /` -> `/setup`)** | **PASS** | `http://localhost:18923/` | `GET /api/v1/auth/session` (`200`), `GET /api/v1/system/status` (`401`), `GET /api/v1/auth/cards` (`200`) | Automatically redirects uninitialized `GET /` to `http://localhost:18923/setup` and displays `"Missing or invalid first-boot setup token. Check your container logs for the /setup?token=... URL."` | `suite1_1_unauthenticated_root.png` |
| **1.2 First-Boot Claim Page (`/setup?token=...` Step 1 of 3)** | **PASS** | `http://localhost:18923/setup?token=kb_setup_...` | `GET /api/v1/auth/session` (`200`, issues `kb_csrf`), `POST /api/v1/setup/claim` (`200`) | `#setup-username`, `#setup-display-name`, `#setup-email`, `#setup-password`, and `#setup-confirm-password` all render and submit cleanly with `X-CSRF-Token`, advancing to `STEP 2 OF 3`. | `suite1_2_setup_page_initial.png`, `suite1_2_setup_filled.png`, `suite1_2_after_submit.png` |
| **1.3 Mandatory AAL2 MFA Enrollment & Recovery Codes (Steps 2 & 3 of 3)** | **PASS** | `http://localhost:18923/setup` | `POST /api/v1/auth/mfa/totp/enroll` (`200`), `POST /api/v1/auth/mfa/totp/confirm` (`200`) | On the unmodified container, TOTP secret enrolls cleanly (`200 OK`), 6-digit TOTP code confirms (`200 OK`), Step 3 displays 10 single-use recovery codes, and `Continue to Workspace` lands on `/`. | `suite1_3_setup_step2_mfa.png`, `suite1_3_setup_step2_totp_key.png`, `suite1_3_setup_step3_recovery_codes.png`, `suite1_4_workspace_after_setup.png` |
| **1.4 Browser Logout & TOTP Re-Login (`/login`)** | **PASS** | `/`, `/login` | `POST /api/v1/auth/logout` (`200`), `GET /api/v1/auth/cards` (`200`), `POST /api/v1/auth/local/login` (`200`), `POST /api/v1/auth/mfa/totp/verify` (`200`) | Topbar avatar menu -> `Log out` clears session and redirects to `/login`. Selecting `Local Admin`, submitting credentials, and verifying 6-digit TOTP code restores AAL2 session and redirects to `/`. | `suite2_1_avatar_clicked.png`, `suite2_2_login.png`, `suite2_2_login_local_admin_filled.png`, `suite2_2_login_mfa_step.png`, `suite2_2_after_relogin.png` |
| **2.1 Create Project `SELF` (`Self Host QA`) via UI** | **PASS** | `/`, `/projects/SELF/issues` | `POST /api/v1/projects` (`201`), `GET /api/v1/projects` (`200`), `GET /api/v1/projects/SELF/issues` (`200`) | Clicking `+ Create Project` opens `CreateProjectModal`. Creating `Self Host QA` (`SELF`) persists to PostgreSQL, navigates to `/projects/SELF/issues`, and lists `Self Host QA` in both the Sidebar and `/` Workspace Home. | `suite3_1_home.png`, `suite3_2_create_project_modal_filled.png`, `suite3_2_after_project_created.png`, `suite3_2_home_with_self_project.png` |
| **2.2 Command Palette (`Ctrl+K`), Theme Toggle & Sidebar Routes** | **PASS** | `/`, `/drafts`, `/your-work`, `/projects/SELF/cycles`, `/projects/SELF/modules`, `/projects/SELF/views` | `GET /api/v1/projects/SELF/cycles` (`200`), `GET /api/v1/projects/SELF/modules` (`200`), `GET /api/v1/projects/SELF/views` (`200`) | `Ctrl+K` opens Command Palette with search + project filter; Theme toggle switches `dark` / `light` on `<html>`; `/drafts`, `/your-work`, `/cycles`, `/modules`, and `/views` all render functional pages inside `AppShell`. | `suite3_command_palette.png`, `suite3_1_theme_dark.png`, `suite3_1_drafts.png`, `suite3_1_your_work.png`, `suite3_1_cycles.png`, `suite3_1_modules.png`, `suite3_1_views.png` |
| **3.1 Create 3+ Issues via `QuickCreateIssueModal` & Verify `F5` Persistence** | **PASS** | `/projects/SELF/issues` | `POST /api/v1/projects/SELF/issues` (`201` x3), `GET /api/v1/projects/SELF/issues` (`200`) | Created `SELF-1` (`Configure TLS termination and HSTS headers`), `SELF-2` (`Verify PostgreSQL RLS policies for multi-tenant isolation`), and `SELF-3` (`Set up automated nightly encrypted backups`). All 3 persist across `F5` (`page.reload()`). | `suite4_1_issues_empty_initial.png`, `suite4_2_press_c_on_issues.png`, `suite4_2_modal_filled.png`, `suite4_2_after_create_before_reload.png`, `suite4_2_after_reload_f5.png` |
| **3.2 Switch Across All 5 Views (`Board`, `List`, `Table`, `Calendar`, `Timeline`)** | **PASS** | `/projects/SELF/issues?layout=board\|list\|table\|calendar\|timeline` | `GET /api/v1/projects/SELF/issues` (`200`) | LayoutSwitcher remains mounted in `AppShell` across all views. `Board` displays all 3 live cards under `Todo 3` (`Backlog 0`, `Todo 3`, `In Progress 0`, `Done 0`, `Canceled 0`). `List`, `Table`, `Calendar`, and `Timeline` all render live PostgreSQL items. | `suite4_3_layout_list.png`, `suite4_3_layout_board.png`, `suite4_1_issues_board.png`, `suite4_3_layout_table.png`, `suite4_3_layout_calendar.png`, `suite4_3_layout_timeline.png` |
| **4.1 Peek Drawer (`?peek=SELF-1`) Background Preservation, Mermaid & State Change** | **PASS** | `/projects/SELF/issues?layout=board&peek=SELF-1` | `GET /api/v1/issues/SELF-1` (`200`), `PATCH /api/v1/issues/SELF-1` (`200`), `POST /api/v1/issues/SELF-1/transitions` (`200`) | Clicking `SELF-1` on the Board opens `.surface--drawer` while keeping the background Board (`SELF-2`, `SELF-3`), Sidebar, and Topbar visible. Saving Markdown + Mermaid renders `[data-testid="issue-mermaid-diagram"]` SVG. Changing state to `In Progress` persists via `/transitions`. | `suite5_1_peek_drawer.png`, `suite5_1_click_kan140.png`, `suite5_2_editing_description.png`, `suite5_2_mermaid_rendered.png` |
| **4.2 Issue Comment Creation & Full-Screen Issue View (`/projects/SELF/issues/SELF-1`)** | **PASS** | `/projects/SELF/issues?layout=board&peek=SELF-1`, `/projects/SELF/issues/SELF-1` | `POST /api/v1/issues/SELF-1/comments` (`201 Created`), `GET /api/v1/issues/SELF-1/comments` (`200`), `GET /api/v1/issues/SELF-1` (`200`) | Clicking `Comment` in `CommentComposer` sends `X-CSRF-Token` (`201 Created`) and renders `"Verified TLS 1.3 cipher suites and HSTS preload header in staging."` in the activity timeline. Full-Screen view (`/projects/SELF/issues/SELF-1`) loads and persists description, `In Progress` state, and comment across `F5`. | `suite5_2_after_comment_and_state.png`, `suite5_2_full_issue.png`, `suite5_2_full_issue_after_reload.png` |
| **5.1 Stickies (`/stickies`) Creation, Autosave, Promotion Banner & `F5` Persistence** | **PASS** | `/stickies` | `POST /api/v1/projects/SELF/stickies` (`201`), `PATCH /api/v1/stickies/{id}` (`200`), `GET /api/v1/projects/SELF/stickies` (`200`) | Clicking `+ New Sticky` creates a sticky card, autosaves >400-char Markdown content, displays `"This sticky is getting detailed. Consider promoting it to a Doc or Issue."` (`Promote to Doc` / `Promote to Issue`), and persists across `F5` reload. | `suite6_1_stickies.png`, `suite6_after_click_new_sticky.png`, `suite6_2_stickies_after_reload.png` |
| **5.2 Project Docs (`/projects/SELF/docs`) Tree Load, Page Creation, Edit & `F5` Persistence** | **PASS** | `/projects/SELF/docs` | `GET /api/v1/projects/SELF/docs/tree` (`200`), `POST /api/v1/docs` (`201`), `POST /api/v1/docs/{id}/pages` (`201`), `PATCH /api/v1/pages/{id}` (`200`) | Zero `404 /api/v1/docs/.../tree` errors! Creating `"Self-Hosting Runbook & Architecture"` (`Self-Host Operations Guide`), editing Markdown content, and pressing `F5` persists the page in the tree and editor. | `suite7_1_docs.png`, `suite7_after_click_new_doc.png`, `suite7_after_submit_create_doc.png` |
| **6.1 Custom Fields (`/projects/SELF/settings/custom-fields`)** | **PASS** | `/projects/SELF/settings/custom-fields` | `GET /api/v1/projects/SELF/custom-fields` (`200`), `POST /api/v1/projects/SELF/custom-fields` (`201`) | Reached via Sidebar `Custom Fields` link. Created `CVSS Score` (`cvss-score`, `NUMBER`), which persists in PostgreSQL across `F5` reload and renders `[data-testid="field-item-cvss-score"]`. | `suite8_2_custom_fields.png`, `suite8_2_after_create_custom_field.png` |
| **6.2 MCP Access Studio (`/settings/mcp`, `/workspaces/settings/mcp`, `/admin/mcp`)** | **PASS** | `/settings/mcp`, `/workspaces/settings/mcp`, `/admin/mcp` | `GET /api/v1/mcp/keys` (`200`), `POST /api/v1/mcp/keys` (`201`), `GET /api/v1/mcp/oauth/grants` (`200`) | Reached via Topbar Avatar menu (`Personal MCP Keys`). Minted key `"QA Self-Host Agent Token"` (`201 Created`), displayed one-time secret modal, and rendered active key row in table. | `suite8_1_settings_mcp.png`, `suite8_1_mint_mcp_modal.png`, `suite8_1_after_mint_key_submit.png`, `suite8_1_workspaces_mcp.png`, `suite8_1_admin_mcp.png` |
| **6.3 Admin Auth Studio (`/admin/auth`) & Standalone Status (`/admin/standalone`)** | **PASS** | `/admin/auth`, `/admin/standalone` | `GET /api/v1/auth/me` (`200`), `GET /api/v1/admin/auth/cards` (`200`), `GET /api/v1/system/status` (`200`), `POST /api/v1/system/export-compose` (`200`) | Reached via Topbar Avatar menu. `/admin/auth` displays `Authentication Studio` with `Local Admin` card + Lockout Guard (`GET /api/v1/auth/me` returns `200 OK`). `/admin/standalone` renders `StandaloneStatusPanel` with `Create & Download Backup` and `Production Compose Export` tabs. | `suite2_3_admin_auth.png`, `suite8_3_standalone_status.png` |
| **7.1 Security Headers & Zero CSP Console Errors** | **PASS** | All routes | `GET /` (`200`), `GET /api/v1/system/status` (`200`) | `Content-Security-Policy` emits valid `img-src 'self' blob: data:;`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`. Zero CSP violations logged. | `suite1_4_workspace_after_setup.png` |
| **8.1 Responsive Viewports (`1440x900`, `768x1024`, `375x812`)** | **PASS** | `/projects/SELF/issues?layout=board` | `GET /api/v1/projects/SELF/issues` (`200`) | Desktop (`1440x900`), Tablet (`768x1024`), and Mobile (`375x812`) render cleanly with zero horizontal page overflow (`scrollWidth <= innerWidth`) and working mobile off-canvas sidebar drawer (`Toggle navigation sidebar`). | `suite8_4_responsive_tablet_768x1024.png`, `suite8_4_responsive_mobile_375x812.png`, `suite8_4_responsive_mobile_sidebar_open.png` |

---

## 3. Detailed Forensic Findings by Suite

### Suite 1: First-Boot Initialization, Claim Wizard, AAL2 MFA & Session Lifecycle (`KANBA-165`, `KANBA-169`, `KANBA-170`)

1. **Test 1.1 - Uninitialized Guard (`GET /` -> `/setup`):**
   - **Action:** Opened `http://localhost:18923/` on a brand-new unmodified container (`kb-qa-retest`).
   - **Result (`PASS`):** `AppShell` checks session/setup status on mount and immediately redirects the browser to `http://localhost:18923/setup`, rendering the setup instructions banner (`"Missing or invalid first-boot setup token. Check your container logs for the /setup?token=... URL."`).
   - **Screenshot:** `docs/qa/human-browser-qa-screenshots/suite1_1_unauthenticated_root.png`

2. **Test 1.2 - First-Boot Claim Wizard Step 1 (`/setup?token=...`):**
   - **Action:** Extracted the one-time setup token from `docker logs kb-qa-retest` and navigated to `/setup?token=kb_setup_...`.
   - **Result (`PASS`):**
     - The URL token is immediately consumed into memory and scrubbed from the address bar via `window.history.replaceState({}, '', '/setup')`.
     - `SetupClaimPage` calls `GET /api/v1/auth/session` (`200 OK`), which sets the `kb_csrf` cookie on cleartext localhost.
     - Filled `#setup-username` (`admin`), `#setup-display-name` (`QA Self-Host Admin`), `#setup-email` (`admin@example.com`), `#setup-password`, and `#setup-confirm-password`, then clicked **Claim Instance & Continue**.
     - `POST /api/v1/setup/claim` succeeded with `200 OK` (`{"principal_id": "...", "username": "admin", "email": "admin@example.com", "next_step": "mfa_enrollment_required"}`), advancing the UI to **STEP 2 OF 3: Mandatory Second-Factor Enrollment (AAL2)**.
   - **Screenshots:** `suite1_2_setup_page_initial.png`, `suite1_2_setup_filled.png`, `suite1_2_after_submit.png`

3. **Test 1.3 - Step 2 & Step 3 Mandatory AAL2 Enrollment & Recovery Codes:**
   - **Action:** On Step 2 of 3 (`Mandatory Second-Factor Enrollment (AAL2)`), clicked **Use Authenticator App (TOTP) Instead** (`#setup-switch-to-totp-btn`), read the Base32 secret from `#setup-totp-secret`, generated a valid 6-digit RFC 6238 TOTP code, entered it into `#setup-totp-code`, and clicked **Verify & Complete Setup** (`#setup-confirm-totp-btn`). On Step 3 of 3, verified the 10 single-use recovery codes, checked `#setup-recovery-ack-checkbox`, and clicked **Continue to Workspace** (`#setup-finish-btn`).
   - **Result (`PASS`):**
     - `POST /api/v1/auth/mfa/totp/enroll` returned `200 OK` under `kanban_app` (column-scoped `SELECT (principal_id, username)` + RLS policy verified).
     - `POST /api/v1/auth/mfa/totp/confirm` returned `200 OK`, advancing to Step 3 of 3 and displaying 10 recovery codes (`#setup-recovery-codes-list li`).
     - Checking the acknowledgment checkbox and clicking **Continue to Workspace** navigated to `http://localhost:18923/` with an active `aal2` session.
   - **Screenshots:** `suite1_3_setup_step2_mfa.png`, `suite1_3_setup_step2_totp_key.png`, `suite1_3_setup_step3_recovery_codes.png`, `suite1_4_workspace_after_setup.png`

4. **Test 1.4 - Logout & Re-Login with TOTP (`/login`):**
   - **Action:** Clicked the Topbar Avatar button (`Q`, `aria-label="User profile and settings"`), verified the dropdown menu items, and clicked **Log out** (`[data-testid="topbar-logout-btn"]`). Then logged back in on `/login` using the `Local Admin` card + 6-digit TOTP code.
   - **Result (`PASS`):**
     - `POST /api/v1/auth/logout` returned `200 OK` and redirected the browser to `/login`.
     - `/login` loaded enabled auth cards via `GET /api/v1/auth/cards` (`200 OK`), opened the `Local Admin` sign-in form, authenticated username/password via `POST /api/v1/auth/local/login` (`200 OK`, `mfa_required: true`), prompted for the 6-digit TOTP code, verified via `POST /api/v1/auth/mfa/totp/verify` (`200 OK`, `aal: "aal2"`), and redirected back to `/`.
   - **Screenshots:** `suite2_1_avatar_clicked.png`, `suite2_2_login.png`, `suite2_2_login_local_admin_filled.png`, `suite2_2_login_mfa_step.png`, `suite2_2_after_relogin.png`

---

### Suite 2: Workspace Shell, Project Creation (`CreateProjectModal`), Command Palette & Navigation (`KANBA-166`, `KANBA-170`)

1. **Test 2.1 - Create Project `SELF` (`Self Host QA`) via UI:**
   - **Action:** On `/` (Workspace Home), clicked `+ Create Project` (`[data-testid="home-create-project-btn"]`), typed Project Name `"Self Host QA"` (which auto-derived Project Key `SELF`), entered Description `"End-to-end human browser QA verification project for self-hosting."`, and clicked **Create Project** (`[data-testid="create-project-submit-btn"]`).
   - **Result (`PASS`):**
     - `POST /api/v1/projects` returned `201 Created`.
     - The browser navigated to `/projects/SELF/issues`, the Sidebar `PROJECTS` section updated dynamically to show `Self Host QA`, and navigating back to `/` showed the `Self Host QA` (`SELF`) card on the Workspace Overview dashboard.
   - **Screenshots:** `suite3_1_home.png`, `suite3_2_create_project_modal_filled.png`, `suite3_2_after_project_created.png`, `suite3_2_home_with_self_project.png`

2. **Test 2.2 - Command Palette (`Ctrl+K`), Theme Toggle & Sidebar Links:**
   - **Action:** Pressed `Ctrl+K` to open the Command Palette, searched `"Self Host"`, closed with `Escape`, toggled Dark/Light theme via the Topbar Avatar menu, and clicked each Sidebar navigation link (`Drafts`, `Your work`, `Cycles`, `Modules`, `Views`).
   - **Result (`PASS`):**
     - Command Palette (`[role="dialog"][aria-label="Command palette"]`) opened with keyboard shortcut `Ctrl+K` and filtered commands/items.
     - Clicking `Dark` in the Avatar menu applied `data-theme="dark"` / `.dark` to `<html>`, and clicking `Light` restored light mode.
     - All Sidebar links (`/drafts`, `/your-work`, `/projects/SELF/cycles`, `/projects/SELF/modules`, `/projects/SELF/views`) rendered functional empty-state/list views inside `AppShell`.
   - **Screenshots:** `suite3_command_palette.png`, `suite3_1_theme_dark.png`, `suite3_1_drafts.png`, `suite3_1_your_work.png`, `suite3_1_cycles.png`, `suite3_1_modules.png`, `suite3_1_views.png`

---

### Suite 3: Issue Creation, PostgreSQL Persistence & Multi-View Switching (`KANBA-166`)

1. **Test 3.1 - Empty State & Creating 3 Live Issues via `QuickCreateIssueModal`:**
   - **Action:** Navigated to `/projects/SELF/issues`, verified zero hardcoded `FIXTURE_12_ISSUES` (`KAN-140`..`KAN-151`) were shown, pressed `c` (and clicked `+ New work item`), and created 3 issues via `QuickCreateIssueModal`:
     - `SELF-1`: `"Configure TLS termination and HSTS headers"`
     - `SELF-2`: `"Verify PostgreSQL RLS policies for multi-tenant isolation"`
     - `SELF-3`: `"Set up automated nightly encrypted backups"`
   - **Result (`PASS`):**
     - Each submission fired `POST /api/v1/projects/SELF/issues` (`201 Created`).
     - Pressing `F5` (`page.reload()`) fired `GET /api/v1/projects/SELF/issues` (`200 OK`) and rendered all 3 issues from PostgreSQL.
   - **Screenshots:** `suite4_1_issues_empty_initial.png`, `suite4_2_press_c_on_issues.png`, `suite4_2_modal_filled.png`, `suite4_2_after_create_before_reload.png`, `suite4_2_after_reload_f5.png`

2. **Test 3.2 - Switching Across All 5 Views (`Board`, `List`, `Table`, `Calendar`, `Timeline`):**
   - **Action:** Used the Topbar `LayoutSwitcher` (`List | Board | Table | Calendar | Timeline`) to switch across all 5 layouts on `/projects/SELF/issues`.
   - **Result (`PASS`):**
     - `AppShell` (Sidebar, Topbar, LayoutSwitcher) remained mounted on every layout.
     - Switching to `Board` (`/projects/SELF/issues?layout=board`) rendered 5 columns (`Backlog 0`, `Todo 3`, `In Progress 0`, `Done 0`, `Canceled 0`) with all 3 live issue cards (`SELF-1`, `SELF-2`, `SELF-3`) visible inside the `Todo` column.
     - `List`, `Table`, `Calendar`, and `Timeline` views all rendered the live project issues cleanly.
   - **Screenshots:** `suite4_3_layout_list.png`, `suite4_3_layout_board.png`, `suite4_1_issues_board.png`, `suite4_3_layout_table.png`, `suite4_3_layout_calendar.png`, `suite4_3_layout_timeline.png`

---

### Suite 4: Issue Peek Drawer (`?peek=...`), Markdown/Mermaid Editor, Properties & Comments (`KANBA-164`, `KANBA-165`)

1. **Test 4.1 - Peek Drawer Background Preservation (`?layout=board&peek=SELF-1`):**
   - **Action:** On `/projects/SELF/issues?layout=board`, clicked card `SELF-1`.
   - **Result (`PASS`):**
     - URL updated to `/projects/SELF/issues?layout=board&peek=SELF-1`.
     - Both `.surface--drawer[aria-label="Issue peek drawer"]` (`count = 1`) and the background `.kb-board-view` (`count = 1`, showing `SELF-2` and `SELF-3` alongside the Sidebar and Topbar) remained mounted and visible simultaneously.
   - **Screenshots:** `suite5_1_peek_drawer.png`, `suite5_1_click_kan140.png`

2. **Test 4.2 - Markdown + Mermaid Description Save & Workflow State Transition:**
   - **Action:** Clicked the description view (`[data-testid="issue-description-view"]`), entered Markdown containing a `### Security Checklist` and a fenced ```` ```mermaid ```` diagram (`graph LR; A[Client Browser] -->|HTTPS TLS 1.3| B[Reverse Proxy]; B -->|HTTP Internal| C[Uvicorn FastAPI]; C -->|asyncpg| D[(PostgreSQL 16 RLS)];`), clicked **Save** (`[data-testid="issue-description-save"]`), and changed `#prop-state-select` from `Todo` to `In Progress`.
   - **Result (`PASS`):**
     - `PATCH /api/v1/issues/SELF-1` returned `200 OK` and rendered the inline Mermaid diagram preview (`[data-testid="issue-mermaid-diagram"]`).
     - Selecting `In Progress` fired `POST /api/v1/issues/SELF-1/transitions` (`200 OK`) and updated the issue state in PostgreSQL.
   - **Screenshots:** `suite5_2_editing_description.png`, `suite5_2_mermaid_rendered.png`

3. **Test 4.3 - Comment Submission & Full-Screen Issue View (`/projects/SELF/issues/SELF-1`):**
   - **Action:** Typed `"Verified TLS 1.3 cipher suites and HSTS preload header in staging."` into `[data-testid="comment-composer-textarea"]` and clicked **Comment** (`[data-testid="comment-submit-button"]`). Then navigated to `/projects/SELF/issues/SELF-1` and reloaded with `F5`.
   - **Result (`PASS`):**
     - Clicking **Comment** fired `POST /api/v1/issues/SELF-1/comments` with `X-CSRF-Token` attached, returning **`201 Created`** and rendering the new comment in the activity stream (`suite5_2_after_comment_and_state.png`).
     - Navigating to `/projects/SELF/issues/SELF-1` and pressing `F5` confirmed that the updated Markdown/Mermaid description, `In Progress` state, and comment all persisted in PostgreSQL (`suite5_2_full_issue.png`, `suite5_2_full_issue_after_reload.png`).
   - **Screenshots:** `suite5_2_after_comment_and_state.png`, `suite5_2_full_issue.png`, `suite5_2_full_issue_after_reload.png`

---

### Suite 5: Stickies (`/stickies`) & Project Docs (`/projects/SELF/docs`) (`KANBA-167`)

1. **Test 5.1 - Stickies Creation, Autosave, Smart Promotion Banner & `F5` Persistence:**
   - **Action:** Clicked `Stickies` in the Sidebar (`/stickies`), clicked `+ New Sticky` (`[data-testid="new-sticky-btn"]`), typed a >400-character Markdown note into the sticky editor, waited for debounced autosave, and pressed `F5` (`page.reload()`).
   - **Result (`PASS`):**
     - `POST /api/v1/projects/SELF/stickies` returned `201 Created`, and `PATCH /api/v1/stickies/{id}` returned `200 OK`.
     - Because the sticky exceeded 400 characters, the UI automatically displayed the smart promotion prompt: `"This sticky is getting detailed. Consider promoting it to a Doc or Issue."` with `Promote to Doc` and `Promote to Issue` buttons.
     - Reloading with `F5` preserved the sticky content from PostgreSQL.
   - **Screenshots:** `suite6_1_stickies.png`, `suite6_after_click_new_sticky.png`, `suite6_2_stickies_after_reload.png`

2. **Test 5.2 - Project Docs (`/projects/SELF/docs`) Tree Load, Page Creation & `F5` Persistence:**
   - **Action:** Clicked `Docs (Pages)` under project `Self Host QA` in the Sidebar (`/projects/SELF/docs`), clicked `+ New Doc`, entered title `"Self-Hosting Runbook & Architecture"`, created the page, edited the Markdown body in `.kb-doc-editor-textarea`, and reloaded with `F5`.
   - **Result (`PASS`):**
     - Loading `/projects/SELF/docs` called `GET /api/v1/projects/SELF/docs/tree` (`200 OK`) with **zero** `404 /api/v1/docs/.../tree` errors (`KANBA-167` verified).
     - Editing the page title/body (`PATCH /api/v1/pages/{id}` -> `200 OK`) and pressing `F5` preserved the page in both the left tree (`[data-testid="doc-tree-node"]`) and the Markdown editor.
   - **Screenshots:** `suite7_1_docs.png`, `suite7_after_click_new_doc.png`, `suite7_after_submit_create_doc.png`

---

### Suite 6: Custom Fields, MCP Access Studio, Auth Studio & Standalone Status (`KANBA-168`, `KANBA-170`)

1. **Test 6.1 - Project Custom Fields (`/projects/SELF/settings/custom-fields`):**
   - **Action:** Clicked `Custom Fields` under project `Self Host QA` in the Sidebar, entered Display Name `"CVSS Score"`, Field Key `"cvss-score"`, Field Type `Number`, and clicked **Create Definition** (`[data-testid="create-field-btn"]`).
   - **Result (`PASS`):**
     - `POST /api/v1/projects/SELF/custom-fields` returned `201 Created` (with `X-CSRF-Token` properly attached).
     - The active custom fields list immediately rendered `[data-testid="field-item-cvss-score"]` (`CVSS Score | NUMBER | key: cvss-score`) and persisted across `F5` reload.
   - **Screenshots:** `suite8_2_custom_fields.png`, `suite8_2_after_create_custom_field.png`

2. **Test 6.2 - MCP Access Studio (`/settings/mcp`, `/workspaces/settings/mcp`, `/admin/mcp`):**
   - **Action:** Opened the Topbar Avatar menu (`Q`), clicked `Personal MCP Keys` (`/settings/mcp`), clicked `+ Mint MCP Key`, entered `"QA Self-Host Agent Token"`, and clicked **Mint Key**. Also visited `/workspaces/settings/mcp` and `/admin/mcp`.
   - **Result (`PASS`):**
     - `POST /api/v1/mcp/keys` returned `201 Created` (with `X-CSRF-Token` attached).
     - The modal displayed the one-time `kb_pat_...` token with a `Copy Token` button, and clicking `Done` listed `"QA Self-Host Agent Token"` (`Active`) in the API keys table.
   - **Screenshots:** `suite8_1_settings_mcp.png`, `suite8_1_mint_mcp_modal.png`, `suite8_1_after_mint_key_submit.png`, `suite8_1_workspaces_mcp.png`, `suite8_1_admin_mcp.png`

3. **Test 6.3 - Admin Auth Studio (`/admin/auth`) & Standalone Status (`/admin/standalone`):**
   - **Action:** Navigated via the Topbar Avatar menu to `Admin Auth Studio` (`/admin/auth`) and `Standalone Status & Backup` (`/admin/standalone`). On `/admin/standalone`, switched between the `Encrypted Database Backup` and `Production Compose Export` tabs.
   - **Result (`PASS`):**
     - `/admin/auth` called `GET /api/v1/auth/me` (`200 OK`) and `GET /api/v1/admin/auth/cards` (`200 OK`), displaying `Authentication Studio`, the `Lockout Guard: Active` badge, and the `Local Admin` card configuration.
     - `/admin/standalone` called `GET /api/v1/system/status` (`200 OK`) and rendered `StandaloneStatusPanel` (`Mode: standalone | Database: embedded (ok) | Public URL: http://localhost:18923`), the `Encrypted Database Backup` tab, and the `Production Compose Export` tab (`POST /api/v1/system/export-compose` -> `200 OK` generating `docker-compose.yml` and `.env.production`).
   - **Screenshots:** `suite2_3_admin_auth.png`, `suite8_3_standalone_status.png`

---

### Suites 7 & 8: Security Headers, CSP Validation & Responsive Viewports (`KANBA-169`)

1. **Test 7.1 - Security Headers & Zero CSP Console Errors:**
   - **Observed HTTP Response Headers on `http://localhost:18923/`:**
     - `content-security-policy: default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; img-src 'self' blob: data:; font-src 'self'; connect-src 'self' wss:; media-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types kanban-sanitizer dompurify;`
     - `x-frame-options: DENY`
     - `x-content-type-options: nosniff`
     - `referrer-policy: strict-origin-when-cross-origin`
     - `cross-origin-opener-policy: same-origin`
     - `cross-origin-resource-policy: same-origin`
   - **Result (`PASS`):** Zero `Content-Security-Policy` console errors or blocked resource violations occurred anywhere in the browser session (`KANBA-169` verified).

2. **Test 8.1 - Responsive Viewports (`1440x900`, `768x1024`, `375x812`):**
   - **Action:** Resized Chromium across Desktop (`1440x900`), Tablet (`768x1024`), and Mobile (`375x812`) on `/projects/SELF/issues?layout=board` and toggled the mobile navigation drawer (`button[aria-label="Toggle navigation sidebar"]`).
   - **Result (`PASS`):** Zero horizontal page overflow (`scrollWidth: 768 <= innerWidth: 768` on tablet; `scrollWidth: 375 <= innerWidth: 375` on mobile), and the mobile hamburger button cleanly opens and closes the off-canvas navigation sidebar.
   - **Screenshots:** `suite8_4_responsive_tablet_768x1024.png`, `suite8_4_responsive_mobile_375x812.png`, `suite8_4_responsive_mobile_sidebar_open.png`
