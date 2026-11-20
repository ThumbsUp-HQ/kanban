# KAN-49 Reality Checker Verification Packet

## Ticket Overview
- Identifier: KAN-49 ([KB-AGENT-SEQ-01])
- Title: Add DB Migration, Swarm Batch Sequence Allocator & SEQUENCE_SKIPPED Audit Event
- Branch: fix/KAN-20-36-rc2
- Base Commit: 7913c2c8 (main)

## Scope & Implementation Summary

### 1. Database Migration & Column-Level ORM Parity
- Migration: `p4_24_agent_safe_sequences` (`database/migrations/versions/p4_24_agent_safe_sequences.py`, `p4_24_agent_safe_sequences.up.sql`, `p4_24_agent_safe_sequences.down.sql`)
- Clean single-head linear chain off `p4_23_oidc_link_intent_fk` verified by `kanban-ctl db check-migrations` (63 valid migrations).
- Schema alterations:
  - Added `skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE` to `projects` table.
  - Added `default_skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE` to `workspace_settings` table.
  - Synced ORM models `database/models/projects.py` and `database/models/workspace_settings.py` with 100% column-level parity.
- Functions created:
  - `compute_agent_safe_sequence_batch(p_current_seq BIGINT, p_count INTEGER, p_skip_loaded BOOLEAN)`:
    - Pure `IMMUTABLE PARALLEL SAFE` function.
    - Skips ONLY exact integers `ARRAY[13, 69, 88, 404, 420, 666, 1337, 1488]` (preserves substrings like 113, 4040).
    - Validates bounds `1 <= p_count <= 1000` (raises `INVALID_SEQUENCE_COUNT`).
    - Enforces safety ceiling `c_max_skip_iterations = 16` (raises `SEQUENCE_SKIP_CEILING_EXCEEDED`).
  - `allocate_issue_sequences(p_project_id UUID, p_count INTEGER DEFAULT 1, p_emit_activity BOOLEAN DEFAULT TRUE)`:
    - `SECURITY DEFINER SET search_path = pg_catalog, public`.
    - Acquires `FOR UPDATE` lock on `projects` row once per batch.
    - Advances `issue_seq_counter` atomically by the required amount.
    - When `p_emit_activity = TRUE` and sequences were skipped, emits `SEQUENCE_SKIPPED` event to `activity_records` preserving the hash chain.
    - Returns `TABLE(allocated_sequences BIGINT[], skipped_sequences BIGINT[])`.
  - Backward compatibility:
    - `allocate_issue_sequence(p_project_id UUID)` delegates directly to `allocate_issue_sequences(p_project_id, 1, TRUE)` and returns single `BIGINT`, preserving existing callers.

### 2. Service Callers, Router Commits & Audit Event
- Added `ActivityEventType.SEQUENCE_SKIPPED = "SEQUENCE_SKIPPED"` mapped to `ActivityCategory.SYSTEM` in `kanban/services/activity.py`.
- Refactored callers to allocate in single batches:
  - `kanban/services/issues.py` (`create_issue`): Calls `allocate_issue_sequences(..., 1, false)` and records `SEQUENCE_SKIPPED` when sequences were skipped. `serialize_issue` and `update_issue` incorporate upstream schema enhancements (`populate_existing=True`, `now_utc`, `created_at`, `updated_at`, `color_hex=state.color_hex`, and `pending_transition_exec_id` `TRANSITION_HELD` 409 guard).
  - `kanban/issues/tree_service.py` (`create_issue_tree`): Computes tree size N, calls `allocate_issue_sequences(..., N, false)` once, distributes sequences sequentially in breadth-first traversal, and emits a single `SEQUENCE_SKIPPED` audit event.
  - `kanban/services/issue_copy.py` (`copy_issue`): Computes total copy batch size (1 + sub-issues count), calls `allocate_issue_sequences(..., total_count, false)` once, assigns sequence IDs, and emits a single `SEQUENCE_SKIPPED` audit event.
  - `kanban/services/projects.py`: Inherits `WorkspaceSettings.default_skip_loaded_sequence_numbers` upon project creation, and supports `skip_loaded_sequence_numbers` in project update and serialization.
  - `kanban/api/v1/{issues,issue_copy,issue_trees}.py`: Added explicit `await session.commit()` before returning responses to eliminate the 0ms post-response commit race.
- Cryptographic activity chain verified via `verify_activity_chain(workspace_id)`.

## Test Verification & Quality Gates
- Migration lifecycle test (`database/tests/migrations/test_p4_24_agent_safe_sequences_migration.py`):
  - Validates full upgrade -> downgrade -> upgrade cycle on hermetic database.
- Concurrency & batch tests (`database/tests/test_p1_05_sequence_concurrency.py`):
  - 20 concurrent connections allocation test (`test_06`).
  - 150 concurrent connections batch allocation test (`test_07`).
  - Exact skipping of 1..1500 loaded sequence numbers + preservation of substrings (`test_08`).
  - Boundary bounds testing for `INVALID_SEQUENCE_COUNT` (`test_09`).
  - Activity emission and `verify_activity_chain` verification (`test_10`).
- Service tests (`kanban/tests/services/test_agent_safe_sequences.py`):
  - Event registration in `ActivityEventType` and `ActivityCategory.SYSTEM`.
  - `create_issue` skipping and audit record emission.
  - `create_issue` non-skipping when `skip_loaded_sequence_numbers=False`.
  - `create_issue_tree` single batch allocation with skipping.
  - `copy_issue` single batch allocation with skipping.
- Regression test suite:
  - 65/65 issue, tree, copy, project, archive, and activity tests passed without failure.
  - 12/12 model, migration, and RLS catalog tests (`test_p1_17_models.py`, `test_p1_14_rls_catalog.py`, `test_p1_05_sequence_concurrency.py`, `test_p4_24_agent_safe_sequences_migration.py`) passed without failure.
  - **Backend Coverage: >=95% across ALL 10 KAN-49 modified modules (TOTAL 98%)**:
    * `database/models/projects.py`: 99%
    * `database/models/workspace_settings.py`: 100%
    * `kanban/api/v1/issue_copy.py`: 100%
    * `kanban/api/v1/issue_trees.py`: 100%
    * `kanban/api/v1/issues.py`: 100%
    * `kanban/issues/tree_service.py`: 95%
    * `kanban/services/activity.py`: 99%
    * `kanban/services/issue_copy.py`: 100%
    * `kanban/services/issues.py`: 97%
    * `kanban/services/projects.py`: 99%


## Static Verification
- `kanban-ctl db check-migrations`: PASS (63 valid migrations, single head).
- `ruff check database kanban`: PASS (0 errors, clean).
- `mypy database kanban`: PASS (0 errors across 748 source files).
- `lint-imports`: PASS (2 contracts kept, 0 broken).
- `python3 -m scripts.check_no_dashes`: PASS (0 em/en-dashes).
