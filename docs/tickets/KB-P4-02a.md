---
id: KB-P4-02a
title: "[Phase 4 / MCP] Scoped kb_* API keys, surface binding, scopes & kanban-api token introspection"
epic: KB-E4
depends_on: [KB-P4-01, KB-P2-06]
spec_sections: ["11.1", "3.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

### User Story
As a **Workspace Admin issuing credentials to coding agents**, I need **surface-bound API keys (`kb_agt_*`, `kb_doc_*`, `kb_adm_*`) stored only as SHA-256 digests and validated by `kanban-api` on every MCP call** so that **an agent key can never invoke admin tools, a leaked database row never reveals a usable key, and revocation takes effect within a bounded window.**

**Requirement Traceability:** `S11.1` (key prefixes, SHA-256 at rest, surface table), `S3.2` (OBO `TokenScope(t)` intersection), requirement `#12`, `#1` | **Dependencies:** `KB-P4-01`, `KB-P2-06`

> Split note: manifest row KB-P4-02 is split into `KB-P4-02a` (this ticket: API keys, surface binding, scopes, introspection, 401 challenge) and `KB-P4-02b` (OAuth 2.1 authorization server + PKCE + protected-resource metadata).

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/<rev>_mcp_api_keys.py` - DDL below.
   - `database/models/mcp_api_key.py` - SQLAlchemy model.
   - `kanban/security/mcp_keys.py` - `mint_mcp_api_key()`, `hash_mcp_api_key()`, `introspect_subject_token()`.
   - `kanban/api/internal/mcp_introspect.py` - `POST /internal/v1/mcp/introspect` (mTLS client cert of the `mcp-gateway` service principal required).
   - `kanban/api/v1/admin/mcp_keys.py` - `POST/GET/DELETE /api/v1/admin/mcp-keys` (Workspace Admin, AAL2).
   - `mcp/auth.py` - `McpAuthMiddleware`, `SCOPE_REQUIREMENTS`, introspection cache.
2. **DDL:**
   ```sql
   CREATE TABLE mcp_api_keys (
       id              UUID PRIMARY KEY DEFAULT uuidv7(),
       workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
       principal_id    UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
       surface         TEXT NOT NULL CHECK (surface IN ('agent', 'docs', 'admin')),
       key_prefix      TEXT NOT NULL CHECK (key_prefix IN ('kb_agt_', 'kb_doc_', 'kb_adm_')),
       key_sha256      BYTEA NOT NULL UNIQUE CHECK (octet_length(key_sha256) = 32),
       display_hint    TEXT NOT NULL CHECK (char_length(display_hint) = 4), -- last 4 chars only
       scopes          TEXT[] NOT NULL,
       created_by_id   UUID NOT NULL REFERENCES principals(id),
       created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
       expires_at      TIMESTAMPTZ NOT NULL,
       revoked_at      TIMESTAMPTZ,
       last_used_at    TIMESTAMPTZ,
       CHECK (expires_at <= created_at + interval '365 days'),
       CHECK ((surface, key_prefix) IN (('agent','kb_agt_'),('docs','kb_doc_'),('admin','kb_adm_')))
   );
   ```
   `ENABLE` + `FORCE ROW LEVEL SECURITY` with workspace policy; activity rows `MCP_KEY_MINTED` / `MCP_KEY_REVOKED` written to `activity_records`.
3. **Key format:** `<prefix><base64url(os.urandom(32)) without padding>` (43 chars after prefix). The plaintext is returned exactly once in the mint response and never logged; only `sha256(plaintext)` is stored. `display_hint` = last 4 chars.
4. **Scopes (closed set):** `agent:read`, `agent:write`, `docs:read`, `docs:write`, `admin:read`, `admin:write`, `admin:destructive`. Mint rejects scopes not belonging to the key's surface (`422`). `admin:destructive` additionally requires the minting admin to be `SERVER_ADMIN`.
5. **Introspection (`kanban-api`):** `POST /internal/v1/mcp/introspect {token, surface}` returns `{active, principal_id, workspace_id, surface, scopes, token_kind: "api_key"}` or `{active: false}`. Lookup is by digest (`WHERE key_sha256 = $1`), so no timing-dependent string compare occurs. Inactive when revoked, expired, principal `status != 'active'`, or surface mismatch. Surface mismatch returns `{active: false, reason: "SURFACE_KEY_MISMATCH"}`. Unknown digests return `{active: false}` after the same code path (no early return before the DB round trip). `last_used_at` updated at most once per 60s per key.
6. **MCP middleware (`mcp/auth.py`):**
   - Missing/blank `Authorization: Bearer` -> HTTP `401` with `WWW-Authenticate: Bearer realm="kanban-mcp", resource_metadata="<base>/.well-known/oauth-protected-resource/mcp/<surface>"` (metadata document itself delivered in KB-P4-02b; this ticket only emits the header).
   - Prefix pre-check before network: a `kb_adm_` token on `/mcp/agent` is rejected locally with HTTP `403` + JSON-RPC-free body `{"error":"SURFACE_KEY_MISMATCH"}`; the same check applies for every prefix/surface pair. (Exception slot for `kb_agt_eph_` is reserved and rejected until KB-P4-13.)
   - Introspection cache: positive results cached `15s` keyed by `sha256(token)`, max `5,000` entries; negative results not cached. Revocation therefore takes effect `<= 15s`.
   - `SCOPE_REQUIREMENTS: dict[str, frozenset[str]]` maps each tool name to required scopes; `tools/call` without them returns `isError: true`, `code: INSUFFICIENT_SCOPE`. `tools/list` returns only tools whose scopes the caller holds.
   - The validated token is forwarded to `kanban-api` in `X-KB-Subject-Token` (KB-P4-01 client); `MCP-Session` binds to `sha256(token)` and a session reused with a different token returns `404`.
7. **Error codes appended to `McpErrorCode`:** none new (uses `UNAUTHENTICATED`, `SURFACE_KEY_MISMATCH`, `INSUFFICIENT_SCOPE`).

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/security/test_mcp_keys.py` (clean-DB `SAVEPOINT` harness from KB-P0-05), `mcp/tests/test_auth.py`
- **Required Test Cases:**
  1. Positive: mint `kb_agt_` key with `["agent:read","agent:write"]`; plaintext length = 7 + 43; DB row stores 32-byte digest and no plaintext column exists (catalog query); introspection returns `active: true` with matching scopes; `tools/list` on `/mcp/agent` succeeds.
  2. Surface binding/security: `kb_agt_` key on `/mcp/admin` -> `403 SURFACE_KEY_MISMATCH` without any introspection call (assert `MockTransport` call count `0`); a forged token with `kb_adm_` prefix but digest of an agent key -> introspect `active: false, reason: SURFACE_KEY_MISMATCH`.
  3. Scope negative: key with only `agent:read` calling a tool requiring `agent:write` -> `INSUFFICIENT_SCOPE`; minting `admin:write` on an `agent` key -> `422`; non-SERVER_ADMIN minting `admin:destructive` -> `403`.
  4. Boundary: `expires_at = created_at + 366 days` rejected by CHECK; expired key (frozen clock) -> `401`; revoked key served from cache until `15s`, rejected at `15s + 1`; principal deactivated -> inactive.
  5. Session binding: same `Mcp-Session-Id` presented with a different valid token -> `404`.
  6. RLS: workspace B admin cannot list workspace A keys (`0` rows).

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** all target files exist; `mcp_api_keys` DDL matches Action 2 including both CHECK constraints and FORCE RLS.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/security/test_mcp_keys.py mcp/tests/test_auth.py -q --cov=mcp --cov=kanban.security --cov-branch --cov-report=term-missing` exits `0`, `0` failures, touched-module coverage `>= 95%`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict mcp kanban database && uv run lint-imports` exits `0`.
- [ ] **Schema Proof:** `docs/qa/<TICKET_ID>/schema-dump.sql` contains `CREATE TABLE mcp_api_keys` with `key_sha256 bytea` and no column holding plaintext keys.
- [ ] **Transcript Captured:** `docs/qa/<TICKET_ID>/mcp-transcript.txt` shows a 401 with `WWW-Authenticate` header, a 403 `SURFACE_KEY_MISMATCH`, an `INSUFFICIENT_SCOPE` tool result, and a successful `tools/list`; zero unredacted keys.
- [ ] **Forensic Proof Packet Complete:** all files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - raw pytest output with coverage.
3. `docs/qa/<TICKET_ID>/build-check.txt` - raw ruff + mypy + lint-imports output.
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - `pg_dump --schema-only -t mcp_api_keys` output.
5. `docs/qa/<TICKET_ID>/mcp-transcript.txt` - captured via `KB_MCP_TRANSCRIPT_PATH=docs/qa/<TICKET_ID>/mcp-transcript.txt uv run pytest mcp/tests/test_auth.py -q`.
6. `docs/qa/<TICKET_ID>/contract-sample.json` - raw introspection request/response pair (active and inactive).
7. `docs/qa/<TICKET_ID>/api-specialist-review.md`
8. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - review of key-mint response shape (one-time reveal, display hint) for the future admin UI.
9. Screenshots: N/A - Non-UI Ticket.
