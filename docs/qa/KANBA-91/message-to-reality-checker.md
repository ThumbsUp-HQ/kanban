# Reality-Checker Verification Packet: KANBA-91 (KB-P3-12)

## 1. Overview & Scope
- **Ticket ID**: `KANBA-91` (`KB-P3-12`: `[Phase 3 / API] Fractional Base-62 (COLLATE "C") board rank, 1-row move API, WIP limits & background rebalance`)
- **Author**: `builder-23`
- **Branch**: `feat/KANBA-91` (worktree: `/tmp/kb-wt-KANBA-91`)
- **Status**: Implemented, Verified (99.24% test coverage across target modules), Build Clean, Ticket remains OPEN on Kanban.

---

## 2. Definition of Done Compliance Matrix

| Requirement | Implementation Detail | Status |
| :--- | :--- | :--- |
| **Fractional Base-62 Rank Engine** | `kanban/services/board_rank.py` implementing ASCII byte-sorted `0-9A-Za-z` matching PostgreSQL `COLLATE "C"`, `is_valid_rank`, `validate_rank`, `to_base62`, `from_base62`, `allocate_initial_board_rank`, `midpoint_rank`, `generate_evenly_spaced_ranks`, and `rebalance_ranks`. | PASS |
| **1-Row Move REST API** | `POST /api/v1/issues/{issue_ref}/move` mounted on `build_v1_router()` in `kanban/api/v1/issue_move.py` with 25.0ms timing equalization via `timing_floor`. | PASS |
| **Single-Row Mutation Proof** | Moving card 50 between cards 2 and 3 in a 100-card column updates `board_rank` on exactly 1 row; remaining 99 sibling rows remain byte-identical. | PASS |
| **Soft & Hard WIP Limits** | Soft WIP limit returns `200` with `wip_warning: {soft_limit, resulting_count}`; hard WIP limit returns `409 WIP_HARD_LIMIT_EXCEEDED` for regular members. | PASS |
| **AAL2 Admin WIP Override** | Lacking AAL2 returns `403 AAL2_REQUIRED`; short reason (< 10 chars) returns `409 WIP_HARD_LIMIT_OVERRIDE_REQUIRED`; valid justification (10..500 chars) succeeds with `200` and records `WIP_HARD_LIMIT_OVERRIDDEN` in activity ledger. Intra-column reorder ignores WIP. | PASS |
| **Anchors & Conflict Detection** | `after_issue` and `before_issue` resolved under caller VIEW (`422 INVALID_ANCHOR`); reversed order returns `409 ANCHOR_ORDER_CONFLICT`. | PASS |
| **Security & Capabilities** | Intra-column move requires `Capability.EDIT`; cross-column move requires `Capability.EDIT` and `Capability.TRANSITION` (`403 INSUFFICIENT_CAPABILITY`); non-viewer returns `404 NOT_FOUND`. | PASS |
| **Background Rebalance & CLI** | `kanban/jobs/board_rebalance.py` with `pg_try_advisory_xact_lock`, bulk rank updates, `BOARD_COLUMN_REBALANCED` activity record, and `column.rebalanced` transactional outbox event. CLI registered at `kanban-ctl jobs run board-rebalance [--project <ID>]`. | PASS |
| **Mandatory Unit Tests & Coverage** | 18 tests passing in 4.24s with `99.24%` total branch+line coverage across target modules (`>= 95%` requirement met). | PASS |
| **Build & Lint Cleanliness** | Ruff check clean, Ruff format clean, Mypy strict clean (167 files), Lint-imports clean (2 kept, 0 broken), License gate clean (`violations=0`), 0 non-ASCII dashes. | PASS |

---

## 3. Forensic Artifact Index
- `docs/qa/KANBA-91/git-diff.patch`: Full unified git diff against `main`.
- `docs/qa/KANBA-91/unit-test-results.txt`: Raw pytest execution log with branch coverage report (99.24%).
- `docs/qa/KANBA-91/build-check.txt`: Static analysis, lint, formatting, imports, and license gate validation.
- `docs/qa/KANBA-91/contract-sample.json`: Recorded HTTP contract exchanges for 1-row move (200), soft WIP warning (200), hard WIP block (409), admin override (200), and anchor conflict (409).
- `docs/qa/KANBA-91/cli-run.txt`: Raw output of `uv run kanban-ctl jobs run board-rebalance` reindexing a fixture column with a 34-char rank.
- `docs/qa/KANBA-91/api-specialist-review.md`: Dual Specialist Gate review by `@arch-reviewer`.
- `docs/qa/KANBA-91/ui-specialist-review.md`: Dual Specialist Gate review by `@ui-specialist`.
- `docs/qa/KANBA-91/message-to-reality-checker.md`: This audit summary document.
