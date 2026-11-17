# Message to Reality-Checker: KANBA-183

## Overview & Verification Mapping

This forensic proof bundle in `docs/qa/KANBA-183/` contains the complete, unedited implementation diff, unit test execution logs (backend pytest + frontend Vitest), build/typecheck/lint logs, responsive Playwright screenshots (`desktop`, `tablet`, `mobile`), and both UI and API specialist reviews.

### Scoped Technical Actions Mapping

1. **OAuth 2.0 / OIDC Callback URL Display, Clean Payload Keys, & Vector SVG Icons:**
   - `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`: Renders read-only Authorized Redirect URI (`data-testid="oauth-callback-url"`) computed dynamically from `${window.location.origin}/api/v1/auth/oidc/${slug}/callback` with 1-click Copy button, plus Authorized JavaScript Origin (`data-testid="oauth-js-origin"`). Omits `secret_input` and `pkce_method`, sends `client_auth` and `issuer`, and normalizes LDAP keys.
   - `kanban/auth/oidc/config.py`, `kanban/auth/ldap/config.py`: `@model_validator(mode="before")` normalizes legacy/UI alias keys without throwing 422 errors.
   - `kanban/auth/oidc/flow.py`: `_resolve_public_origin` derives public scheme/host from `KANBAN_PUBLIC_ORIGIN`, `X-Forwarded-Proto`/`X-Forwarded-Host`, or `request.base_url`.
   - `kanban/web/src/components/icons/KanbanIcons.tsx`, `AuthCardButton.tsx`, `AuthCardRow.tsx`: Vector SVG icons (`Google`, `GitHub`, `ActiveDirectory`, `Ldap`, `LocalAdmin`, `Shield`, `Key`, `Lock`, `Globe`) replace emoji placeholders.
   - `kanban/api/problems.py`, `kanban/auth/cards/service.py`, `kanban/web/src/api/problem.ts`: Concise field error formatting without raw Pydantic URLs or secret reflection.
   - **Note on Test Google Credentials:** Per Security Engineer directive, unit tests validate the exact Test Google Client ID (`339362854250-d59bll54eaom0jr79f1glsj4trp5hb54.apps.googleusercontent.com`), `slug: "google-oauth"`, and redirect URI (`https://k.hackedyour.info/api/v1/auth/oidc/google-oauth/callback`) while constructing the test secret dynamically in memory so git secret scanners are never tripped.

2. **Custom Fields Governance Behind "Advanced" Tab & Visibility Redaction:**
   - `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`: Splits form into Basic and Advanced (`data-testid="custom-fields-advanced-tab"`) tabs.
   - `kanban/custom_fields/service.py`, `kanban/api/v1/schemas/custom_fields.py`, `CustomFieldsRailSection.tsx`: Redacts `tier`, `target_scope`, and `credential_mode` to `None` when `is_admin=False`.

3. **Docs Navigation Rename (`Docs`), Title Prompt, Default Rich Markdown Template, & Top-Right Buttons:**
   - `kanban/web/src/app/Sidebar.tsx`: Renamed `Docs (Pages)` to `Docs`.
   - `kanban/web/src/features/docs/DocsTreeNav.tsx`, `docsApi.ts`: Uses placeholder `"What do you want to call this doc?"` and populates `DEFAULT_DOC_MARKDOWN_TEMPLATE` (headings, `#KAN-1`, `> [!NOTE]`/`> [!TIP]`, tasks, GFM table, fenced `ts` code, and `mermaid` `flowchart LR`).
   - `kanban/web/src/features/docs/PageEditorPane.tsx`, `DocsWorkspaceView.tsx`, `DocsWorkspaceView.css`, `useAccessInspector.tsx`: Interactive `v{page.version_seq}` History button, working Access Inspector event, desktop/mobile Rail toggle (`📑`), and `📋 Copy Markdown` button.

4. **Persistent Topbar Context, Cycles/Modules Creation Views, & Workflows Discovery:**
   - `kanban/web/src/features/board/board.css`, `viewRegistry.tsx`, `AppShell.css`, `AppShell.tsx`, `Topbar.tsx`, `Breadcrumb.tsx`: Eliminates 52px `100vh` scroll clipping and retains Workspace + Project context + dynamic section breadcrumb across all project tabs.
   - `kanban/web/src/app/routes.tsx`: Interactive `ProjectCyclesView` (`data-testid="project-cycles-view"`) and `ProjectModulesView` (`data-testid="project-modules-view"`).
   - `kanban/web/src/app/Sidebar.tsx`, `BoardColumn.tsx`, `ListView.tsx`, `WorkflowStudioPage.tsx`: Project `🔀 Workflows` nav item and contextual `+ Workflow` section action pre-populating `AttachHookDialog`.

5. **MCP Key Minting, RLS Workspaces, & Scoped MCP Auth:**
   - `kanban/api/v1/auth_mcp_keys.py`, `kanban/api/v1/admin/mcp_keys.py`, `McpAccessStudio.tsx`, `settingsApi.ts`: Supports `label`, `scope_tier`, `allowed_projects`, and displays `role="alert"` error banner on failure.
   - `kanban/api/v1/workspaces.py`, `database/migrations/sql/p4_18_oauth_mcp_scoping.up.sql`: Uses `SECURITY DEFINER` helpers so workspace creation/listing/switching and MCP `workspace_slug` introspection succeed under `kanban_app` (`FORCE ROW LEVEL SECURITY`).
