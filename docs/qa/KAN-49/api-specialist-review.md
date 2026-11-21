# API Specialist Clean-Room Audit & Signoff: KAN-49

- **Ticket:** KAN-49 (`[KB-AGENT-SEQ-01]`)
- **Title:** Add DB Migration, Swarm Batch Sequence Allocator & SEQUENCE_SKIPPED Audit Event
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-49`
- **Branch:** `main` (commit `78074a1d`)
- **Container Environment:** `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Audit Scope

This clean-room API, Security, and Database Architecture audit inspects ticket **KAN-49** on branch `main` at commit `78074a1d`. KAN-49 establishes agent-safe sequence allocation across the universal object graph, preventing collision with culturally sensitive or agent-triggering loaded numbers while maintaining strict relational integrity, linear migration history, high-concurrency throughput, and cryptographic audit accountability. This review incorporates direct evidence from zero-mock live execution against container `kanban-liveqa-3` (`http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-49/live-fullstack-proof.txt`, verified unit test results (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

The implementation addresses four architectural requirements and incorporates all reality-checker remediations:
1. **Linear Single-Head Database Migration (`p4_24_agent_safe_sequences`):**
   - Adds `skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE` to `projects`.
   - Adds `default_skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE` to `workspace_settings`.
   - Synchronizes SQLAlchemy ORM models with 100% column-level parity (`database/models/projects.py` and `database/models/workspace_settings.py`).
   - Clean linear migration chaining off `p4_23_oidc_link_intent_fk` verified by `kanban-ctl db check-migrations` (63 valid migrations).
2. **Pure Sequence Mathematics & Atomic Locking:**
   - Pure function `compute_agent_safe_sequence_batch(p_current_seq BIGINT, p_count INTEGER, p_skip_loaded BOOLEAN)` declared `IMMUTABLE PARALLEL SAFE`.
   - Skips only exact integers `ARRAY[13, 69, 88, 404, 420, 666, 1337, 1488]`.
   - Preserves substrings (e.g. `113`, `4040`, `6660`) without false positive filtering.
   - Enforces bounds checking (`1 <= p_count <= 1000`, raising `INVALID_SEQUENCE_COUNT`) and safety loop ceiling (`c_max_skip_iterations = 16`, raising `SEQUENCE_SKIP_CEILING_EXCEEDED`).
   - State-modifying function `allocate_issue_sequences(p_project_id UUID, p_count INTEGER, p_emit_activity BOOLEAN)` declared `SECURITY DEFINER SET search_path = pg_catalog, public`.
   - Acquires `FOR UPDATE` lock once per batch on the target `projects` row, eliminating lock thrashing.
   - Preserves backward compatibility via legacy delegate `allocate_issue_sequence(p_project_id UUID)`.
3. **Service Integration & Batch Optimization:**
   - Registered `ActivityEventType.SEQUENCE_SKIPPED = "SEQUENCE_SKIPPED"` mapped to `ActivityCategory.SYSTEM` in `kanban/services/activity.py`.
   - Refactored `create_issue` (`kanban/services/issues.py`): allocates sequence via `allocate_issue_sequences(:proj, 1, false)` and records `SEQUENCE_SKIPPED` via Python's `record_activity`, maintaining strict boundary discipline (zero modifications to `serialize_issue`).
   - Refactored `create_issue_tree` (`kanban/issues/tree_service.py`): computes total node count N, executes single batch allocation, assigns sequence IDs via breadth-first traversal, and emits a single consolidated `SEQUENCE_SKIPPED` event.
   - Refactored `copy_issue` (`kanban/services/issue_copy.py`): computes total count `1 + len(readable_rows)`, executes single batch allocation, assigns sequence IDs across parent and sub-issues, and emits a single consolidated `SEQUENCE_SKIPPED` event.
4. **Cryptographic Audit Chain & Comprehensive Test Coverage:**
   - All `SEQUENCE_SKIPPED` audit events preserve ledger continuity, verified by `verify_activity_chain(workspace_id)`.
   - Live execution on container `kanban-liveqa-3` confirmed `verify_activity_chain('01a1fb43-704a-786f-8bf1-28f9315b14ef')` returned `is_valid=t`, `checked_rows=463`, `first_broken_seq=NULL`.
   - Comprehensive test coverage: Database tests (12 passed in 5.98s), Kanban tests (65 passed in 49.69s), totaling 77 passed tests with 98% statement and branch coverage across all 10 modified production files (1565 statements, 450 branches).

---

## 2. Detailed Contract & Security Verification

### 2.1 Database Schema & Migration Parity
- Files Audited:
  * `database/migrations/versions/p4_24_agent_safe_sequences.py`
  * `database/migrations/sql/p4_24_agent_safe_sequences.up.sql`
  * `database/migrations/sql/p4_24_agent_safe_sequences.down.sql`
  * `database/models/projects.py`
  * `database/models/workspace_settings.py`
- Schema Invariants:
  * Migration cleanly downgrades back to `p4_23_oidc_link_intent_fk` by dropping batch functions, dropping columns, and restoring the original `allocate_issue_sequence(uuid)` definition.
  * Full lifecycle upgrade -> downgrade -> upgrade tested and verified in `database/tests/migrations/test_p4_24_agent_safe_sequences_migration.py`.
  * Column parity:
    - `projects.skip_loaded_sequence_numbers`: mapped in `Project` as `Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))`.
    - `workspace_settings.default_skip_loaded_sequence_numbers`: mapped in `WorkspaceSettings` as `Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")`.
  * Ownership & Grants:
    - `compute_agent_safe_sequence_batch`: Owner `kanban_migrator`, granted to `kanban_app, app_rls_reader`.
    - `allocate_issue_sequences`: Owner `kanban_migrator`, granted to `kanban_app`.
    - `allocate_issue_sequence`: Owner `kanban_migrator`, granted to `kanban_app`.

### 2.2 Live Full-Stack Execution on Container `kanban-liveqa-3` (`:18963`, Commit `78074a1d`)
1. **Single Issue Sequence Progression:**
   - Created SAFE-1 through SAFE-12 sequentially.
   - Next single issue creation allocated `SAFE-14` (sequence 13 was skipped cleanly).
   - PostgreSQL activity ledger emitted `SEQUENCE_SKIPPED` event:
     `70|SEQUENCE_SKIPPED|{"reason": "agent_safe_sequence_numbering", "project_key": "SAFE", "skipped_sequences": [13], "allocated_sequence": 14}`.
2. **Issue Tree Batch Sequence Allocation:**
   - Created 5-issue tree batch starting at sequence 68:
     Allocated keys: `['SAFE-68', 'SAFE-70', 'SAFE-71', 'SAFE-72', 'SAFE-73']` (sequence 69 was skipped cleanly in batch).
     `125|SEQUENCE_SKIPPED|{"reason": "agent_safe_sequence_numbering", "project_key": "SAFE", "skipped_sequences": [69], "allocated_sequence": 68}`.
3. **Substring Preservation & 88 Boundary:**
   - Created 40-issue batch spanning 74 to 114:
     Skipped sequence 88; allocated sequence 113 (`SAFE-113` was NOT skipped, confirming substring preservation).
     `131|SEQUENCE_SKIPPED|{"reason": "agent_safe_sequence_numbering", "project_key": "SAFE", "skipped_sequences": [88], "allocated_sequence": 74}`.
4. **Immediate 0ms Copy Issue Allocation:**
   - Executed `POST /api/v1/issues/SAFE-401/copy` right after issue tree creation at 0ms latency:
     Succeeded on the very first attempt with HTTP 201 Created (0ms commit race permanently eliminated).
     Allocated root `SAFE-403` and sub-issue `SAFE-405` (sequence 404 skipped cleanly).
     `460|SEQUENCE_SKIPPED|{"reason": "agent_safe_sequence_numbering", "project_key": "SAFE", "skipped_sequences": [404], "allocated_sequence": 403}`.
5. **Ledger Integrity:**
   - Ran `verify_activity_chain('01a1fb43-704a-786f-8bf1-28f9315b14ef')`:
     `is_valid=True`, `checked_rows=463`, `first_broken_seq=NULL`.
6. **UI & Page Load Performance:**
   - Measured board and list view load latencies across Desktop Light/Dark, Tablet, Mobile:
     Desktop Light Board: 1917ms; Desktop Dark Board: 1887ms; Tablet: 1847ms; Mobile: 1805ms; Desktop List: 1891ms; SAFE-14 detail: 829ms (all well below 3000ms threshold).
     `consoleErrors=0`, `pageErrors=0`, `badResponses=0`.

---

## 3. Test Suites, Coverage, & Static Analysis Verification

### 3.1 Test Suites and Coverage Breakdown (98% Coverage)
- **Database Suite:** 12/12 passed in 5.98s (`test_p1_17_models.py`, `test_p1_14_rls_catalog.py`, `test_p1_05_sequence_concurrency.py`, `test_p4_24_agent_safe_sequences_migration.py`).
- **Kanban Suite:** 65/65 passed in 49.69s (`test_agent_safe_sequences.py`, `test_activity.py`, `test_issues.py`, `test_issue_copy.py`, `test_issue_trees.py`, `test_projects.py`, `test_issue_patch_etag_parity.py`, `test_issue_archive.py`).
- **Combined Results:** 77 passed in 55.67s (100% pass rate).
- **Coverage on 10 Modified Production Files:**
  * `database/models/projects.py`: 99% (108 stmts, 1 miss)
  * `database/models/workspace_settings.py`: 100% (22 stmts)
  * `kanban/api/v1/issue_copy.py`: 100% (18 stmts)
  * `kanban/api/v1/issue_trees.py`: 100% (20 stmts)
  * `kanban/api/v1/issues.py`: 100% (58 stmts)
  * `kanban/issues/tree_service.py`: 95% (344 stmts, 152 branch)
  * `kanban/services/activity.py`: 99% (214 stmts, 8 branch)
  * `kanban/services/issue_copy.py`: 100% (126 stmts, 40 branch)
  * `kanban/services/issues.py`: 97% (461 stmts, 186 branch)
  * `kanban/services/projects.py`: 99% (194 stmts, 56 branch)
  * **TOTAL:** 98% across 1565 statements and 450 branches (surpassing 95% threshold).

### 3.2 Static Gate Verification (Commit `78074a1d`)
- `uv run kanban-ctl db check-migrations`: OK: 63 migrations valid, single head (`p4_24_agent_safe_sequences`).
- `uv run ruff check .`: Clean across 2023 files.
- `uv run ruff format --check .`: Clean across 2023 files.
- `uv run mypy database kanban mcp agent`: Clean (Success: 995 source files).
- `uv run lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `pnpm --dir kanban/web run typecheck`: Clean (0 errors).
- `pnpm --dir kanban/web run lint`: Clean (0 errors, 0 warnings).
- `pnpm --dir kanban/web run build`: Production bundle built in 1.15s.
- `python3 -m scripts.check_no_dashes --all` and `thumbs-up-kanban.wiki`: 0 forbidden unicode dashes.

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Exact Sequence Skipping** | Skip only exact integers `[13, 69, 88, 404, 420, 666, 1337, 1488]` | Immutable PL/pgSQL function | PASS |
| **Substring Safety** | Keep `113`, `4040`, `6660` without false positives | Strict integer equality in array search | PASS |
| **Locking Isolation** | `FOR UPDATE` on projects row per batch | Serialized batch lock in PL/pgSQL | PASS |
| **Single-Allocation Trees** | Batch sequence allocation for issue trees | `create_issue_tree` single batch call | PASS |
| **Single-Allocation Copies** | Batch sequence allocation for issue clones | `copy_issue` single batch call | PASS |
| **Audit Ledger Continuity** | `SEQUENCE_SKIPPED` preserved in hash chain | `verify_activity_chain` returns `is_valid=t` | PASS |
| **Single Migration Head** | Linear single-head migration chain | Verified via `check-migrations` (63 valid) | PASS |
| **Unidirectional Layering** | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| **Style Compliance** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Certification Signoff

STATUS: APPROVED

Ticket KAN-49 is fully verified on `main` at commit `78074a1d` against live container `kanban-liveqa-3` (`:18963`, `LIVE_STACK_VERDICT: PASS`). Database migration `p4_24_agent_safe_sequences`, batch sequence allocation functions, service callers, audit ledger chain continuity, and unit test coverage (98% across 10 touched modules) are certified ready for reality-checker QA gate closure.
