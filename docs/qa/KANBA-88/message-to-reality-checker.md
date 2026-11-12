# Reality-Checker Audit Note: KANBA-88 (KB-P3-10a)

## Architectural Scope & Technical Implementation
This ticket (`KANBA-88` / `KB-P3-10a`: `[Phase 3 / API] Cycles API, status transitions, rollover & burndown`) implements the sprint planning cycles lifecycle, status state transitions, unfinished issue rollover, and historical burndown computation under S7.2 (8g) and S11.4:

1. **Target Files**:
   - `kanban/api/v1/cycles.py`: 10 REST endpoints mounted on `build_v1_router()` with `timing_floor(floor_ms=25.0)`.
   - `kanban/api/v1/schemas/cycles.py`: Pydantic request/response schemas with `ConfigDict(extra="forbid")`, supporting `CycleCreate`, `CyclePatch`, `CycleComplete`, `CycleResponse`, `CycleCompleteResponse`, `BurndownPoint`, `BurndownIdealPoint`, and `BurndownResponse`.
   - `kanban/services/cycles.py`: Complete cycle lifecycle service implementing `list_cycles`, `create_cycle`, `get_cycle`, `patch_cycle`, `start_cycle`, `complete_cycle`, `delete_cycle`, `add_issue_to_cycle`, `remove_issue_from_cycle`, and `set_project_cycles_enabled`.
   - `kanban/services/burndown.py`: Historical burndown engine replaying `activity_records` (`ISSUE_FIELD_CHANGED` and `ISSUE_STATE_CHANGED`) to compute daily scope, remaining unfinished issues, and linear ideal lines.
   - `database/models/projects.py`: Dynamic `cycles_enabled` property on `Project` model backed by `project_metadata`.
   - `kanban/services/activity.py`: Added `CYCLE_CREATED`, `CYCLE_UPDATED`, `CYCLE_STATUS_CHANGED`, `CYCLE_ACTIVATED`, `CYCLE_COMPLETED`, and `CYCLE_DELETED` under category `HISTORY`.

2. **Security & State Machine Invariants**:
   - **Status Transitions**: Strict enforcement of `upcoming -> active` (`POST .../start` and alias `.../activate`) and `active -> completed` (`POST .../complete`). Any illegal transition returns `409 INVALID_CYCLE_TRANSITION`.
   - **One Active Cycle Constraint**: Enforces at most one active cycle per project with row-level `SELECT ... FOR UPDATE` on project; starting an overlapping active cycle returns `409 ACTIVE_CYCLE_EXISTS`.
   - **Completed Immutability**: Completed cycles cannot be patched or deleted (`409 CYCLE_COMPLETED`).
   - **Issue Membership Safety**: Enforces at most one active/upcoming cycle per issue. Attempting to assign an issue already in another active/upcoming cycle returns `409 ISSUE_IN_ANOTHER_CYCLE`.
   - **Rollover Mechanics**: Unfinished issues in `todo`, `in_progress`, or `triage` states are rolled over to `rollover_to_cycle_id`. Target must be upcoming or active in the same project (`422 ROLLOVER_TARGET_INVALID`). Rollover of >1000 issues is rejected (`409 ROLLOVER_TOO_LARGE`). Null target unassigns `cycle_id`. Each rolled issue records `ISSUE_FIELD_CHANGED` with `reason: "rollover"`.
   - **Burndown RLS & Replay**: Daily metric replay counts only issues readable by caller under RLS. Maximum burndown window of 366 days enforced (`422 CYCLE_RANGE_TOO_LONG`). Backwards dates rejected (`422 DATE_ORDER`).
   - **Feature Toggle**: When `projects.cycles_enabled = false`, all cycle routes return `404 FEATURE_DISABLED`.
   - **Activity Ledger**: All lifecycle operations write immutable SHA-256 hash-chained `activity_records`.

3. **Verification & Quality Status**:
   - **Unit Tests**: 14/14 tests passing in 6.19s with **97%** branch + line coverage (`kanban.api.v1.cycles` 100%, `kanban.services.cycles` 97%, `kanban.services.burndown` 96%), exceeding the 95% threshold.
   - **Static Checks**: Ruff check clean, Ruff format clean (149 files), Mypy strict clean (147 files), Lint-imports clean (2 kept, 0 broken), License gate clean (violations=0), Zero non-ASCII dashes repo-wide.
   - **Contract Proof**: `contract-sample.json` captures 8 HTTP wire exchanges (`create_cycle_201`, `get_cycle_200`, `burndown_200`, `start_cycle_200`, `active_cycle_exists_409`, `complete_cycle_rollover_200`, `forbidden_403`, `not_found_404`).
