---
id: KB-P3-01b
title: "[Phase 3 / API] Project architect API (part b): workflow states, custom priorities, labels with exclusive groups & WIP limits"
epic: KB-E3
depends_on: [KB-P3-01a]
spec_sections: ["7.2", "6.4", "12.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: second half of manifest row `KB-P3-01`.

### User Story
As a **Project Administrator**, I need **REST endpoints to manage workflow states (with soft/hard WIP limits), per-project priorities and labels with optional exclusive groups** so that **the board, ticket drawer and later move/WIP logic read a project-specific, admin-controlled vocabulary**.

**Requirement Traceability:** Spec S7.2 `8c`, `8i`; S6.4 item 3 (Soft/Hard WIP); S12.2; requirements `#8c`, `#8i`, `#9j` | **Dependencies:** `KB-P3-01a`

### Scoped Technical Actions
1. **Target Files:**
   - `kanban/api/v1/project_config.py` (router for states, priorities, labels)
   - `kanban/api/v1/schemas/project_config.py`
   - `kanban/services/project_config.py`
   - `database/migrations/versions/<rev>_workflow_state_wip_limits.py` (Alembic versions directory from KB-P1-01)
   - `kanban/services/activity.py` (append event types only)
2. **Migration:** add to `workflow_states`:
   ```sql
   ALTER TABLE workflow_states
     ADD COLUMN wip_soft_limit INTEGER CHECK (wip_soft_limit IS NULL OR wip_soft_limit BETWEEN 1 AND 999),
     ADD COLUMN wip_hard_limit INTEGER CHECK (wip_hard_limit IS NULL OR wip_hard_limit BETWEEN 1 AND 999),
     ADD CONSTRAINT wip_soft_le_hard CHECK (wip_soft_limit IS NULL OR wip_hard_limit IS NULL OR wip_soft_limit <= wip_hard_limit);
   ```
   Downgrade drops the constraint and both columns.
3. **Endpoints (base `/api/v1/projects/{project_ref}`; unreadable project returns `404 NOT_FOUND` equalized; readable without capability returns `403 INSUFFICIENT_CAPABILITY`):**

   | Method + Path | Capability | Success | Errors |
   | :-- | :-- | :-- | :-- |
   | `GET .../states` | `VIEW` | `200` list ordered by `sort_order` | `404` |
   | `POST .../states` | `ADMIN` | `201` | `422`, `409 STATE_NAME_TAKEN` |
   | `PATCH .../states/{state_id}` | `ADMIN` | `200` | `404`, `422`, `409 STATE_NAME_TAKEN` |
   | `DELETE .../states/{state_id}?migrate_to={state_id}` | `ADMIN` | `204` | `409 STATE_IN_USE` (issues exist, no `migrate_to`), `409 LAST_STATE_IN_GROUP` (deleting the only `completed` or only `cancelled` or only `backlog` state), `409 DEFAULT_STATE` |
   | `GET .../priorities` | `VIEW` | `200` | `404` |
   | `POST .../priorities` | `ADMIN` | `201` | `422`, `409 PRIORITY_SLUG_TAKEN` |
   | `PATCH .../priorities/{priority_id}` | `ADMIN` | `200` | `404`, `422` |
   | `DELETE .../priorities/{priority_id}?migrate_to={priority_id}` | `ADMIN` | `204` | `409 PRIORITY_IN_USE`, `409 DEFAULT_PRIORITY` |
   | `GET .../labels` | `VIEW` | `200` | `404` |
   | `POST .../labels` | `EDIT` (S7.2 `8i`: instant create for authorized members) | `201` | `422`, `409 LABEL_NAME_TAKEN` |
   | `PATCH .../labels/{label_id}` | `ADMIN` | `200` | `404`, `422`, `409 LABEL_NAME_TAKEN` |
   | `DELETE .../labels/{label_id}` | `ADMIN` | `204` (removes `issue_labels` rows) | `404` |

   - State body: `{"name": "In Review", "group": "started", "color_hex": "#3B82F6", "sort_order": 30, "is_default": false, "wip_soft_limit": 3, "wip_hard_limit": 5}`; `group` in `backlog|unstarted|started|completed|cancelled`; `name` `1..64` chars, unique per project case-insensitively; `color_hex` regex `^#[0-9A-Fa-f]{6}$`. Setting `is_default=true` clears the previous default in the same transaction (exactly one default).
   - Priority body: `{"slug": "blocker", "label": "Blocker", "emoji": "🧯", "color_hex": "#B91C1C", "sort_order": 0, "is_default": false}`; `slug` regex `^[a-z][a-z0-9_-]{0,31}$`; `emoji` `1..8` code points; exactly one default.
   - Label body: `{"name": "type:bug", "color_hex": "#EF4444", "exclusive_group": "type"}`; `name` `1..64` chars; `exclusive_group` `null` or regex `^[a-z0-9][a-z0-9_-]{0,31}$`.
   - `migrate_to` must reference a state/priority in the same project (else `422 MIGRATE_TARGET_INVALID`); migration and delete run in one transaction and write one `ISSUE_FIELD_CHANGED` activity per moved issue only if `<= 500` issues, otherwise `409 MIGRATION_TOO_LARGE` (bounded transaction size).
   - Every list response item includes `id`; states also include `issue_count` (non-archived, non-deleted) for WIP display.
4. **Activity events emitted (append to `ActivityEventType`, category `HISTORY`):** `STATE_CREATED`, `STATE_UPDATED {changes}`, `STATE_DELETED {migrated_issue_count, migrate_to}`, `PRIORITY_CREATED`, `PRIORITY_UPDATED`, `PRIORITY_DELETED`, `LABEL_CREATED`, `LABEL_UPDATED`, `LABEL_DELETED`, all recorded against the project object id; `ISSUE_FIELD_CHANGED {field: "state_id" | "priority_id", old, new, reason: "state_deleted" | "priority_deleted"}` against each migrated issue.
5. **Security invariants:** `state_id`/`priority_id`/`label_id` from another project returns `404` (never reveals existence); all writes run in the RLS session; `color_hex` and `emoji` are never interpolated into HTML server-side.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_project_config.py`, `database/tests/test_migration_wip_limits.py`
- **Required Test Cases:**
  1. Positive: admin creates a `started` state with `wip_soft_limit=3`, `wip_hard_limit=5`; `GET .../states` returns it with `issue_count: 0`; `STATE_CREATED` activity row exists.
  2. Negative/security: `EDIT` user `POST .../states` gets `403`; non-member gets `404`; label id from project B patched via project A path returns `404`.
  3. Exclusive group: creating label `type:bug` with group `type` succeeds; group `Type!` returns `422`.
  4. Boundary/state transitions: `wip_soft_limit=6, wip_hard_limit=5` returns `422`; `999` accepted, `1000` rejected; deleting the only `completed` state returns `409 LAST_STATE_IN_GROUP`; deleting an in-use state without `migrate_to` returns `409 STATE_IN_USE`, with valid `migrate_to` returns `204` and moves issues.
  5. Default invariants: setting a second default priority leaves exactly one `is_default=true`; deleting the default priority returns `409 DEFAULT_PRIORITY`.
  6. Migration test: upgrade then downgrade leaves `workflow_states` columns identical to pre-upgrade (catalog comparison).
- Clean-DB `SAVEPOINT` harness from KB-P0-05. Touched-module coverage `>= 95%`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** the 4 target source files and the migration exist; all 12 endpoints in the table are implemented.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_project_config.py database/tests/test_migration_wip_limits.py -q --cov=kanban.api.v1.project_config --cov=kanban.services.project_config --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check kanban database && uv run mypy --strict kanban database && uv run lint-imports` exits `0`.
- [ ] **Contract Sample:** `docs/qa/<TICKET_ID>/contract-sample.json` includes state create `201`, state delete in-use `409 STATE_IN_USE`, WIP invalid `422`, label create by `EDIT` user `201`, priority patch by `EDIT` user `403`, cross-project id `404`.
- [ ] **Specialist Reviews:** `api-specialist-review.md` and `ui-specialist-review.md` exist with an explicit `APPROVED` line.
- [ ] **Forensic Proof Packet Complete:** all files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - raw output of the pytest command above.
3. `docs/qa/<TICKET_ID>/build-check.txt` - raw output of the ruff/mypy/lint-imports command.
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - `pg_dump --schema-only -t workflow_states` after `alembic upgrade head`.
5. `docs/qa/<TICKET_ID>/contract-sample.json` - via `KB_TICKET_ID=<TICKET_ID> KB_CONTRACT_OUT=docs/qa/<TICKET_ID>/contract-sample.json uv run pytest kanban/tests/api/test_project_config.py -q`.
6. `docs/qa/<TICKET_ID>/api-specialist-review.md`
7. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - confirms state/priority/label payloads support the settings screen and `issue_count` WIP badge.
8. Screenshots: N/A - Non-UI Ticket.
