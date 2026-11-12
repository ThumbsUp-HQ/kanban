---
id: KB-P3-10a
title: "[Phase 3 / API] Cycles API: CRUD, status transitions, unfinished rollover & burndown"
epic: KB-E3
depends_on: [KB-P3-01a, KB-P3-02]
spec_sections: ["7.2", "11.4"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P3-10` is split into `KB-P3-10a` (cycles) and `KB-P3-10b` (modules). `KB-P3-02` added as a dependency because rollover mutates issues and burndown reads `ISSUE_STATE_CHANGED` / `ISSUE_FIELD_CHANGED` events defined there.

### User Story
As a **Project Administrator running sprints**, I need **cycle CRUD with `upcoming -> active -> completed` transitions, one-click rollover of unfinished issues and burndown data** so that **sprint planning and progress tracking work without a paid tier**.

**Requirement Traceability:** Spec S7.2 `8g`; S11.4 tool 6; requirement `#8g` | **Dependencies:** `KB-P3-01a`, `KB-P3-02`

### Scoped Technical Actions
1. **Target Files:** `kanban/api/v1/cycles.py`, `kanban/api/v1/schemas/cycles.py`, `kanban/services/cycles.py`, `kanban/services/burndown.py`, `kanban/services/activity.py` (append events).
2. **Endpoints:**

   | Method + Path | Capability | Success | Errors |
   | :-- | :-- | :-- | :-- |
   | `GET /api/v1/projects/{project_ref}/cycles?status=` | `VIEW` | `200` | `404`, `422` |
   | `POST /api/v1/projects/{project_ref}/cycles` | project `ADMIN` | `201` | `404`, `403`, `422` |
   | `GET /api/v1/cycles/{cycle_id}` | `VIEW` on project | `200` | `404` |
   | `PATCH /api/v1/cycles/{cycle_id}` | project `ADMIN` | `200` | `404`, `403`, `409 CYCLE_COMPLETED`, `422` |
   | `POST /api/v1/cycles/{cycle_id}/start` | project `ADMIN` | `200` | `404`, `403`, `409 ACTIVE_CYCLE_EXISTS`, `409 INVALID_CYCLE_TRANSITION` |
   | `POST /api/v1/cycles/{cycle_id}/complete` body `{"rollover_to_cycle_id": "<uuid>|null"}` | project `ADMIN` | `200` | `404`, `403`, `409 INVALID_CYCLE_TRANSITION`, `422 ROLLOVER_TARGET_INVALID`, `409 ROLLOVER_TOO_LARGE` |
   | `DELETE /api/v1/cycles/{cycle_id}` | project `ADMIN` | `204` | `404`, `403`, `409 CYCLE_COMPLETED` |
   | `GET /api/v1/cycles/{cycle_id}/burndown` | `VIEW` | `200` | `404`, `422 CYCLE_RANGE_TOO_LONG` |

   - Create body: `{"name": "Cycle 4: Sec", "start_date": "2026-11-11", "end_date": "2026-11-25"}`; `name` `1..120`; `end_date >= start_date` else `422 DATE_ORDER`; new cycles are `upcoming`.
   - Transitions: only `upcoming -> active` (`start`) and `active -> completed` (`complete`); anything else `409 INVALID_CYCLE_TRANSITION`. At most one `active` cycle per project (`409 ACTIVE_CYCLE_EXISTS`, enforced with `SELECT ... FOR UPDATE` on the project row). Completed cycles are immutable (`PATCH`/`DELETE` -> `409 CYCLE_COMPLETED`).
   - Rollover: unfinished = issues in the cycle whose state group is not `completed`/`cancelled` and not deleted. Target must be an `upcoming` or `active` cycle in the same project, different from the source (else `422 ROLLOVER_TARGET_INVALID`). Max `1000` issues per rollover (`409 ROLLOVER_TOO_LARGE`, nothing written). Null target clears `cycle_id` on unfinished issues. Response: `{"cycle": {...status: "completed"}, "rolled_over": 7, "rollover_to_cycle_id": "..."}`.
   - Delete sets `issues.cycle_id = NULL` (FK `ON DELETE SET NULL`).
   - Cycle serializer: `{"id", "name", "status", "start_date", "end_date", "issue_count", "completed_count"}`.
   - Burndown (`kanban/services/burndown.py`): for each calendar day `start_date..min(end_date, today)` compute `scope` (issues in cycle at end of day) and `remaining` (scope minus issues in `completed`/`cancelled` group at end of day), replaying `ISSUE_FIELD_CHANGED{field: "cycle_id"}` and `ISSUE_STATE_CHANGED` activity rows for issues currently or formerly in the cycle. Max range `366` days. Response:
     ```json
     {"cycle_id": "...", "series": [{"date": "2026-11-11", "scope": 10, "remaining": 10},
                                    {"date": "2026-11-12", "scope": 11, "remaining": 8}],
      "ideal": [{"date": "2026-11-11", "remaining": 10}, {"date": "2026-11-25", "remaining": 0}]}
     ```
     Only issues readable by the caller are counted (RLS session).
3. **Activity events emitted (category `HISTORY`):** `CYCLE_CREATED`, `CYCLE_UPDATED {changes}`, `CYCLE_STATUS_CHANGED {from, to}`, `CYCLE_DELETED` against the cycle object (`object_type='cycle'` registered on create); `ISSUE_FIELD_CHANGED {field: "cycle_id", old, new, reason: "rollover"}` against each rolled issue.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_cycles.py`, `kanban/tests/services/test_burndown.py`
- **Required Test Cases:**
  1. Positive: create `201` (`upcoming`), start `200` (`active`), complete with rollover moves exactly the 3 unfinished of 5 issues; `CYCLE_STATUS_CHANGED` and 3 `ISSUE_FIELD_CHANGED{reason: "rollover"}` rows written.
  2. State machine: starting a second cycle while one is active returns `409 ACTIVE_CYCLE_EXISTS`; completing an `upcoming` cycle returns `409 INVALID_CYCLE_TRANSITION`; `PATCH` completed cycle returns `409 CYCLE_COMPLETED`.
  3. Security: `EDIT` member `POST` cycle `403`; non-viewer `GET` cycle `404`; rollover target in another project `422 ROLLOVER_TARGET_INVALID`.
  4. Boundary: `end_date == start_date` accepted, `end_date < start_date` `422`; 1001 unfinished issues returns `409 ROLLOVER_TOO_LARGE` with zero changes; burndown on a 367-day cycle returns `422`.
  5. Burndown: seeded activity (issue added day 2, completed day 3) produces exact `scope`/`remaining` series; issue in an unreadable project is excluded.
- Clean-DB `SAVEPOINT` harness. Coverage `>= 95%`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** target files exist; 8 endpoints and burndown computation implemented.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_cycles.py kanban/tests/services/test_burndown.py -q --cov=kanban.api.v1.cycles --cov=kanban.services.cycles --cov=kanban.services.burndown --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check kanban && uv run mypy --strict kanban && uv run lint-imports` exits `0`.
- [ ] **Contract Sample:** includes create `201`, start `200`, `409 ACTIVE_CYCLE_EXISTS`, complete with rollover `200`, burndown `200`, `403`, `404`.
- [ ] **Specialist Reviews:** `api-specialist-review.md` and `ui-specialist-review.md` with `APPROVED`.
- [ ] **Forensic Proof Packet Complete.**

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/contract-sample.json` - via `KB_TICKET_ID=<TICKET_ID> KB_CONTRACT_OUT=docs/qa/<TICKET_ID>/contract-sample.json uv run pytest kanban/tests/api/test_cycles.py -q`.
5. `docs/qa/<TICKET_ID>/api-specialist-review.md`
6. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - confirms burndown series shape and rollover response feed the Cycles tab.
7. Screenshots: N/A - Non-UI Ticket.
