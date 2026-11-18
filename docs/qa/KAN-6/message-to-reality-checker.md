# Forensic QA Message: KAN-6 Verification Packet

## Summary of Changes
Ticket: KAN-6 (`[MCP-AGENT-LOD-FULL-03]`)
Branch: `feat/kan-4-5-6`
Base Commit: `323192a`

### Implementation Summary
1. `mcp/lod.py`:
   - Added `_compact_access_manifest(manifest)` stripping internal UUIDs (`workspace_id`, `project_id`, `principal_id`), redundant `canonical_key`/`object_type`, and zero counts (`explicit_grant_count: 0`, `redacted_count: 0`), preserving `pill_label`, `caller_capabilities`, compact `inherited_scope` (`kind`, `scope_label`, `project_key`), and compact principal entries (`handle`, `grant_source`, `capabilities`).
   - Added `_compact_manifest_principals` and `_compact_inherited_scope` helper functions to maintain strict cyclomatic complexity within linter limits.
   - Updated `_extract_provenance` to format `created_by` and `original_created_by` as `@handle` strings; when `overridden` is `False`, omitted `overridden` and `original_created_by`.
   - Updated `_project_issue_full` to apply `_compact_access_manifest`.
2. `mcp/surfaces/agent/read_ticket.py`:
   - Populated `normalized_issue["access"]` from `access_manifest.get("pill_label")` when top-level `issue_data.get("access")` is absent.
   - Applied `_compact_access_manifest` to `normalized_issue["access_manifest"]`.
   - Updated `_load_comments` to compact `author` as `@handle` and omit internal UUIDs (`author_id`, `issue_id`, `body_sha256`).
   - Updated `_load_activity` to omit internal `id`, `category`, format `actor` as `@handle` or agent slug, strip `from_state_id`, `to_state_id`, `body_sha256`, `comment`, and `body_markdown` from payload.
3. Tests:
   - Added `test_read_ticket_standard_populates_access_from_pill_label` and `test_read_ticket_full_compacts_manifest_activity_provenance` in `mcp/tests/agent/test_read_ticket.py`.
   - Added `test_provenance_overridden_boundary_cases` and `test_compact_access_manifest_unit` in `mcp/tests/test_lod_help.py`.
   - Token benchmark `mcp/tests/test_token_benchmark.py` passes with >= 78.0% token reduction.

## UI Specialist Gate & Visual Proof Note
Visual Screenshots: N/A - Non-UI Ticket.
This ticket modifies backend MCP server schemas, serialization, and LOD projection routines only. No HTML, CSS, frontend client components, or UI views were created or modified. Per project rules, Playwright UI screenshots are marked N/A.

## Artifact Manifest
- `git-diff.patch`: Complete diff between base `323192a` and current working tree excluding `docs/qa/KAN-6/`.
- `changed-files-manifest.txt`: List of modified files.
- `build-check.txt`: Ruff and Mypy validation outputs (0 errors, 0 warnings).
- `unit-test-results.txt`: Pytest execution results for targeted unit tests (31 passed).
- `contract-sample.json`: Representative before-and-after samples demonstrating compact serialization.
