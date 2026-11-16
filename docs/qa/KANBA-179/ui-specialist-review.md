# UI Specialist Review: KANBA-179

- **Reviewer:** UI / UX Design Specialist (`ui-specialist`)
- **Date:** 2026-11-16
- **Ticket:** KANBA-179 ([KB-MCP-AGY] Mount Live MCP Surfaces on App Server (Fix 501 Not Implemented) & Update Antigravity (agy) Client Config Snippets)
- **Scope Inspected:**
  - `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`
  - `kanban/web/src/features/settings/__tests__/McpConfigSnippetModal.test.tsx`
  - `docs/qa/KANBA-179/screenshots/mcp-snippet-modal-agy.png`
  - `docs/qa/KANBA-179/unit-test-results.txt`
  - `docs/qa/KANBA-179/build-check.txt`
  - `docs/qa/KANBA-179/mcp-initialize-transcript.txt`
  - `docs/qa/KANBA-179/git-diff.patch`
  - `docs/qa/KANBA-179/changed-files-manifest.txt`
  - `docs/qa/KANBA-179/message-to-reality-checker.md`

---

## 1. Visual & UX Design Evaluation

### A. Modal Layout, Hierarchy, and Spatial Framing
- **Backdrop & Centering:** Inspected `mcp-snippet-modal-agy.png`. The modal is cleanly centered over a dark, blurred overlay backdrop (`rgba(0, 0, 0, 0.75)` with `backdrop-filter: blur(4px)`).
- **Header & Dismissal:** Modal title `MCP Access Key & Config Snippet` is rendered in bold white text with comfortable vertical breathing room, paired with an accessible dismiss icon (`✕`).
- **Secret Key Banner:** The one-time token banner (`NEW SECRET KEY (SHOWN ONCE)`) uses an unmistakable blue callout container with the raw token displayed in an accessible monospace input field (`kb_agt_antigravity_live_demo_key_999`), adjacent to a prominent `Copy Key` button. The warning caption ("This secret will never be shown again. Store it securely in your client config.") clearly communicates security finality to the operator.
- **Scope Dropdown Ergonomics:** The `Target Scope URL` selector clearly displays hierarchical narrowing (`Project (/mcp/agent/w/kanban/p/KANBA)`), allowing instant visual verification of the selected MCP boundary.

### B. Antigravity Streamable HTTP Snippet & Client Tabs
- **Client Selector Tabs:** High-contrast tab segmenter with options for `Gemini CLI (.gemini/settings.json)`, `Antigravity (mcp_config.json)` (highlighted active), and `Claude Code / Codex`.
- **Snippet Accuracy & Formatting:**
  - The configuration snippet container renders valid canonical JSON with high-contrast syntax highlighting on a deep black background:
    ```json
    {
      "mcpServers": {
        "kanban": {
          "serverUrl": "http://127.0.0.1:4173/mcp/agent/w/kanban/p/KANBA",
          "headers": {
            "Authorization": "Bearer kb_agt_antigravity_live_demo_key_99..."
          }
        }
      }
    }
    ```
  - Replaces legacy stdio dummy commands with the official Antigravity streamable HTTP specification (`serverUrl` + `headers.Authorization: Bearer <key>`).
- **CLI One-Liner Ergonomics:**
  - Accompanying CLI command snippet uses the exact flag order required by `agy mcp add`:
    `agy mcp add --header "Authorization: Bearer <key>" kanban <endpointUrl>`
- **Footer Actions:** Clean secondary `Copy Snippet` button paired with a primary green `Done` button (`#2e7d32`) provides unambiguous closure.

### C. Content Security Policy (CSP) & Accessibility Compliance
- **Zero Inline Styles:** Verified that `McpConfigSnippetModal.tsx` contains zero inline `style={{...}}` attributes; all visual properties use semantic CSS classes from the design token system.
- **Zero Raw HTML Injection:** No usage of `dangerouslySetInnerHTML`.
- **Keyboard Navigation:** Tab controls and buttons support logical focus cycling with high-contrast `:focus-visible` outlines.

---

## 2. Test Suite & Verification Results

- **Frontend Tests:** `McpConfigSnippetModal.test.tsx` (3 tests) passed cleanly in 91ms (Vitest 5.1.0).
- **Backend Tests:** 41 passed pytest tests with 96.54% branch coverage (exceeding the 95% threshold requirement).
- **Quality Gates:** `pnpm run typecheck` (`tsc -b --noEmit`) and `eslint` passed with 0 errors on frontend files. Backend `ruff check`, `ruff format`, `mypy --strict`, and `lint-imports` all passed on owned files.
- **Visual Artifacts:** Verified real Playwright screenshot `docs/qa/KANBA-179/screenshots/mcp-snippet-modal-agy.png`.

---

## 3. Specialist Conclusion

The updated Antigravity client configuration modal in KANBA-179 adheres to our design system tokens, provides exceptional copy ergonomics for agent operators, complies with streamable HTTP specifications, and satisfies all CSP and visual quality invariants.

**Verdict:** APPROVED
