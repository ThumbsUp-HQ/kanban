# Reality-Checker Audit Note: KANBA-101 (KB-P3-09b)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-101` / `KB-P3-09b`: `[Phase 3 / API] Delete with blast-radius preview, soft trash, restore & retention purge job`) implements issue deletion with blast-radius calculation, cryptographic blast-hash concurrency protection, soft-delete trash bin, issue restoration, and periodic retention purge job:

1. **Target Files**:
   - `kanban/api/v1/issue_delete.py` (and alias `trash.py`): 4 REST endpoints wrapped with `timing_floor(floor_ms=25.0)`.
   - `kanban/api/v1/schemas/issue_delete.py`: Pydantic schemas for `BlastRadiusResponse`, `IssueDeleteResponse`, `TrashedIssueItem`, and `TrashedIssueList`.
   - `kanban/services/issue_delete.py` (and alias `trash.py`): Core logic for `compute_blast_radius`, `trash_issue`, `list_trash`, and `restore_issue`.
   - `kanban/services/issue_keys.py`: Enhanced `resolve_issue_ref` with `include_deleted: bool = False` parameter to support restore while keeping 404 discipline on all standard read paths.
   - `kanban/jobs/trash_purge.py`: Periodic background job (`run_trash_purge` and `run_trash_purge_pass`) guarded by PostgreSQL advisory lock `hashtext('kanban.trash_purge')`, calling `audit_object_links` and `purge_invalid_object_links` before row deletion.
   - `kanban/jobs/__init__.py`: Registered `trash_purge` job in `JobRegistry` with 3600s interval.
   - `kanban/cli/jobs.py`: Added CLI subparser `kanban-ctl jobs run trash-purge [--now ISO8601]`.
   - `kanban/settings.py`: Added `trash_retention_days` (default 30, range 1..365) and `database_url` with validation.
   - `kanban/services/activity.py`: Added `ISSUE_TRASHED`, `ISSUE_RESTORED`, and `ISSUE_PURGED` history event types.
   - `kanban/api/problems.py`: Added `current_preview` attribute to `Problem` and `ProblemException`.

2. **Security & Concurrency Invariants & Specialist Review Resolutions**:
   - **Blast Radius Cryptographic Hash (B2)**: `blast_hash` is computed as lowercase SHA-256 over canonical JSON of `(issue_id, description_sha256, sorted child ids, sorted inbound link ids, sorted outbound link ids, comment count, attachment count)`. Powered by `SECURITY DEFINER` function `get_issue_blast_radius_privileged(uuid, uuid)`, counts include rows the caller cannot view under RLS as aggregate numbers without exposing identifiers or keys.
   - **Child Unparenting (B2)**: Powered by `SECURITY DEFINER` function `unparent_issue_children_privileged(uuid, uuid)`, direct children hidden from the deleter under RLS are unparented (`parent_issue_id = NULL`) so no dangling parent references remain.
   - **Concurrency Guard**: `DELETE` requires `Kb-Blast-Hash` header (428 `BLAST_HASH_REQUIRED`). Inside a transaction with `SELECT ... FOR UPDATE`, the blast radius is recomputed; if changed, returns 412 `BLAST_RADIUS_CHANGED` with `current_preview`.
   - **Graph Link Protection & Scoped Purge (B1)**: Deletion sets `objects.deleted_at = clock_timestamp()` and unparents direct children. In `trash_purge.py`, `purge_invalid_object_links()` is scoped strictly to audits touching the issues being purged, ensuring unrelated `FLAGGED_INVALID` links remain un-purged and open until their own lifecycle expires.
   - **Restoration Rules**: `POST /restore` rejects un-trashed issues (409 `NOT_IN_TRASH`) and issues past retention window (409 `RETENTION_EXPIRED`). Direct children remain unparented, as noted in the response `"note": "sub-issues remain unparented"`.
   - **Audited Purge**: Expired issues (`deleted_at <= now - retention_days`) are purged using `SERVICE_PRINCIPAL system:trash-purge`. The job runs `audit_object_links()` followed by `purge_invalid_object_links()` with reason `TRASH_RETENTION_EXPIRED` (emitting `INVALID_OBJECT_LINK_PURGED`), then deletes dependent entities and issues/objects rows, emitting `ISSUE_PURGED` against the project.

3. **Verification & Quality Status**:
   - **Unit Tests**: 15/15 tests passing in 6.13s with **96.11%** branch + line coverage (`kanban.api.v1.issue_delete` 100%, `kanban.services.issue_delete` 95%, `kanban.jobs.trash_purge` 96%), exceeding >=95% requirement.
   - **Static Checks**: Ruff check clean, Ruff format clean, Mypy strict clean (193 files), Lint-imports clean (2 kept, 0 broken), Zero non-ASCII dashes repo-wide, Make license clean (violations=0).
   - **Contract Proof**: `contract-sample.json` captures all 7 required wire exchanges (`get_delete_preview_200`, `delete_issue_200`, `list_trash_200`, `delete_missing_hash_428`, `delete_blast_radius_changed_412`, `restore_issue_200`, `restore_retention_expired_409`).
   - **CLI Proof**: `cli-run.txt` captures successful execution of `kanban-ctl jobs run trash-purge --now 2026-11-12T00:00:00Z`.
