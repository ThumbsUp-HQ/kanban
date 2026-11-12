# API Specialist Gate Final Audit: APPROVED for KANBA-88 (KB-P3-10a)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-88`
- Branch: `feat/KANBA-88`
- Ticket: `KANBA-88` (`KB-P3-10a`: `[Phase 3 / API] Cycles API: CRUD, status transitions, unfinished rollover & burndown`)

---

### 1. Executive Summary & Verification Matrix
A forensic backend architecture and API Specialist Gate audit was conducted for `KANBA-88` in `/tmp/kb-wt-KANBA-88`. `KB-P3-10a` delivers the sprint and cycle tracking engine, including cycle CRUD, strict status state machine (`upcoming -> active -> completed`), concurrency-safe at-most-one active cycle enforcement, unfinished issue rollover, immutable completed sprint records, issue membership routes, and historical activity-replayed burndown chart series. All REST endpoints, timing floors, project row concurrency locks, and activity event emissions were evaluated against Spec Sections 7.2 (8g), 11.4, 3.4, and 5.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Router & Mounting** | Endpoints mounted on `build_v1_router()` | Mounted via `cycles_router` in `kanban/api/v1/cycles.py` | PASS |
| **Timing Equalization** | 25.0ms timing floor on all endpoints | Wrapped in `async with timing_floor(floor_ms=25.0):` | PASS |
| **Status State Machine** | Strict `upcoming -> active -> completed` | Enforced; illegal transitions return RFC 7807 `409 INVALID_CYCLE_TRANSITION` | PASS |
| **Single Active Cycle Concurrency** | At most 1 active cycle per project | `SELECT ... FOR UPDATE` on project row prevents races; returns `409 ACTIVE_CYCLE_EXISTS` | PASS |
| **Completed Immutability** | Completed cycles cannot be patched/deleted | `PATCH`/`DELETE` returns RFC 7807 `409 CYCLE_COMPLETED` | PASS |
| **Date Range Validation** | `end_date >= start_date`, max 366 days | `end_date < start_date` returns `422 DATE_ORDER`; burndown > 366d returns `422 CYCLE_RANGE_TOO_LONG` | PASS |
| **Rollover Target Validation** | Same project, `upcoming`/`active`, distinct | Cross-project, self, or completed target returns `422 ROLLOVER_TARGET_INVALID` | PASS |
| **Batch Rollover Safety Cap** | Max 1000 unfinished issues | >1000 issues returns `409 ROLLOVER_TOO_LARGE` without partial writes | PASS |
| **Burndown Replay & RLS** | Replay `ISSUE_FIELD_CHANGED` / `STATE_CHANGED` | Computes daily `scope` and `remaining` strictly under caller RLS session | PASS |
| **Anti-Enumeration Boundary** | Unreadable project / cycle returns 404 | Out-of-boundary lookups return uniform `404 NOT_FOUND` | PASS |
| **Feature Toggle Contract** | `projects.cycles_enabled = false` | Emits RFC 7807 `404 FEATURE_DISABLED` | PASS |
| **Activity Ledger** | Emits CREATED, UPDATED, STATUS_CHANGED, DELETED | Emitted under category `HISTORY`; rollover emits `ISSUE_FIELD_CHANGED {reason: "rollover"}` | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 14/14 passed in 6.90s; 97.27% branch+line coverage across target modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (149 files), Mypy strict clean (147 files), Lint-imports clean | PASS |

---

### 2. Forensic Architectural Analysis

1. **REST Router Mounting & Timing Equalization:**
   - Mounted in `kanban/api/v1/cycles.py` and composed in `kanban/api/v1/__init__.py:build_v1_router()`:
     * `GET /api/v1/projects/{project_ref}/cycles`
     * `POST /api/v1/projects/{project_ref}/cycles`
     * `GET /api/v1/cycles/{cycle_id}`
     * `PATCH /api/v1/cycles/{cycle_id}`
     * `POST /api/v1/cycles/{cycle_id}/start`
     * `POST /api/v1/cycles/{cycle_id}/activate`
     * `POST /api/v1/cycles/{cycle_id}/complete`
     * `DELETE /api/v1/cycles/{cycle_id}`
     * `GET /api/v1/cycles/{cycle_id}/burndown`
     * `PUT /api/v1/cycles/{cycle_id}/issues/{issue_ref}`
     * `DELETE /api/v1/cycles/{cycle_id}/issues/{issue_ref}`
   - Every single endpoint is wrapped with `async with timing_floor(floor_ms=25.0):`, ensuring timing side-channels during project lookups, permission evaluations, and cycle updates are completely suppressed.

2. **Concurrency-Safe State Machine & Active Cycle Invariant:**
   - In `kanban/services/cycles.py`, lifecycle progression enforces `upcoming -> active` (`start` / `activate`) and `active -> completed` (`complete`).
   - Starting an already active cycle or completing an upcoming cycle rejects with RFC 7807 `409 INVALID_CYCLE_TRANSITION`.
   - To guarantee at most one active cycle per project under concurrent activation attempts, `activate_cycle` issues `SELECT id FROM projects WHERE id = :project_id FOR UPDATE` before inspecting whether another cycle in the project has `status = 'active'`. If an active cycle exists, it raises RFC 7807 `409 ACTIVE_CYCLE_EXISTS`.
   - Completed cycles are strictly immutable: `PATCH` and `DELETE` requests raise RFC 7807 `409 CYCLE_COMPLETED`.

3. **Sprint Closure & Atomic Rollover Engine:**
   - When completing an active cycle with `POST /api/v1/cycles/{cycle_id}/complete`:
     * Target cycle must belong to the same project, must have status `upcoming` or `active`, and cannot be the current cycle. Violations raise RFC 7807 `422 ROLLOVER_TARGET_INVALID`.
     * Unfinished issues are queried strictly where `state_group NOT IN ('completed', 'cancelled')` and `deleted_at IS NULL`.
     * Bounded by `MAX_ROLLOVER_ISSUES = 1000`. Exceeding 1000 issues raises RFC 7807 `409 ROLLOVER_TOO_LARGE` without making any partial updates.
     * When `rollover_to_cycle_id` is null, unfinished issues have `cycle_id` cleared to null.
     * When a valid target is supplied, issues are atomically reassigned to the target cycle. Each moved issue generates an `ISSUE_FIELD_CHANGED` activity record with `field: "cycle_id"` and `reason: "rollover"`.
     * Cycle status transition emits `CYCLE_STATUS_CHANGED` with `from_status: "active"` and `to_status: "completed"`.

4. **Historical Burndown Replay & RLS Isolation:**
   - In `kanban/services/burndown.py`, burndown series are reconstructed across each calendar day from `start_date` to `min(end_date, today)`.
   - Cycles spanning more than 366 days raise RFC 7807 `422 CYCLE_RANGE_TOO_LONG`.
   - For each day, the engine computes:
     * `scope`: issues belonging to the cycle at that day's cutoff timestamp.
     * `remaining`: scope minus issues in terminal states (`completed`, `cancelled`) at that day's cutoff timestamp.
   - Historical status and membership are accurately determined by replaying `activity_records` (`ISSUE_FIELD_CHANGED` for `cycle_id` and `ISSUE_STATE_CHANGED`).
   - All queries run strictly within the caller's RLS database session. Issues or cycles in unauthorized projects are excluded from the burndown series, preventing information leaks.

5. **Anti-Enumeration Boundary & Feature Toggle:**
   - Looking up an unreadable project or cycle returns indistinguishable RFC 7807 `404 NOT_FOUND`.
   - When `projects.cycles_enabled = false`, cycle endpoints fail closed with RFC 7807 `404 FEATURE_DISABLED`.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have completed the backend architecture and API Specialist Gate audit for `KANBA-88`. All REST contracts, timing floors, lifecycle transitions, concurrency locks, rollover safety boundaries, and burndown calculations are satisfied.

Verdict: APPROVED
