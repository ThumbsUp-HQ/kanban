# API Specialist Gate Review: KANBA-133 (KB-P4-15) - Dynamic MCP Connection Scoping

- Ticket: KANBA-133 (KB-P4-15)
- Title: Dynamic MCP Connection Scoping: Global (/mcp/{s}), Workspace (/w/{slug}) & Project (/w/{slug}/p/{key}) Routes + Header Narrowing
- Status: APPROVED
- Reviewer: arch-reviewer (Swarm Architectural & API Specialist Gate)

---

## 1. Architectural & Security Verification

1. **Three-Tier Connection Scoping & Monotonic Narrowing (Spec S11.1, S11.2)**:
   - Validated `mcp.scoping.intersect_key_and_connection_scope()`. A connection scope may only narrow token authority, never widen it.
   - Mode A (Global: `/mcp/{surface}`): Global tokens operate across authorized workspaces. Single-workspace or single-project tokens inherit their token boundary automatically, so narrow keys work seamlessly on short URLs.
   - Mode B (Workspace: `/mcp/{surface}/w/{slug}` or `X-Workspace-Slug`): Constrains calls to the designated workspace. Foreign workspace requests return HTTP 403 `KEY_SCOPE_VIOLATION` (or 404 under zero visibility).
   - Mode C (Project: `/mcp/{surface}/w/{slug}/p/{key}` or `X-Workspace-Slug` + `X-Project-Key`): Pins both workspace and project. Auto-fills `project` on tool invocations and blocks cross-project mutations. Naked `X-Project-Key` without workspace context correctly returns HTTP 400 `VALIDATION_FAILED`.

2. **Session Fingerprint Binding & Replay Defense (Spec S11.1, S11.3)**:
   - Evaluated `mcp.scoping.compute_session_fingerprint()`. Generates `sha256(token_sha256 || \0 || ws_id || \0 || proj_id)`.
   - Protocol session store (`InMemorySessionStore`) binds `scope_fingerprint` to every session.
   - Replaying an `Mcp-Session-Id` generated for `/mcp/agent/w/kanban/p/KANBA` against global `/mcp/agent` or foreign project `/w/kanban/p/OTHER` returns HTTP 404, strictly preventing session hijacking across scope boundaries.

3. **Header vs Path Consistency (Spec S11.1)**:
   - `parse_connection_scope()` enforces strict equality when both path and scope headers are present.
   - Conflicting workspace or project values return HTTP 400 `CONFLICTING_SCOPE_HEADERS` before authentication or upstream dispatch occurs.

4. **Upstream Header Forwarding & RLS Isolation (Spec S11.1, S11.2)**:
   - `KanbanApiClient.request()` extracts `connection_scope` from `McpRequestContext` and forwards:
     * `X-KB-Scope-Workspace: <workspace_slug_or_id>`
     * `X-KB-Scope-Project: <project_key_or_id>`
     * `X-KB-Scope-Global: true`
   - Downstream `kanban-api` (`kanban/resolve/service.py`, `kanban/services/issue_keys.py`, `kanban/services/search.py`) enforces session boundaries, pins RLS workspace context, and rejects unauthorized cross-workspace queries.

5. **Cross-Workspace Entity Resolution & Disambiguation (Spec S11.1)**:
   - `ResolutionService` and `resolve_issue_ref` support unconstrained resolution when invoked under `global` scope tier.
   - When an issue key exists across multiple workspaces (e.g. `API-1` in `ws-prod` and `ws-stage`), resolution raises canonical HTTP 409 `AMBIGUOUS_IDENTIFIER` with candidate list and actionable remediation hint (`pass workspace=<slug> or connect via /mcp/agent/w/<slug>`).
   - Providing `workspace=<slug>` disambiguates with HTTP 200.

6. **Cross-Project Mutation Defense**:
   - `enforce_connection_scope_on_tool_call()` inspects tool arguments (`project`, `identifier`, `parent`, `ticket`).
   - Foreign project targets (e.g. attempting to update `NETALERTXN-1` or create ticket in `GENER` while pinned to `KANBA`) are blocked before database mutation with `isError: true` and `code: CONNECTION_SCOPE_VIOLATION`.

---

## 2. Test Coverage & Quality Verification

- Unit test suite: 22/22 tests passing in 3.73s across `mcp/tests/test_connection_scoping.py`, `kanban/tests/api/test_global_and_scoped_resolution.py`, `kanban/tests/api/test_resolve.py`, and `kanban/tests/services/test_issue_keys.py`.
- Line and branch coverage: 97.77% across target modules:
  * `kanban/resolve/service.py`: 97%
  * `kanban/services/issue_keys.py`: 99%
  * `mcp/scoping.py`: 98%
- Static analysis: Zero errors across Ruff, Ruff format check (1101 files), Mypy strict (558 source files), and Import Linter (2 kept, 0 broken).
- Typography: Zero Unicode dashes (`check_no_dashes.py --all` clean).

---

## 3. Verdict

APPROVED. The dynamic connection scoping architecture fulfills all requirements for KB-P4-15 with rigorous cryptographic session binding and boundary enforcement.
