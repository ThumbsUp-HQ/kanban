# API and Security Specialist Review: KAN-67

- **Ticket:** KAN-67 ([KB-SEC-05]) - Enforce CredentialBoundary in PostgreSQL FORCE RLS Session GUCs, Enforce capability_mask at MCP Tool Dispatch, & Validate Trusted-Proxy Client IP for CIDR Checks
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `main` (merged from `feat/KAN-67-rls-mcp-credential-boundary`)
- **Commit Under Audit (`HEAD`):** `370cacc2445c5e9d7507bc18f6ccdf2859d74b8e` (`370cacc2`)
- **Base Commit (`main`):** `c0d45cd38df496c421f233f055533fae04d26ba3` (`c0d45cd3`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan67-34988261`
- **Status:** APPROVED

---

## 1. Executive Security & Architecture Evaluation

Ticket KAN-67 enforces end-to-end credential boundary scoping across three defense-in-depth security layers:
1. **PostgreSQL FORCE RLS Session GUC Enforcement (Alembic Migration `p6_04`):**
   - Migration `p6_04_enforce_credential_boundary_rls_gucs` installs SQL functions `app_credential_workspaces()`, `app_credential_projects()`, and `app_credential_capability_mask()`.
   - Modifies `app_current_workspace_id()`, `app_principal_has_role()`, and `app_has_object_capability()` to enforce allowlists and bitwise capability masks directly at the database engine layer under `FORCE ROW LEVEL SECURITY`.
   - Modifies `objects_select_rls` policy on the `objects` table to verify caller workspace, project, and VIEW capability bit (1) in SQL.
   - `RLSContext` and `bind_rls_context` in `database/rls/context.py` and `database/session.py` safely normalize and bind session GUCs via `SET LOCAL app.credential_*`.
2. **MCP Tool Dispatch capability_mask & allowed_tools Boundary Enforcement:**
   - Canonical `Capability(IntFlag)` and `CredentialBoundary` defined in `mcp/scoping.py` conforming to architectural layering rules (import-linter: 2 kept, 0 broken).
   - Maps read tools to VIEW (1), write tools to EDIT (4), workflow transitions to TRANSITION (8), destructive actions to DELETE (128), comments to COMMENT (2), links to LINK (16), and administration to ADMIN (64).
   - `enforce_credential_boundary_on_tool_call` enforces tool allowlists and capability masks, returning structured `KbMcpError` (`INSUFFICIENT_SCOPE`, `EPHEMERAL_TOOL_FORBIDDEN`, `KEY_SCOPE_VIOLATION`).
   - Automatically filters out unauthorized mutation and transition tools in `tools/list` when the credential is read-only.
3. **Trusted-Proxy Client IP Validation for CIDR Checks:**
   - In `mcp/auth.py`, replaces direct trust of `X-Forwarded-For` with `resolve_client_ip(scope, trusted_proxies=...)`.
   - Untrusted peer IPs cannot bypass CIDR blocks by injecting spoofed forwarding headers.

---

## 2. Wire Contracts & Security Invariants

### A. MCP Wire Contracts & Error Structures
- Tools call failure on insufficient capability returns RFC JSON-RPC 2.0 error payload with `code: "INSUFFICIENT_SCOPE"` and structured details identifying the missing bit and capability flag.
- Read-only tokens querying `tools/list` receive only tools permitted by their capability mask, hiding unreachable write/admin actions.
- Spoofed IP attempts return HTTP 403 `KEY_CIDR_DENIED` evaluating direct peer IP.

### B. Database RLS Invariants
- Under `kanban_app` with `FORCE ROW LEVEL SECURITY` active, rows outside credential boundaries are invisible at the query engine level, preventing any application layer omission from leaking tenant data.
- Session authorization drops cleanly from `kanban_migrator` to `kanban_app` during test runs, validating non-superuser enforcement.

---

## 3. Unit Test Coverage & Verification Metrics

- **Database RLS Tests:** 6 passed in 0.65s (`database/tests/test_rls_credential_boundary.py`, `database/tests/migrations/test_p6_04_enforce_credential_boundary_rls_gucs_migration.py`).
- **MCP Scoping & CIDR Tests:** 23 passed in 0.10s (`mcp/tests/test_mcp_capability_mask_and_cidr.py`, `mcp/tests/test_key_narrowing.py`, `mcp/tests/test_connection_scoping.py`).
- **Static Quality Checks:**
  - `ruff check`: All checks passed.
  - `ruff format`: Clean.
  - `mypy`: 0 issues found in 1194 source files.
  - `lint-imports`: 2 kept, 0 broken.
  - `check-migrations`: Valid single head `p6_04_enforce_credential_boundary_rls_gucs`.
  - `check_no_dashes`: Clean across all changed and repository files.

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
