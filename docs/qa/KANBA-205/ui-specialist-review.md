# UI Specialist Review: KANBA-205

**Ticket:** KANBA-205  
**Title:** [KB-QA-MCP] CLI MCP Scoping QA: User vs Project Agent Matrix (agy & codex)  
**Reviewer:** `ui-specialist` (UX Architect & UI Designer Specialist Persona)  
**Date:** 2026-11-18  
**Scope Classification:** `N/A - Non-UI Ticket`  
**Verdict:** `APPROVED`  

---

## 1. Executive Summary & Review Scope

Ticket KANBA-205 establishes the end-to-end verification and scoping QA matrix for the Model Context Protocol (MCP) server across dynamic connection tiers and CLI execution harnesses (`agy` and `codex`).

While KANBA-205 modifies zero browser DOM elements, front-end templates, or CSS stylesheets, the project-local Dual Specialist Gate mandates UI/UX Specialist review of:
1. **Developer Experience (DX) & CLI Ergonomics:** Inspecting the CLI configuration surface (`mcp_config.json`, `config.toml`) and verifying that tool catalogs and connection schemas present intuitive, clean, and unambiguous representations across `agy` and `codex`.
2. **Scoping Error Copy & Usability:** Evaluating error structures and messages emitted when cross-scope or cross-surface violations occur, ensuring developers and autonomous agents receive actionable failure feedback rather than opaque error codes.
3. **Atomic Configuration Safety:** Auditing `docs/qa/KANBA-205/mcp-config-integrity.log` to confirm that live probe operations guarantee bit-for-bit configuration rollback without residual probe entries or secret leakage.
4. **Non-UI Scope Verification:** Verifying the explicit declaration of `N/A - Non-UI Ticket` in `docs/qa/KANBA-205/message-to-reality-checker.md`.

---

## 2. Forensic Audit Findings

### 2.1 CLI Tool Ergonomics & Discovery
- **Evidence Inspected:** `docs/qa/KANBA-205/cli-probes.txt`, `docs/qa/KANBA-205/contract-sample.json`
- **Findings:**
  - In Condition A (`agy` and `codex` probes), tool discovery returns exactly 9 core agent tools (`search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`).
  - Descriptions are terse, imperative, and plain-English, eliminating prompt token bloat while giving LLM harnesses clear guidance on arguments and behavior.

### 2.2 Error Ergonomics & Actionability
- **Evidence Inspected:** `docs/qa/KANBA-205/cli-probes.txt`, `docs/qa/KANBA-205/contract-sample.json`, `tests/mcp/test_mcp_scoping_qa_matrix.py`
- **Findings:**
  - Scope violations emit structured error responses:
    - `KEY_SCOPE_VIOLATION`: Clearly communicates allowed project bindings (e.g. `{"error":"KEY_SCOPE_VIOLATION","message":"Token is pinned to specific project(s)...","allowed_projects":["QAUSR1"]}`).
    - `SURFACE_KEY_MISMATCH`: Emitted cleanly upon cross-surface access (e.g., agent key on docs/admin endpoints).
    - Unauthenticated challenges provide RFC 9728 `WWW-Authenticate` response with `resource_metadata` link, directing the agent or developer to the appropriate discovery endpoint.

### 2.3 Configuration Integrity & Clean Environment
- **Evidence Inspected:** `docs/qa/KANBA-205/mcp-config-integrity.log`
- **Findings:**
  - Baseline SHA-256 validation verified `/home/adamoutler/.gemini/config/mcp_config.json` and `/home/adamoutler/.codex/config.toml` were restored bit-for-bit with zero dangling probe configurations.
  - Zero raw tokens or secrets leaked across any logs or transcripts (all sanitized to `kb_agt_***REDACTED***`).

---

## 3. Compliance Checklist

| Standard / Invariant | Observation | Status |
| :--- | :--- | :---: |
| **Non-UI Ticket Classification** | Verified `N/A - Non-UI Ticket` in message-to-reality-checker.md | PASS |
| **CLI Output Ergonomics** | Clean, readable tool catalogs for agy and codex | PASS |
| **Error Feedback Clarity** | Explicit violation reasons and allowed bounds returned | PASS |
| **Typography & Copy** | Plain ASCII hyphens throughout; zero em/en-dashes | PASS |
| **Config Rollback Hygiene** | Confirmed bit-for-bit SHA-256 match in mcp-config-integrity.log | PASS |
| **Test Coverage** | 328 tests passed, 95.67% branch coverage on mcp | PASS |

---

## 4. UI Specialist Verdict

**`APPROVED`**

The CLI configuration ergonomics, error feedback clarity, and test matrix fulfill all UX and quality requirements for KANBA-205.
