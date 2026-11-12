# Reality-Checker Audit Note: KANBA-87 (KB-P3-09a)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-87` / `KB-P3-09a`: `[Phase 3 / API] Archive / unarchive with Plane rule & periodic auto-archive job`) implements issue archive/unarchive lifecycle controls adhering to Plane's exact archive rule, sub-issue dependency enforcement, read-only guards on archived items, list filtering with conflict validation, and a periodic background auto-archive job guarded by PostgreSQL advisory locks:

1. **Target Files**:
   - `kanban/api/v1/issue_archive.py` (and alias `archive.py`): REST endpoints `POST /api/v1/issues/{issue_ref}/archive` and `POST /api/v1/issues/{issue_ref}/unarchive` wrapped with `timing_floor(floor_ms=25.0)`.
   - `kanban/services/issue_archive.py` (and alias `archive.py`): Core archive logic enforcing state group rule, open sub-issue guards with caller capability evaluations, timestamp recording, and immutable activity ledger append.
   - `kanban/api/v1/schemas/issues.py`: Added `ArchiveEligibility` schema and `archived_at` + `archive_eligibility` fields to `IssueResponse`.
   - `kanban/services/issues.py` & `kanban/api/v1/issues.py`: Read-only guard on archived issues (`PATCH` returns RFC 7807 `409 ISSUE_ARCHIVED`), list endpoint query parameters (`include_archived=false` by default, `only_archived=true`), and 422 `ARCHIVE_FILTER_CONFLICT` on contradictory parameters.
   - `kanban/jobs/auto_archive.py`: Background job (`run_auto_archive` and `run_auto_archive_pass`) scanning projects where `auto_archive_days IS NOT NULL`, guarded by PostgreSQL single-runner advisory lock `pg_try_advisory_lock(hashtext('kanban.auto_archive'))`, batch processing with `with_for_update(skip_locked=True)`, and service principal role binding under RLS.
   - `kanban/jobs/__init__.py`: `JobRegistry`, `JobScheduler`, and FastAPI `lifespan` context manager registering `auto_archive` at 3600s interval.
   - `kanban/cli/jobs.py` & `kanban/cli/ctl.py`: CLI command `kanban-ctl jobs run auto-archive [--now ISO8601]` printing JSON summary report.
   - `kanban/services/activity.py`: Added `ISSUE_ARCHIVED` and `ISSUE_UNARCHIVED` history events.
   - `kanban/api/problems.py`: Added RFC 7807 problem attributes (`state_group`, `open_subissue_keys`, `hidden_open_count`).

2. **Security & Concurrency Invariants**:
   - **Plane Rule Strictness**: Archive is only permitted when `workflow_states.state_group IN ('completed', 'cancelled')`. Otherwise returns 409 `ARCHIVE_NOT_ALLOWED` with exact detail string `"Only completed or canceled work items can be archived"`.
   - **Sub-Issue Guard**: Issues with open sub-issues cannot be archived, returning 409 `ARCHIVE_OPEN_SUBISSUES` with `open_subissue_keys` for readable children and `hidden_open_count` for unreadable children, preventing permission leakage.
   - **Read-Only Invariant**: Archived issues reject `PATCH` operations with 409 `ISSUE_ARCHIVED`.
   - **Advisory Lock Concurrency Guard**: Auto-archive job uses `hashtext('kanban.auto_archive')` single-runner advisory lock. Concurrent runs skip gracefully without duplicate processing or lock contention.
   - **Connection Pool Safety**: Auto-archive job operates over a single pooled connection per pass, preventing connection starvation in resource-constrained environments.

3. **Verification & Quality Status**:
   - **Unit Tests**: 7/7 passed in 3.36s with **98.61%** branch + line coverage (`kanban.api.v1.issue_archive` 100%, `kanban.services.issue_archive` 100%, `kanban.jobs.auto_archive` 98%).
   - **Static Checks**: Ruff check clean, Ruff format clean, Mypy strict clean (133 source files), Lint-imports clean (2 kept, 0 broken), Zero non-ASCII dashes repo-wide.
   - **Contract Proof**: `contract-sample.json` captures all 5 required wire exchanges (`archive_issue_200`, `unarchive_issue_200`, `archive_issue_409_not_allowed`, `archive_issue_404_not_found`, `archive_conflict_422`).
   - **CLI Proof**: `cli-run.txt` captures successful execution of `kanban-ctl jobs run auto-archive --now 2026-11-11T00:00:00Z`.
