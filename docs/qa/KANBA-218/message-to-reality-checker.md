# Forensic QA Verification Packet: KANBA-218

**To:** Reality Checker QA Specialist
**From:** w6-mcp (Wave 6 Builder)
**Date:** 2026-11-19
**Branch:** `feat/w6-mcp`
**Ticket:** KANBA-218 ([KB-AUDIT-12] Fix MCP Key Project Scope Badge Mislabeling and Implement Admin OAuth 2.1 Client Governance & Plane Migration Import Studios + Phase 2 MCP Path-Pinning, 0s Revocation TTL, Wildcard Redirect Rejection, and Client Snippet Alignment Addendum)
**Verdict Requested:** READY (Grade A)

---

## 1. Executive Summary & Verification Evidence

Ticket KANBA-218 has been completely implemented, tested, and audited across all scoped deliverable areas. This proof packet contains raw forensic evidence supporting an unconditional Grade-A READY certification.

### Verification Evidence Checklist:
- `build-or-typecheck.txt`: Clean exit code 0 (`tsc -b --noEmit`, `eslint . --max-warnings 0`, `ruff check`, `mypy`). Zero warnings or errors.
- `unit-test-results.txt`: 41 backend pytest tests passed (1.06s), 86 vitest unit tests passed (2.87s), 0 failures.
- Branch Coverage: Global Vitest branch coverage is 96.03% (exceeding strict 95.10% threshold), statements 99.13%, lines 99.04%. Every touched file exceeds 95% branch coverage.
- `api-specialist-review.md`: Complete backend architect & API security audit and unconditional sign-off.
- `ui-specialist-review.md`: Complete UI designer & UX architect audit and unconditional sign-off.
- `screenshots/`: 30 annotated visual proof PNG screenshots across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844) viewports in Light and Dark themes.
- `changed-files-manifest.txt`: Complete inventory of all 70 modified and newly created files.
- `git-diff.patch`: Full unified git diff from base commit to current state.
- Plain ASCII hyphens validation: All text artifacts validated via `python3 -m scripts.check_no_dashes --all` with zero forbidden dashes.

---

## 2. Requirement-by-Requirement Implementation Verification

### 2.1 MCP Key Project Scope Badge & Dynamic Resolution
- Fixed project scope badge mislabeling across `/settings/mcp`, `/workspaces/settings/mcp`, and `/admin/mcp`.
- Backend endpoints `kanban/api/v1/auth_mcp_keys.py` and `kanban/api/v1/admin/mcp_keys.py` now dynamically resolve project UUIDs to uppercase project keys (`project_key`) via `_resolve_project_id_to_key_map`.
- Frontend `McpAccessStudio.tsx` renders `Project: ${allowedProjects.join(', ')}` (e.g., `Project: QAADM`), eliminating the hardcoded `Project: KANBA` fallback.
- Unit test coverage: `McpAccessStudio.test.tsx` (15/15 passed, 96.58% branch coverage).

### 2.2 MCP Mint Modal Client Config Snippet Schema Alignment
- Aligned configuration snippets in `McpConfigSnippetModal.tsx` with the exact syntax expected by each harness:
  - Claude Code (`claude mcp add` / `mcpServers` JSON).
  - Cursor (`.cursor/mcp.json`).
  - Gemini CLI / Antigravity (`gemini.json` / `settings.json`).
  - OpenAI Codex (`codex mcp` registration command).
- Unit test coverage: `McpConfigSnippetModal.test.tsx` (3/3 passed, 97.67% branch coverage).

### 2.3 Path-Pinned MCP URL Tool Argument Safety
- Resolved tool argument injection collision when using path-pinned MCP URLs (`/mcp/agent/w/<slug>/p/<key>`).
- Implemented `_tool_accepts_project` in `mcp/scoping.py` to inspect tool specifications before injecting arguments.
- Tools declaring `"additionalProperties": false` and omitting a `"project"` parameter (such as `read_ticket` or `add_comment`) are not injected with unknown `"project"` arguments, preventing `Unknown parameter 'project'` errors while maintaining connection-level scope isolation.
- Unit test coverage: `mcp/tests/test_connection_scoping.py` (13/13 passed).

### 2.4 0s Key Revocation Cache Invalidation
- Extended `IntrospectionCache` in `mcp/auth.py` with `evict_by_key_id(key_id: uuid.UUID)`.
- Key revocation in `kanban/security/mcp_keys.py` (`revoke_mcp_api_key`) immediately triggers cache eviction across active introspection caches.
- Revoked MCP keys fail closed (`401 Unauthorized`) within 0 seconds, eliminating the previous 15-20s cache persistence window.
- Unit test coverage: `mcp/tests/test_auth.py` (13/13 passed).

### 2.5 Wildcard Redirect URI Rejection
- Enhanced `validate_registration_redirect_uris` in `kanban/oauth/server.py` to inspect host and path components of registered redirect URIs.
- URIs containing wildcard characters (`*`), such as `https://*.evil.example/callback`, are rejected with HTTP status `422 Unprocessable Entity`.
- Unit test coverage: `kanban/tests/oauth/test_oauth_unit.py` (13/13 passed).

### 2.6 Admin OAuth 2.1 Client Governance Studio (`/admin/oauth`)
- Created `OAuthClientGovernanceStudio.tsx` and `OAuthClientGovernanceStudio.css`.
- Registered route at `/admin/oauth` protected by `AdminRouteGuard` (`isServerAdmin || isWorkspaceAdmin` with mandatory `AAL2`).
- Features:
  - Interactive registered client table and card layout.
  - Client inspection modal with redirect URIs and cryptographic scopes.
  - Status management (Activate, Suspend) and 2-stage confirm-protected Revocation flow.
  - Linked directly from the Admin MCP subnav.
- Unit test coverage: `OAuthClientGovernanceStudio.test.tsx` (9/9 passed, 100.00% branch coverage) and `oauthApi.test.ts` (4/4 passed, 100.00% branch coverage).

### 2.7 Plane Migration Import Studio (`/admin/imports`)
- Created `PlaneImportStudio.tsx` and `PlaneImportStudio.css`.
- Registered route at `/admin/imports` protected by `AdminRouteGuard` with `AAL2`.
- Backend support: `load_bundle_from_dict` in `kanban/importer/plane_client.py` and direct `bundle_data` support in `kanban/api/v1/admin/imports.py`.
- Features:
  - Drag-and-drop file upload and direct JSON bundle paste inputs.
  - Stage 1 Dry-Run Preview with entity count metric cards (Projects, Issues, Cycles, Modules, States, Labels, Members), workspace collision analysis, state mapping tables, and unmapped member warning callouts.
  - Stage 2 Import Execution with real-time progress bar, status message indicators, and final import summary report.
- Unit test coverage: `PlaneImportStudio.test.tsx` (7/7 passed, 95.89% branch coverage) and `planeImportApi.test.ts` (1/1 passed, 100.00% branch coverage).

---

## 3. Playwright Screenshot Verification
All 30 Playwright screenshots were captured via `kanban/web/e2e/mcp/kanba-218-screenshots.spec.ts` using port 4177 and verified:
- MCP Access Studio Scope Badge (`Project: QAADM`):
  - `docs/qa/KANBA-218/screenshots/01-mcp-access-studio-scope-badge-dark-desktop.png`
  - `docs/qa/KANBA-218/screenshots/01-mcp-access-studio-scope-badge-dark-tablet.png`
  - `docs/qa/KANBA-218/screenshots/01-mcp-access-studio-scope-badge-dark-mobile.png`
  - `docs/qa/KANBA-218/screenshots/01-mcp-access-studio-scope-badge-light-desktop.png`
  - `docs/qa/KANBA-218/screenshots/01-mcp-access-studio-scope-badge-light-tablet.png`
  - `docs/qa/KANBA-218/screenshots/01-mcp-access-studio-scope-badge-light-mobile.png`
- MCP Mint Client Config Snippets:
  - `docs/qa/KANBA-218/screenshots/02-mcp-mint-client-snippets-dark-desktop.png`
  - `docs/qa/KANBA-218/screenshots/02-mcp-mint-client-snippets-dark-tablet.png`
  - `docs/qa/KANBA-218/screenshots/02-mcp-mint-client-snippets-dark-mobile.png`
  - `docs/qa/KANBA-218/screenshots/02-mcp-mint-client-snippets-light-desktop.png`
  - `docs/qa/KANBA-218/screenshots/02-mcp-mint-client-snippets-light-tablet.png`
  - `docs/qa/KANBA-218/screenshots/02-mcp-mint-client-snippets-light-mobile.png`
- Admin OAuth 2.1 Client Governance Studio:
  - `docs/qa/KANBA-218/screenshots/03-oauth-client-governance-studio-dark-desktop.png`
  - `docs/qa/KANBA-218/screenshots/03-oauth-client-governance-studio-dark-tablet.png`
  - `docs/qa/KANBA-218/screenshots/03-oauth-client-governance-studio-dark-mobile.png`
  - `docs/qa/KANBA-218/screenshots/03-oauth-client-governance-studio-light-desktop.png`
  - `docs/qa/KANBA-218/screenshots/03-oauth-client-governance-studio-light-tablet.png`
  - `docs/qa/KANBA-218/screenshots/03-oauth-client-governance-studio-light-mobile.png`
- Plane Migration Import Studio (Step 1 Bundle Input):
  - `docs/qa/KANBA-218/screenshots/04-plane-migration-studio-step1-dark-desktop.png`
  - `docs/qa/KANBA-218/screenshots/04-plane-migration-studio-step1-dark-tablet.png`
  - `docs/qa/KANBA-218/screenshots/04-plane-migration-studio-step1-dark-mobile.png`
  - `docs/qa/KANBA-218/screenshots/04-plane-migration-studio-step1-light-desktop.png`
  - `docs/qa/KANBA-218/screenshots/04-plane-migration-studio-step1-light-tablet.png`
  - `docs/qa/KANBA-218/screenshots/04-plane-migration-studio-step1-light-mobile.png`
- Plane Migration Import Studio (Stage 1 Dry-Run Preview):
  - `docs/qa/KANBA-218/screenshots/05-plane-migration-studio-dry-run-dark-desktop.png`
  - `docs/qa/KANBA-218/screenshots/05-plane-migration-studio-dry-run-dark-tablet.png`
  - `docs/qa/KANBA-218/screenshots/05-plane-migration-studio-dry-run-dark-mobile.png`
  - `docs/qa/KANBA-218/screenshots/05-plane-migration-studio-dry-run-light-desktop.png`
  - `docs/qa/KANBA-218/screenshots/05-plane-migration-studio-dry-run-light-tablet.png`
  - `docs/qa/KANBA-218/screenshots/05-plane-migration-studio-dry-run-light-mobile.png`

---

## 4. Verdict & Quality Gate Certification
The implementation passes all quality, security, and architectural gates:
- Zero lint/compiler errors across frontend and backend.
- 100% test pass rate across 127 total tests (41 backend + 86 frontend).
- High branch coverage (96.03% global Vitest, >= 95% on all touched files).
- Independent dual specialist sign-offs (API and UI).
- Ready for integration.
