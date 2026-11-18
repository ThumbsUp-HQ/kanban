# UI/UX Specialist Forensic Review: KANBA-205

## Metadata
- **Ticket ID:** KANBA-205
- **Title:** [KB-QA-MCP] CLI MCP Scoping QA: User vs Project Agent Matrix (agy & codex)
- **Reviewer:** ui-specialist (UX Architect & UI Designer Persona)
- **Target Branch:** `feat/kanba-205`
- **Review Date:** 2026-11-18
- **Verdict:** APPROVED

---

## 1. CLI Scoping & Developer Experience Assessment

### 1.1 MCP Configuration Snippet & CLI Setup Ergonomics
- **CLI Commands Parity:**
  - Evaluated command ergonomics for both Antigravity CLI (`agy mcp add --header "Authorization: Bearer <token>" <name> <url>`) and OpenAI Codex CLI (`codex mcp add --bearer-token-env-var <ENV_VAR> <name> --url <url>`).
  - Flags and parameter positioning align cleanly with upstream CLI specifications: flags precede the server name in `agy` and follow `--url` in `codex`.
  - Ephemeral naming convention (`kb_probe_<id>`) avoids collisions with developer workspace server configurations.
  - Setup UX eliminates manual token pasting into persistent config files via environment variable binding (`--bearer-token-env-var`).

### 1.2 Error Messages, Clarity, and Actionable Hints
- **Human-Readable Error Explanations:**
  - `KEY_SCOPE_VIOLATION` provides explicit extra fields listing authorized workspaces/projects alongside actionable hints recommending appropriate connection endpoints.
  - `CONNECTION_SCOPE_VIOLATION` displays pinned scope versus attempted foreign target and hints at Global mode or foreign endpoint URLs.
  - `SURFACE_KEY_MISMATCH` clearly differentiates agent, docs, and admin key prefixes to guide developers to the correct surface without ambiguity.
  - `INSUFFICIENT_SCOPE` reports exact missing scopes required for the tool or specific administrative action.

### 1.3 Whitespace, Formatting, and Non-UI Ticket Alignment
- Verified clean output formatting in JSON-RPC and YAML serialization.
- Verified zero em-dashes or en-dashes in developer documentation, review files, and CLI output streams.
- Confirmed this ticket is a Non-UI backend and CLI protocol test suite; no web UI layouts or browser DOM components were altered.

---

## 2. Review Verdict

The CLI MCP scoping workflow, error guidance, and setup ergonomics meet project standards.

**Verdict: APPROVED**
