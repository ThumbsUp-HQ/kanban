# Reality-Checker Verification Packet: KANBA-47 (KB-P1-07)

**Ticket:** KANBA-47 (`KB-P1-07`)
**Title:** [Phase 1 / Database] Created-by provenance trigger with admin-only override & CREATOR_OVERRIDDEN ledger entry
**Epic:** KB-E1
**Branch:** `feat/KANBA-47` (Worktree: `/tmp/kb-wt-KANBA-47`)
**Author:** `builder-23`
**Spec Traceability:** `S7.2 8d` (Created By fixed + admin override, provenance tooltip, CREATOR_OVERRIDDEN audit entry), `S1.2` (audit ledger covers creator overrides), Requirement #8d
**Dependencies:** `KB-P1-05`, `KB-P1-12`, `KB-P1-13`

---

## 1. Executive Summary

This ticket implements the database-level creator provenance enforcement and administrative override security triggers on the `issues` table:
- **`issues_creator_insert_bi` (BEFORE INSERT ON issues):** Enforces creator provenance initialization at row creation. Forces `NEW.original_created_by_id := NEW.created_by_id`, `NEW.creator_modified_by_id := NULL`, and `NEW.creator_modified_at := NULL`, discarding any forged or client-supplied values.
- **`issues_creator_provenance_bu` (BEFORE UPDATE OF created_by_id, original_created_by_id, creator_modified_by_id, creator_modified_at ON issues, SECURITY DEFINER):**
  - Strict Immutability Guard: Verifies `NEW.original_created_by_id IS NOT DISTINCT FROM OLD.original_created_by_id` (raises `CREATOR_PROVENANCE_IMMUTABLE` if altered).
  - No-op Fast Path: If `created_by_id` has not changed and modified columns have not changed, returns `NEW` with zero activity side-effects. Direct alteration of `creator_modified_by_id` or `creator_modified_at` without changing creator raises `CREATOR_PROVENANCE_IMMUTABLE`.
  - Session Context & Authorization: Requires active session principal context (`app_current_principal_id()` non-NULL, else raises `RLS_CONTEXT_REQUIRED`). Validates that the principal (or any inherited group) holds `PROJECT_ADMIN` on `NEW.project_id` or `SERVER_ADMIN` at server scope via `app_principal_has_role(NEW.project_id, ARRAY['PROJECT_ADMIN','SERVER_ADMIN'])` (raises `CREATOR_OVERRIDE_FORBIDDEN` otherwise).
  - Actor User Validation: Verifies that the acting principal is a concrete human user in the `users` table (raises `CREATOR_OVERRIDE_ACTOR_NOT_USER` otherwise).
  - Workspace Match Validation: Verifies that the new creator user belongs to the same workspace as the issue (raises `CREATOR_OVERRIDE_WORKSPACE_MISMATCH` otherwise).
  - Provenance Tracking: Sets `NEW.creator_modified_by_id := v_actor` and `NEW.creator_modified_at := clock_timestamp()`.
  - Graph Spine Synchronization: Synchronizes `objects.created_by_id = NEW.created_by_id` for the issue entity.
  - Immutable Audit Ledger: Appends an immutable activity ledger record via `append_activity(NEW.workspace_id, NEW.id, 'issue', v_actor, 'CREATOR_OVERRIDDEN', jsonb_build_object('from_user_id', OLD.created_by_id, 'to_user_id', NEW.created_by_id, 'original_created_by_id', OLD.original_created_by_id))`.
- **Down Migration:** Drops both triggers and functions cleanly.

---

## 2. Definition of Done Compliance Matrix

| DoD Requirement | Status | Evidence File / Proof |
| :--- | :---: | :--- |
| **File Existence & Implementation:** `p1_07_creator_provenance.py`, `p1_07_creator_provenance.up.sql`, `p1_07_creator_provenance.down.sql` exist; up SQL contains `CREATOR_OVERRIDE_FORBIDDEN`, `CREATOR_PROVENANCE_IMMUTABLE`, `ARRAY['PROJECT_ADMIN','SERVER_ADMIN']`, and call to `append_activity(... 'CREATOR_OVERRIDDEN' ...)` | PASS | `database/migrations/versions/p1_07_creator_provenance.py`<br>`database/migrations/sql/p1_07_creator_provenance.up.sql`<br>`database/migrations/sql/p1_07_creator_provenance.down.sql` |
| **Single Head:** `uv run alembic -c database/alembic.ini heads` prints exactly one head: `p1_07_creator_provenance (head)` | PASS | `docs/qa/KANBA-47/alembic-heads.txt` |
| **Unit Tests Implemented & Passing:** `uv run pytest database/tests/test_p1_07_creator_provenance.py database/tests/migrations/test_p1_07_migration.py -q --cov=database --cov-branch --cov-report=term-missing` exits `0` with `0` failures and >=95% coverage | PASS | `docs/qa/KANBA-47/unit-test-results.txt` (7 passed in 1.11s, 100% statement/branch coverage on touched modules) |
| **Build / Type / Lint Clean:** `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database` exits `0` | PASS | `docs/qa/KANBA-47/build-check.txt` |
| **Forensic Proof Packet Complete:** All files exist under `docs/qa/KANBA-47/` | PASS | `git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, `alembic-heads.txt`, `schema-dump.sql`, `activity-sample.txt`, `message-to-reality-checker.md` |

---

## 3. Test Traceability Matrix

| Test Function | Scoped Requirement | Verifications |
| :--- | :--- | :--- |
| `test_01_positive_project_admin_override` | Test Case 1 | Session principal with `PROJECT_ADMIN` binding on the project changes `created_by_id` U1 -> U2; row shows `created_by_id=U2`, `original_created_by_id=U1`, `creator_modified_by_id=<admin>`, non-NULL `creator_modified_at`; `objects.created_by_id = U2`; exactly one `activity_records` row with `event_type='CREATOR_OVERRIDDEN'` and payload `from_user_id=U1`, `to_user_id=U2`, `original_created_by_id=U1`; 32-byte sha256 `prev_hash` and `row_hash`. |
| `test_02_positive_server_admin_direct_and_group` | Test Case 2 | Direct `SERVER_ADMIN` (server scope) overrides creator; user holding `SERVER_ADMIN` solely via group membership closure overrides creator. |
| `test_03_negative_forbidden_roles` | Test Case 3 | `MEMBER` raises `CREATOR_OVERRIDE_FORBIDDEN`; `WORKSPACE_ADMIN` raises `CREATOR_OVERRIDE_FORBIDDEN`; `PROJECT_ADMIN` of another project raises `CREATOR_OVERRIDE_FORBIDDEN`; zero activity records written in all rejected attempts. |
| `test_04_negative_provenance_immutability` | Test Case 4 | Any role updating `original_created_by_id` raises `CREATOR_PROVENANCE_IMMUTABLE`; directly setting `creator_modified_by_id` or `creator_modified_at` without changing creator raises `CREATOR_PROVENANCE_IMMUTABLE`. |
| `test_05_negative_context_and_workspace_mismatch` | Test Case 5 | Override without session RLS context raises `RLS_CONTEXT_REQUIRED`; actor who is not a user (e.g. AGENT principal) raises `CREATOR_OVERRIDE_ACTOR_NOT_USER`; target user from another workspace raises `CREATOR_OVERRIDE_WORKSPACE_MISMATCH`. |
| `test_06_boundary_insert_sanitization_and_summary_update` | Test Case 6 | INSERT with client-supplied `original_created_by_id <> created_by_id` and non-NULL `creator_modified_*` stores `original_created_by_id = created_by_id` and NULL modified columns; UPDATE touching only `summary` or non-changing `created_by_id` writes no activity rows. |
| `test_07_creator_provenance_migration_lifecycle` | Test Case 7 | Upgrade to `p1_07_creator_provenance` creates triggers and functions; downgrade to `p1_09_prose_tables` drops them cleanly; re-upgrade succeeds and restores triggers and functions. |

---

## 4. Verification Proof Artifacts

- `docs/qa/KANBA-47/git-diff.patch`: Clean unified diff against base commit (`0882fa7`).
- `docs/qa/KANBA-47/unit-test-results.txt`: Test execution results with coverage report (7 passed in 1.11s, 100% touched-module coverage, exit code 0).
- `docs/qa/KANBA-47/build-check.txt`: Ruff lint, format, mypy strict, import-linter, license gate, and zero-dash check outputs (all exit code 0).
- `docs/qa/KANBA-47/alembic-heads.txt`: Single linear head verification (`p1_07_creator_provenance (head)`).
- `docs/qa/KANBA-47/schema-dump.sql`: Verbatim `\sf` source of `issues_creator_insert_bi` and `issues_creator_provenance_bu` plus `information_schema.triggers` query.
- `docs/qa/KANBA-47/activity-sample.txt`: Verified sample of the `CREATOR_OVERRIDDEN` activity record containing full payload, `prev_hash_hex`, and `row_hash_hex`.
- Screenshots: N/A (Backend Database & Migration Ticket).
