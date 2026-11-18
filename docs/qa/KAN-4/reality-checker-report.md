# Forensic QA Reality-Checker Audit Report: KAN-4

## Metadata
- **Ticket ID:** KAN-4
- **Title:** [MCP-AGENT-SCHEMA-01] Harden /mcp/agent Tool Schemas (verification_proof, if_match) and INVALID_TRANSITION Valid-State Hints
- **Module:** `mcp.surfaces.agent`, `mcp.help`, `kanban.issues.workflow_service`
- **Evaluated Commit:** `8048b36` (merged into `main`)
- **Auditor:** reality-checker (Passive Forensic QA Gate)
- **Date:** 2026-11-17
- **Overall Grade:** A
- **Verdict:** READY

---

## 1. Reality Check & Scope Validation

### 1.1 UI & Visual Proof Audit
- **Classification:** MCP Tool Schemas, Help Defaults, and Backend Workflow REST API Error Payloads.
- **UI Modifications:** Zero frontend React/TypeScript UI code, styles, templates, or HTML presentation were added or modified.
- **Browser Screenshot Requirement:** N/A (Confirmed non-UI ticket).

### 1.2 Specialist Gates Cross-Validation
- **Dual Specialist Mandate:** Both API and UI specialists must review MCP/API contract changes.
- **API Specialist Review:** `docs/qa/KAN-4/api-specialist-review.md` present and audited.
  - Reviewer: `api-specialist` (Backend Architect & API Tester Persona).
  - Assessment: Verified `VERIFICATION_PROOF_SCHEMA` typed properties (`qa_dir`, `artifacts`, `reality_checker` with enum/pattern validation, `ci_run_url`), `if_match` ETag schema hints, `help.py` parameter default alignment (`to_state`, `verification_proof`), and `INVALID_TRANSITION` hint generation with `extra.valid_states`.
  - Verdict: **APPROVED**.
- **UI Specialist Review:** `docs/qa/KAN-4/ui-specialist-review.md` present and audited.
  - Reviewer: `ui-specialist` (ArchitectUX & UI Designer Persona).
  - Assessment: Evaluated client and agent consumer ergonomics, self-documenting JSON schemas, elimination of parameter guessing, and actionable error recovery payloads.
  - Verdict: **APPROVED**.

---

## 2. Forensic Proof Packet Inspection (`docs/qa/KAN-4/`)

1. **`git-diff.patch`**:
   - Matches merged commit `8048b36`.
   - Modifies 10 files across MCP agent schemas, help generation, workflow services, and test suites.
   - Introduces `mcp/surfaces/agent/proof.py:VERIFICATION_PROOF_SCHEMA` replacing unconstrained object typing.
   - Enforces `VERIFICATION_PROOF_SCHEMA` across `complete_work.py` and `transition_ticket.py`.
   - Adds concise hints to `update_ticket.py` for `if_match` (64-char SHA-256 hex ETag requirement) and `description_markdown`.
   - Fixes `mcp/help.py` parameter defaults: changes legacy `"state"` to canonical `"to_state"` on `transition_ticket`, and adds explicit parameter defaults for `complete_work`.
   - Enriches `kanban/issues/workflow_service.py` to append valid workflow states to `detail` and return structured `extra={"hint": hint, "valid_states": valid_state_names}` on `INVALID_TRANSITION`.

2. **`changed-files-manifest.txt`**:
   - Lists 10 modified/created files cataloged.

3. **`unit-test-results.txt`**:
   - Verbatim pytest execution: 39 passed in 8.52s (`test_workflow_argument_validation.py`, `test_workflow_tools.py`, `test_update_ticket.py`, `test_schema_budget.py`, `test_lod_help.py`), Exit Code: 0.

4. **`build-check.txt`**:
   - Raw `ruff check mcp/ kanban/`: All checks passed.
   - Dash check: `scripts.check_no_dashes --all` passed with 0 violations.

5. **`contract-sample.json`**:
   - Concrete schema dumps for `COMPLETE_WORK_SCHEMA`, `UPDATE_TICKET_SCHEMA`, and sample `INVALID_TRANSITION` error payload with `extra.valid_states`.

---

## 3. Definition of Done Compliance Matrix

| Requirement | Implementation Evidence | Status |
| :--- | :--- | :---: |
| Explicit `verification_proof` Schema | `mcp/surfaces/agent/proof.py:VERIFICATION_PROOF_SCHEMA` with required fields, enum verdict, regex grade | PASS |
| Hardened `complete_work` & `transition_ticket` | Enforces `VERIFICATION_PROOF_SCHEMA` with `additionalProperties: false` | PASS |
| ETag Schema Hints on `update_ticket` | `if_match` documented as 64-char SHA-256 hex ETag required for description edits | PASS |
| Help Defaults Canonical Alignment | `transition_ticket` uses `"to_state"`; `complete_work` defines explicit parameter defaults | PASS |
| `INVALID_TRANSITION` Valid State Hints | Resolves valid project states, appends to `detail`, and exposes structured `extra.valid_states` | PASS |
| Completed Group Validation | Non-completed state in `complete_work` details valid completed states | PASS |
| Dual Specialist Approvals | API Specialist and UI Specialist both issued independent `APPROVED` verdicts | PASS |
| Comprehensive Proof Packet | Complete unified diff, 39 passed unit tests, clean linter and dash checks | PASS |

---

## 4. Certification

The forensic proof submitted in `docs/qa/KAN-4/` provides indisputable, comprehensive evidence of correctness, architectural isolation, schema hardening, and actionable error feedback for calling agents and clients.

- **Grade:** A
- **Verdict:** READY
