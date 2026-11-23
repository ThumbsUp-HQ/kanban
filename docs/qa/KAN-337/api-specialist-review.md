# API and Security Specialist Review: KAN-337

- **Ticket:** KAN-337 ([KB-REDTEAM-06]) - Wire Read-Taint Guards and Exfiltration Blocks Across Docs and Stickies Endpoints
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-23
- **Branch:** `feat/KAN-337-341`
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan337-341-814e49d3`
- **Status:** APPROVED

---

## 1. Executive Security Evaluation

Ticket KAN-337 addresses red-team finding GSF-020 and KAN-63 architectural mandates by closing prompt-injection read-taint and exfiltration blind spots across all Document, Page, and Sticky note REST endpoints:
1. **Read-Taint Ingestion:** Wires FastAPI dependency `TaintRecorder` across read routes in `kanban/api/v1/docs.py` (`get_doc`, `list_docs`, `get_page`, `list_pages`, `list_page_versions`) and `kanban/api/v1/stickies.py` (`get_sticky`, `list_project_stickies`, `list_workspace_stickies`). When an agent or caller under `mcp-gateway` reads sensitive docs or stickies, the project scope is recorded into `mcp_read_taint`.
2. **Exfiltration & Mutation Guards:** Wires `TaintGuard` across all mutating endpoints in `docs.py` (`create_doc`, `update_doc`, `delete_doc`, `create_project_page`, `create_page`, `update_page`, `delete_page`, `move_page`, `restore_page`) and `stickies.py` (`create_sticky`, `update_sticky`, `delete_sticky`, `promote_sticky_to_doc`, `snooze_sticky_promotion`, `unarchive_sticky_as_copy`).
3. **Fail-Closed Enforcement:** Subsequent attempts to write, mutate, or promote content into broader-ACL projects raise `409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED` and write an immutable `MCP_TAINT_BLOCKED` audit record to the activity ledger.

---

## 2. API Contract & Coverage Metrics

- **Unit Test Suite:** `kanban/tests/security/test_docs_stickies_read_taint.py`
  - `test_case_1_docs_read_taint_recorded_and_blocks_cross_project_write`: PASSED
  - `test_case_2_stickies_read_taint_recorded_and_blocks_cross_project_write`: PASSED
  - `test_case_3_pages_and_stickies_mutation_blocks`: PASSED
- **Existing Regression Suite:** `kanban/tests/api/test_docs_pages.py` (9 passed) and `kanban/tests/api/test_stickies.py` (7 passed) remain 100% green.
- **Coverage:** `>=95%` code coverage achieved across modified endpoint logic.
- **Dashes & Linter Invariants:** Zero em-dashes and zero en-dashes; `make check` passes with 0 errors.

**Recommendation:** APPROVED for merge.
