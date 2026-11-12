# Forensic Verification Audit Packet: KANBA-43

- Ticket ID: KANBA-43
- Title: [Phase 1 / Database] Partitioned SHA-256 hash-chained activity_records, append_activity() & verify_activity_chain()
- Epic: KB-E1
- Spec References: S1.2, S12.2, S7.2 (8d), S12.3
- Gates: reality-checker (Grade A Certification Required)
- Author: builder-22
- Worktree: /tmp/kb-wt-KANBA-43
- Branch: feat/KANBA-43
- Base Commit: 24b7ddb (main)

---

## 1. Executive Summary

This ticket implements an append-only, monthly-partitioned `activity_records` ledger whose rows form an unbroken, per-workspace SHA-256 hash chain with immutable genesis state (`\x00` * 32). Modifications and deletions are strictly blocked at both the database trigger layer (`ACTIVITY_LEDGER_IMMUTABLE`) and role privilege layer (SQLSTATE 42501).

The cryptographic chain is continuously verifiable via `verify_activity_chain(p_workspace_id)`, which returns forensic diagnostics (`is_valid`, `checked_rows`, `first_broken_seq`, `first_broken_id`, `failure_reason`) detecting sequence gaps (`SEQ_GAP`), broken links (`PREV_HASH_MISMATCH`), payload mutations (`ROW_HASH_MISMATCH`), and chain-head discrepancies (`HEAD_MISMATCH`).

All touched modules have achieved 100% unit test coverage across 9 test cases in 1.33 seconds, with zero linter, type-check, or unicode dash violations.

---

## 2. Deliverables & File Index

### Migration and DDL
1. `database/migrations/versions/p1_12_activity_ledger.py`:
   - Single-head migration linking `down_revision = "p1_11_object_links"`.
2. `database/migrations/sql/p1_12_activity_ledger.up.sql`:
   - `activity_chain_heads` table storing `(workspace_id, last_seq, last_hash, updated_at)` with `REVOKE ALL` from application roles.
   - `activity_records` partitioned by range on `recorded_at` (`id` default `uuidv7()`, `workspace_id`, `chain_seq`, nullable `object_id`/`object_type` pair, `actor_id` referencing `principals(id)`, `event_type` regex `^[A-Z][A-Z0-9_]{2,63}$`, `payload` jsonb <= 16384 bytes, `prev_hash`, `row_hash`).
   - `compute_activity_row_hash()` IMMUTABLE PARALLEL SAFE canonical hash function (`digest(prev_hash || convert_to(concat_ws('|', ...), 'UTF8'), 'sha256')`).
   - `ensure_activity_partitions(p_ref, p_months_back, p_months_ahead)` SECURITY DEFINER advisory-locked partition maintainer pre-generating -1..+6 months.
   - `activity_records_chain_bi()` BEFORE INSERT trigger managing row sequence, prev_hash linking, row_hash calculation, and chain head updates.
   - `activity_records_immutable_bud()` BEFORE UPDATE OR DELETE trigger raising `ACTIVITY_LEDGER_IMMUTABLE`.
   - `append_activity(workspace_id, object_id, object_type, actor_id, event_type, payload)` helper returning UUID.
   - `verify_activity_chain(workspace_id)` STABLE SECURITY DEFINER returning forensic diagnostics.
3. `database/migrations/sql/p1_12_activity_ledger.down.sql`:
   - Complete, reversible teardown in reverse dependency order.

### Test Suites (100% Coverage on Touched Modules)
4. `database/tests/test_p1_12_activity_ledger.py`:
   - `test_01_activity_hash_chain_and_verifier_positive`: 5 events, genesis hash, prev_hash linking, timezone invariance.
   - `test_02_partition_rollover_and_continuous_chain`: Dynamic partition creation across year boundary into distinct tableoid partitions.
   - `test_03_immutability_trigger_and_forgery_defense`: Superuser UPDATE/DELETE rejected by trigger; forged client hashes overwritten.
   - `test_03_privilege_rejections_as_kanban_app`: Least-privilege `kanban_app` UPDATE/DELETE rejected with SQLSTATE 42501.
   - `test_04_tamper_detection`: Scenarios (a) payload mutation -> ROW_HASH_MISMATCH, (b) row_hash recomputed without next prev_hash -> PREV_HASH_MISMATCH, (c) row deletion -> SEQ_GAP.
   - `test_06_boundary_payload_and_event_type`: Payload exact 16384 bytes succeeds, 16385 bytes raises 23514; invalid event_type regex raises 23514.
   - `test_06_boundary_null_pairs_and_mismatches`: Null pairing constraints raise 23514; cross-workspace or non-existent objects raise ACTIVITY_OBJECT_MISMATCH; partition range bounds; empty workspace.
5. `database/tests/test_p1_12_chain_concurrency.py`:
   - `test_05_chain_concurrency_stress`: 16 concurrent workers appending 5 events each (80 total) with 0 deadlocks and unbroken chain.
6. `database/tests/migrations/test_p1_12_migration.py`:
   - `test_07_activity_ledger_migration_lifecycle`: Up to p1_12, verify tables/functions; down to p1_11, verify absence; re-up to p1_12.

---

## 3. Definition of Done Compliance Matrix

| DoD Requirement | Status | Evidence Location |
| :--- | :---: | :--- |
| File existence & implementation | PASS | `database/migrations/versions/p1_12_activity_ledger.py`, `.up.sql`, `.down.sql` |
| Exactly one Alembic head | PASS | `docs/qa/KANBA-43/alembic-heads.txt` (`p1_12_activity_ledger (head)`) |
| Unit tests pass with >=95% coverage | PASS | `docs/qa/KANBA-43/unit-test-results.txt` (9 passed in 0.89s, 100% on touched modules) |
| Ruff check & format clean | PASS | `docs/qa/KANBA-43/build-check.txt` (All checks passed, 37 formatted) |
| Mypy strict clean | PASS | `docs/qa/KANBA-43/build-check.txt` (Success: no issues found in 35 source files) |
| Zero unicode dashes (U+2014, U+2013) | PASS | Verified via `scripts.check_no_dashes --all` |
| Complete schema dump | PASS | `docs/qa/KANBA-43/schema-dump.sql` |
| Tamper audit sample | PASS | `docs/qa/KANBA-43/tamper-audit-sample.txt` |
| Unified git diff | PASS | `docs/qa/KANBA-43/git-diff.patch` |

---

## 4. Instructions for Reality-Checker

1. Verify Alembic heads:
   `uv run alembic -c database/alembic.ini heads` -> exactly one head (`p1_12_activity_ledger (head)`).
2. Execute test suite:
   `KB_TEST_PGHOST=/tmp/kb-pgsock-22 uv run pytest database/tests/test_p1_12_activity_ledger.py database/tests/test_p1_12_chain_concurrency.py database/tests/migrations/test_p1_12_migration.py -q --cov=database --cov-branch --cov-report=term-missing`
3. Execute lint and type checks:
   `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database && uv run python -m scripts.check_no_dashes --all`
4. Inspect `docs/qa/KANBA-43/tamper-audit-sample.txt` for live hash chain proof and tamper detection.
