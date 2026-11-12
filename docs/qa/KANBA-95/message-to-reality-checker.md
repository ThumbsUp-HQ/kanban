# Reality-Checker Audit Note: KANBA-95 (KB-P4-02a)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-95` / `KB-P4-02a`: `[Phase 4 / MCP] Scoped kb_* API keys, surface binding, scopes & kanban-api token introspection`) implements surface-bound API keys (`kb_agt_*`, `kb_doc_*`, `kb_adm_*`) stored strictly as 32-byte SHA-256 digests, token introspection for `kanban-api`, and MCP authentication middleware:

1. **Target Files**:
   - `database/migrations/versions/p4_02a_mcp_api_keys.py`: Alembic migration chaining from `p2_06_oidc_auth_requests`. Single head maintained.
   - `database/migrations/sql/p4_02a_mcp_api_keys.up.sql`: Table `mcp_api_keys` with `FORCE ROW LEVEL SECURITY`, `key_sha256 BYTEA UNIQUE (32 bytes)`, constraints on surface, key_prefix, display_hint (4 chars), expires_at <= created_at + 365 days, and security definer function `introspect_mcp_api_key(BYTEA)` for fast lookup and throttled (60s) `last_used_at` updates.
   - `database/migrations/sql/p4_02a_mcp_api_keys.down.sql`: Clean downgrade DDL dropping function and table.
   - `database/models/mcp_api_key.py`: `McpApiKey` ORM model mapped in `database.models`. Schema parity validated against all 42 models in `database/tests/test_p1_17_models.py`.
   - `kanban/security/mcp_keys.py`: Key minting (`mint_mcp_api_key`), revoking (`revoke_mcp_api_key`), hashing (`hash_mcp_api_key`), token format generation (`kb_<surface>_<43chars_b64url>` = 50 chars total), subject token introspection (`introspect_subject_token`), and internal mTLS service-to-service auth header creation/verification.
   - `kanban/services/activity.py`: Ledger event types `MCP_KEY_MINTED` and `MCP_KEY_REVOKED` under `ActivityCategory.SYSTEM` with audit trail recording.
   - `kanban/api/v1/admin/mcp_keys.py`: Admin endpoints `POST /api/v1/admin/mcp-keys`, `GET /api/v1/admin/mcp-keys`, `DELETE /api/v1/admin/mcp-keys/{key_id}` enforcing `WORKSPACE_ADMIN` / `SERVER_ADMIN` and `AAL2_REQUIRED`. Plaintext token returned exactly once on mint (HTTP 201). Scope validation ensures surface binding and requires `SERVER_ADMIN` for `admin:destructive`.
   - `kanban/api/internal/mcp_introspect.py`: Internal endpoints `POST /internal/v1/mcp/introspect` and alias `POST /internal/mcp/introspect` with `dependencies=[Depends(verify_internal_auth)]` enforcing fail-fast 401 unauthenticated challenge before database session initialization.
   - `mcp/auth.py`: `McpAuthMiddleware` with RFC 6750 401 challenge, local surface prefix pre-check rejecting mismatches with HTTP 403 `{"error": "SURFACE_KEY_MISMATCH"}` without network calls, 15-second positive-only introspection cache (`max_entries=5000`), tool gating via `SCOPE_REQUIREMENTS`, session token binding (`Mcp-Session-Id` bound to token hash, mismatch -> 404). Decoupled from `database` to satisfy layer constraints (`agent -> mcp -> kanban -> database`).
   - `mcp/app.py` & `mcp/protocol.py`: Tool filtering in `tools/list` to return only held scopes, `INSUFFICIENT_SCOPE` error on unauthorized `tools/call`.

2. **Security Invariants Asserted & Verified**:
   - **Zero Plaintext Secrets at Rest**: Only 32-byte `sha256(token)` is stored in `key_sha256 BYTEA`. Catalog queries verify zero columns contain plaintext keys.
   - **One-Time Token Revelation**: Plaintext key is returned once in the HTTP 201 response body and never written to disk or logs.
   - **Local Surface Mismatch Defense**: Mismatched prefixes (e.g. `kb_adm_` on `/mcp/agent` or `kb_agt_` on `/mcp/admin`) are rejected immediately with HTTP 403 `{"error": "SURFACE_KEY_MISMATCH"}` with zero upstream network calls.
   - **Constant-Time Digest Lookup**: Token lookup in Postgres compares only 32-byte SHA-256 digests (`WHERE key_sha256 = $1`). No timing-dependent string comparison is performed.
   - **Introspection Cache Safety**: Positive introspection results are cached for at most 15 seconds. Inactive/failed introspections are never cached, ensuring immediate revocation propagation after 15s.
   - **Session Token Binding**: `Mcp-Session-Id` header is cryptographically bound to the SHA-256 digest of the session token. Presenting the same session ID with a different token returns 404.
   - **AAL2 Admin Gate**: Admin endpoints strictly require `AAL2_REQUIRED` and `WORKSPACE_ADMIN`. Minting `admin:destructive` scope strictly requires `SERVER_ADMIN`.
   - **Internal Route Protection**: `/internal/v1/mcp/introspect` requires valid internal authentication credentials, returning 401 fail-fast before database connection acquisition.
   - **Multi-Tenant RLS Isolation**: `mcp_api_keys` table enforces row-level security per workspace. Admins cannot list or view keys from other workspaces.

3. **Verification & Quality Status**:
   - **Unit Tests**: 22/22 passed in 1.18s across `kanban/tests/security/test_mcp_keys.py`, `kanban/tests/api/test_admin_mcp_keys_api.py`, and `mcp/tests/test_auth.py`.
   - **Coverage**: **99.0%** total coverage across touched modules (`kanban.api.internal.mcp_introspect` 100%, `kanban.api.v1.admin.mcp_keys` 100%, `kanban.security.mcp_keys` 98%, `mcp.auth` 98%).
   - **Static Quality Gates**: Clean (0 errors across `ruff check`, `ruff format --check`, `mypy --strict mcp kanban database`, `lint-imports`, `scripts/license_gate.py`, and `scripts/check_no_dashes.py --all`).
