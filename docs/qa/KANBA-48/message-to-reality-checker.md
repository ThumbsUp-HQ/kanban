# Reality-Checker Verification Packet: KANBA-48 (KB-P1-08)

## Ticket Overview
- **Ticket ID**: `KANBA-48` (`KB-P1-08`)
- **Title**: [Phase 1 / Database] cycles, modules, assignees, labels & subscriptions join tables
- **Branch**: `feat/KANBA-48`
- **Base Commit**: `f38fbc2adf37df3da7253805476cc63e4586d865` (HEAD of `feat/KANBA-41`)
- **Author**: `builder-21`

---

## Technical Deliverables Summary

1. **Database Schema & DDL (`p1_08_planning_joins.up.sql`)**:
   - `cycles` table:
     * Graph entity with `FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT`.
     * Strict name length check (1 to 200 chars).
     * `status IN ('upcoming', 'active', 'completed')` with unique index `cycles_one_active_per_project` enforcing single active cycle per project.
     * Date range check (`end_date >= start_date`).
     * `EXCLUDE USING gist (project_id WITH =, daterange(start_date, end_date, '[]') WITH &&)` preventing overlapping cycle dates in the same project.
   - `issues_cycle_fk`:
     * Foreign key on `issues(cycle_id) REFERENCES cycles(id) ON DELETE SET NULL`.
   - `modules` table:
     * Graph entity with `FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT`.
     * `UNIQUE (project_id, name)` and `target_date >= start_date` constraint.
   - 5 Join Tables:
     * `project_module_defaults`: `(project_id, module_id)` PK with cascade delete on module.
     * `issue_modules`: `(issue_id, module_id)` PK with cascade delete on issue/module.
     * `issue_assignees`: `CHECK (num_nonnulls(principal_id, free_text_assignee) = 1)`, unique index on `(issue_id, principal_id)`, case-insensitive unique index on `(issue_id, lower(free_text_assignee))`. Documented in column comment that free-text assignees grant zero system access.
     * `issue_labels`: `(issue_id, label_id)` PK with cascade delete.
     * `issue_subscriptions`: `(issue_id, principal_id)` PK, `source IN ('MANUAL', 'CREATOR', 'ASSIGNEE', 'MENTION')`, `is_muted` flag.

2. **Database Triggers & Invariants**:
   - `cycles_spine_match_biu` / `modules_spine_match_biu`: Enforces that `objects.workspace_id` and `objects.project_id` match the row values (`PLANNING_SPINE_MISMATCH`).
   - `issues_cycle_project_biu`: Validates that `cycle.project_id == issue.project_id` on INSERT/UPDATE of `cycle_id` (`CYCLE_PROJECT_MISMATCH`).
   - `issue_modules_guard_bi` / `project_module_defaults_guard_bi`: Validates that `module.project_id == project_id`, and that `projects.modules_enabled = TRUE` (`MODULES_DISABLED` and `MODULE_PROJECT_MISMATCH`). Sets `workspace_id` from parent.
   - `issues_apply_module_defaults_ai`: When `projects.modules_enabled = TRUE`, automatically populates `issue_modules` from `project_module_defaults` on issue insertion.
   - `issue_assignees_guard_bi`: Enforces that assigned principal is `principal_type IN ('USER', 'AGENT')`, has `status = 'ACTIVE'`, and shares the issue's `workspace_id` (`ASSIGNEE_INVALID_PRINCIPAL`). Sets `workspace_id` from parent.
   - `issue_labels_exclusive_bi`: Locks parent issue `FOR UPDATE`, enforces `label.project_id == issue.project_id` (`LABEL_PROJECT_MISMATCH`), and automatically deletes existing issue labels within the same non-NULL `exclusive_group`. Sets `workspace_id` from parent.
   - `issues_autosubscribe_creator_ai`: Automatically subscribes the issue creator with `source = 'CREATOR'`.
   - `issue_assignees_autosubscribe_ai`: Automatically subscribes principal assignees with `source = 'ASSIGNEE'`.
   - `issue_subscriptions_guard_bi`: Validates that principal and issue belong to the same workspace (`SUBSCRIPTION_WORKSPACE_MISMATCH`). Sets `workspace_id` from parent.

3. **Reversible Down Migration (`p1_08_planning_joins.down.sql`)**:
   - Drops all 11 triggers and trigger functions.
   - Drops all 5 join tables.
   - Drops `issues_cycle_fk` foreign key constraint.
   - Drops `modules` and `cycles` tables.

4. **Single Linear Migration Head**:
   - `p1_08_planning_joins` chains cleanly after `p1_05_issues`.
   - `alembic heads` confirms single head: `p1_08_planning_joins (head)`.

5. **Automated Test Suite & Coverage**:
   - `database/tests/test_p1_08_planning.py`: 7 test suites validating cycle deletion setting NULL, module defaults and autosubscribe, exclusive labels auto-replacement, assignee check constraints, security mismatch guards, boundary rules (overlapping ranges 23P01, adjacent ranges ok, active cycle 23505, text len 120/121), and AGENT principal assignee support.
   - `database/tests/migrations/test_p1_08_migration.py`: Full migration lifecycle test (upgrade -> table/FK presence -> downgrade -> table/FK absence -> re-upgrade).
   - Test results: 8/8 tests passed in 0.91s.
   - Coverage: 100% statement and branch coverage on all touched modules.

---

## Artifact Index
- `docs/qa/KANBA-48/git-diff.patch`
- `docs/qa/KANBA-48/unit-test-results.txt`
- `docs/qa/KANBA-48/build-check.txt`
- `docs/qa/KANBA-48/alembic-heads.txt`
- `docs/qa/KANBA-48/schema-dump.sql`
- `docs/qa/KANBA-48/message-to-reality-checker.md`
