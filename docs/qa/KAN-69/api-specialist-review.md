# API and Security Specialist Review: KAN-69

- **Ticket:** KAN-69 ([KB-CONCURRENCY-01]) - Add Atomic Issue Claim Leases, Heartbeats, Monotonic fencing_token CAS & Multi-Worker Gate Claiming
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-69-issue-leases-fencing`
- **Commit Under Audit:** `9b39a79e` (`feat(concurrency): implement atomic issue claim leases, heartbeats, monotonic fencing CAS and multi-worker gate claiming (KAN-69)`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan69-631e67fb`
- **Status:** APPROVED

---

## 1. Executive Concurrency & Security Architecture Evaluation

Ticket KAN-69 establishes strict atomic concurrency controls, lease heartbeating, monotonic fencing tokens, and distributed multi-worker queue claiming across both REST and Model Context Protocol (MCP) surfaces.

Audited implementations across the four core problem areas:
1. **Schema Migration & PL/pgSQL Concurrency Trigger (`p6_05_issue_leases_and_fencing`):**
   - Chains linearly onto `p6_04_enforce_credential_boundary_rls_gucs` with verified clean rollback in `.down.sql`.
   - Adds `fencing_token BIGINT NOT NULL DEFAULT 0` and `row_version BIGINT NOT NULL DEFAULT 1` to `issues`.
   - Creates `issue_leases` table with primary key `(issue_id)`, unique constraint `(workspace_id, issue_id)`, and `FORCE ROW LEVEL SECURITY`.
   - Installs trigger `check_issues_concurrency_guard()` before `UPDATE` on `issues`:
     - Increments `NEW.row_version = OLD.row_version + 1`.
     - Rejects stale fencing tokens (`FENCING_TOKEN_STALE`, SQLSTATE 42001) if `NEW.fencing_token < OLD.fencing_token`.
     - Rejects unauthorized updates when an active lease is held by another principal (`LEASE_HELD`, SQLSTATE 42002) unless `kanban.admin_override = 'true'`.
     - Seamlessly permits non-leased updates when no active lease exists on the issue, preserving backward compatibility.
2. **Lease Management, Heartbeats, and CAS Services (`kanban/issues/lease_service.py`):**
   - Row-level lock acquisition using `SELECT ... FROM issues WHERE id = :id FOR UPDATE`.
   - Rejects concurrent foreign claims with RFC 7807 409 `LEASE_HELD`.
   - Idempotently allows the holding principal to renew leases, returning `lease_id`, `fencing_token`, and `lease_expires_at`.
   - Implements heartbeat extension endpoint `POST /api/v1/issues/{key}/lease/heartbeat` and release endpoint `DELETE /api/v1/issues/{key}/lease`.
   - Enforces full-row `row_version` and `If-Match` optimistic concurrency in `update_issue`.
   - Automates lease lifecycle in workflow mutations: `begin_work` acquires lease, `transition_ticket` renews or releases via `lease_action`, and `complete_work` auto-releases caller leases upon completion.
3. **MCP Tool Surface Concurrency Integration:**
   - Updated schemas in `begin_work`, `update_ticket`, `transition_ticket`, and `complete_work` to support `fencing_token`, `lease_action`, and `lease_ttl_seconds`.
   - Schema budget test (`test_schema_budget_agent_tools`) verified at 2,361 tokens (well under the 2,450 budget limit).
4. **Distributed Queue Claiming & Expired Lease Sweeping:**
   - Background sweeper `LeaseExpirySweeper` reclaims expired leases via `SELECT ... FOR UPDATE SKIP LOCKED` and logs `ISSUE_LEASE_EXPIRED`.
   - Gate runner `GateWorkerRunner` claims pending `WorkflowHookInvocation` records using `with_for_update(skip_locked=True)` with worker IDs and claim deadlines, preventing duplicate executions in multi-replica deployments.

---

## 2. Wire Contracts & Security Invariants

### A. HTTP & MCP Error Contracts
- Concurrent claim conflict returns HTTP 409 `LEASE_HELD` with holder information and expiration timestamp.
- Out-of-order write returns HTTP 409 `FENCING_TOKEN_STALE` with current and supplied tokens.
- All errors follow standard Problem Details specifications.

### B. Anti-Tampering & Security Boundaries
- Fencing tokens are strictly monotonic and cannot be decremented.
- Lease release and heartbeat operations strictly verify caller identity against the lease `principal_id` unless executed by an administrator.

---

## 3. Unit Test Coverage & Verification Metrics

- **Pytest Results:** 57 passed, 0 failed in 9.19s (`test_p6_05_issue_leases_and_fencing_migration.py`, `test_p1_17_models.py`, `test_issue_leases_and_fencing.py`, `test_issue_workflow.py`, `test_agent_lease_fencing.py`, `test_workflow_argument_validation.py`, `test_schema_budget.py`, `test_runner_skip_locked.py`, `test_gate_runner.py`).
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2193 files formatted.
  - `mypy`: 0 issues found in 1214 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.
  - `check-migrations`: Valid single head `p6_05_issue_leases_and_fencing` (67 migrations).
  - `check_no_dashes`: Clean across all files (0 violations).

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
