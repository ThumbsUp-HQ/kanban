# UI Specialist Forensic QA Review: KAN-4

- **Ticket ID:** `KAN-4` ([MCP-AGENT-SCHEMA-01])
- **Ticket Title:** Harden /mcp/agent Tool Schemas (verification_proof, if_match) and INVALID_TRANSITION Valid-State Hints
- **Auditor:** `ui-specialist` (ArchitectUX & UI Designer Specialist)
- **Merged Commit:** `8048b36` on `main`
- **Review Date:** 2026-11-17
- **Verdict:** `APPROVED`

---

## 1. Executive Summary & Review Scope

As part of the dual specialist gate mandated for API and MCP contract changes, an independent audit of ticket `KAN-4` was conducted on `main` at commit `8048b36`.

The audit evaluated the agent and frontend consumer ergonomics of:
1. **Schema Contract Definitions (`mcp/surfaces/agent/proof.py`, `complete_work.py`, `transition_ticket.py`, `update_ticket.py`):** Replacement of unconstrained `"type": "object"` payloads with strictly typed JSON Schema contracts.
2. **Interactive Help Ergonomics (`mcp/help.py`):** Alignment of tool parameter defaults with canonical implementations (`to_state`, `verification_proof`).
3. **Actionable Error Feedback for Agents and UIs (`kanban/issues/workflow_service.py`):** Remediation of `INVALID_TRANSITION` errors to include human-readable hints and structured `extra.valid_states` lists.
4. **Forensic Proof Packet Validation (`docs/qa/KAN-4/`):** Review of `git-diff.patch`, `contract-sample.json`, `build-check.txt`, `unit-test-results.txt`, and confirmation of the non-UI screenshot exemption (`N/A - Non-UI Ticket`).

---

## 2. Non-UI Exemption & Visual Asset Audit

- **Screenshot Exemption:** In accordance with the project specification and `docs/qa/KAN-4/message-to-reality-checker.md`, `KAN-4` modifies backend MCP schemas, CLI help dictionaries, and REST API error payload hints exclusively. No web components, templates, or styles were modified.
- **Visual Artifacts:** Declared `N/A - Non-UI Ticket`.

---

## 3. Agent & Client Consumer Ergonomics Audit

### 3.1 Verification Proof Schema (`VERIFICATION_PROOF_SCHEMA`)
- **Previous State:** `verification_proof` was defined vaguely as `"type": "object"` without property descriptions or requirements, leading calling agents to guess payload structure or submit malformed data.
- **Hardened State:**
  - `qa_dir`: Explicit directory path string.
  - `artifacts`: Array of file path strings.
  - `reality_checker`: Nested object requiring `verdict` (strictly enum `["READY", "NEEDS_WORK"]`), `grade` (regex pattern `^[A-F]$`), and `report_path`.
  - `ci_run_url`: Canonical URL string.
  - `required: ["qa_dir", "artifacts", "reality_checker", "ci_run_url"]` with `additionalProperties: false`.
- **UX Impact:** Tool definitions are now self-documenting for both client code and LLM tool-calling harnesses, preventing schema guessing and invalid submissions.

### 3.2 Update Ticket Concurrency Hints (`UPDATE_TICKET_SCHEMA`)
- `if_match` now includes an explicit description: `"64-char SHA-256 hex ETag (required when description_markdown is provided)"`.
- `description_markdown` clearly states: `"Description (requires if_match)"`.
- **UX Impact:** Eliminates mid-turn confusion for calling agents regarding optimistic concurrency requirements.

### 3.3 Tool Help Defaults Alignment (`mcp/help.py`)
- Corrected the parameter key for `transition_ticket` from outdated `"state"` to canonical `"to_state"`.
- Added explicit parameter defaults for `complete_work`: `{"identifier": "KAN-142 | uuid", "summary_markdown": "str", "verification_proof": "object"}`.
- **UX Impact:** Prevents hallucinated parameter keys when agents query tool usage through `help`.

### 3.4 Actionable Error Recovery (`INVALID_TRANSITION`)
- When an invalid state name or typo is submitted to `_resolve_state_by_ref`:
  - The API queries all active workflow states for the project and appends an actionable hint to `detail`: e.g. `"Target state 'FlyingToMars' not found in project. Valid states: Backlog, Todo, In Progress, Done, Cancelled"`.
  - Returns structured `extra`: `{"hint": "...", "valid_states": ["Backlog", "Todo", "In Progress", "Done", "Cancelled"]}`.
- In `complete_work`, if the state is not in the `completed` group, the API returns: `"Valid completed states: Done, Cancelled"`.
- **UX Impact:** Client UIs (e.g. state transition menus or error dialogs) can parse `extra.valid_states` directly to display valid alternative choices. AI agents can immediately self-correct without needing an extra round-trip to query project workflow states.

---

## 4. Test Verification & Code Quality Status

- **Unit & Integration Test Suite:**
  - `mcp/tests/agent/test_workflow_argument_validation.py` (6 passed)
  - `mcp/tests/agent/test_workflow_tools.py` (8 passed)
  - `mcp/tests/agent/test_update_ticket.py` (11 passed)
  - `mcp/tests/test_schema_budget.py` (1 passed)
  - `mcp/tests/test_lod_help.py` (13 passed)
  - Total: 39 tests passed in 8.52s with 0 failures (`docs/qa/KAN-4/unit-test-results.txt`).
- **Static Analysis:**
  - `ruff check mcp/ kanban/` passed cleanly with 0 errors (`docs/qa/KAN-4/build-check.txt`).
  - `python3 -m scripts.check_no_dashes --all` passed with 0 violations.

---

## 5. Final Verdict

**VERDICT: `APPROVED`**

Ticket `KAN-4` successfully delivers hardened MCP tool contracts, accurate parameter defaults, and self-correcting `INVALID_TRANSITION` error hints that significantly improve the reliability and ergonomics of agent and UI consumers.
