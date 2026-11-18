# Message to Reality-Checker: KANBA-206 (KB-QA-RECONCILE) Forensic QA Packet

- **Ticket**: `KANBA-206` (`[KB-QA-RECONCILE]: Architecture Reconciliation, Codex CLI Fix, Docker Sandbox Stage, E2E Gate Rework Loop, and Admin MCP Scopes`)
- **Status**: Complete, Tested, and Ready for Reality-Checker Forensic Certification
- **Branch**: `feat/kanba-206`

---

## 1. Executive Summary

This deliverable fulfills all reconciliation and hardening requirements for ticket `KANBA-206`:

1. **OpenAI Codex CLI Invocation Hardening**:
   - Pinned `CODEX_PINNED_PREFIX` in `kanban/agents/cli_policy.py` and `agent/runners/cli_pipe.py` to `("exec", "-s", "read-only", "-")`.
   - Updated CLI policy validators to reject `-p` or `--profile` with `CODEX_SANDBOX_OVERRIDE` or `BANNED_CLI_FLAG`.
   - Updated fixtures, agent examples, and documentation. Documented in `docs/ARCHITECTURE_DELTA.md` that Anthropic Claude execution requires either `claude -p` or an OpenAI-compatible proxy (`OPENAI_BASE_URL`) when using `codex exec -`.

2. **Dockerfile `sandbox` Stage**:
   - Added `FROM runtime-slim AS sandbox` in `Dockerfile` running as non-root user `UID 10001:10001` with entrypoint `/usr/local/bin/kanban-sandbox-worker` executing module `kanban.sandbox.worker`.
   - Added automated test in `kanban/tests/ops/test_dockerfile_stages.py` confirming Dockerfile stages match `docker-compose.yml` service `script-sandbox`. Built and verified image `thumbs-up-kanban:sandbox`.

3. **E2E Transition Gate Reject -> Rework -> Accept Loop**:
   - Implemented `tests/workflows/test_e2e_transition_gate_rework_loop.py` exercising a complete lifecycle transition against a live temporary Git repository snapshot:
     - Transition 1: enters `pending_agent_gate` (`⏳🤖`), verifier analyzes commit snapshot, emits `verdict="REJECT"` with `cited_files=["src/calc.py"]`, rolls back hold to source state (`🛑🤖`), posts veto comment authored by agent principal, and logs `GATE_REJECTED` in immutable activity ledger.
     - Rework: developer commits and pushes the fix to the Git snapshot repository.
     - Transition 2: re-enters gate, verifier analyzes updated commit SHA, emits `verdict="APPROVE"`, advances state to target state (`✅🤖`), clears hold, and logs `GATE_APPROVED` + `ISSUE_STATE_CHANGED`.
     - Validates cryptographic hash chain integrity (`row_hash == prev_hash`) and outbox event `workflow.gate.approved`.

4. **All 12 `/mcp/admin` Tools in `SCOPE_REQUIREMENTS`**:
   - Added the 6 missing `/mcp/admin` tools (`configure_workspace`, `manage_auth_cards`, `architect_project`, `manage_cycles_and_modules`, `manage_custom_fields_and_scripts`, `manage_workflow_interceptors`) to `SCOPE_REQUIREMENTS` in `mcp/auth.py`.
   - Enforced action-aware scope checks in `mcp/protocol.py` (`admin:read` for inspection queries, `admin:write` for mutations, and `admin:destructive` for deletions and purges).
   - Added `project` alias to `project_key` in `mcp/surfaces/admin/architect_project.py` and `mcp/admin/tools/manage_ai_and_agent_runners.py`.
   - Added unit tests in `mcp/tests/test_admin_scope_requirements_all_12.py`.

5. **Favicon Serving & AuthStudio Principal Types**:
   - Added `GET /favicon.ico` returning brand SVG icon with HTTP 200, `Content-Type: image/svg+xml`, and `Cache-Control: public, max-age=86400` in `kanban/app.py`.
   - Added principal kind tabs (`ALL`, `USER`, `GROUP`, `AGENT`) and creation modal support for `GROUP` and `AGENT` principals in `AuthStudioPage.tsx` and `adminAuthApi.ts`.
   - Added CSS styling `.auth-principal-filters` in `adminAuth.css`.

6. **Agent Frontmatter Cleanup & Wiki Architecture Delta Sync**:
   - Removed legacy CLI tool lists (`glob`, `replace`, etc.) from `.agents/agents/*.md` frontmatter so Antigravity subagent loading never encounters unknown tool declarations.
   - Documented `ServerName: "chrome-devtools"` (with hyphen) in `.agents/skills/kanban-agent-manager/SKILL.md`.
   - Updated Wiki `User-Tasks-and-QA-Matrix.md` (added `UT-17`, `UT-18`, `UT-19`) and `Architecture-Delta-and-Missing-Features.md` + `docs/ARCHITECTURE_DELTA.md` (split `Implementation Status` vs `Verification Status` across all 15 sections, documented Codex CLI flags, Dockerfile sandbox stage, OpenAPI regeneration check, and E2E gate rework loop).
   - Verified zero em/en dashes across all repo and wiki files.

---

## 2. Forensic Proof Matrix

| # | Artifact | Description / Proof Summary | Status |
| :- | :--- | :--- | :-: |
| 1 | `docs/qa/KANBA-206/changed-files-manifest.txt` | Complete manifest of all changed and created files | **PASS** |
| 2 | `docs/qa/KANBA-206/unit-test-results.txt` | 63 unit tests passed across Dockerfile stages, MCP scopes, E2E gate rework loop, verdict parser, and CLI policy | **PASS** |
| 3 | `docs/qa/KANBA-206/build-check.txt` | Ruff clean (0 errors), pnpm typecheck (0 errors), Vite production build (built in 997ms) | **PASS** |
| 4 | `docs/qa/KANBA-206/contract-sample.json` | Sample payloads for transition gate verdicts, Codex CLI contract, MCP admin scopes, and principal create | **PASS** |
| 5 | `docs/qa/KANBA-206/api-specialist-review.md` | API Specialist audit and certification | **APPROVED** |
| 6 | `docs/qa/KANBA-206/ui-specialist-review.md` | UI / UX Specialist audit and certification | **APPROVED** |
| 7 | `docs/qa/KANBA-206/screenshots/` | 9 Playwright screenshots across Desktop, Tablet, and Mobile viewports | **PASS** |
| 8 | `docs/qa/KANBA-206/git-diff.patch` | Unified git patch for KANBA-206 changes | **PASS** |

---

## 3. Specialist Reviews Summary

- **API Specialist**: Verified Codex CLI execution parameters, Dockerfile stage target, E2E transition gate rollback and advance invariants, MCP admin tool action scoping, and favicon endpoint. Outcome: **APPROVED**.
- **UI Specialist**: Verified AuthStudio principal kind filtering, creation modal options, CSS design token compliance, and responsive multi-viewport layouts. Outcome: **APPROVED**.
