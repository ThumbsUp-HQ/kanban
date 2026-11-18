# API Specialist Forensic QA Review: KAN-4

## Metadata
- **Ticket ID:** KAN-4
- **Title:** [MCP-AGENT-SCHEMA-01] Harden /mcp/agent Tool Schemas (verification_proof, if_match) and INVALID_TRANSITION Valid-State Hints
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `8048b36` (merged into `main`)
- **Review Date:** 2026-11-17
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 Tool Schema Hardening & Explicit Verification Proof Typing
- **`VERIFICATION_PROOF_SCHEMA` Definition (`mcp/surfaces/agent/proof.py`):**
  - Replaces vague unconstrained `"type": "object"` with explicit JSON Schema:
    - `qa_dir`: string path to directory.
    - `artifacts`: array of string paths.
    - `reality_checker`: object requiring `verdict` (enum `["READY", "NEEDS_WORK"]`), `grade` (pattern `^[A-F]$`), and `report_path` (string).
    - `ci_run_url`: string URL.
    - `required`: `["qa_dir", "artifacts", "reality_checker", "ci_run_url"]`.
    - `additionalProperties`: `False`.
  - Reused across both `COMPLETE_WORK_SCHEMA` (`mcp/surfaces/agent/complete_work.py`) and `TRANSITION_TICKET_SCHEMA` (`mcp/surfaces/agent/transition_ticket.py`).
- **ETag & `if_match` Constraint Documentation (`mcp/surfaces/agent/update_ticket.py`):**
  - Clarified schema descriptions for `if_match` ("64-char SHA-256 hex ETag (required when description_markdown is provided)") and `description_markdown` ("Description (requires if_match)"), providing explicit hints to calling agents without expanding schema token footprints excessively.
- **Help Defaults Alignment (`mcp/help.py`):**
  - Fixed `transition_ticket` param defaults from legacy `"state"` to canonical `"to_state"`.
  - Added explicit param defaults for `complete_work`: `{"identifier": "KAN-142 | uuid", "summary_markdown": "str", "verification_proof": "object"}`.

### 1.2 REST API Error Usability: `INVALID_TRANSITION` Hints (`kanban/issues/workflow_service.py`)
- **State Resolution Hints (`_resolve_state_by_ref`):**
  - When an unknown target state is requested, queries all active workflow states for the target project ordered by `sort_order` and `id`.
  - Returns `hint`: `"Valid states: Backlog, Todo, In Progress, Done, Cancelled"`.
  - Appends hint directly to problem `detail` and exposes structured fields `extra={"hint": hint, "valid_states": valid_state_names}`.
- **Completed Group Resolution Hints (`complete_work`):**
  - If a requested `to_state` is not in the `completed` state group, queries and reports `"Valid completed states: Done, Cancelled"`.
  - If no completed state exists in the project, details the error with project-wide state hints.
- **Consumer Usability:** Enables calling AI agents to immediately self-correct state names in the next turn without querying `read_ticket` or project metadata first.

---

## 2. Test Suite & Proof Verification

### 2.1 Unit & Integration Test Verification
- Executed MCP argument validation, workflow tools, help generation, and schema token budget test suites:
  - `mcp/tests/agent/test_workflow_argument_validation.py`
  - `mcp/tests/agent/test_workflow_tools.py`
  - `mcp/tests/test_lod_help.py`
  - `mcp/tests/test_schema_budget.py`
  - **Result:** 28 passed in 2.49s, 0 failures, 0 regressions.
- Verified:
  - `COMPLETE_WORK_SCHEMA` and `TRANSITION_TICKET_SCHEMA` enforce `VERIFICATION_PROOF_SCHEMA`.
  - Calling `transition_ticket` with unknown state returns `INVALID_TRANSITION` detailing valid state names in `detail` and `extra`.
  - `build_help` for `transition_ticket` and `complete_work` reflects correct parameter keys.
  - Token budget check passes within updated limit.

### 2.2 Proof Artifacts Audit (`docs/qa/KAN-4/`)
- `git-diff.patch`: Clean unified diff matching commit `8048b36`.
- `changed-files-manifest.txt`: All 10 modified/created files cataloged.
- `unit-test-results.txt`: Confirms 39 passing tests across affected test suites.
- `build-check.txt`: Clean static analysis (`ruff check mcp/ kanban/`).
- `contract-sample.json`: Valid concrete JSON payloads documenting schemas and `INVALID_TRANSITION` error responses.
- `message-to-reality-checker.md`: Accurate non-UI declaration and requirement mapping.

---

## 3. Specialist Verdict

The implementation in commit `8048b36` satisfies all tool schema requirements, error payload usability improvements, and schema budget limits specified in KAN-4.

**Verdict: APPROVED**
