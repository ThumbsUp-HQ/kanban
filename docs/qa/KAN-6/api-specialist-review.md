# API Specialist Forensic QA Review: KAN-6

## Metadata
- **Ticket ID:** KAN-6
- **Title:** [MCP-AGENT-LOD-FULL-03] Compact read_ticket Full LOD Serialization: access_manifest, Activity, Comments, and Provenance Compactness
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `681886e` (merged into `main`)
- **Review Date:** 2026-11-17
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 `access_manifest` Compactness & Fallback Access Population
- **Access Pill Fallback (`mcp/surfaces/agent/read_ticket.py`):**
  - When top-level `issue_data.get("access")` is absent or None, `read_ticket` falls back to `access_manifest.get("pill_label")`, ensuring `access: "Project"` is reliably projected even in `lod=standard` without needing the full manifest.
- **Manifest Compaction (`mcp/lod.py:_compact_access_manifest`):**
  - Strips internal database UUIDs (`workspace_id`, `project_id`, `principal_id`).
  - Strips redundant metadata keys (`canonical_key`, `object_type`).
  - Omits zero-count fields (`explicit_grant_count: 0`, `redacted_count: 0`), emitting only positive counts.
  - Compacts `inherited_scope` to retain only `kind`, `scope_label`, and `project_key`.
  - Normalizes principal entries (`users`, `groups`, `agents`, `principals`) to compact objects containing clean `@handle`, `grant_source`, and `capabilities`.

### 1.2 Comments & Activity History Compaction
- **Comments (`mcp/surfaces/agent/read_ticket.py:_load_comments`):**
  - Normalizes `author` into a clean `@handle` string.
  - Strips internal UUIDs and redundant digests (`author_id`, `issue_id`, `body_sha256`).
- **Activity History (`mcp/surfaces/agent/read_ticket.py:_load_activity`):**
  - Omits internal ledger record `id` and `category`.
  - Normalizes `actor` into `@handle` or agent slug string.
  - Filters `payload` to remove redundant internal state IDs (`from_state_id`, `to_state_id`), `body_sha256`, and duplicate comments (`comment`, `body_markdown`).

### 1.3 Provenance Compaction (`mcp/lod.py:_extract_provenance`)
- Formats `created_by`, `original_created_by`, and `creator_modified_by` as clean `@handle` strings.
- When `overridden` is `False`, omits both `overridden` and `original_created_by`, minimizing context tokens for normal, non-overridden tickets.

---

## 2. Test Suite & Proof Verification

### 2.1 Unit & Integration Test Verification
- Executed `mcp/tests/agent/test_read_ticket.py`, `mcp/tests/test_lod_help.py`, and `mcp/tests/test_token_benchmark.py`:
  - **Result:** 31 passed in 3.40s, 0 failures, 0 regressions.
  - Verified:
    - `test_read_ticket_standard_populates_access_from_pill_label`: verifies `access: "Project"` is populated when top-level access is absent.
    - `test_read_ticket_full_compacts_manifest_activity_provenance`: verifies `access_manifest` strips internal UUIDs, comments compact author to `@handle`, and activity strips state IDs.
    - `test_provenance_overridden_boundary_cases`: verifies omitted `overridden: false`.
    - `test_token_benchmark.py`: Passes with >= 78.0% token reduction across LOD tiers.

### 2.2 Proof Artifacts Audit (`docs/qa/KAN-6/`)
- `git-diff.patch`: Clean unified diff matching commit `681886e`.
- `changed-files-manifest.txt`: 4 modified files cataloged.
- `unit-test-results.txt`: Confirms 31 passed tests with exit code 0.
- `build-check.txt`: Clean static analysis (`ruff check mcp/`, `mypy --strict mcp`).
- `contract-sample.json`: Representative before-and-after samples demonstrating compact serialization.
- `message-to-reality-checker.md`: Accurate non-UI declaration and requirement traceability.

---

## 3. Specialist Verdict

The implementation in commit `681886e` satisfies all LOD full compactness contracts, token reduction targets, and access manifest compaction invariants specified in KAN-6.

**Verdict: APPROVED**
