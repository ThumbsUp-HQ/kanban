# Reality-Checker Verification Packet: KAN-67

**Ticket ID:** KAN-67  
**Title:** [KB-SEC-05] Enforce CredentialBoundary in PostgreSQL FORCE RLS Session GUCs, Enforce capability_mask at MCP Tool Dispatch, & Validate Trusted-Proxy Client IP for CIDR Checks  
**Branch:** `main` (merged from `feat/KAN-67-rls-mcp-credential-boundary`)  
**Merged Commit (`HEAD`):** `370cacc2445c5e9d7507bc18f6ccdf2859d74b8e` (`370cacc2`)  
**Pre-Ticket Base Commit (`main`):** `c0d45cd38df496c421f233f055533fae04d26ba3` (`c0d45cd3`)  
**Visual Browser Screenshots:** `N/A - Non-UI Ticket`  

---

## 1. Executive Summary & Verification Proof

All 3 actions for ticket KAN-67 have been fully implemented, rigorously tested under PostgreSQL FORCE ROW LEVEL SECURITY and ASGI simulation, checked against strict static gates (zero warnings, mypy zero errors, import-linter 2 kept 0 broken), and documented with zero em-dashes or en-dashes.

### Action 1: PostgreSQL FORCE RLS Session GUCs (SQL Row-Level Security)
- Created Alembic migration `p6_04_enforce_credential_boundary_rls_gucs` (`.up.sql` and `.down.sql`) with verified clean upgrade and downgrade lifecycle.
- In `p6_04_enforce_credential_boundary_rls_gucs.up.sql`:
  * Created SQL helper functions:
    - `app_credential_workspaces() RETURNS uuid[]`: Parses comma-separated UUID list in `app.credential_workspaces` session GUC, returning empty array if unconstrained.
    - `app_credential_projects() RETURNS uuid[]`: Parses comma-separated UUID list in `app.credential_projects` session GUC, returning empty array if unconstrained.
    - `app_credential_capability_mask() RETURNS integer`: Parses integer bitmask in `app.credential_capability_mask`, returning `255` (all bits) if unset or invalid.
    - Explicitly set `ALTER FUNCTION ... OWNER TO kanban_migrator;` for clean downgrade privilege.
  * Updated `app_current_workspace_id()`:
    - Verifies that `app.current_workspace_id` belongs to `app_credential_workspaces()`. If outside allowlist, returns `NULL` fail-closed.
  * Updated `app_principal_has_role(target_project_id, allowed_roles)`:
    - Validates project allowlist. If project allowlist is non-empty and `target_project_id` is outside allowlist, returns `FALSE` fail-closed.
  * Updated `app_has_object_capability(target_object_id, required_capability)`:
    - Restricts effective capability check to project allowlist and bitwise AND with `app_credential_capability_mask()`. If required bit is not set in mask, returns `FALSE` fail-closed.
  * Updated `objects_select_rls` policy on `objects` table:
    - Enforces workspace allowlist, project allowlist, and VIEW capability bit (1) at the SQL row level under `FORCE ROW LEVEL SECURITY`.
- In `database/rls/context.py` and `database/session.py`:
  * Extended `RLSContext` to ingest and normalize `credential_workspaces`, `credential_projects`, `credential_capability_mask`, and duck-typed `credential_boundary`.
  * Updated `bind_rls_context` to issue `SET LOCAL app.credential_workspaces = ...`, `SET LOCAL app.credential_projects = ...`, and `SET LOCAL app.credential_capability_mask = ...` in active transactions.
- Tested in `database/tests/test_rls_credential_boundary.py` and `database/tests/migrations/test_p6_04_enforce_credential_boundary_rls_gucs_migration.py`:
  * All 6 tests PASSED in 1.04s under `kanban_app` with `FORCE ROW LEVEL SECURITY` active.

### Action 2: MCP Tool Dispatch capability_mask & allowed_tools Enforcement
- In `mcp/scoping.py`:
  * Defined canonical `Capability(IntFlag)` and `CredentialBoundary` dataclass directly in MCP module without violating architectural layering contracts (`lint-imports` kept 2, broken 0).
  * Implemented `get_required_tool_capability(tool_name, action=None)`:
    - Maps read tools (`search_tickets`, `read_ticket`, `search`, `read_doc`) -> `Capability.VIEW` (1).
    - Maps write/mutation tools (`create_ticket`, `update_ticket`, `create`, `update`) -> `Capability.EDIT` (4).
    - Maps state transition tools (`begin_work`, `transition_ticket`, `complete_work`) -> `Capability.TRANSITION` (8).
    - Maps destructive tools (`destructive_lifecycle`, `delete_*`, `purge_*`, `revoke_*`) -> `Capability.DELETE` (128).
    - Maps comment tools (`add_comment`) -> `Capability.COMMENT` (2).
    - Maps link tools (`link_objects`) -> `Capability.LINK` (16).
    - Maps admin write tools -> `Capability.ADMIN` (64).
  * Implemented `enforce_credential_boundary_on_tool_call(tool_name, arguments, boundary)`:
    - Enforces `allowed_tools` narrowing on both ephemeral and standard API keys, raising structured `KbMcpError` (`EPHEMERAL_TOOL_FORBIDDEN` or `INSUFFICIENT_SCOPE`).
    - Enforces `capability_mask` bitmask, raising `INSUFFICIENT_SCOPE` with structured extra data (`required_capability`, `required_bit`, `capability_mask`).
    - Enforces `workspace_allowlist` and `project_allowlist`, raising `KEY_SCOPE_VIOLATION` if target workspace/project is outside boundary.
  * Implemented `_validate_boundary_workspace` and `_validate_boundary_project` in `intersect_key_and_connection_scope` to prevent connection scope widening beyond credential boundary.
- In `mcp/protocol.py`:
  * Connected `enforce_credential_boundary_on_tool_call` into `_handle_tools_call` prior to dispatching any tool.
  * Connected capability mask filtering in `_handle_tools_list` to automatically filter out mutating/transition/destructive tools when caller credential only has `Capability.VIEW`.
- In `mcp/auth.py`:
  * Instantiates `CredentialBoundary` from introspection payload and binds it to `McpAuthContext.credential_boundary`.

### Action 3: Trusted-Proxy Client IP Validation for MCP CIDR Checks
- In `mcp/auth.py`:
  * Replaced direct trust of `X-Forwarded-For` with `resolve_client_ip(scope, trusted_proxies=...)` from `kanban.security.client_ip`.
  * Untrusted direct peers (e.g., external clients or attackers attempting to inject spoofed `X-Forwarded-For` headers) have their spoofed headers ignored. The direct peer IP is checked against `allowed_cidrs`.
  * Trusted proxies (configured via `settings.trusted_proxies` or loopback defaults) have their forwarded client IP correctly resolved and evaluated.
  * Tested direct spoofing rejection (403 `KEY_CIDR_DENIED`) and trusted proxy pass in `mcp/tests/test_mcp_capability_mask_and_cidr.py`.

---

## 2. Verification Artifacts & Test Evidence

- `docs/qa/KAN-67/unit-test-results.txt`:
  * `database/tests/test_rls_credential_boundary.py` (5 tests PASSED)
  * `database/tests/migrations/test_p6_04_enforce_credential_boundary_rls_gucs_migration.py` (1 test PASSED)
  * `mcp/tests/test_mcp_capability_mask_and_cidr.py` (6 tests PASSED)
  * `mcp/tests/test_key_narrowing.py` (3 tests PASSED)
  * `mcp/tests/test_connection_scoping.py` (14 tests PASSED)
  * Total: 29 tests PASSED in under 2 seconds.
- `docs/qa/KAN-67/build-check.txt`:
  * `uv run ruff check .` (All checks passed)
  * `uv run ruff format --check .` (2154 files already formatted)
  * `uv run mypy` (Success: no issues found in 1194 source files)
  * `uv run lint-imports` (Contracts: 2 kept, 0 broken)
  * `uv run python -m scripts.check_no_dashes --all` (0 errors)
  * `uv run python -m database.migrations.cli check-migrations --static-only` (OK: All 66 migrations valid. Single head: p6_04_enforce_credential_boundary_rls_gucs)
- `docs/qa/KAN-67/contract-sample.json`:
  * Contains representative JSON-RPC payloads for capability mask tool rejection, read-only tools/list filtering, and 403 KEY_CIDR_DENIED spoofed IP rejection.
- `docs/qa/KAN-67/git-diff.patch`:
  * Clean, minimal patch touching only owned slice.

---

## 3. Zero Gate Bypasses & Security Invariants

- No bypasses of `FORCE ROW LEVEL SECURITY`.
- No tests were deleted or commented out.
- Zero warnings, safe typing throughout.
- All public text, QA artifacts, and comments verified to contain 0 unicode em-dashes and 0 unicode en-dashes.
