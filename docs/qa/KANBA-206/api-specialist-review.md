# API Specialist Review: KANBA-206 (KB-QA-RECONCILE)

- **Audited Ticket**: `KANBA-206` (`[KB-QA-RECONCILE]: Architecture Reconciliation, Codex CLI Fix, Docker Sandbox Stage, E2E Gate Rework Loop, and Admin MCP Scopes`)
- **Reviewer**: API Specialist / Backend Architect
- **Date**: 2026-11-17
- **Certification Outcome**: **APPROVED**

---

## 1. Scope of Audit

The API specialist audited the following backend and protocol surfaces:
1. **Codex CLI Invocation Enforcement**: `kanban/agents/cli_policy.py` and `agent/runners/cli_pipe.py`.
2. **Dockerfile `sandbox` Stage & Entrypoint**: `Dockerfile` and `kanban/sandbox/worker.py`.
3. **E2E Transition Gate Reject -> Rework -> Accept Loop**: `tests/workflows/test_e2e_transition_gate_rework_loop.py`.
4. **All 12 `/mcp/admin` Tools in `SCOPE_REQUIREMENTS`**: `mcp/auth.py`, `mcp/protocol.py`, `mcp/admin/tools/manage_ai_and_agent_runners.py`, and `mcp/surfaces/admin/architect_project.py`.
5. **Favicon Endpoint**: `kanban/app.py`.

---

## 2. Invariant Verification & Security Analysis

### A. Codex CLI Policy (`codex exec -s read-only -`)
- **Validation**: `CODEX_PINNED_PREFIX` is strictly pinned to `("exec", "-s", "read-only", "-")`.
- **Security Check**: Attempting to supply `-p` or `--profile` is rejected fail-closed with `CODEX_SANDBOX_OVERRIDE` or `BANNED_CLI_FLAG`. Execution strictly forces standard input sentinel `-` and read-only sandbox mode `-s read-only`.
- **Compatibility**: Verified against Anthropic Claude proxy scenarios and documented in `docs/ARCHITECTURE_DELTA.md`.

### B. Dockerfile `sandbox` Stage
- **Validation**: Stage `FROM runtime-slim AS sandbox` runs as non-root user `UID 10001:10001` with entrypoint `/usr/local/bin/kanban-sandbox-worker` executing module `kanban.sandbox.worker`.
- **Consistency**: Verified against `docker-compose.yml` service `script-sandbox`. `docker build --target sandbox` passes cleanly.

### C. Transition Gate E2E State Machine & TOCTOU Integrity
- **Loop Flow**:
  1. Transition 1 enters `pending_agent_gate` (`⏳🤖`), runs the verifier against an isolated Git repository snapshot, emits `verdict="REJECT"` with `cited_files=["src/calc.py"]`, rolls back to source state (`🛑🤖`), and posts the veto comment.
  2. Rework step pushes the corrected commit to the Git repository.
  3. Transition 2 re-enters the gate, inspects the updated commit SHA, emits `verdict="APPROVE"`, advances state to target state (`✅🤖`), clears hold, and updates immutable audit ledger.
- **Cryptographic Audit Ledger**: Validated that `row_hash` and `prev_hash` form an unbroken cryptographic chain across all ledger entries (`GATE_REJECTED`, `GATE_APPROVED`, `ISSUE_STATE_CHANGED`).

### D. MCP Admin Tools Scope Enforcement
- **All 12 Tools**: Verified that all 12 official `/mcp/admin` tools are present in `SCOPE_REQUIREMENTS`.
- **Action-Aware Scopes**: Enforces `admin:read` for inspection queries, `admin:write` for mutations, and `admin:destructive` for deletions and purges.
- **Alias Resolution**: `project` and `project_key` correctly alias to `project_id`.

### E. Favicon Serving
- **Route**: `GET /favicon.ico` serves SVG brand mark with HTTP 200, `Content-Type: image/svg+xml`, and `Cache-Control: public, max-age=86400`.

---

## 3. Test & Linter Verifications

- **Unit Tests**: 63 passed in 0.93s (`kanban/tests/ops/test_dockerfile_stages.py`, `mcp/tests/test_admin_scope_requirements_all_12.py`, `tests/workflows/test_e2e_transition_gate_rework_loop.py`, `agent/tests/context/test_verdict.py`, `kanban/tests/agents/test_cli_policy.py`, `agent/tests/runners/test_cli_pipe.py`).
- **Code Quality**: `uv run ruff check .` passed with 0 errors and 0 warnings.
- **Dashes Audit**: `uv run python -m scripts.check_no_dashes --all` returned 0 violations.

---

## 4. Final Verdict

The API and backend changes adhere strictly to the Paranoiac Security Invariants, pass all verification checks, and are certified for production deployment.

**Verdict**: **APPROVED**
