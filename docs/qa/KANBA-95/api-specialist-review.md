# API Specialist Gate Review: KANBA-95 (KB-P4-02a)

- **Ticket**: `KANBA-95` (`KB-P4-02a`: Scoped kb_* API keys, surface binding, scopes & kanban-api token introspection)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-95` (`HEAD: f5ce074`)
- **Worktree**: `/tmp/kb-wt-KANBA-95`
- **Scope**: `database/migrations/sql/p4_02a_mcp_api_keys.up.sql`, `database/models/mcp_api_key.py`, `kanban/security/mcp_keys.py`, `kanban/api/internal/mcp_introspect.py`, `kanban/api/v1/admin/mcp_keys.py`, `mcp/auth.py`, `mcp/protocol.py`

---

### 1. Architectural & Security Evaluation

#### A. Token Format & Cryptographic Storage (S11.1)
- Keys follow the canonical specification: `<prefix><base64url(os.urandom(32)) without padding>` (total length 50 characters).
- Plaintext tokens are returned strictly once in the `POST /api/v1/admin/mcp-keys` HTTP 201 mint response and are never persisted to disk or emitted to logs.
- The PostgreSQL schema (`mcp_api_keys`) contains no plaintext column; tokens are persisted exclusively as 32-byte SHA-256 digests (`key_sha256 BYTEA UNIQUE CHECK (octet_length(key_sha256) = 32)`).
- `display_hint` stores strictly the final 4 characters (`CHECK (char_length(display_hint) = 4)`), preventing any leakage of token entropy.
- Maximum key TTL is capped at 365 days both via schema check constraint (`CHECK (expires_at <= created_at + interval '365 days')`) and API validation.

#### B. Surface Binding & Local Prefix Pre-Check (S11.1 / S3.2)
- Key prefixes strictly enforce surface partitioning: `kb_agt_` -> `agent`, `kb_doc_` -> `docs`, `kb_adm_` -> `admin` (`CHECK ((surface, key_prefix) IN (('agent','kb_agt_'),('docs','kb_doc_'),('admin','kb_adm_')))`).
- `McpAuthMiddleware` performs local prefix validation prior to dispatching network traffic: presenting a `kb_adm_` key to `/mcp/agent` immediately yields HTTP 403 `{"error": "SURFACE_KEY_MISMATCH"}` with zero upstream introspection calls.
- The reserved ephemeral prefix `kb_agt_eph_` is explicitly intercepted and rejected with 403 until the ephemeral agent key feature arrives in KB-P4-13.
- Database introspection function `introspect_mcp_api_key` verifies token prefix against key prefix, preventing cross-surface forgery even if digests were manipulated.

#### C. Scope Governance & Privilege Escalation Defenses (S3.2)
- Scopes are constrained to a closed set per surface:
  - `agent`: `agent:read`, `agent:write`
  - `docs`: `docs:read`, `docs:write`
  - `admin`: `admin:read`, `admin:write`, `admin:destructive`
- Minting rejects scopes outside the key's surface with HTTP 422 `INVALID_SCOPE`.
- The `admin:destructive` scope is restricted: attempting to mint it without the `SERVER_ADMIN` role is blocked with HTTP 403 `INSUFFICIENT_CAPABILITY`.
- `tools/list` filters returned tool descriptors to only those whose required scopes are a subset of the caller's held scopes.
- `tools/call` rejects unauthorized tool execution with JSON-RPC `{isError: true, error: {code: INSUFFICIENT_SCOPE}}`.

#### D. Introspection Endpoint & Timing Equalization (S11.1 / S3.4)
- `POST /internal/v1/mcp/introspect` requires internal gateway authentication (timestamped HMAC header `x-kb-internal-auth` with 300s drift window or mTLS client certificate).
- Token lookup queries the database by digest (`WHERE key_sha256 = :digest`), eliminating timing-dependent string comparisons.
- Unknown digests execute the exact same database lookup path before returning `{active: false}`, preventing timing side-channel enumeration.
- `last_used_at` timestamp is rate-limited in SQL to update at most once per 60 seconds per key, preventing write thrashing under high-frequency MCP calls.

#### E. Cache Eviction & Revocation Semantics
- Positive active introspection results are cached in an LRU cache for at most 15.0 seconds (`DEFAULT_CACHE_TTL_S`).
- Inactive, revoked, expired, or invalid results are never cached.
- Key revocation immediately sets `revoked_at` in the database and records an `MCP_KEY_REVOKED` activity entry; cached authorizations expire in <= 15s.

#### F. Session-to-Token Cryptographic Binding
- In `mcp/protocol.py`, each initialized session records the SHA-256 digest of the authenticating token (`session.token_sha256`).
- Subsequent requests presenting an existing `Mcp-Session-Id` header validate that the caller's token digest matches the session's digest. Presenting a mismatched token returns HTTP 404, preventing cross-tenant session hijacking.

#### G. Admin API Access Control & RLS Isolation
- All admin endpoints (`POST/GET/DELETE /api/v1/admin/mcp-keys`) require AAL2 authentication (`require_admin_aal2`) and workspace/server admin role.
- Table `mcp_api_keys` enforces `FORCE ROW LEVEL SECURITY`. Workspace isolation prevents Workspace Admin B from listing or viewing keys in Workspace A.
- Key deletion for a nonexistent or cross-workspace key returns uniform 404, preventing enumeration of foreign key identifiers.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 22/22 pytest passed in 1.27s across `test_mcp_keys.py`, `test_admin_mcp_keys_api.py`, and `test_auth.py`.
- **Coverage**: 99% branch+line across touched modules:
  - `kanban/api/internal/mcp_introspect.py`: 100%
  - `kanban/api/v1/admin/mcp_keys.py`: 100%
  - `kanban/security/mcp_keys.py`: 98%
  - `mcp/auth.py`: 98%
- **Static Analysis**: Ruff check clean, Ruff format clean, Mypy strict clean (318 files), ImportLinter 2/2 kept (agent -> mcp -> kanban -> database layers preserved, mcp isolated from database), License gate 0 violations, zero Unicode dashes.
- **Proof Bundle**: Complete forensic bundle (`schema-dump.sql`, `mcp-transcript.txt`, `contract-sample.json`, `unit-test-results.txt`, `build-check.txt`, `git-diff.patch`).

---

### 3. Gate Verdict

The scoped API key subsystem, surface binding rules, token introspection service, session binding, and admin management endpoints comply with all architectural, security, and quality invariants.

**VERDICT: APPROVED**
