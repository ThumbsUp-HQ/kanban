# Reality-Checker Verification Packet: KAN-19 (RC4)

## Summary of Implementation

Ticket **KAN-19** (`[KB-P3-AUDIT-13] Implement Progressive-Disclosure Self-Correcting YAML Error UX (did_you_mean, valid_options, cli_example) Across All MCP Surfaces (3 Problems)`) has been fully remediated and verified on branch `fix/KAN-19-rc4`.

This RC4 remediation directly resolves all Clean-Room Reality-Checker R3 (`2ad85cfc`) findings:

### 1. Populated `fix_hint` and `cli_example` Across All Domain NOT_FOUND Error Paths
- **`mcp/surfaces/agent/read_ticket.py`**:
  * Fixed lines 365-385: preserves and supplies `fix_hint` (`Ticket '{identifier}' was not found or you do not have access. Search accessible tickets first.`) and `cli_example=f'kanban-cli-agent search_tickets --query="{safe_identifier}"'`, `field="identifier"`, and `message="ticket not found"`.
  * Added fallback NOT_FOUND handler for non-dict `issue_data` with identical self-correction metadata.
- **`mcp/surfaces/agent/update_ticket.py`**:
  * Added `field="identifier"`, `fix_hint`, and `cli_example` to upstream NOT_FOUND error capture and non-dict issue branch.
- **`mcp/surfaces/agent/link_objects.py`**:
  * Added `field="link_type"`, `fix_hint`, and `cli_example` on UNLINK NOT_FOUND path.
- **`mcp/surfaces/docs/update.py`**:
  * Populated `field="parent"`, actionable `fix_hint`, and `cli_example` in `_resolve_parent_ids` (line 140).
  * Populated `field="id"`, actionable `fix_hint`, and `cli_example` in `_fetch_current_entity` (line 242).
- **`mcp/surfaces/docs/create.py` & `search.py` & `read_doc.py` & `upsert_doc.py`**:
  * Added `field`, actionable `fix_hint`, and `cli_example` for missing project, missing sticky, and missing doc/page.
- **`mcp/surfaces/admin/architect_project.py`, `manage_cycles_and_modules.py`, `override_ticket_provenance.py`**:
  * Enriched all NOT_FOUND branches (`project`, `cycle`, `module`, `view`, `target_state`) with `field`, `fix_hint`, and `cli_example`.
- **`mcp/internal_client.py`**:
  * Updated lines 354-365: both `NOT_FOUND` and `SECTION_NOT_FOUND` fallback mappings provide `fix_hint` and sensible fallback `cli_example`.
- **`mcp/markdown_sections.py`**:
  * Enriched `SECTION_NOT_FOUND` with `field="section"`, `fix_hint`, and `cli_example=f'kanban-cli-docs search --query="{safe_heading}"'`.
- **Resolved Unawaited Coroutine Warning**:
  * Diagnosed and fixed `AsyncMockMixin._execute_mock_call` unraisable `RuntimeWarning` in `mcp/tests/test_app.py` by mocking `verify_schema_head` as an `AsyncMock` during lifespan testing. Full pytest suite now runs with 0 unraisable warnings!
- **Added Explicit Regression Tests**:
  * Added `test_not_found_regression_progressive_disclosure` in `mcp/tests/test_progressive_disclosure_errors.py` explicitly asserting both `read_ticket("KAN-99999")` and `update("DOC-99999")` return NOT_FOUND YAML containing both `hint:`, `fix_hint:`, and `cli_example:`.

### 2. Aligned Wiki Example 7, Sidebar, and Code Block CSS Wrapping
- **Wiki Example 7 (`ALREADY_PROMOTED`)**:
  * In `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` Example 7, moved `target_doc_key: DOC-KAN-42` below `cli_example:` so YAML key ordering matches `KbMcpError.to_yaml()` (`self.extra` serialized after `optional_fields`) and `docs/qa/KAN-19/progressive-error-samples.yaml` 100%.
- **Wiki Sidebar Tool Count**:
  * In `thumbs-up-kanban.wiki/_Sidebar.md` line 31, updated `[MCP Tools Reference (27 Tools)](MCP-Tools-Reference)` to `[MCP Tools Reference (24 Tools)](MCP-Tools-Reference)` matching `MCP-Tools-Reference.md` header (24 intent-driven tools).
- **Wiki Example 10**:
  * Added Example 10 (`Entity Not Found`) showing canonical self-correcting NOT_FOUND YAML error payload.
  * Wiki committed cleanly on `main` in `/home/adamoutler/kanban/thumbs-up-kanban.wiki` (commit `535fe9e`).
- **CSS Code Block Readability & Wrapping**:
  * Updated `kanban/web/src/editor/MarkdownEditor.css` (`.ProseMirror pre`, `.ProseMirror pre.kb-code-block`, `pre.kb-code-block`) and `kanban/web/src/features/docs/DocsWorkspaceView.css` (`.docs-editor-container pre`, `.docs-prose pre`, `.docs-center-pane pre`).
  * Enforced `white-space: pre-wrap; overflow-wrap: break-word; word-break: break-word; overflow-x: auto;`.
  * YAML code blocks now wrap cleanly and never clip text mid-word on desktop or mobile viewports (`390x844`).
  * Vitest `cssTokensAudit.test.ts` passed 4/4 (100% canonical tokens, 0 inline styles).

### 3. Refreshed Verification Proof Packet
- **Unit Test Results (`docs/qa/KAN-19/unit-test-results.txt`)**:
  * Full MCP test suite: 356 passed, 0 failed in 46.07s.
  * Web Vitest tests: 434 passed across 38 files.
  * Coverage across all 8 touched files:
    - `mcp/errors.py`: 100%
    - `mcp/internal_client.py`: 96%
    - `mcp/protocol.py`: 95%
    - `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
    - `mcp/surfaces/agent/read_ticket.py`: 96%
    - `mcp/surfaces/agent/transition_ticket.py`: 95%
    - `mcp/surfaces/agent/update_ticket.py`: 97%
    - `mcp/surfaces/docs/update.py`: 97%
    - Overall coverage across all touched files: 96% (all >= 95%).
- **Static Quality Gates (`docs/qa/KAN-19/build-or-typecheck.txt`)**:
  * `ruff check .`: 0 errors
  * `ruff format --check .`: 1880 files already formatted
  * `mypy mcp/`: Success across 113 source files
  * `lint-imports`: 2 kept, 0 broken
  * `check_no_dashes`: 0 dash violations across repository and wiki
- **Patches and Samples**:
  * `docs/qa/KAN-19/git-diff.patch`: clean patch against base `887e7e0` (excluding `docs/qa/`)
  * `docs/qa/KAN-19/wiki-diff.patch`: clean patch against `5e93c1a`
  * `docs/qa/KAN-19/changed-files-manifest.txt`: updated list of all touched source, test, and wiki files
  * `docs/qa/KAN-19/progressive-error-samples.yaml`: complete set of 11 verified error YAML samples including sample 11 (`NOT_FOUND`)

### 4. Zero-Mock Live Full-Stack & Browser Proof (R4: Commit `18bcddb` / `18bcddb7`, Wiki `535fe9e`)
- **Live Stack Proof Log (`docs/qa/KAN-19/live-fullstack-proof.txt`)**:
  * Executed against standalone container `kanban-liveqa-1` (`http://localhost:18951`) backed by embedded PostgreSQL 16 (`FORCE ROW LEVEL SECURITY`, UID 65532) with zero mocks.
  * Completed `/setup`, enrolled TOTP for AAL2 admin session, created `KAN-1`, and minted real scoped `agent`, `docs`, and `admin` MCP API keys.
  * Verified all 10 live JSON-RPC 2.0 MCP cases across `/mcp/agent`, `/mcp/docs`, and `/mcp/admin`, including:
    - Case 1: `/mcp/agent` `link_objects` `{"source": "help"}` -> `isError: false`, JIT help YAML.
    - Case 2: `/mcp/admin` `manage_cycles_and_modules` `{"action": "help"}` -> `isError: false`, `list_cycles` present (zero `--action=list` typo).
    - Case 3A: `/mcp/agent` `read_ticket` `{"identifier": "KAN-99999"}` -> `isError: true`, `code: NOT_FOUND`, `hint:`, `fix_hint:`, and `cli_example: kanban-cli-agent search_tickets --query="KAN-99999"`.
    - Case 3B: `/mcp/docs` `update` `{"id": "DOC-99999", "type": "DOC", "content": "x"}` -> `isError: true`, `code: NOT_FOUND`, `hint:`, `fix_hint:`, and `cli_example: kanban-cli-docs search --query="DOC-99999"`.
    - Cases 4-9: `did_you_mean`, `valid_options`, `field: summary`, `CONFLICT_ETAG` with `current_etag`, and `cli_example` across `/mcp/agent`, `/mcp/docs`, and `/mcp/admin`.
  * Rendered exact `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` (`535fe9e`) in `/projects/KAN/docs` and verified via unmocked Playwright Chromium (`console.error`: `0`, `pageerror`: `0`, `<pre>` computed `whiteSpace === "pre-wrap"`, `scrollWidth <= clientWidth` across all 10 `<pre>` blocks, mobile `390x844` `documentElement.scrollWidth === 390`).
- **Visually Inspected Live Screenshots**:
  * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-desktop-light.png` (`1440x900` light, Examples 1-2, wrapped YAML lines with zero right-edge clipping)
  * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-desktop-dark.png` (`1440x900` dark, Examples 1-2, crisp contrast, zero right-edge clipping)
  * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-mobile-light.png` (`390x844` light, outline backdrop dismissed, wrapped YAML lines with zero mid-character clipping)
  * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-examples-bottom-desktop-light.png` (`1440x2160` light, Examples 6-10 showing `CONFLICT_ETAG`, `ALREADY_PROMOTED` with `target_doc_key` below `cli_example`, `PATCH_TARGET_AMBIGUOUS`, and `NOT_FOUND`)
  * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-cycles-desktop-light.png` (`1440x900` light, `manage_cycles_and_modules` showing `--action="list_cycles"`)
- **Overall Live Stack Verdict**: `OVERALL KAN-19 LIVE_STACK_VERDICT: PASS`
