# Verification Proof Packet: KANBA-179

**Ticket ID:** KANBA-179  
**Summary:** [KB-MCP-AGY] Mount Live MCP Surfaces on App Server (Fix 501 Not Implemented) & Update Antigravity (agy) Client Config Snippets  
**Author:** worker-179  
**Date:** 2026-11-15  

---

## 1. Scope of Work Completed
1. **Live MCP Mounts in App Server (`kanban/app.py`):**
   - Removed the 501 Not Implemented placeholder on `/mcp/{surface:path}`.
   - Mounted live Starlette MCP app via `_McpProxyApp` on `/mcp` and `/.well-known/oauth-protected-resource/mcp`.
   - Placed mounts prior to root SPA fallback (`/`), ensuring live MCP endpoints and metadata discovery URLs route properly.
   - Implemented dynamic fallback to `app.state.mcp_app` for test isolation.

2. **Standalone Security Headers & In-Process Client Hardening (`mcp/internal_client.py`):**
   - Switched internal client `base_url` from `http://kanban.local` to `http://localhost` to comply with default standalone host enforcement in `SecurityHeadersMiddleware`.
   - Guaranteed `X-KB-Service-Principal: mcp-gateway` header presence on internal requests.

3. **RFC 9728 Discovery & Token Whitespace Handling (`mcp/auth.py`, `mcp/protocol.py`):**
   - Exempted `/.well-known/oauth-protected-resource/mcp/*` from authentication in `McpAuthMiddleware`, returning 200 JSON discovery metadata unauthenticated.
   - Hardened `Authorization: Bearer <token>` extraction against leading/trailing whitespace, tabs, and multi-space delimiters.

4. **Antigravity Streamable HTTP Config (`kanban/web/src/features/settings/McpConfigSnippetModal.tsx`):**
   - Updated snippet to render `serverUrl` + `headers` streamable HTTP JSON.
   - Appended validated `agy mcp add --header "Authorization: Bearer <key>" kanban <url>` command.

5. **Automated Verification & Unit Tests:**
   - Created `kanban/tests/mcp/test_live_mcp_mount.py` covering RFC 9728 discovery, 401 challenges, in-process client loopback, whitespace tolerance, and authenticated JSON-RPC tools listing.
   - Created `mcp/tests/test_app.py` covering `create_mcp_app`, `_build_surface_sub_app`, `kanban.app` lifespan and runtime bootstrap, and internal client error mapping.
   - Updated `kanban/tests/test_app.py` to assert 401 challenges on live MCP surfaces instead of 501.
   - Updated vitest assertions in `McpConfigSnippetModal.test.tsx` and `McpAccessStudio.test.tsx`.

---

## 2. Test Evidence
- **Backend Tests & Coverage:**
  `uv run pytest kanban/tests/test_app.py kanban/tests/mcp/test_live_mcp_mount.py mcp/tests/test_app.py mcp/tests/test_auth.py -q --cov=kanban.app --cov=mcp.internal_client --cov-branch --cov-fail-under=95`
  -> **41 passed in 13.69s**, achieving **96.54% total branch coverage** (`kanban/app.py`: 97%, `mcp/internal_client.py`: 96%).
- **Frontend Tests:**
  `cd kanban/web && pnpm exec vitest run src/features/settings/__tests__/McpConfigSnippetModal.test.tsx`
  -> **3 passed in 1.17s**
- **Linters & Contracts on Owned Files:**
  - `uv run ruff check kanban/app.py kanban/tests/mcp/test_live_mcp_mount.py mcp/` -> **0 errors**
  - `uv run ruff format --check kanban/app.py kanban/tests/mcp/test_live_mcp_mount.py mcp/` -> **0 errors (111 files formatted)**
  - `uv run mypy --strict kanban/app.py kanban/tests/mcp/test_live_mcp_mount.py mcp` -> **0 errors (109 source files checked)**
  - `uv run lint-imports` -> **Contracts: 2 kept, 0 broken**
  - `pnpm run typecheck` (in `kanban/web`) -> **0 errors**
  - `pnpm exec eslint src/features/settings/McpConfigSnippetModal.tsx src/features/settings/__tests__/McpConfigSnippetModal.test.tsx` -> **0 errors**

---

## 3. Forensic QA Artifacts in `docs/qa/KANBA-179/`
- `mcp-initialize-transcript.txt`: Verbatim ASGI TestClient execution trace hitting Global `/mcp/agent`, Workspace `/mcp/agent/w/kanban`, Project `/mcp/agent/w/kanban/p/KANBA`, RFC 9728 discovery metadata, 401 unauthenticated challenge, 403 surface mismatch, and multi-space Bearer whitespace tolerance.
- `screenshots/mcp-snippet-modal-agy.png`: High-resolution Playwright screenshot displaying the Antigravity tab inside the MCP Access Studio snippet modal with streamable HTTP JSON (`serverUrl` + `headers.Authorization`) and `agy mcp add --header` CLI snippet.
- `unit-test-results.txt`: Verbatim raw unedited pytest execution log with >=95% branch coverage output and vitest execution log.
- `build-check.txt`: Verbatim quality checks covering scoped linters/types and documenting repo-wide status.
- `git-diff.patch`: Clean scoped patch across all 12 KANBA-179 files.
- `changed-files-manifest.txt`: Structured inventory of modified and new files.
- `api-specialist-review.md`: Backend/API architect audit.
- `ui-specialist-review.md`: UI/Frontend specialist audit.
- `message-to-reality-checker.md`: This verification summary.
