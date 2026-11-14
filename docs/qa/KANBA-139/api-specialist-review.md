# API Specialist Gate Review: KANBA-139 (KB-P4-12)

- **Ticket**: `KANBA-139` (`KB-P4-12`: `[Phase 4 / MCP] /mcp/admin tool 12: two-stage destructive_lifecycle (request_delete -> execute_delete with 5m blast-hash token)`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-139`
- **Worktree**: `/tmp/kb-wt-KANBA-139`
- **Scope**:
  - `database/migrations/versions/p4_12_destructive_tokens.py`
  - `database/migrations/sql/p4_12_destructive_tokens.up.sql`
  - `database/migrations/sql/p4_12_destructive_tokens.down.sql`
  - `database/models/destructive_token.py`
  - `kanban/services/destructive_lifecycle.py`
  - `kanban/api/v1/admin/destructive.py`
  - `mcp/surfaces/admin/destructive_lifecycle.py`
  - `mcp/surfaces/admin/__init__.py`
  - `mcp/auth.py`
  - `mcp/errors.py`
  - `mcp/internal_client.py`

---

### 1. Architectural & Security Evaluation

#### A. Database Schema & Token Invariants (Spec S11.4, S7.2 8q, S1.1)
- Table `destructive_confirmation_tokens`:
  - `FORCE ROW LEVEL SECURITY` enabled on the table with workspace tenancy isolation policies.
  - Foreign key to `objects(id, object_type) ON DELETE CASCADE`.
  - Check constraint `CHECK (expires_at <= created_at + interval '300 seconds')` strictly guarantees a maximum 5-minute TTL.
  - Check constraint `CHECK (octet_length(token_sha256) = 32)` ensures only cryptographic SHA-256 hashes of plaintext tokens are stored; plaintext tokens (`kb_del_<base64url>`) are never persisted in the database.
  - Check constraint `CHECK (char_length(blast_hash) = 64)` guarantees 256-bit hexadecimal blast radius hash integrity.

#### B. Recursive Blast-Radius & Execution Engine (`kanban/services/destructive_lifecycle.py`)
- Evaluates and executes destructive operations across all 8 Universal Object Graph kinds: `issue`, `project`, `doc`, `page`, `sticky`, `cycle`, `module`, `view`.
- `compute_object_blast_radius`:
  - Generates deterministic `blast_hash` across canonical JSON `{target_object_id, target_object_type, mode, content_etag_or_updated_at, sorted_descendant_ids, sorted_inbound_link_ids, sorted_outbound_link_ids, child_counts}`.
  - Minted `confirm_phrase` follows the strict uppercase convention: e.g. `TRASH ISSUE KAN-142`, `PURGE PROJECT KAN`, `RESTORE DOC Architecture`.
- Authorization Hierarchy:
  - All endpoints enforce `require_admin_aal2` dependency (rejecting AAL1 tokens with HTTP 403 `AAL2_REQUIRED`).
  - `mode="trash"` and `mode="restore"`: Require `DELETE` capability or `PROJECT_ADMIN` / `SERVER_ADMIN`. Unreadable entities return equalized HTTP 404 `NOT_FOUND` to prevent metadata probing.
  - `mode="permanent_purge"`: Strictly gated to `SERVER_ADMIN` callers (`403 SERVER_ADMIN_REQUIRED` otherwise).
  - Pre-purge Soft-Trash Rule: Entities supporting soft-trash (`issue`, `project`, `doc`, `page`, `sticky`) must reside in trash (`deleted_at IS NOT NULL`) before permanent purge is permitted (`409 SOFT_TRASH_REQUIRED_FIRST`). Entities without soft-trash (`cycle`, `module`, `view`) permit direct permanent purge after link audit accounting.
- Zero Silent Cascade Link Drops (Spec S12.3):
  - On `permanent_purge`, the service executes `audit_object_links(workspace_id)` followed by `purge_invalid_object_links()` with full audit trail before removing object rows, preventing silent cascade drops and preserving foreign key referential integrity.
  - Project permanent purge enables `SET LOCAL kanban.allow_project_delete = 'on'` to safely bypass the terminal state safeguard `workflow_states_group_guard_bd` in `p4_12_destructive_tokens.up.sql`.

#### C. Stage 2 Zero-TOCTOU Verification & Fail-Closed Token Burning
- Atomically claims token:
  `UPDATE destructive_confirmation_tokens SET consumed_at = clock_timestamp() WHERE token_sha256 = :digest AND consumed_at IS NULL AND expires_at > clock_timestamp() RETURNING *`
- Enforces strict single-use semantics: replaying an already-consumed or expired token fails with HTTP 409 `CONFIRMATION_TOKEN_INVALID_OR_EXPIRED`.
- Fail-Closed Security Invariant:
  - If a caller mismatch occurs (`caller_principal_id != current_principal_id`), the token is burned immediately and HTTP 403 `TOKEN_CALLER_MISMATCH` is returned.
  - If a phrase mismatch occurs (`confirm_phrase != row.confirm_phrase`), the token is burned immediately and HTTP 422 `CONFIRM_PHRASE_MISMATCH` is returned.
  - Swapping targets returns HTTP 409 `TOKEN_TARGET_MISMATCH`.
- Live Blast Hash Re-Verification:
  - Locks the target row `SELECT ... FOR UPDATE` and re-evaluates live blast radius. If any concurrent modification occurred (e.g. child attached or link created), execution aborts with HTTP 412 `BLAST_RADIUS_CHANGED` with zero destructive writes.

#### D. MCP Tool 12 Integration (`mcp/surfaces/admin/destructive_lifecycle.py`)
- Registered strictly on `/mcp/admin` under tool name `destructive_lifecycle`.
- Mapped to scope `admin:destructive` in `mcp/auth.py`; non-destructive admin keys (`admin:read`, `admin:write`) are rejected with `INSUFFICIENT_SCOPE`.
- RFC 9457 error code propagation through `mcp/internal_client.py` and `mcp/errors.py`.
- Formatted summary YAML output for `request_delete` conforming to Spec S11.4 Tool 12.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 23/23 pytest passed in 19.22s:
  - `kanban/tests/api/test_destructive_lifecycle.py`: 6 tests covering all mandatory specification test cases.
  - `kanban/tests/api/test_destructive_lifecycle_coverage.py`: 6 deep coverage tests across all 8 Universal Object Graph kinds, error branches, and edge conditions.
  - `mcp/tests/admin/test_destructive_lifecycle.py`: 10 MCP surface tests verifying JSON-RPC 2.0 tool calls, help action, scopes, AAL2, and error payloads.
  - `database/tests/migrations/test_p4_12_migration.py`: Migration lifecycle test verifying up/down schema operations and constraints.
- **Coverage**:
  - `kanban/api/v1/admin/destructive.py`: 100%
  - `kanban/services/destructive_lifecycle.py`: 95%
  - `mcp/surfaces/admin/destructive_lifecycle.py`: 100%
  - Combined Touched Targets: **96%** (exceeds >= 95% threshold).
- **Static Quality Gates**:
  - Ruff check: All checks passed (0 errors).
  - Ruff format: Clean (1222 files formatted).
  - Mypy strict: Clean (0 errors across 710 source files).
  - ImportLinter: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database` preserved).
  - License gate: 0 non-permissive dependencies (`SUMMARY python=115 node=1 violations=0`).
  - Typography: 0 Unicode dashes repo-wide (`check_no_dashes.py --all` clean).
- **Proof Bundle**:
  - `unit-test-results.txt`: Captured full pytest run with 96% coverage table.
  - `build-check.txt`: Captured all 6 static quality gate tools exiting 0.
  - `schema-dump.sql`: Schema dump from PostgreSQL 16 container proving DDL and RLS constraints.
  - `mcp-transcript.txt`: Captured live MCP traffic with automatic secret redaction (`KB_MCP_TRANSCRIPT_PATH`).
  - `contract-sample.json`: Wire samples for request, execute, restore, and error responses.

---

### 3. Gate Verdict

The REST endpoints and MCP Tool 12 (`destructive_lifecycle`) adhere to all security, role gating, TOCTOU blast-hash protection, and test coverage requirements.

**Verdict: APPROVED**
