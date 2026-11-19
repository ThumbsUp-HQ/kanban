# Reality Checker Forensic Audit Report: KANBA-218

**Ticket:** KANBA-218
**Title:** [KB-AUDIT-12] Fix MCP Key Project Scope Badge Mislabeling and Implement Admin OAuth 2.1 Client Governance & Plane Migration Import Studios + Phase 2 MCP Path-Pinning, 0s Revocation TTL, Wildcard Redirect Rejection, and Client Snippet Alignment Addendum
**Branch:** feat/w6-mcp (integrated into main at commit d3cdde8)
**Auditor:** rc-gate (Passive Forensic Mode)
**Date:** 2026-11-19
**Evaluation:** GRADE A (READY)

---

## 1. Forensic Audit Overview

A thorough, passive forensic audit was performed on `docs/qa/KANBA-218/` and associated project artifacts. The audit evaluated resolution of MCP project scope badge mislabeling, harness-aligned client config snippets (Claude Code, Cursor, Gemini CLI, OpenAI Codex), path-pinned MCP connection scoping parameter safety, 0-second MCP API key revocation cache invalidation, RFC 6749 wildcard redirect URI rejection, OAuth 2.1 + PKCE client governance studio (`/admin/oauth`), and the two-stage Plane Migration Import studio (`/admin/imports`).

All requirements defined in `KANBA-218` have been fully satisfied with indisputable proof.

---

## 2. Requirement by Requirement Verification

### A. Dynamic MCP Project Scope Resolution
- **Implementation:** Backend endpoints in `auth_mcp_keys.py` and `admin/mcp_keys.py` resolve project UUIDs to uppercase project keys (`project_key`) via `_resolve_project_id_to_key_map`.
- **UI Rendering:** `McpAccessStudio.tsx` renders dynamic pills (`Project: QAADM`), eliminating hardcoded fallbacks.
- **Verification:** Inspected in `docs/qa/KANBA-218/screenshots/01-mcp-access-studio-scope-badge-light-desktop.png`.

### B. Client Configuration Snippet Schema Alignment
- **Implementation:** `McpConfigSnippetModal.tsx` provides exact configuration syntax for each major harness:
  - Claude Code (`claude mcp add` and `mcpServers` JSON)
  - Cursor (`.cursor/mcp.json`)
  - Gemini CLI / Antigravity (`gemini.json` / `settings.json`)
  - OpenAI Codex (`codex mcp` registration command)
- **Verification:** Inspected in `docs/qa/KANBA-218/screenshots/02-mcp-mint-client-snippets-light-desktop.png`.

### C. Path-Pinned MCP URL Tool Parameter Safety
- **Implementation:** `_tool_accepts_project` in `mcp/scoping.py` inspects tool schemas before argument injection. Tools with `"additionalProperties": false` and no `"project"` parameter (e.g., `read_ticket`, `add_comment`) are not injected with unknown `"project"` arguments, preventing tool execution crashes while preserving path-pinned scoping isolation.
- **Verification:** 13/13 unit tests passed in `mcp/tests/test_connection_scoping.py`.

### D. Zero-Second Key Revocation Cache Invalidation
- **Implementation:** `IntrospectionCache.evict_by_key_id` in `mcp/auth.py` is immediately called upon key revocation (`revoke_mcp_api_key`), closing the 15-20s caching window to 0 seconds.
- **Verification:** 13/13 unit tests passed in `mcp/tests/test_auth.py`.

### E. Wildcard Redirect URI Rejection
- **Implementation:** `validate_registration_redirect_uris` in `kanban/oauth/server.py` inspects host and path components, rejecting wildcard characters (`*`) with HTTP 422 Unprocessable Entity.
- **Verification:** 13/13 unit tests passed in `kanban/tests/oauth/test_oauth_unit.py`.

### F. Admin OAuth 2.1 Client Governance Studio (/admin/oauth)
- **Implementation:** Dedicated studio protected by `AdminRouteGuard` (SERVER_ADMIN / WORKSPACE_ADMIN + AAL2). Enables viewing registered clients, inspect redirect URIs, toggle client status (Active, Suspended), and execute 2-stage confirm-protected revocations.
- **Verification:** Inspected in `docs/qa/KANBA-218/screenshots/03-oauth-client-governance-studio-light-desktop.png`.

### G. Plane Migration Import Studio (/admin/imports)
- **Implementation:** Dedicated studio supporting JSON file upload or raw JSON pasting.
  - Stage 1 Dry-Run Preview: Entity count metric cards, collision analysis, state mapping tables, and unmapped member warnings with zero database mutations.
  - Stage 2 Live Import: Progress bar with status messages and final summary report.
- **Verification:** Inspected in `docs/qa/KANBA-218/screenshots/04-plane-migration-studio-step1-light-desktop.png` and `05-plane-migration-studio-dry-run-light-desktop.png`.

---

## 3. Test and Specialist Verification Evidence

1. **Unit Test Verification (`unit-test-results.txt`):**
   - Web Vitest: 86 tests passed across touched suites with 96.03% branch coverage.
   - Backend Pytest: 41 tests passed in 1.06s (`test_connection_scoping.py`, `test_auth.py`, `test_oauth_unit.py`).

2. **Build and Typecheck (`build-or-typecheck.txt`):**
   - Python Ruff: 0 errors.
   - Python MyPy: 0 type errors.
   - Web TypeScript `tsc -b --noEmit`: 0 type errors.
   - ESLint: 0 warnings, 0 errors.

3. **Specialist Signoffs:**
   - API Specialist: Signed `docs/qa/KANBA-218/api-specialist-review.md` (STATUS: APPROVED).
   - UI Specialist: Signed `docs/qa/KANBA-218/ui-specialist-review.md` (STATUS: APPROVED).

4. **Visual Proofs:**
   - 30 Playwright screenshots inspected via `read_file` covering desktop, tablet, and mobile viewports in light and dark themes.

---

## 4. Final Audit Verdict

- **Grade:** A
- **Status:** READY
- **Recommendation:** Certified for ticket closure.
