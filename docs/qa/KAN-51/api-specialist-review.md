# API Specialist Clean-Room Audit & Signoff: KAN-51

- Ticket: KAN-51 (`[KB-AGENT-SEQ-03]`)
- Title: MCP /mcp/agent Ticket Surface Parity for key, issue_key, sequence_number
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-51`
- Branch: `main`
- Commit: `07d04cde`
- Container Environment: `http://127.0.0.1:18963/mcp/agent` (container: `kanban-liveqa-3`)
- Live Stack Status: `LIVE_STACK_VERDICT: PASS`
- Status: STATUS: APPROVED

---

## 1. Executive Summary & Audit Scope

This clean-room API, Security, and Architectural Audit inspects ticket KAN-51 on `main` at commit `07d04cde`. Ticket KAN-51 establishes typed field parity for `key: str`, `issue_key: str`, and `sequence_number: int` across the Model Context Protocol (MCP) agent tool surface (`/mcp/agent`) and the Level-of-Detail (LOD) projection engine (`mcp/lod.py`). This review incorporates direct evidence from zero-mock live execution against container `kanban-liveqa-3` (`http://127.0.0.1:18963/mcp/agent`), verified unit test results (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

Under the project dual-specialist gate standard, this audit verifies that:
1. Every `/mcp/agent` ticket tool (`read_ticket`, `search_tickets`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`) emits strongly typed `key: str`, `issue_key: str`, and integer `sequence_number: int` across all execution outcomes, including normal success and `202 Accepted` (`pending_agent_gate`) holds.
2. The core LOD projection system in `mcp/lod.py` guarantees that all LOD profiles (`summary`, `standard`, `full`) and nested child hierarchies (`children` lists) preserve typed sequence numbers and dual key representations (`key` and `issue_key`).
3. The helper `extract_issue_sequence(raw, key)` safely resolves sequence numbers from dictionary fields (`sequence_number`, `sequence_id`) or falls back to robust parsing of composite `<PROJECT_KEY>-<SEQ>` keys, returning `0` on empty or malformed inputs without throwing unhandled exceptions.
4. Compact YAML serialization via `InlineSafeDumper` maintains strict token budgets without leaking YAML anchors or generating bloated payloads.
5. High unit test coverage is maintained: all 8 touched backend modules achieve `>=96%` line and branch coverage (overall touched files coverage: `97%`).
6. All 373 tests in the `mcp/tests` suite pass with 0 regressions, and all static analysis checks (`ruff`, `mypy`, `lint-imports`, `check_no_dashes`) pass with 0 errors and 0 em/en-dashes.
7. Zero-mock live stack verification on `kanban-liveqa-3` proves typed field serialization (`key: str`, `issue_key: str`, `sequence_number: int`) across all 7 tools, all 3 LOD tiers, and nested children.

---

## 2. Detailed Contract & Schema Verification

### 2.1 LOD Projection Engine (`mcp/lod.py`)
- Key Definitions:
  - Added `issue_key` and `sequence_number` to `_SUMMARY_ISSUE_KEYS` in `mcp/lod.py`.
  - Both keys are natively included in `_STANDARD_ISSUE_KEYS` and `_FULL_ISSUE_KEYS`.
- Sequence Extraction Helpers:
  - `_parse_seq_from_key(key: str | None) -> int`: Parses trailing integer from `<PROJECT>-<SEQ>` or numeric string; returns `0` if invalid or empty.
  - `extract_issue_sequence(raw: dict[str, Any] | None = None, key: str | None = None) -> int`:
    * Evaluates `sequence_number` and `sequence_id` in `raw`.
    * If missing or non-integer, resolves `key` or `issue_key` and parses via `_parse_seq_from_key`.
    * Safely catches `ValueError` and `TypeError`, guaranteeing non-crashing behavior.
- Normalization & Child Hierarchy:
  - `_normalize_issue_data(raw: dict[str, Any]) -> dict[str, Any]`: Automatically synchronizes `key`, `issue_key`, and `sequence_number` if either key field is present.
  - `_project_child_issue(child: dict[str, Any]) -> dict[str, Any]`: Projects sub-issues with typed `key`, `issue_key`, `sequence_number: int`, `summary`, `state`, `priority`, and `parent`.
  - `_project_issue_summary`, `_project_issue_standard`, and `_project_issue_full`: Normalize input and project `children` arrays through `_project_child_issue`.

### 2.2 Target `/mcp/agent` Ticket Surfaces
- `read_ticket.py`:
  - Formats `key`, `issue_key`, and `sequence_number: int` on root issues.
  - Formats nested `children` items using `_format_children` and `_project_child_issue`.
  - Refactored helper functions (`_extract_labels`, `_format_children`) reduce cyclomatic complexity and adhere to architectural layering.
- `search_tickets.py`:
  - Projects each search result through `project_issue(..., lod)`, ensuring consistent `key`, `issue_key`, and `sequence_number: int` on all returned ticket items across summary and standard profiles.
- `create_ticket.py`:
  - Formats `key`, `issue_key`, and `sequence_number: int` on created root tickets and child sub-issues.
- `update_ticket.py`:
  - Returns `key`, `issue_key`, and `sequence_number: int` in summary projection.
- `begin_work.py`:
  - Returns `key`, `issue_key`, and `sequence_number: int` on started tickets (`status: "started"`).
  - Returns `key`, `issue_key`, and `sequence_number: int` on held transitions (`status: "pending_agent_gate"`).
- `transition_ticket.py`:
  - Returns `key`, `issue_key`, and `sequence_number: int` on transitioned tickets (`status: "transitioned"`).
  - Returns `key`, `issue_key`, and `sequence_number: int` on held transitions (`status: "pending_agent_gate"`).
- `complete_work.py`:
  - Returns `key`, `issue_key`, and `sequence_number: int` on completed tickets (`status: "completed"`).
  - Returns `key`, `issue_key`, and `sequence_number: int` on held transitions (`status: "pending_agent_gate"`).

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt`)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-51/live-fullstack-proof.txt` executed against target container `kanban-liveqa-3` (`http://127.0.0.1:18963/mcp/agent`, commit `07d04cde`):
1. Key Minting & Authentication:
   - Minted scoped `/mcp/agent` key with prefix `kb_agt_`.
2. Hierarchical Ticket Creation (`create_ticket`):
   - Created root ticket `KAN-33` with nested children `KAN-34` and `KAN-35`.
   - Verified typed fields: root (`key: KAN-33`, `issue_key: KAN-33`, `sequence_number: 33`); child Alpha (`key: KAN-34`, `issue_key: KAN-34`, `sequence_number: 34`, `parent: KAN-33`); child Beta (`key: KAN-35`, `issue_key: KAN-35`, `sequence_number: 35`, `parent: KAN-33`).
3. Level-of-Detail Tiers (`read_ticket`):
   - `lod=summary`: `key: KAN-33`, `issue_key: KAN-33`, `sequence_number: 33`, `summary`, `state: Backlog`, `priority: high`.
   - `lod=standard`: typed key and sequence fields, `description_markdown`, outbound `PARENT_OF` links to `KAN-34` and `KAN-35`, `etag`, `access: Project`.
   - `lod=full`: typed key and sequence fields, `access_manifest` with user/agent capabilities, immutable `activity` log, `provenance`.
4. Discovery & Search (`search_tickets`):
   - `lod=summary`: `mode: lexical`, `executed_mode: lexical`, total: 5. All items (`KAN-33`, `KAN-30`, `KAN-27`, `KAN-24`, `KAN-21`) contain `key: str`, `issue_key: str`, `sequence_number: int`, and `match_reason`.
   - `lod=standard`: All items include typed key and sequence fields, `description_markdown`, `workspace: kanban`, and `match_reason`.
5. Lifecycle Transitions:
   - `update_ticket`: `key: KAN-33`, `issue_key: KAN-33`, `sequence_number: 33`, `changed: [summary]`, `etag`.
   - `begin_work`: `status: started`, `key: KAN-33`, `issue_key: KAN-33`, `sequence_number: 33`, `state: In Progress`, `assignees: ['@admin']`, `comment: KAN-33#c-01a1fab7`.
   - `transition_ticket`: `status: transitioned`, `key: KAN-33`, `issue_key: KAN-33`, `sequence_number: 33`, `from_state: In Progress`, `to_state: Todo`.
   - `complete_work`: `status: completed`, `key: KAN-33`, `issue_key: KAN-33`, `sequence_number: 33`, `state: Done`, `proof: {qa_dir: docs/qa/KAN-33/, artifacts: 1, verdict: READY}`, `comment: KAN-33#c-01a1fab7`.
6. Live Stack Verdict:
   - Verified `yaml.safe_load -> isinstance(key, str), isinstance(issue_key, str), isinstance(sequence_number, int)` across ALL 7 tools, all 3 LOD tiers, and nested children.
   - `LIVE_STACK_VERDICT: PASS`

---

## 4. Test Suite & Coverage Verification

- Full MCP Test Suite (`unit-test-results.txt`):
  - 373 passed in 58.96s with 0 regressions.
  - Token benchmarks (`test_token_benchmark.py`), schema budgets (`test_schema_budget.py`), and error disclosure contracts all pass cleanly.
- Touched Modules Scoped Coverage (`unit-test-results.txt`):
  - `mcp/tests/test_lod_help.py`: 18 passed in 0.18s.
  - `mcp/tests/agent/`: 85 passed in 50.23s.
  - Line and branch coverage across touched modules:
    * `mcp/lod.py`: 97% (301 stmts, 3 miss, 196 branch, 14 brpart)
    * `mcp/surfaces/agent/begin_work.py`: 96% (73 stmts, 2 miss, 28 branch, 2 brpart)
    * `mcp/surfaces/agent/complete_work.py`: 96% (93 stmts, 2 miss, 36 branch, 3 brpart)
    * `mcp/surfaces/agent/create_ticket.py`: 96% (124 stmts, 4 miss, 62 branch, 3 brpart)
    * `mcp/surfaces/agent/read_ticket.py`: 96% (269 stmts, 4 miss, 140 branch, 13 brpart)
    * `mcp/surfaces/agent/search_tickets.py`: 99% (172 stmts, 1 miss, 84 branch, 2 brpart)
    * `mcp/surfaces/agent/transition_ticket.py`: 96% (96 stmts, 4 miss, 38 branch, 2 brpart)
    * `mcp/surfaces/agent/update_ticket.py`: 97% (253 stmts, 2 miss, 160 branch, 11 brpart)
    * Total Touched Modules: 97% coverage (1381 stmts, 22 miss, 744 branch, 50 brpart). All modules exceed the 95% threshold.
- Static Analysis Gates (`build-or-typecheck.txt`):
  - `ruff check mcp`: Clean (All checks passed).
  - `ruff format --check mcp`: Clean (115 files already formatted).
  - `mypy mcp`: Clean (Success: no issues found in 113 source files).
  - `lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Key Typings | `key: str` and `issue_key: str` | Emitted across all ticket tools | PASS |
| Sequence Typings | `sequence_number: int` | Integer validated in all responses | PASS |
| Safe Sequence Parsing | Non-crashing parser for keys | `extract_issue_sequence` handles malformed input | PASS |
| Child Projection Parity | Sub-issues inherit typed sequence fields | `_project_child_issue` ensures consistency | PASS |
| Pending Gate Framing | Held transitions retain sequence fields | Verified in `begin`, `transition`, `complete` | PASS |
| Token Budget Preservation | Compact YAML serialization | Verified in benchmark and budget suites | PASS |
| Unidirectional Layering | Layer hierarchy preserved | `lint-imports` confirms 2 kept, 0 broken | PASS |
| Coverage Mandate | >=95% coverage on all touched files | 97% achieved across all 8 modules | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All `/mcp/agent` ticket tools and the LOD projection engine in `mcp/lod.py` for KAN-51 on `main` at commit `07d04cde` have been thoroughly audited, verified against unit test coverage and static analysis gates, and certified on live stack `kanban-liveqa-3` with `LIVE_STACK_VERDICT: PASS`. Both API Specialist and UI Specialist gates are complete. Ready for Clean-Room Reality-Checker QA.
