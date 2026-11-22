# KAN-69 Forensic QA Dossier: Atomic Issue Claim Leases, Heartbeats, Monotonic fencing_token CAS and Multi-Worker Gate Claiming

## Overview
- Ticket ID: KAN-69
- Spec: [KB-CONCURRENCY-01] Add Atomic Issue Claim Leases, Heartbeats, Monotonic fencing_token CAS & Multi-Worker Gate Claiming
- Branch: `main` (merged from `feat/KAN-69-issue-leases-fencing`)
- Merged Commit (`HEAD`): `b1b3d4654ee661168f2306a5afeb0a0973c437f5` (`b1b3d465`)
- Pre-Ticket Base Commit (`main`): `fdf95ee9c7e1314cf59df4ac9499769fa192c930` (`fdf95ee9`)
- Visual Browser Screenshots: `N/A - Non-UI Ticket`
- Workspace: `/home/adamoutler/kanban`

## Forensic Summary of Solved Problems

### Problem 1: Schema Migration & PL/pgSQL Concurrency Trigger
- Alembic Migration: `database/migrations/versions/p6_05_issue_leases_and_fencing.py` (with companion SQL files `.up.sql` and `.down.sql`).
- Single-head linear chain onto `p6_04_enforce_credential_boundary_rls_gucs` verified via `uv run kanban-ctl db check-migrations --static-only`.
- Added `fencing_token BIGINT NOT NULL DEFAULT 0` and `row_version BIGINT NOT NULL DEFAULT 1` to `issues`.
- Created `issue_leases` table with primary key `(issue_id)`, unique constraint `(workspace_id, issue_id)`, foreign keys to `issues` and `workspaces`, and `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`.
- Added PL/pgSQL trigger `check_issues_concurrency_guard()` before UPDATE on `issues` to:
  1. Increment `NEW.row_version = OLD.row_version + 1`.
  2. Reject stale fencing token writes (`FENCING_TOKEN_STALE`, SQLSTATE 42001) when `NEW.fencing_token < OLD.fencing_token`.
  3. Reject unauthorized writes when an unexpired lease is held by another principal (`LEASE_HELD`, SQLSTATE 42002) unless `kanban.admin_override = 'true'`. Existing callers writing without a lease when no lease is active succeed seamlessly.
- Added `claimed_by_worker VARCHAR(255)` and `claim_expires_at TIMESTAMPTZ` to `workflow_hook_invocations` table and model.
- Maintained 100% ORM model parity in `database/models/issue_lease.py`, `database/models/issues.py`, and `database/models/workflow.py`.

### Problem 2: Issue Lease Service, Heartbeats, and Monotonic CAS
- Implemented `kanban/issues/lease_service.py`:
  - `acquire_or_renew_issue_lease`: Row lock via `SELECT ... FOR UPDATE`, checks existing lease, rejects concurrent foreign claim with `409 LEASE_HELD`, atomically increments `fencing_token`, upserts `issue_leases` (`default_ttl_seconds=900`, clamped to `60..7200`).
  - `heartbeat_issue_lease`: Extends lease TTL, verifies caller or admin, validates `fencing_token`.
  - `release_issue_lease`: Deletes active lease for holder or admin.
  - `validate_caller_lease_and_fencing`: Guard against stale fencing tokens and foreign unexpired leases.
- Updated `kanban/issues/workflow_service.py`:
  - `begin_work`: Claims row, acquires lease, and returns `lease_id`, `fencing_token`, `lease_expires_at`.
  - `transition_ticket`: Validates lease and fencing token, supports `lease_action` (`renew` or `release`).
  - `complete_work`: Validates lease and fencing token, auto-releases caller's active lease.
- Updated `kanban/services/issues.py`:
  - `update_issue`: Enforces `validate_caller_lease_and_fencing`, full-row `row_version` CAS, and `If-Match` matching against `row_version`.
- Updated `kanban/api/v1/issue_workflow.py`:
  - `POST /api/v1/issues/{issue_key}/begin-work` returns lease attributes.
  - `POST /api/v1/issues/{issue_key}/lease/heartbeat` extends active lease.
  - `DELETE /api/v1/issues/{issue_key}/lease` releases active lease.
  - `POST /api/v1/issues/{issue_key}/transition` and `POST /api/v1/issues/{issue_key}/complete-work` accept `fencing_token` and `lease_action`.
- Updated MCP Surface Tools:
  - `mcp/surfaces/agent/begin_work.py`: Optional `lease_ttl_seconds`.
  - `mcp/surfaces/agent/update_ticket.py`: Optional `fencing_token`.
  - `mcp/surfaces/agent/transition_ticket.py`: Optional `fencing_token` and `lease_action`.
  - `mcp/surfaces/agent/complete_work.py`: Optional `fencing_token`.
  - Preserved strict token budget under 2,450 tokens (`mcp/tests/test_schema_budget.py` passed at 2,361 tokens).

### Problem 3: Background Lease Expiry Sweeper
- Implemented `kanban/issues/lease_sweeper.py` (`LeaseExpirySweeper`):
  - Periodic sweeper querying expired `issue_leases` (`expires_at < now`).
  - Concurrency safety: Claims rows using `FOR UPDATE SKIP LOCKED`.
  - Deletes expired lease rows and records activity log entry `ISSUE_LEASE_EXPIRED`.

### Problem 4: Distributed Gate Worker Claiming
- Updated `agent/gates/runner.py` (`GateWorkerRunner`):
  - In `_poll_once`, selects pending or expired workflow hook invocations using `with_for_update(skip_locked=True)`.
  - Stamps `claimed_by_worker = self.worker_id` and `claim_expires_at = now + claim_timeout`.
  - Prevents race conditions and duplicate executions across multi-worker deployments.

## Verification Evidence & Test Artifacts
- Unit Test Log: `docs/qa/KAN-69/unit-test-results.txt` (57 tests passed across all touched modules).
- Static Build Check Log: `docs/qa/KAN-69/build-check.txt`:
  - Ruff check: 0 errors
  - Ruff format: clean
  - Mypy: 1,214 source files clean
  - Lint imports: 2 kept, 0 broken
  - No dashes check: 0 errors
  - Check migrations: 67 valid migrations, single head `p6_05_issue_leases_and_fencing`
- Contract Samples: `docs/qa/KAN-69/contract-sample.json`
- Git Diff Patch: `docs/qa/KAN-69/git-diff.patch`
