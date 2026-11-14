# Reality Checker Forensic Audit Packet: KANBA-132 (KB-P4-13)

## Ticket Overview
- **Ticket ID**: KANBA-132
- **Ticket File**: `docs/tickets/KB-P4-13.md`
- **Title**: [Phase 4 / MCP] Ephemeral kb_agt_eph_* read-only MCP tokens (execution_id, Invoker ∩ Agent ∩ Project, TTL<=120s, max_calls<=25)
- **Branch**: `feat/KANBA-132` in worktree `/tmp/kb-wt-KANBA-132`
- **Base Commit**: `32bce38`
- **Status**: Ready for Verification / Forensic QA Audit

---

## 1. Deliverables & Component Architecture

1. **Alembic Migration & Schema DDL (`database/migrations/`)**:
   - `database/migrations/sql/p4_13_mcp_ephemeral_tokens.up.sql`
   - `database/migrations/sql/p4_13_mcp_ephemeral_tokens.down.sql`
   - `database/migrations/versions/p4_13_mcp_ephemeral_tokens.py`
   - Creates `mcp_ephemeral_tokens` table with check constraints on `allowed_tools` (cardinality 1..4, subset of `{'search_tickets','read_ticket','search_knowledge','read_doc'}`), `max_calls <= 25`, `calls_used <= max_calls`, `expires_at <= created_at + 120s`, `FORCE ROW LEVEL SECURITY`, indices, and helper functions `app_effective_principal_set_for` and `app_has_object_capability`.

2. **SQLAlchemy Model (`database/models/mcp_ephemeral_token.py`)**:
   - `McpEphemeralToken` model with exact column definitions, check constraints, foreign keys to `workspaces`, `principals`, and `projects`, registered in `database/models/__init__.py`.

3. **Ephemeral Token Security Service (`kanban/security/ephemeral_mcp_tokens.py`)**:
   - `generate_ephemeral_mcp_token()`: Generates 256-bit entropy token with `kb_agt_eph_` prefix and SHA-256 digest.
   - `mint_ephemeral_token()`: Validates TTL, max_calls, allowed_tools, and active principal statuses, persisting the digest record.
   - `revoke_ephemeral_tokens_by_execution()`: Atomic invalidation of all tokens bound to an `execution_id`.
   - `introspect_and_consume_ephemeral_token()`: Surface filtering, non-consuming checks (`initialize`, `tools/list`), and atomic SQL decrement `UPDATE ... SET calls_used = calls_used + 1 ... RETURNING ...` for `tools/call`. Returns structured reason codes (`EPHEMERAL_TOOL_FORBIDDEN`, `EPHEMERAL_CALL_BUDGET_EXCEEDED`, `TOKEN_EXPIRED_OR_REVOKED`).

4. **Internal Endpoints & Route Protection (`kanban/api/internal/`)**:
   - `kanban/api/internal/mcp_ephemeral.py`: `POST /internal/v1/mcp/ephemeral-tokens` (mint) and `POST /internal/v1/mcp/ephemeral-tokens/by-execution/{execution_id}/revoke`. Enforces mTLS / HMAC authentication and service principal allowlisting (`agent-runtime`, `kanban-api` allowed, `mcp-gateway` 403 forbidden). Mounted in `kanban/app.py` and exported in `kanban/api/v1/__init__.py`.
   - `kanban/api/internal/mcp_introspect.py`: Added `consume_call` and `tool_name` parameters to request schema and `calls_used`, `max_calls`, `allowed_tools`, `token_kind`, `reason` to response schema.

5. **Session, RLS & Permission Binding (`database/session.py`, `kanban/api/deps.py`, `kanban/security/permissions.py`)**:
   - `database/session.py`: `RLSContext` and `bind_rls_context` set PostgreSQL session variables `app.agent_principal_id`, `app.ephemeral_project_id`, and `SET LOCAL TRANSACTION READ ONLY`.
   - `kanban/api/deps.py`: `PrincipalContext` extracts subject token properties and configures `get_rls_session`.
   - `kanban/security/permissions.py`: Evaluates OBO intersection (`Invoker ∩ Agent`) and enforces strict project-pin confinement.

6. **MCP Gateway Protocol & Auth Middleware (`mcp/`)**:
   - `mcp/auth.py`: Bypasses 15s positive introspection cache for `kb_agt_eph_*` tokens (0s cache delay). Surface pre-check immediately returns `403 SURFACE_KEY_MISMATCH` on `/mcp/admin`. Budget exhaustion passes through to protocol layer.
   - `mcp/errors.py`: Added error codes `EPHEMERAL_TOOL_FORBIDDEN`, `EPHEMERAL_CALL_BUDGET_EXCEEDED`, `TOKEN_EXPIRED_OR_REVOKED`.
   - `mcp/protocol.py`: Evaluates ephemeral tool allowlist before generic scope checks; formats JSON-RPC error responses with canonical YAML error payloads.
   - `mcp/internal_client.py`: Adds `X-KB-Service-Principal: mcp-gateway` header.

7. **Feature Unit Tests (`kanban/tests/security/test_ephemeral_mcp_tokens.py`, `mcp/tests/test_ephemeral_auth.py`)**:
   - 24 tests total covering all 5 mandatory test cases from `KB-P4-13.md` and edge cases.
   - 97.64% combined test coverage across touched modules (`--cov-fail-under=95` satisfied).

---

## 2. Forensic Verification Bundle Index

The following artifacts have been generated in `docs/qa/KANBA-132/`:
1. `git-diff.patch`: Complete git diff relative to base commit `32bce38`.
2. `unit-test-results.txt`: Verbose test run log with branch coverage report (24 passed in 3.72s, 97.64% coverage).
3. `build-check.txt`: Clean output from `ruff check`, `ruff format --check`, `mypy --strict`, and `lint-imports` (exit code 0).
4. `schema-dump.sql`: Complete DDL for `mcp_ephemeral_tokens`, check constraints, RLS policies, and helper functions.
5. `mcp-transcript.txt`: Recorded HTTP exchanges across MCP surfaces capturing `tools/list`, read-only lookups, call budget exhaustion, write-tool prohibition, and surface mismatch.
6. `contract-sample.json`: Representative request/response JSON payloads for mint, introspect (list), introspect (call), tool forbidden, budget exceeded, and revoke.
7. `api-specialist-review.md`: Signed API Specialist Gate review with `APPROVED` verdict.
8. `ui-specialist-review.md`: Signed UI Specialist Gate review with `APPROVED` verdict confirming alignment with `S3.4` and `S14.4`.
9. Screenshots: N/A - Non-UI Ticket.

---

## 3. Ready for Integration

This packet fulfills all requirements specified in `docs/tickets/KB-P4-13.md` and `AGENTS.md`. Handing off strictly to `@builder-w00` for integration onto `main`.
