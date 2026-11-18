# UI Specialist Forensic QA Review: KAN-6

- **Ticket ID:** `KAN-6` ([MCP-AGENT-LOD-FULL-03])
- **Ticket Title:** Compact read_ticket Full LOD Serialization: access_manifest, Activity, Comments, and Provenance Compactness
- **Auditor:** `ui-specialist` (ArchitectUX & UI Designer Specialist)
- **Merged Commit:** `681886e` on `main`
- **Review Date:** 2026-11-17
- **Verdict:** `APPROVED`

---

## 1. Executive Summary & Review Scope

As part of the mandatory dual specialist gate for API and MCP contract modifications, an independent audit of ticket `KAN-6` was conducted on `main` at commit `681886e`.

The review focused on the UI, agent, and cognitive ergonomics of the MCP `read_ticket` serialization across `lod="standard"` and `lod="full"` projections:
1. **Access Pill Population in Standard LOD (`read_ticket.py`):** Ensuring that tickets with absent or unhydrated top-level `access` attributes reliably project the human-readable pill label from the access manifest (e.g. `access: "Project"`).
2. **Access Manifest Compaction in Full LOD (`lod.py`):** Elimination of internal database UUIDs (`workspace_id`, `project_id`, `principal_id`), redundant keys (`canonical_key`, `object_type`), and zero-count noise (`explicit_grant_count: 0`, `redacted_count: 0`).
3. **Timeline & Activity History Ergonomics (`read_ticket.py`):** Normalization of `actor` to clean `@handle` strings, removal of internal state UUIDs (`from_state_id`, `to_state_id`) and hash digests (`body_sha256`), and elimination of duplicate comment bodies inside activity event payloads.
4. **Comments Streamlining (`read_ticket.py`):** Formatting authors as `@handle` strings and removing internal UUIDs and redundant checksums.
5. **Provenance Compaction (`lod.py`):** Pruning redundant `original_created_by` and `overridden: false` keys when provenance has not been overridden.
6. **Forensic Proof Packet Validation (`docs/qa/KAN-6/`):** Audit of `git-diff.patch`, `contract-sample.json`, `build-check.txt`, `unit-test-results.txt`, and confirmation of the non-UI screenshot exemption (`N/A - Non-UI Ticket`).

---

## 2. Non-UI Exemption & Visual Asset Audit

- **Screenshot Exemption:** Per `docs/qa/KAN-6/message-to-reality-checker.md`, this ticket exclusively refines backend MCP response serialization, LOD projection routines, and token compaction helpers. No frontend templates, CSS stylesheets, or browser DOM components were added or altered.
- **Visual Artifacts:** Declared `N/A - Non-UI Ticket`.

---

## 3. Agent & Client Consumer Ergonomics Audit

### 3.1 Reliable Access Scope Exposure in Standard LOD
- **Previous Defect:** When top-level `issue_data.get("access")` was null or missing in raw database rows, `read_ticket(lod="standard")` omitted the access scope entirely, leaving calling agents and lightweight UI views unaware of access boundaries without incurring the token cost of `lod="full"`.
- **Remediated State:** In `read_ticket.py:640-646`, `read_ticket` falls back to `access_manifest.get("pill_label")`, guaranteeing `access: "Project"` is reliably projected.
- **UX Impact:** Direct, immediate visibility of sharing/access scope in compact card feeds and agent reasoning loops without payload bloat.

### 3.2 Signal-to-Noise Compaction in `access_manifest`
- **Previous Defect:** The full access manifest leaked multiple internal PostgreSQL UUIDv7 identifiers (`workspace_id`, `project_id`, `principal_id`), repeated the ticket key and object type, and emitted verbose zero counts (`explicit_grant_count: 0`, `redacted_count: 0`).
- **Remediated State:**
  - `_compact_access_manifest` strips all internal UUIDs.
  - User entries format handles cleanly as `@handle` with explicit capabilities (`["ADMIN", "EDIT", "VIEW"]`).
  - `inherited_scope` retains only essential human-readable fields (`kind`, `scope_label`, `project_key`).
- **UX Impact:** Eliminates context clutter and reduces cognitive load for agents reading sharing permissions.

### 3.3 Activity Feed & Comments Readability
- **Previous Defect:** Activity items contained raw database record IDs, category flags, dictionary actors `{"handle": "adam", "type": "USER"}`, foreign key UUIDs (`from_state_id`, `to_state_id`), 64-character SHA-256 hashes, and duplicate comment text.
- **Remediated State:**
  - Activity items project a clean timeline: `event_type`, `actor: "@adam"`, `created_at`, and a simplified `payload` with human-readable state names (`from_state: "Backlog"`, `to_state: "In Progress"`).
  - Comments strip internal `author_id`, `issue_id`, and `body_sha256`, presenting clean `@author` attribution.
- **UX Impact:** Activity and comment streams render as natural, legible conversational logs rather than verbose database dumps.

### 3.4 Provenance Normalization
- When `overridden` is false (the vast majority of issues), `_extract_provenance` returns only `created_by: "@handle"`, omitting the redundant duplicate `original_created_by` and boolean flag.
- When overridden is true, both distinct `@handle` strings and the `overridden: true` indicator are clearly displayed.

---

## 4. Test Verification & Code Quality Status

- **Unit & Integration Test Suite:**
  - `mcp/tests/agent/test_read_ticket.py` (11 passed, including full manifest compaction tests)
  - `mcp/tests/test_lod_help.py` (15 passed, verifying provenance boundary cases and manifest unit tests)
  - `mcp/tests/test_token_benchmark.py` (5 passed, confirming >= 78.0% token reduction across LOD tiers)
  - Total: 31 tests passed in 3.06s with 0 failures (`docs/qa/KAN-6/unit-test-results.txt`).
- **Static Analysis & Type Checks:**
  - `ruff check mcp/` passed with 0 errors (`docs/qa/KAN-6/build-check.txt`).
  - `mypy --strict mcp` passed with 0 issues found.
  - `python3 -m scripts.check_no_dashes --all` passed with 0 violations.

---

## 5. Final Verdict

**VERDICT: `APPROVED`**

Ticket `KAN-6` dramatically optimizes `read_ticket` serialization, eliminating database UUID noise, formatting actors and authors as clean `@handle` references, and ensuring consistent access pill exposure to deliver superior ergonomics for agent and UI consumers.
