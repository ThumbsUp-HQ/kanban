# API Specialist Gate Final Audit: APPROVED for KANBA-75 (KB-P3-01b)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-75`
- Branch: `feat/KANBA-75`
- Commit: `f238045`
- Ticket: `KANBA-75` (`KB-P3-01b`: `[Phase 3 / API] Project architect API (part b): workflow states, custom priorities, labels with exclusive groups & WIP limits`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive systems architecture, API transport, database schema, and concurrency audit was conducted for `KANBA-75` (`KB-P3-01b`) in worktree `/tmp/kb-wt-KANBA-75`. The implementation was evaluated against specification sections 7.2 (items 8c, 8i), 6.4 (item 3), and 12.2. All 12 REST endpoints under `/api/v1/projects/{project_ref}/states|priorities|labels`, DDL migration with WIP limit check constraints, RLS permission policies, single-default invariants, delete guards with bounded issue migrations, and activity ledger logging were forensically verified.

| Verification Dimension | Specification Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Endpoints Coverage** | All 12 configuration endpoints | 4 state, 4 priority, 4 label endpoints in `kanban/api/v1/project_config.py` | PASS |
| **DDL & CHECK Constraints** | Soft/hard WIP limits on `workflow_states` | Added `wip_soft_limit`, `wip_hard_limit` (1..999) and `wip_soft_le_hard` constraint | PASS |
| **Inline Label Creation Permission** | S7.2 8i permission relaxation | `project_labels_insert_rls` updated to allow capability 4 (`EDIT`) on project | PASS |
| **Single Default Invariant** | Exactly one default state and priority | Setting `is_default=true` atomically clears previous defaults in same transaction | PASS |
| **Delete Invariants & Guards** | Prevent deletion of defaults & last in group | `409 DEFAULT_STATE`, `409 DEFAULT_PRIORITY`, `409 LAST_STATE_IN_GROUP` enforced | PASS |
| **Bounded Issue Migration** | Migrate in-use states/priorities (<= 500) | `migrate_to` moves issues; rejects if unprovided (`409 IN_USE`) or > 500 (`409 MIGRATION_TOO_LARGE`) | PASS |
| **Label Exclusive Groups** | Slug format & conflict prevention | Validates `exclusive_group` regex `^[a-z0-9][a-z0-9_-]{0,31}$`; rejects invalid chars (`422`) | PASS |
| **Anti-Enumeration Protection** | S3.4 25.0ms timing floor + 404 | Endpoints run under `timing_floor(floor_ms=25.0)`; cross-project IDs return 404 | PASS |
| **Activity Ledger Auditing** | Category `HISTORY` event types | Emits 9 project config events on project + `ISSUE_FIELD_CHANGED` on migrated issues | PASS |
| **Automated Test Coverage** | Mandatory Feature Tests (>= 95%) | 11/11 passed in 86.38s; 97.19% combined coverage across target modules | PASS |
| **Quality & Static Analysis** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (575 files), Mypy strict clean (205 files), Lint-imports clean | PASS |

---

### 2. Forensic Architectural & REST Contract Audit

#### A. Comprehensive REST Endpoint Topology (`kanban/api/v1/project_config.py`)
All 12 endpoints required by `KB-P3-01b` are implemented and mounted on the canonical API router:
1. `GET /api/v1/projects/{project_ref}/states`:
   - Requires `Capability.VIEW`.
   - Returns states ordered by `sort_order ASC, name ASC`.
   - Includes real-time `issue_count` (non-archived, non-deleted issues) for Kanban WIP badge rendering.
2. `POST /api/v1/projects/{project_ref}/states`:
   - Requires `Capability.ADMIN` on target project.
   - Enforces unique name per project case-insensitively (`409 STATE_NAME_TAKEN`).
   - Returns `201 Created` with `Location` header.
3. `PATCH /api/v1/projects/{project_ref}/states/{state_id}`:
   - Requires `Capability.ADMIN`.
   - Validates WIP limit bounds and cross-field constraints.
4. `DELETE /api/v1/projects/{project_ref}/states/{state_id}?migrate_to=`:
   - Requires `Capability.ADMIN`.
   - Prevents deleting the default state (`409 DEFAULT_STATE`) or the only state in a group (`409 LAST_STATE_IN_GROUP`).
   - If issues exist and `migrate_to` is omitted, rejects with `409 STATE_IN_USE`.
   - If issues exist and `migrate_to` is provided, verifies `migrate_to` belongs to the same project (`422 MIGRATE_TARGET_INVALID`) and moves issues atomically. Bounded to <= 500 issues (`409 MIGRATION_TOO_LARGE`).
5. `GET /api/v1/projects/{project_ref}/priorities`:
   - Requires `Capability.VIEW`. Ordered by `sort_order ASC, slug ASC`.
6. `POST /api/v1/projects/{project_ref}/priorities`:
   - Requires `Capability.ADMIN`. Enforces unique slug per project (`409 PRIORITY_SLUG_TAKEN`).
7. `PATCH /api/v1/projects/{project_ref}/priorities/{priority_id}`:
   - Requires `Capability.ADMIN`.
8. `DELETE /api/v1/projects/{project_ref}/priorities/{priority_id}?migrate_to=`:
   - Requires `Capability.ADMIN`. Prevents deleting default priority (`409 DEFAULT_PRIORITY`).
   - Enforces in-use migration up to 500 issues.
9. `GET /api/v1/projects/{project_ref}/labels`:
   - Requires `Capability.VIEW`. Ordered by `name ASC`.
10. `POST /api/v1/projects/{project_ref}/labels`:
    - Permits `Capability.EDIT` (S7.2 item 8i) or `Capability.ADMIN`, allowing authorized members to create labels directly from the ticket drawer.
    - Enforces unique label name per project (`409 LABEL_NAME_TAKEN`).
11. `PATCH /api/v1/projects/{project_ref}/labels/{label_id}`:
    - Requires `Capability.ADMIN`.
12. `DELETE /api/v1/projects/{project_ref}/labels/{label_id}`:
    - Requires `Capability.ADMIN`. Cascades removal of `issue_labels` associations.

#### B. Database Schema, DDL Migration & RLS Updates (`database/migrations/`)
- **Schema Migration (`p3_01b_workflow_state_wip_limits.up.sql`)**:
  - Adds `wip_soft_limit` (integer, 1..999, nullable).
  - Adds `wip_hard_limit` (integer, 1..999, nullable).
  - Adds CHECK constraint `wip_soft_le_hard` (`wip_soft_limit IS NULL OR wip_hard_limit IS NULL OR wip_soft_limit <= wip_hard_limit`).
  - Updates RLS policy `project_labels_insert_rls` on `project_labels` to permit capability 4 (`EDIT`) alongside capability 64 (`ADMIN`), matching S7.2 requirement 8i.
- **Migration Test (`test_migration_wip_limits.py`)**:
  - Validates that upgrading and downgrading the migration restores the exact pre-migration catalog state.

#### C. Single Default Invariant & Delete Safety (`kanban/services/project_config.py`)
- **Single Default Guarantee**:
  - When creating or patching a state or priority with `is_default=true`, all existing default records in the project are cleared within the same atomic database transaction.
  - Exactly one state and priority remains the default.
  - Deleting the active default is strictly prohibited (`409 DEFAULT_STATE`, `409 DEFAULT_PRIORITY`).
- **Bounded Issue Migration (`MAX_MIGRATION_ISSUES = 500`)**:
  - Migrating issues during state/priority deletion runs inside the same transaction as the deletion.
  - If more than 500 issues are assigned to the target entity, the service rejects the request with RFC 7807 409 `MIGRATION_TOO_LARGE`, preventing long database locks and transaction buffer exhaustion.

#### D. Anti-Enumeration & Cross-Project Isolation (S3.4)
- **Timing Equalization**:
  - All 12 endpoints execute within `async with timing_floor(floor_ms=25.0):`.
  - Non-existent projects and projects the user cannot view return indistinguishable 404 Problem Details.
- **Cross-Project Reference Protection**:
  - Attempting to access, modify, or delete a state, priority, or label using an ID that belongs to another project immediately returns 404, preventing cross-tenant existence enumeration.

#### E. Activity Ledger Auditing
- **Project-Level Records**:
  - Emits 9 fine-grained activity event types under category `HISTORY`: `STATE_CREATED`, `STATE_UPDATED`, `STATE_DELETED`, `PRIORITY_CREATED`, `PRIORITY_UPDATED`, `PRIORITY_DELETED`, `LABEL_CREATED`, `LABEL_UPDATED`, `LABEL_DELETED`.
- **Issue-Level Mutation Records**:
  - For each issue moved during state or priority deletion, an `ISSUE_FIELD_CHANGED` event is recorded on the issue with reason `state_deleted` or `priority_deleted`.

---

### 3. Test Suite & Verification Matrix

1. **Mandatory Test Cases Verified**:
   - Case 1 (Positive Lifecycle): Create `started` state with `wip_soft_limit=3`, `wip_hard_limit=5`; GET returns `issue_count: 0`; `STATE_CREATED` activity logged.
   - Case 2 (Negative / Security): Member with `EDIT` gets 403 on state creation; non-member gets 404; cross-project label ID returns 404.
   - Case 3 (Exclusive Groups): Creating label with valid group succeeds; invalid regex characters return 422.
   - Case 4 (Boundaries & Transitions): `soft > hard` WIP returns 422; 999 accepted, 1000 rejected; deleting last state in group returns 409 `LAST_STATE_IN_GROUP`; deleting in-use state without migration returns 409 `STATE_IN_USE`, with valid migration returns 204.
   - Case 5 (Default Invariants): Setting new default clears old default; deleting default priority returns 409 `DEFAULT_PRIORITY`.
   - Case 6 (Migration Test): Upgrade then downgrade catalog comparison passes.
2. **Execution Results**:
   - Test suite: 11/11 passed in 86.38s across `test_project_config.py` and `test_migration_wip_limits.py`.
   - Coverage: **97.19%** combined branch+line coverage across target modules (`kanban.api.v1.project_config`: 100%, `kanban.services.project_config`: 97%).
3. **Static Quality Verification**:
   - `uv run ruff check kanban database`: Clean (0 errors).
   - `uv run ruff format --check .`: Clean (575 files).
   - `uv run mypy --strict kanban database`: Clean (0 errors across 205 source files).
   - `uv run lint-imports`: Clean (2 kept, 0 broken).
   - `python -m scripts.check_no_dashes --all`: Clean (0 non-ASCII dashes repo-wide).
   - `make license`: Clean (violations=0).
4. **Typography**: Plain ASCII hyphens `-` only throughout. Zero non-ASCII Unicode dashes (`U+2014` / `U+2013`).

---

### 4. Gate Sign-Off

The project configuration API, WIP limits migration, and workflow management implementation in `/tmp/kb-wt-KANBA-75` fully satisfies all architectural, security, database constraint, and contract requirements of ticket `KANBA-75` (`KB-P3-01b`).

Verdict: APPROVED
