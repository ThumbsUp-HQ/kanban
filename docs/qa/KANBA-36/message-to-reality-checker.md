# Forensic QA Packet: KANBA-36 (KB-P1-04)

- Ticket: KANBA-36
- Spec Reference: docs/tickets/KB-P1-04.md
- Specification Authority: docs/ARCHITECTURE_AND_PRODUCT_SPEC.md (S7.2 8c/8p, S12.2)
- Author: builder-20
- Branch: feat/KANBA-36

## Summary of Implementation

Implemented Phase 1 database schema and migrations for projects, workflow_states, project_priorities, and project_labels:
1. Migration files:
   - database/migrations/versions/p1_04_projects.py: down_revision = 'p1_02_objects_spine'
   - database/migrations/sql/p1_04_projects.up.sql: DDL, triggers, and functions
   - database/migrations/sql/p1_04_projects.down.sql: clean rollback
2. Tables & Constraints:
   - projects: identifier regex `^[A-Z][A-Z0-9]{1,9}$`, description_markdown <= 524288 bytes, modules_enabled DEFAULT FALSE, issue_seq_counter BIGINT DEFAULT 0, auto_archive_days BETWEEN 1 AND 365, UNIQUE (workspace_id, identifier), composite FK (id, workspace_id) to objects.
   - objects: ADD CONSTRAINT objects_project_fk FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED.
   - workflow_states: 5 groups (backlog, unstarted, started, completed, cancelled), color_hex regex, UNIQUE (project_id, name), partial unique index workflow_states_one_default on (project_id) WHERE is_default.
   - project_priorities: slug regex, label, emoji (length 1-8), color_hex, sort_order, UNIQUE (project_id, slug), partial unique index project_priorities_one_default on (project_id) WHERE is_default.
   - project_labels: name (1-100 chars), color_hex, exclusive_group regex, UNIQUE (project_id, name).
3. Triggers & Functions:
   - projects_spine_match_biu: verifies objects.workspace_id = NEW.workspace_id and objects.canonical_key = NEW.identifier or raises PROJECT_SPINE_MISMATCH.
   - projects_seq_guard_bu: prevents issue_seq_counter decrease or raises ISSUE_SEQ_DECREASE_FORBIDDEN.
   - Child workspace matching triggers (*_workspace_match_biu): auto-populates workspace_id from project or raises PROJECT_CHILD_WORKSPACE_MISMATCH if different.
   - projects_seed_defaults_ai: seeds 5 default workflow states (Backlog default) and 5 default priorities (urgent, high, medium, low, none default with emojis).
   - workflow_states_group_guard_bd: prevents deleting the last terminal state (completed or cancelled) or raises LAST_TERMINAL_STATE_REQUIRED.

## Definition of Done Verification

| DoD Item | Requirement | Result | Evidence |
| :--- | :--- | :--- | :--- |
| File Existence | 3 migration files created | PASS | p1_04_projects.py, .up.sql, .down.sql |
| Single Alembic Head | Exactly one head: p1_04_projects (head) | PASS | alembic-heads.txt |
| Unit Tests Passing | All 9 tests pass with 0 failures | PASS | unit-test-results.txt |
| Coverage | >=95% branch+line coverage on touched modules | PASS (100%) | unit-test-results.txt |
| Lint / Type Check | ruff check, ruff format, mypy --strict pass | PASS | build-check.txt |
| Schema Dump | pg_dump --schema-only for 4 tables | PASS | schema-dump.sql |
| Seed Sample | Seed verification queries | PASS | seed-sample.txt |
| UI Changes | Non-UI Ticket | N/A | Non-UI Ticket |
| Unicode Dashes | Zero U+2014 or U+2013 characters | PASS | scripts.check_no_dashes |

## Test Traceability Matrix

1. Positive seeding (5 states, 5 priorities, Plane defaults): test_01_project_creation_and_seeding (PASSED)
2. Positive labels (with and without exclusive groups): test_02_project_labels_positive (PASSED)
3. Negative identifier regex: test_03_project_identifier_validation (PASSED)
4. Negative duplicate identifier and spine mismatch: test_04_duplicate_identifier_and_spine_mismatch (PASSED)
5. Child workspace mismatch and single default: test_05_workspace_match_and_default_uniqueness (PASSED)
6. Boundary description (512KB) and auto_archive_days (1-365): test_06_description_and_auto_archive_boundaries (PASSED)
7. Terminal state deletion guard and seq decrease guard: test_07_terminal_state_guard_and_seq_counter (PASSED)
8. Child workspace auto-population: test_08_child_workspace_auto_population (PASSED)
9. Migration up/down/re-up lifecycle: test_08_projects_migration_lifecycle (PASSED)
