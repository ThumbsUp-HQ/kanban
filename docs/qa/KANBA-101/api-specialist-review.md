# API Specialist Gate Review: KANBA-101 (KB-P3-09b)

- **Ticket**: `KANBA-101` (`KB-P3-09b`: Delete with blast-radius preview, soft trash, restore & retention purge job)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-101` (`HEAD: beb8efb`)
- **Worktree**: `/tmp/kb-wt-KANBA-101`
- **Scope**: `kanban/api/v1/issue_delete.py`, `kanban/services/issue_delete.py`, `kanban/jobs/trash_purge.py`, `database/migrations/versions/p3_09b_issue_delete_blast_radius.py`, `database/migrations/sql/p3_09b_issue_delete_blast_radius.up.sql`

---

### 1. Architectural & Security Evaluation

#### A. Resolution of Blocker B1: Scoped Link Audit Purging (S12.3 / AGENTS Invariant 5)
- In `kanban/jobs/trash_purge.py`, the open link audit query (`touching_audits_stmt`) joins `invalid_object_link_audits` with `object_links` and filters strictly to links that touch the expired issues in the current batch: `(l.source_id = ANY(:issue_ids) OR l.target_id = ANY(:issue_ids))`.
- Purge accounting accurately maps purged link counts per issue (`purged_counts_per_issue`) for `ActivityEventType.ISSUE_PURGED` ledger payloads.
- Verified via unit test `test_unrelated_flagged_link_survives_trash_purge`: unrelated open invalid audits in the workspace survive retention purging untouched until their own target objects expire.

#### B. Resolution of Blocker B2: Privileged Blast Radius Calculation & Child Unparenting (S3.4 / S7.2 8q)
- Migration `p3_09b_issue_delete_blast_radius` introduces two hardened `SECURITY DEFINER` stored procedures (`SET search_path = pg_catalog, public`):
  1. `get_issue_blast_radius_privileged`: securely counts active direct children, inbound/outbound links, comments, and attachments across the workspace regardless of caller RLS visibility.
  2. `unparent_issue_children_privileged`: atomically unparents all direct child issues (`SET parent_issue_id = NULL`) across the workspace and returns the list of unparented IDs.
- `compute_blast_radius` folds RLS-hidden children and links into the canonical SHA-256 `blast_hash` and reports `sub_issues_unparented` and `inbound_links_flagged` as opaque integer counts only, preventing confidential issue key or title leakage.
- Concurrency verification: modifications to the underlying blast radius (e.g. adding a child or link) between preview and deletion alter the `blast_hash`, immediately aborting deletion with HTTP 412 `BLAST_RADIUS_CHANGED`.
- On confirmed deletion, `trash_issue` invokes `unparent_issue_children_privileged`, ensuring zero dangling `parent_issue_id` pointers survive.

#### C. Soft Trash, Restore & Background Retention Purge Invariants
- Soft deletion marks `objects.deleted_at = clock_timestamp()` and `issues.trashed_at = clock_timestamp()`, hiding the issue from normal board and list queries under RLS.
- Restore endpoint (`POST /api/v1/issues/{id}/restore`) clears deletion timestamps and re-runs `audit_object_links` to re-validate link integrity.
- Retention purge job runs periodically under PostgreSQL advisory locking (`pg_try_advisory_lock`), deleting items exceeding `trash_retention_days` (default 30 days) in bounded chunks of 500, unlinking attachments, and recording `ISSUE_PURGED` activity records.
- All endpoints (`GET .../delete-preview`, `POST .../delete`, `POST .../restore`) are wrapped in `timing_floor(floor_ms=25.0)`.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 15/15 pytest passed in 6.09s across `test_issue_delete.py` and `test_trash_purge.py`, verifying blast-radius calculation, preview confirmation, 412 hash mismatch, soft deletion, restore, retention purge, unreadable child masking, and unrelated audit survival.
- **Coverage**: 96.11% combined branch+line coverage across touched modules:
  - `kanban/api/v1/issue_delete.py`: 100%
  - `kanban/jobs/trash_purge.py`: 96%
  - `kanban/services/issue_delete.py`: 95%
- **Static Analysis**: Ruff check clean, Ruff format clean (745 files), Mypy strict clean (193 files), ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.
- **Proof Bundle**: Complete forensic proof bundle (`git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, `contract-sample.json`, `cli-run.txt`, `ui-specialist-review.md`).

---

### 3. Gate Verdict

Both Blocker B1 and Blocker B2 have been resolved with hardened, security-definer database functions, accurate audit filtering, and comprehensive test coverage.

**VERDICT: APPROVED**
