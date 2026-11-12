# API Specialist Gate Final Audit: APPROVED for KANBA-87 (KB-P3-09a)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-87`
- Branch: `feat/KANBA-87`
- Ticket: `KANBA-87` (`KB-P3-09a`: `[Phase 3 / API] Archive / unarchive with Plane rule & periodic auto-archive job`)

---

### 1. Executive Summary & Verification Matrix
A forensic backend architecture and API Specialist Gate audit was conducted for `KANBA-87` in `/tmp/kb-wt-KANBA-87`. `KB-P3-09a` implements issue archiving and unarchiving under Plane's strict terminal workflow state rules, open sub-issue dependency guards, read-only archived issue immutability, list filter extensions, and a periodic background auto-archive job protected by single-runner PostgreSQL advisory locks. All endpoints, concurrency protections, authorization orders, anti-enumeration boundaries, and activity events were evaluated against Spec Sections 7.2 (8p), 3.4, and Section 5.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Router & Mounting** | Archive and unarchive endpoints mounted | Mounted in `kanban/api/v1/issue_archive.py` via `build_v1_router()` | PASS |
| **Timing Equalization** | 25.0ms timing floor on endpoints | Wrapped in `async with timing_floor(floor_ms=25.0):` | PASS |
| **Plane Rule Enforcement** | Archive only if state is completed/cancelled | Returns RFC 7807 `409 ARCHIVE_NOT_ALLOWED` with exact detail | PASS |
| **Sub-Issue Dependency Guard**| Open sub-issues block parent archive | Emits `409 ARCHIVE_OPEN_SUBISSUES` separating visible keys from hidden count | PASS |
| **Read-Only Invariant** | PATCH on archived issue returns 409 | `update_issue()` checks `archived_at` and raises `409 ISSUE_ARCHIVED` | PASS |
| **List Filter Flags** | `include_archived` & `only_archived` flags | Default excludes archived; rejects contradictory query params (`422`) | PASS |
| **Serializer Parity** | `archived_at` & `archive_eligibility` | Serializes eligibility status with inline explanatory reasons | PASS |
| **Advisory Lock Concurrency**| Single-runner advisory lock on job | Uses `pg_try_advisory_lock(hashtext('kanban.auto_archive'))` | PASS |
| **Job Batching & Locking** | Batching with SKIP LOCKED | `with_for_update(skip_locked=True)` in batches of 500 under service principal | PASS |
| **CLI & Scheduler** | CLI invocation and lifespan job registry | `kanban-ctl jobs run auto-archive` and 3600s scheduler registered | PASS |
| **Activity Ledger** | Emits ISSUE_ARCHIVED & ISSUE_UNARCHIVED | Logged under category `HISTORY` with mode metadata (`manual` / `auto`) | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 7/7 passed in 2.97s; 98.61% branch+line coverage across target modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean, Mypy strict clean (238 files), Lint-imports clean | PASS |

---

### 2. Forensic Architectural Analysis

1. **REST Router Mounting & Timing Equalization:**
   - Mounted in `kanban/api/v1/issue_archive.py` and included in `build_v1_router()`:
     * `POST /api/v1/issues/{issue_ref}/archive`
     * `POST /api/v1/issues/{issue_ref}/unarchive`
   - Both routes execute within `async with timing_floor(floor_ms=25.0):`, ensuring uniform response timing across existing, non-existent, and ACL-restricted issues.
   - Caller must hold `Capability.EDIT` on the issue (missing yields `403 INSUFFICIENT_CAPABILITY`; unreadable issue yields `404 NOT_FOUND`).

2. **Plane Rule & Sub-Issue Dependency Safeguards:**
   - **Terminal State Validation:** In `archive_issue()`, the issue's current `WorkflowState` is checked. If `state_group` is not in `ARCHIVE_TERMINAL_GROUPS` (`completed`, `cancelled`), the request is rejected with:
     * Code: `ARCHIVE_NOT_ALLOWED`
     * Status: `409`
     * Detail: `"Only completed or canceled work items can be archived"` (verbatim per Spec S7.2 8p)
   - **Open Sub-Issue Isolation:** A parent issue cannot be archived while open sub-tasks exist. The service queries child issues where `workflow_states.state_group NOT IN ('completed', 'cancelled')`.
   - **Section 3.4 Visibility Boundary:** For open sub-issues, the service verifies `Capability.VIEW` for the caller on each child. Readable sub-issues are listed in `open_subissue_keys`, while unreadable ones are grouped into `hidden_open_count`. This prevents callers from enumerating confidential sub-issues they do not have permission to view.
   - **Already Archived:** Probing archive on an already archived issue returns RFC 7807 `409 ALREADY_ARCHIVED`. Unarchive on an active issue returns `409 NOT_ARCHIVED`.

3. **Read-Only Invariant & List Filtering:**
   - In `kanban/services/issues.py:update_issue()`, modifying an issue whose `ObjectRecord.archived_at` is not null is rejected with `409 ISSUE_ARCHIVED` ("Archived issues are read-only and cannot be modified").
   - In `kanban/api/v1/issues.py:list_issues()`, query parameter `include_archived` defaults to `False`. `only_archived=True` filters exclusively for archived items. If both `not include_archived` and `only_archived` are submitted, the API returns RFC 7807 `422 ARCHIVE_FILTER_CONFLICT`.

4. **Serializer Contract Alignment (`archive_eligibility`):**
   - Every issue serialized through `serialize_issue()` provides:
     * `archived_at`: Timestamp of archive or `None`.
     * `archive_eligibility`: Structured object containing `allowed: bool` and `reason: str | None`.
   - Explanatory reasons are pre-computed:
     * `"Issue is already archived"`
     * `"Only completed or canceled work items can be archived"`
     * `"Cannot archive work item with open sub-issues"`
     * `None` when eligible for archive.

5. **Auto-Archive Background Job & Concurrency:**
   - `run_auto_archive()` in `kanban/jobs/auto_archive.py`:
     * Single-runner guarantee: Acquires PostgreSQL advisory lock `pg_try_advisory_lock(hashtext('kanban.auto_archive'))`. Concurrent runs exit immediately with 0 processed items without blocking workers.
     * Evaluates projects with non-null `auto_archive_days`.
     * Calculates cutoff time from the latest `ISSUE_STATE_CHANGED` activity record (fallback to `objects.created_at`).
     * Selects completed/cancelled issues with no open sub-issues using `with_for_update(skip_locked=True)` in batches (default 500).
     * Runs under dedicated workspace service principal `system:auto-archive` with bound RLS context and workspace admin credentials.
     * Sets `objects.archived_at = clock_timestamp()` and writes `ISSUE_ARCHIVED` activity records with `{"mode": "auto", "threshold_days": auto_archive_days}`.
   - Lifespan scheduler registers execution at 3600s intervals.
   - CLI command `kanban-ctl jobs run auto-archive [--now ISO8601]` parses arguments, runs the pass, and prints the execution summary JSON (`docs/qa/KANBA-87/cli-run.txt`).

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have completed the backend architecture and API Specialist Gate audit for `KANBA-87`. All endpoint specifications, Plane rule validations, sub-issue guards, read-only invariants, advisory locking, and background job mechanics are satisfied without exception.

Verdict: APPROVED