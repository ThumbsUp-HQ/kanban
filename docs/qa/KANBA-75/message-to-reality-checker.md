# Reality-Checker Verification Packet: KANBA-75 (KB-P3-01b)

## Ticket Overview
- **Ticket ID**: KANBA-75
- **Specification**: docs/tickets/KB-P3-01b.md
- **Title**: [Phase 3 / API] Project architect API (part b): workflow states, custom priorities, labels with exclusive groups & WIP limits
- **Branch**: feat/KANBA-75
- **Worktree**: /tmp/kb-wt-KANBA-75

## Target Files Implemented
1. `database/migrations/sql/p3_01b_workflow_state_wip_limits.up.sql`:
   - Adds `wip_soft_limit` and `wip_hard_limit` (integer, 1..999, nullable).
   - Adds constraint `wip_soft_le_hard` (`wip_soft_limit IS NULL OR wip_hard_limit IS NULL OR wip_soft_limit <= wip_hard_limit`).
   - Updates `project_labels_insert_rls` to permit capability 4 (`EDIT`) per S7.2 item 8i.
2. `database/migrations/sql/p3_01b_workflow_state_wip_limits.down.sql`:
   - Drops constraint `wip_soft_le_hard` and columns `wip_soft_limit`, `wip_hard_limit`.
   - Restores `project_labels_insert_rls` to capability 64 (`ADMIN`).
3. `database/migrations/versions/p3_01b_workflow_state_wip_limits.py`:
   - Alembic migration chained from `p2_18_rate_limit_buckets`.
4. `database/models/projects.py`:
   - Added mapped columns `wip_soft_limit: Mapped[int | None]` and `wip_hard_limit: Mapped[int | None]` to `WorkflowState`.
5. `kanban/api/v1/schemas/project_config.py`:
   - Request and response schemas for states, priorities, and labels with `extra="forbid"`.
   - Validates WIP bounds, cross-field soft <= hard, emoji length 1..8, and regex constraints.
6. `kanban/services/project_config.py`:
   - CRUD logic for states, priorities, labels.
   - Enforces single default invariant (setting `is_default=true` clears other defaults).
   - Enforces delete invariants: default state/priority cannot be deleted (`409 DEFAULT_STATE`, `409 DEFAULT_PRIORITY`).
   - Prevents deleting last completed, cancelled, or backlog state (`409 LAST_STATE_IN_GROUP`).
   - Enforces migration for in-use states/priorities (`409 STATE_IN_USE`, `409 PRIORITY_IN_USE`, `422 MIGRATE_TARGET_INVALID`, max 500 issues `409 MIGRATION_TOO_LARGE`).
   - Records activity events on project and migrated issues.
7. `kanban/api/v1/project_config.py`:
   - 12 REST endpoints under `/api/v1/projects/{project_ref}/states|priorities|labels`.
   - Timing floor wrapper (25.0ms) on all endpoints.
   - Capability enforcement: VIEW on GET, ADMIN on states/priorities and label updates, EDIT on label creation.
8. `kanban/api/v1/__init__.py`:
   - Mounted `project_config_router` on `build_v1_router()`.
9. `kanban/services/activity.py`:
   - Appended 9 project config event types (`STATE_CREATED`, `STATE_UPDATED`, `STATE_DELETED`, `PRIORITY_CREATED`, `PRIORITY_UPDATED`, `PRIORITY_DELETED`, `LABEL_CREATED`, `LABEL_UPDATED`, `LABEL_DELETED`) and `ISSUE_FIELD_CHANGED` with `ActivityCategory.HISTORY`.
10. `database/tests/test_migration_wip_limits.py`:
    - Tests migration upgrade/downgrade catalog equivalence, check constraints, and RLS policy updates.
11. `kanban/tests/api/test_project_config.py`:
    - 10 comprehensive test functions covering all mandatory cases, security anti-enumeration, exclusive groups, WIP limits, default invariants, and branch coverage.

## Verification Matrix
1. **Unit Tests and Coverage**:
   - 11/11 tests passed in 81.64s.
   - Coverage:
     * `kanban/api/v1/project_config.py`: 100%
     * `kanban/api/v1/schemas/project_config.py`: 100%
     * `kanban/services/project_config.py`: 97%
     * **TOTAL**: 97.81% (exceeds mandatory >= 95% threshold).
   - Stored in `docs/qa/KANBA-75/unit-test-results.txt`.
2. **Static Quality Checks**:
   - `ruff check kanban database`: Clean (0 errors).
   - `ruff format --check .`: Clean (575 files already formatted).
   - `mypy --strict kanban database`: Clean (0 errors across 205 files).
   - `lint-imports`: 2 kept, 0 broken.
   - `scripts.check_no_dashes --all`: Clean (0 non-ASCII dashes repo-wide).
   - `make license`: Clean (violations=0).
   - Stored in `docs/qa/KANBA-75/build-check.txt`.
3. **Artifacts**:
   - `docs/qa/KANBA-75/schema-dump.sql`: DDL dump for `workflow_states`, `project_priorities`, `project_labels`.
   - `docs/qa/KANBA-75/contract-sample.json`: Recorded HTTP exchanges including 201 Created and error cases.

## Specialist Gate Approvals
- API Specialist Gate (`api-specialist-review.md`): Requested from `@arch-reviewer`.
- UI Specialist Gate (`ui-specialist-review.md`): Requested from `@ui-specialist`.
