# Reality Checker Evidence Packet: KAN-51

## Overview
- Ticket: KAN-51 ([KB-AGENT-SEQ-03] Emit Typed sequence_number and issue_key YAML Framing Across /mcp/agent Ticket Tools)
- Branch: feat/KAN-51 (branched from main 837f657d)
- Scope: mcp/lod.py and all 7 /mcp/agent ticket tools (read_ticket, search_tickets, create_ticket, update_ticket, begin_work, transition_ticket, complete_work), ensuring typed `key: str`, `issue_key: str`, and `sequence_number: int` across all LOD tiers and nested issue items.

## Changes Summary
1. `mcp/lod.py`:
   - Updated `_SUMMARY_ISSUE_KEYS` to include `key`, `issue_key`, and `sequence_number`.
   - Exported and implemented `extract_issue_sequence(raw: Any, key: str | None = None) -> int` to extract an integer sequence number from `sequence_number`, `sequence_id`, or by parsing the `<PROJECT>-<SEQ>` key pattern (with safety bounds checking).
   - Added `_project_child_issue(child: Any) -> dict[str, Any]` and `_normalize_issue_data(raw: Any) -> dict[str, Any]` to format child issues with typed sequence numbers and keys.
   - Updated `_project_issue_summary`, `_project_issue_standard`, and `_project_issue_full` to ensure `key`, `issue_key`, and `sequence_number: int` are present on every issue projection.
2. Target `/mcp/agent` Ticket Tools:
   - `mcp/surfaces/agent/create_ticket.py`: Returns `key`, `issue_key`, and `sequence_number: int` on root and nested child items.
   - `mcp/surfaces/agent/read_ticket.py`: Formats `key`, `issue_key`, and `sequence_number: int` on root issues and nested `children` items. Refactored into clean modular helpers to stay under cyclomatic complexity and statement limits.
   - `mcp/surfaces/agent/search_tickets.py`: Projects search results via `project_issue`, emitting typed `key`, `issue_key`, and `sequence_number: int` across summary and standard tiers.
   - `mcp/surfaces/agent/update_ticket.py`: Returns `key`, `issue_key`, and `sequence_number: int` in summary projection.
   - `mcp/surfaces/agent/begin_work.py`: Returns `key`, `issue_key`, and `sequence_number: int` on both normal responses and `pending_agent_gate` responses.
   - `mcp/surfaces/agent/transition_ticket.py`: Returns `key`, `issue_key`, and `sequence_number: int` on both normal responses and `pending_agent_gate` responses.
   - `mcp/surfaces/agent/complete_work.py`: Returns `key`, `issue_key`, and `sequence_number: int` on both normal responses and `pending_agent_gate` responses.
3. Unit Test Coverage:
   - Added comprehensive assertions for `issue_key` and `isinstance(sequence_number, int)` across all 7 agent tools and LOD profiles.
   - Added unit test cases for helper functions and edge cases in `mcp/tests/agent/test_read_ticket.py`, `mcp/tests/agent/test_search_tickets.py`, and `mcp/tests/test_lod_help.py`.
   - All 8 touched modules achieve >=96% line and branch coverage (total touched files coverage: 97%).
   - All 373 tests in the full `mcp/tests` suite pass with 0 regressions.
4. Static Analysis and Code Standards:
   - Ruff check: 0 errors
   - Ruff format: 0 errors
   - Mypy: 0 errors (checked 113 source files)
   - Lint imports: 0 errors (2 kept contracts, 0 broken)
   - Check no dashes: 0 em/en-dashes across all files

## Verification Evidence
- Git Diff: `docs/qa/KAN-51/git-diff.patch`
- Changed Files Manifest: `docs/qa/KAN-51/changed-files-manifest.txt`
- Unit Test Results and Coverage: `docs/qa/KAN-51/unit-test-results.txt`
- Build and Typecheck Results: `docs/qa/KAN-51/build-or-typecheck.txt`
