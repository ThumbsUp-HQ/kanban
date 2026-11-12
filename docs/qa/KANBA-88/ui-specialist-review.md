# UI Specialist Gate Final Audit: APPROVED for KANBA-88 (KB-P3-10a)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-88`
- Branch: `feat/KANBA-88`
- Ticket: `KANBA-88` (`KB-P3-10a`: `[Phase 3 / API] Cycles API: CRUD, status transitions, unfinished rollover & burndown`)

---

### 1. Executive Summary & Verification Matrix
A forensic UI, UX, and frontend API contract audit was conducted for `KANBA-88` in `/tmp/kb-wt-KANBA-88`. `KB-P3-10a` implements the core sprint planning and cycle tracking engine: cycle CRUD, strict status state machine (`upcoming -> active -> completed`), at-most-one active cycle concurrency control, unfinished issue rollover, immutable completed sprint history, and historical activity-replayed burndown chart series.

While this ticket implements backend REST services without frontend UI templates (`Screenshots: N/A - Non-UI Ticket`), the API Specialist + UI Specialist Dual Gate mandate requires auditing the frontend consumer contract, data shapes for the Cycles tab, burndown chart visualization feeds, completion modal summary structures, and RFC 7807 problem details semantics.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Cycle List & Card Contract** | `id`, `name`, `status`, dates, counts | Returns `issue_count` and `completed_count` for instant progress bar rendering | PASS |
| **Status Filter Routing** | Query parameter `?status=` | Filters by `upcoming`, `active`, `completed` for clean tabbed navigation | PASS |
| **Sprint Progress Calculation**| Zero N+1 issue queries required | Real-time aggregate counts enable immediate percentage computation in UI | PASS |
| **Date Validation Ergonomics** | Rejects `end_date < start_date` | Emits RFC 7807 `422 DATE_ORDER` allowing targeted input error highlighting | PASS |
| **Cycle Immutability Guard** | Completed cycles cannot be modified | `PATCH`/`DELETE` returns RFC 7807 `409 CYCLE_COMPLETED` preserving audit history | PASS |
| **Sprint Activation Concurrency**| At most 1 active cycle per project | Emits RFC 7807 `409 ACTIVE_CYCLE_EXISTS` to trigger resolution modal | PASS |
| **State Transition Guards** | Strict `upcoming -> active -> completed` | Emits RFC 7807 `409 INVALID_CYCLE_TRANSITION` on illegal lifecycle actions | PASS |
| **Rollover Modal Summary UX** | Response feeds sprint summary modal | `CycleCompleteResponse` provides `rolled_over` count and target cycle ID | PASS |
| **Rollover Validation Safety** | Prevent invalid rollover targets | Emits `422 ROLLOVER_TARGET_INVALID` (self, cross-project, or completed) | PASS |
| **Batch Rollover Safety Cap** | Max 1000 issues per rollover | Emits `409 ROLLOVER_TOO_LARGE` without partial writes to prevent UI stalls | PASS |
| **Burndown Chart Data Shape** | Dual series: actual vs ideal | `BurndownResponse` yields daily `series` and 2-point `ideal` linear target | PASS |
| **Burndown Duration Cap** | Max 366 days for burndown range | Emits `422 CYCLE_RANGE_TOO_LONG` preventing chart canvas/SVG degradation | PASS |
| **Feature Toggle Contract** | Project-level `cycles_enabled` switch | Emits RFC 7807 `404 FEATURE_DISABLED` when cycles are disabled | PASS |
| **Screenshots Compliance** | Verification of Non-UI ticket status | `Screenshots: N/A - Non-UI Ticket` confirmed | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 14/14 passed in 6.86s; 97.27% branch+line coverage across target modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (149 files), Mypy strict clean (147 files) | PASS |

---

### 2. Forensic UI & UX Architecture Analysis

#### 2.1 Cycles Tab & Card Metric Serialization (`CycleResponse`)
The `CycleResponse` schema directly powers the project Cycles management interface:
- **Aggregate Progress Metrics:** In addition to lifecycle metadata (`id`, `name`, `status`, `start_date`, `end_date`), the serializer computes `issue_count` and `completed_count` using database-level aggregate filtering against workflow state groups (`completed` and `cancelled`).
- **Frontend Benefit:** This eliminates the need for the frontend client to query individual issues when rendering cycle lists or sprint cards. The UI calculates the visual progress fill:
  ```ts
  const progressPercent = cycle.issue_count > 0
    ? Math.round((cycle.completed_count / cycle.issue_count) * 100)
    : 0;
  ```
- **Tab Navigation & Ordering:** `GET /api/v1/projects/{ref}/cycles?status=` orders cycles deterministically by `start_date.asc().nulls_last()` and `name.asc()`. Filtering by status (`upcoming`, `active`, `completed`) feeds dedicated sub-views without client-side array manipulation.

#### 2.2 Sprint Activation & State Machine Ergonomics (`POST /start`)
- The sprint lifecycle strictly allows `upcoming -> active` and `active -> completed`.
- When an administrator starts a cycle, the service acquires a PostgreSQL row-level lock on the parent `Project` (`SELECT ... FOR UPDATE`), guaranteeing that at most one active cycle exists per project at any given moment.
- If another cycle is currently active, the endpoint yields RFC 7807 `409 ACTIVE_CYCLE_EXISTS` (`"Another cycle is already active in this project"`). The frontend captures this error code to trigger a prompt modal:
  * "Cycle 'Sprint 12' is currently active. Would you like to complete it before starting 'Sprint 13'?"

#### 2.3 Sprint Closure & Rollover Modal UX (`POST /complete`)
- When a sprint concludes, active issues that have not reached a terminal state (`completed` or `cancelled`) must be handled.
- The `CycleComplete` payload accepts `{"rollover_to_cycle_id": "<uuid> | null"}`:
  - If a valid target cycle is specified, all unfinished issues are atomically transitioned to the target cycle, emitting both `ISSUE_FIELD_CHANGED {field: "cycle_id"}` and `ISSUE_CYCLE_CHANGED` activity entries for audit transparency.
  - If `null` is passed, unfinished issues are unlinked (`cycle_id = NULL`), returning them cleanly to the project backlog.
- **Defensive Rollover Boundaries:**
  - `422 ROLLOVER_TARGET_INVALID`: Prevents circular rollover to the cycle being completed, to cross-project cycles, or to already completed cycles.
  - `409 ROLLOVER_TOO_LARGE`: Prevents transaction timeouts or UI freezes if more than 1,000 unfinished issues are queued for rollover.
- **Modal Feedback:** Returns `CycleCompleteResponse` containing the finalized `cycle` entity and `rolled_over` count, populating the sprint closure celebration dialog ("Sprint completed: 7 unfinished issues rolled over to Sprint 14").

#### 2.4 Burndown Visualization Feed (`GET /cycles/{cycle_id}/burndown`)
The `BurndownResponse` schema provides an optimal data contract for SVG, Canvas, or charting components:
- **Actual Burndown Series (`series: list[BurndownPoint]`):**
  - Contains daily objects `{"date": "YYYY-MM-DD", "scope": int, "remaining": int}` for each calendar day from `start_date` through `min(end_date, today)`.
  - Replays historical `activity_records` (`ISSUE_FIELD_CHANGED` and `ISSUE_STATE_CHANGED`) to accurately reconstruct scope increases (issues added mid-sprint) and remaining work drops (issues transitioned to completed).
- **Ideal Guideline (`ideal: list[BurndownIdealPoint]`):**
  - Provides a 2-point reference vector starting at `{"date": start_date, "remaining": initial_scope}` and concluding at `{"date": end_date, "remaining": 0}`.
- **Rendering Protection:** Burndown range is capped at 366 days (`422 CYCLE_RANGE_TOO_LONG`), ensuring the frontend chart component never encounters unbounded data arrays.

#### 2.5 Feature Toggle Contract (`404 FEATURE_DISABLED`)
When `projects.cycles_enabled` is false, all cycle endpoints return RFC 7807 `404 FEATURE_DISABLED`. This enables the client shell to hide the "Cycles" navigation item or render a project configuration enablement banner without broken error states.

---

### 3. Screenshots Verification
- `Screenshots: N/A - Non-UI Ticket`: Confirmed. This ticket delivers core backend sprint management, burndown calculation, and cycle transition endpoints without frontend HTML/React components.

---

### 4. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 5. Gate Sign-Off
I have completed the UI and UX Architecture Specialist Gate audit for `KANBA-88`. The cycle serialization model, burndown series structure, rollover completion feedback, and discrete RFC 7807 problem details align with frontend user experience and sprint planning requirements.

Verdict: APPROVED
