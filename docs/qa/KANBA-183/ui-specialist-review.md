# UI & UX Specialist Review: KANBA-183

**Auditor:** UI Specialist (`ux-architect` / ArchitectUX)  
**Date:** 2026-11-16  
**STATUS: APPROVED**  
**Target Ticket:** `KANBA-183` (`[KB-UX-07] OAuth Callback URL & SVG Icons (Fix 422 Validation), Persistent Project Topbar Context, Custom Fields Advanced Tab & Visibility, Docs Template/Actions, and Cycles/Modules/Workflows UI`)

---

## 1. Executive Summary & Audit Scope

As the project UI Specialist and UX Architect, I conducted a comprehensive forensic audit of the frontend implementation for `KANBA-183` across all modified components in `kanban/web/`, verifying design token compliance, responsive layout behavior, visual hierarchy, ARIA accessibility, CSP compliance (zero inline styles), and multi-device ergonomics.

The scope of this audit covers five major functional areas:
1. **Admin Auth Studio (`AuthCardEditorDrawer.tsx`, `AuthCardRow.tsx`, `AuthCardButton.tsx`, `KanbanIcons.tsx`, `problem.ts`):** Live Callback URL & JavaScript Origin display, 1-click clipboard feedback, pure vector SVG provider icons, clean schema payloads, and field-level error attribution.
2. **MCP Access Studio (`McpAccessStudio.tsx`, `settingsApi.ts`):** Tier-aware MCP key minting (`scope_tier`) and prominent `role="alert"` error notification.
3. **Custom Fields Governance (`CustomFieldDefinitionEditor.tsx`, `CustomFieldsRailSection.tsx`):** Basic vs. Advanced tab segmentation and permission-gated visibility redaction.
4. **Docs Workspace & Navigation (`Sidebar.tsx`, `DocsTreeNav.tsx`, `docsApi.ts`, `PageEditorPane.tsx`, `DocsWorkspaceView.tsx`, `DocsWorkspaceView.css`, `useAccessInspector.tsx`):** Sidebar label refinement (`Docs`), intuitive root document prompt, feature-showcase Markdown template, interactive Version History pill, Access Inspector integration, and responsive rail controls.
5. **App Shell & Project Context Navigation (`AppShell.tsx`, `AppShell.css`, `board.css`, `viewRegistry.tsx`, `Topbar.tsx`, `Breadcrumb.tsx`, `Breadcrumb.css`, `routes.tsx`, `BoardColumn.tsx`, `ListView.tsx`, `WorkflowStudioPage.tsx`):** Elimination of the 52px viewport scroll clipping bug, persistent Workspace + Project breadcrumb context, zero-inline-style CSP compliance, interactive Cycles and Modules views, and contextual `+ Workflow` creation shortcuts.

---

## 2. Detailed Technical & UX Review by Area

### Area 1: Admin Auth Studio, Live Callback URL, SVG Icons & Error Attribution

- **Live Browser Callback URL Display (`AuthCardEditorDrawer.tsx`):**
  - Evaluated the Authorized Redirect URI input (`data-testid="oauth-callback-url"`) rendered whenever `providerKind === 'OIDC' || providerKind === 'OAUTH2'`.
  - The URL is dynamically computed as `${window.location.origin}/api/v1/auth/oidc/${slug.trim() || 'oauth1'}/callback`.
  - The 1-click `Copy` button provides immediate visual feedback (`Copied!`), reverting after 2,000ms.
  - The Authorized JavaScript Origin (`${window.location.origin}`) is clearly exposed (`data-testid="oauth-js-origin"`), eliminating operator configuration errors in Google Cloud Console and GitHub Developer settings.
- **Pure Vector SVG Provider Icons (`KanbanIcons.tsx`, `AuthCardButton.tsx`, `AuthCardRow.tsx`):**
  - Replaced all emoji glyphs (e.g., `🔴 Google`, `🐙 GitHub`, `🔑`) with dedicated SVG components: `<Google />`, `<GitHub />`, `<ActiveDirectory />`, `<Ldap />`, `<LocalAdmin />`, `<Shield />`, `<Key />`, `<Lock />`, and `<Globe />`.
  - `renderAuthIcon()` dynamically resolves presets to 20x20px SVGs with standard theme-adaptive properties (`currentColor`), accompanied by `aria-hidden="true"`.
- **Payload Cleanliness & Problem Detail Parsing (`problem.ts`, `AuthCardEditorDrawer.tsx`):**
  - Extraneous frontend keys that previously triggered FastAPI `ConfigDict(extra="forbid")` 422 errors (`secret_input`, `pkce_method`) were eliminated.
  - `ApiProblem` now extracts structured error arrays (`errors: [{ path, message }]`) and appends exact field attributions (e.g., `Request validation failed: secret: Client Secret is required`).
  - `AuthCardEditorDrawer` captures `fieldErrors` and binds them directly to corresponding form inputs with high-contrast error banners.

### Area 2: MCP Access Studio Key Minting & Error Handling

- **Scope Tier Parameter (`McpAccessStudio.tsx`, `settingsApi.ts`):**
  - The minting payload now passes explicit `scope_tier: tier === 'global' ? 'global' : tier === 'project' ? 'project' : 'workspace'`, aligning with backend RLS scoping invariants.
- **Form Error Banner (`role="alert"`):**
  - Replaced the previously empty `catch { // Handle error }` block with stateful error capture.
  - Failed minting requests render a visible, accessible banner (`.kb-mcp-mint-error`, `role="alert"`, `data-testid="mint-error-banner"`), preventing silent UI stalls.

### Area 3: Custom Fields Governance & Visibility Gating

- **Basic vs. Advanced Tabbed Architecture (`CustomFieldDefinitionEditor.tsx`):**
  - Form fields are now partitioned into **Basic** (`Field Name`, `Field Slug`, `Output Format`, `Script Source`) and **Advanced** (`data-testid="custom-fields-advanced-tab"`).
  - ARIA tablist patterns (`role="tablist"`, `role="tab"`, `aria-selected`, `aria-controls`, `role="tabpanel"`) are strictly implemented with keyboard focus accessibility.
  - The Advanced tab houses sensitive governance controls:
    1. Execution Tier (`#execution-tier`: `Wasmtime` vs `nsjail`)
    2. Token Scope (`#target-scope`: `PROJECT`, `WORKSPACE`, `SERVER`)
    3. Credential Mode (`#credential-mode`: `INVOKING_USER`, `PROJECT_ADMIN_SP`, `SERVER_ADMIN_SP`)
- **Permission-Gated Visibility (`CustomFieldsRailSection.tsx`):**
  - In `CustomFieldsRailSection.tsx`, the `EmojiHint` popover conditionally checks `tier !== null && tier !== undefined`.
  - Non-administrative users who receive redacted metadata (`null` tier, scope, and credential mode) are shown only user-facing execution stats (e.g. latency), completely hiding internal sandbox infrastructure from unprivileged principals.

### Area 4: Docs Workspace & Authoring Experience

- **Navigation Label & Prompt Ergonomics:**
  - Sidebar label changed from `Docs (Pages)` to clean `Docs` (`Sidebar.tsx`).
  - Document creation modal placeholder updated from technical jargon (`"Specification title..."`) to user-friendly conversational copy (`"What do you want to call this doc?"`).
- **Default Feature-Showcase Markdown Template (`docsApi.ts`, `DEFAULT_DOC_MARKDOWN_TEMPLATE`):**
  - New documents are automatically seeded with a rich Markdown template showcasing:
    - Heading hierarchy (`#`, `##`, `###`), bold/italic formatting, and Universal Object Graph issue links (`#KAN-1`).
    - GFM alert callout blocks (`> [!NOTE]`, `> [!TIP]`).
    - Interactive task list items (`- [x]`, `- [ ]`).
    - Data tables (`| Component | Status | Tier | SLA Target |`).
    - Syntax-highlighted TypeScript code block.
    - Mermaid diagram block (`flowchart LR`).
- **Interactive Metadata & Action Controls:**
  - **Version Pill (`v{page.version_seq}`):** Converted from a static `<span>` to an interactive `<button>` (`data-testid="page-version-pill"`) that toggles open the right-hand rail and switches to the **History** tab.
  - **Copy Markdown Action:** Added `📋 Copy Markdown` button (`data-testid="copy-doc-markdown-btn"`) with 2,000ms `"Copied!"` confirmation and ARIA live region announcement.
  - **Access Inspector Pill:** Corrected custom event dispatch payload to `{ detail: { objectId: page.id, object_id: page.id } }`, enabling seamless one-click inspection of document RLS ACLs.
  - **Responsive Rail Toggle:** Updated `.docs-rail-pane` styles and `DocsWorkspaceView.tsx` to ensure clicking `📑` toggles the outline/history rail on desktop (`>= 1280px`) as well as mobile/tablet.

### Area 5: App Shell, Topbar Context, Cycles/Modules Views, and Workflow Discovery

- **Elimination of the 52px Viewport Scroll Clipping Bug:**
  - In `board.css`, replaced `#main { height: 100vh; max-height: 100vh; }` with `.kb-main-canvas { height: 100%; max-height: 100%; min-height: 0; }`.
  - In `AppShell.css`, updated grid definition to `grid-template-rows: var(--topbar-h, 52px) minmax(0, 1fr)`.
  - In `viewRegistry.tsx`, converted duplicate `<main id="main">` inside `IssuesWorkspaceRoute` to a semantic `<div className="issues-workspace">`, ensuring a single valid `#main` landmark exists on the page.
  - Confirmed that page navigation no longer scrolls the topbar or sidebar off-screen.
- **Persistent Workspace & Project Context in Breadcrumb (`Breadcrumb.tsx`, `Breadcrumb.css`):**
  - Topbar breadcrumb now reflects both **Workspace** (`workspaceName = 'kanban'`) and **Project** (`projectName (projectKey)`), with dynamic section computation (`currentSection`) derived from `location.pathname` (Work Items, Cycles, Modules, Views, Docs, Custom Fields, Workflows, Settings).
  - All legacy inline `style={{ ... }}` attributes were removed in favor of scoped CSS classes in `Breadcrumb.css`, satisfying strict CSP directives (`style-src 'self'`).
- **Interactive Cycles & Modules Views (`routes.tsx`):**
  - Replaced static placeholder views with fully functional management screens:
    - `ProjectCyclesView`: Displays existing cycles with status badges, date ranges, and an integrated form (`data-testid="create-cycle-form"`) to create new sprint cycles via `POST /api/v1/projects/{key}/cycles`.
    - `ProjectModulesView`: Displays active modules with description cards and an integrated form (`data-testid="create-module-form"`) to create new modules via `POST /api/v1/projects/{key}/modules`.
- **Workflow Discovery & Direct Transition Attachment:**
  - Added `🔀 Workflows` navigation item under each project in `Sidebar.tsx`.
  - In `BoardColumn.tsx` and `ListView.tsx`, added contextual `+ Workflow` buttons (`data-testid="section-add-workflow-btn-{stateName}"`) on column and section headers.
  - Clicking `+ Workflow` navigates to `/projects/{key}/settings/workflows?to_state={state}&attach=1`.
  - `WorkflowStudioPage.tsx` parses these query parameters on mount and automatically opens `AttachHookDialog` with the target state pre-selected.

---

## 3. Automated Test & Build Evidence

- **Frontend Unit & Component Tests (`docs/qa/KANBA-183/frontend-vitest.log`):**
  - `16` test files executed and passed:
    - `src/api/problem.test.ts` (11 tests passed)
    - `src/features/auth/AuthCardButton.test.tsx` (5 tests passed)
    - `src/features/board/BoardColumn.test.tsx` (6 tests passed)
    - `src/features/admin-auth/AuthCardRow.test.tsx` (7 tests passed)
    - `src/features/custom-fields/__tests__/CustomFieldsRailSection.test.tsx` (8 tests passed)
    - `src/features/docs/DocsTreeNav.test.tsx` (9 tests passed)
    - `src/features/docs/PageEditorPane.test.tsx` (10 tests passed)
    - `src/features/settings/__tests__/McpAccessStudio.test.tsx` (10 tests passed)
    - `src/app/AppShell.test.tsx` (3 tests passed)
    - `src/features/docs/DocsWorkspaceView.test.tsx` (7 tests passed)
    - `src/features/list/ListView.test.tsx` (10 tests passed)
    - `src/features/workflows/__tests__/WorkflowStudioPage.test.tsx` (8 tests passed)
    - `src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx` (20 tests passed)
    - `src/app/Sidebar.test.tsx` (14 tests passed)
    - `src/features/admin-auth/AuthCardEditorDrawer.test.tsx` (20 tests passed)
    - `src/app/routes.test.tsx` (17 tests passed)
  - Total: **165 tests passed, 0 failed**.
- **Typecheck & Linter Verification (`docs/qa/KANBA-183/frontend-build.log`):**
  - `tsc -b --noEmit`: Exited with code `0`, zero type errors.
  - `eslint . --max-warnings 0`: Exited with code `0`, zero warnings or lint errors.
  - `vite build`: Production client bundle compiled in `1.08s`.
- **Visual Artifacts & Style Probing:**
  - Multi-device Playwright screenshots captured and verified in `docs/qa/KANBA-183/screenshots/`:
    - `01-auth-studio-list-desktop.png`, `01-auth-studio-list-tablet.png`, `01-auth-studio-list-mobile.png`
    - `02-card-reordered-desktop.png`, `02-card-reordered-tablet.png`, `02-card-reordered-mobile.png`
    - `05-handshake-failed-hint-desktop.png`, `05-handshake-failed-hint-tablet.png`, `05-handshake-failed-hint-mobile.png`
    - `06-non-admin-not-found-desktop.png`, `06-non-admin-not-found-tablet.png`, `06-non-admin-not-found-mobile.png`
  - Computed style probes verified in `docs/qa/KANBA-183/computed-styles-*.json`.

---

## 4. UI Specialist Sign-off & Verdict

The frontend implementation for `KANBA-183` satisfies all visual, ergonomic, accessibility, and structural requirements defined in the specification and the 👍kanban design system. Zero regressions or CSP violations were detected.

**STATUS: APPROVED**  
**Role:** UI Specialist (`ux-architect` / ArchitectUX)  
**Verification Packet:** `docs/qa/KANBA-183/`
