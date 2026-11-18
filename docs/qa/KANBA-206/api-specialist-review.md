# API Specialist Forensic QA Review: KANBA-206

## Metadata
- **Ticket ID:** KANBA-206
- **Title:** [KB-QA-RECONCILE] Architecture Reconciliation, Codex CLI Fix, Docker Sandbox Stage, E2E Gate Rework Loop, and Admin MCP Scopes
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `43910c7` (merged into `main`)
- **Review Date:** 2026-11-18
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 OpenAI Codex CLI Invocation Hardening (`kanban/agents/cli_policy.py`, `agent/runners/cli_pipe.py`)
- **Strict Prefix Pinning:** `CODEX_PINNED_PREFIX` is pinned immutably to `("exec", "-s", "read-only", "-")`.
- **Banned Flags & Sandbox Enforcement:**
  - Attempts to supply `-p` or `--profile` fail-closed with `CODEX_SANDBOX_OVERRIDE` or `BANNED_CLI_FLAG`.
  - Execution strictly forces standard input sentinel `-` and read-only sandbox mode `-s read-only`.
  - Documented in `docs/ARCHITECTURE_DELTA.md` that Anthropic Claude execution requires either `claude -p` or an OpenAI-compatible proxy (`OPENAI_BASE_URL`) when using `codex exec -`.

### 1.2 Dockerfile `sandbox` Stage & Execution Security (`Dockerfile`, `kanban/sandbox/worker.py`)
- **Isolated Non-Root Worker:**
  - Stage `FROM runtime-slim AS sandbox` runs as non-root user `UID 10001:10001`.
  - Entrypoint configured as `/usr/local/bin/kanban-sandbox-worker` running module `kanban.sandbox.worker`.
  - Matches `docker-compose.yml` service `script-sandbox` definition.
  - Automated test in `kanban/tests/ops/test_dockerfile_stages.py` guarantees multi-stage Docker build parity.

### 1.3 E2E Transition Gate Reject -> Rework -> Accept Lifecycle (`tests/workflows/test_e2e_transition_gate_rework_loop.py`)
- **Cryptographic & State Invariants:**
  - Transition 1 enters `pending_agent_gate` (`⏳🤖`), executes the verifier against an isolated Git repository snapshot, emits `verdict="REJECT"` with `cited_files=["src/calc.py"]`, rolls back to source state (`🛑🤖`), posts an agent-authored veto comment, and logs `GATE_REJECTED` in the immutable activity ledger.
  - Rework step applies the fix to the Git snapshot repository.
  - Transition 2 re-evaluates the updated commit SHA, emits `verdict="APPROVE"`, advances state to target state (`✅🤖`), clears hold, and logs `GATE_APPROVED` + `ISSUE_STATE_CHANGED`.
  - Validates that `row_hash` and `prev_hash` form an unbroken cryptographic chain across all ledger entries, and outbox event `workflow.gate.approved` is recorded.

### 1.4 MCP Admin Scope Enforcement for All 12 Tools (`mcp/auth.py`, `mcp/protocol.py`)
- **All 12 Tools Registered:** All 12 official `/mcp/admin` tools are present in `SCOPE_REQUIREMENTS`:
  `configure_workspace`, `manage_auth_cards`, `architect_project`, `manage_cycles_and_modules`, `manage_custom_fields_and_scripts`, `manage_workflow_interceptors`, `manage_ai_and_agent_runners`, `manage_users_and_groups`, `manage_project_policies`, `manage_object_links`, `manage_audit_ledger`, `manage_system_settings`.
- **Action-Aware Scopes:** Protocol routing enforces `admin:read` for inspection queries, `admin:write` for mutations, and `admin:destructive` for deletions and purges.
- **Alias Resolution:** `project` alias maps cleanly to `project_key` / `project_id` in `mcp/surfaces/admin/architect_project.py` and `mcp/admin/tools/manage_ai_and_agent_runners.py`.

### 1.5 Favicon Endpoint & AuthStudio Principal Support (`kanban/app.py`, `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`)
- **Favicon:** `GET /favicon.ico` serves SVG brand mark with HTTP 200, `Content-Type: image/svg+xml`, and `Cache-Control: public, max-age=86400`.
- **Principals:** Backend supports creation of `GROUP` and `AGENT` principals via `POST /api/v1/admin/principals`, properly integrated with frontend filter tabs.

---

## 2. Test Suite & Proof Verification

### 2.1 Backend Unit & Integration Tests
- Executed `kanban/tests/ops/test_dockerfile_stages.py`, `mcp/tests/test_admin_scope_requirements_all_12.py`, `tests/workflows/test_e2e_transition_gate_rework_loop.py`, `kanban/tests/agents/test_cli_policy.py`, and `agent/tests/runners/test_cli_pipe.py`:
  - 48 passed in 0.99s, 0 failures, 0 regressions.
  - Verified:
    - Dockerfile sandbox stage target.
    - All 12 MCP admin tools scope enforcement and action-aware checks.
    - Complete E2E transition gate rework loop with cryptographic hash chain audit.
    - CLI policy enforcement rejecting `-p` / `--profile` and mandating `exec -s read-only -`.

### 2.2 Proof Artifacts Audit (`docs/qa/KANBA-206/`)
- `git-diff.patch`: Unified git diff covering all reconciliation changes.
- `changed-files-manifest.txt`: 46 modified/created files cataloged.
- `unit-test-results.txt`: Confirms 63 unit tests passed across all reconciliation domains.
- `build-check.txt`: Clean static analysis (`ruff check .`, `pnpm run typecheck`, `pnpm run build`).
- `contract-sample.json`: Valid JSON contract sample documenting transition gate verdicts, Codex CLI invocation contract, MCP admin scopes, and principal create.
- `message-to-reality-checker.md`: Detailed narrative mapping architecture and verification proofs.

---

## 3. Specialist Verdict

The implementation in commit `43910c7` satisfies all architecture reconciliation requirements, Codex CLI invocation invariants, Dockerfile sandbox stages, E2E gate rework loop guarantees, and MCP admin scope controls specified in KANBA-206.

**Verdict: APPROVED**
