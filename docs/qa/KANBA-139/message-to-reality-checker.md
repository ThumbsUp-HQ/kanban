# Reality-Checker Audit Note: KANBA-139 (KB-P4-12)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-139` / `KB-P4-12`: `[Phase 4 / MCP] /mcp/admin tool 12: two-stage destructive_lifecycle (request_delete -> execute_delete with 5m blast-hash token)`) implements the administrative two-stage confirmation gate for soft-trashing, permanent purging, and restoring Universal Object Graph entities.

1. **Target Files & Components**:
   - `database/migrations/versions/p4_12_destructive_tokens.py`: Migration creating `destructive_confirmation_tokens` with `FORCE ROW LEVEL SECURITY`, 5-minute TTL check constraint, SHA-256 token storage, and foreign key to `objects(id, object_type) ON DELETE CASCADE`. Also updates trigger `workflow_states_group_guard_bd` in `p4_12_destructive_tokens.up.sql` to support bypass during project purges (`kanban.allow_project_delete = 'on'`).
   - `database/models/destructive_token.py`: SQLAlchemy ORM model registered in `database/models/__init__.py` with 1:1 ORM table count parity in `database/tests/test_p1_17_models.py` (67 tables).
   - `kanban/services/destructive_lifecycle.py`: Recursive blast-radius engine across all 8 universal kinds (`issue`, `project`, `doc`, `page`, `sticky`, `cycle`, `module`, `view`). Implements:
     * `request_delete`: Computes blast radius, emits natural language summary, SHA-256 blast hash, uppercase confirmation phrase, mints single-use `kb_del_...` token stored solely as SHA-256 hash.
     * `execute_delete`: Atomically claims token (`consumed_at = clock_timestamp()`), verifies caller binding and confirmation phrase (burning the token fail-closed on mismatch), locks target row, verifies live blast hash (`412 BLAST_RADIUS_CHANGED` on TOCTOU), runs link audit accounting before permanent purge, and writes immutable `DESTRUCTIVE_LIFECYCLE_EXECUTED` activity rows.
     * `restore_object`: Restores soft-trashed items, re-parents to project root if parent was permanently purged, and records activity.
   - `kanban/api/v1/admin/destructive.py`: Three admin REST endpoints mounted with `Depends(require_admin_aal2)`:
     * `POST /api/v1/admin/destructive:request`
     * `POST /api/v1/admin/destructive:execute`
     * `POST /api/v1/admin/destructive:restore`
   - `mcp/surfaces/admin/destructive_lifecycle.py`: MCP Tool 12 implementing `request_delete`, `execute_delete`, `restore`, and `help`. Formats structured summary YAML for `request_delete`.
   - `mcp/surfaces/admin/__init__.py`: Registered `destructive_lifecycle` tool.
   - `mcp/auth.py`: Mapped `destructive_lifecycle` to `admin:destructive` scope.
   - `mcp/errors.py`: Registered error codes `CONFIRMATION_TOKEN_INVALID_OR_EXPIRED`, `TOKEN_CALLER_MISMATCH`, `TOKEN_TARGET_MISMATCH`, `BLAST_RADIUS_CHANGED`, `SOFT_TRASH_REQUIRED_FIRST`, `SERVER_ADMIN_REQUIRED`.
   - `mcp/internal_client.py`: Mapped problem types to MCP error codes.

2. **Security & Redaction Invariants**:
   - **MFA AAL2 Gate**: Caller AAL2 verification is enforced on all endpoints and MCP handler (`403 AAL2_REQUIRED`).
   - **Single-Use Cryptographic Tokens**: Plaintext tokens (`kb_del_<base64url>`) are held strictly in memory and returned once; database persists only `sha256(token)`.
   - **Fail-Closed Token Burning**: Any invalid execution attempt (wrong caller, wrong phrase) commits `consumed_at` to burn the token, preventing brute-force attacks.
   - **Zero-TOCTOU Blast-Hash Verification**: Stage 2 locks the target row and verifies `live_blast_hash == token.blast_hash`. Concurrently attached children or links trigger HTTP 412 `BLAST_RADIUS_CHANGED` with zero destructive writes.
   - **Server Admin Required for Permanent Purge**: Gated strictly to `SERVER_ADMIN` callers (`403 SERVER_ADMIN_REQUIRED`).
   - **Pre-purge Soft-Trash Rule**: Objects with soft-trash support must reside in trash before permanent purge (`409 SOFT_TRASH_REQUIRED_FIRST`).
   - **Link-Audit Provenance (Spec S12.3)**: `audit_object_links()` and `purge_invalid_object_links()` execute before permanent purge to ensure zero silent cascade link drops.
   - **Zero Secret Leaks**: Transcripts and wire exchanges redact all tokens and session secrets.
   - **Typography Standards**: Zero Unicode em/en-dashes (`U+2014`, `U+2013`); ASCII hyphens `-` only.

3. **Verification & Quality Metrics**:
   - **Unit Tests**: 23/23 pytest passed in 19.22s:
     * `kanban/api/v1/admin/destructive.py`: 100%
     * `kanban/services/destructive_lifecycle.py`: 95%
     * `mcp/surfaces/admin/destructive_lifecycle.py`: 100%
     * **Combined Touched Targets Coverage: 96%** (threshold: >=95%).
   - **Static Analysis**: Clean across `ruff check .`, `ruff format --check .`, `mypy --strict`, `lint-imports` (2 kept, 0 broken), `license_gate.py` (0 violations), and `check_no_dashes.py --all` (0 violations).
   - **Database Schema**: `docs/qa/KANBA-139/schema-dump.sql` captured from PostgreSQL 16 container proving DDL and RLS constraints.
   - **MCP Transcript**: `docs/qa/KANBA-139/mcp-transcript.txt` captured via `KB_MCP_TRANSCRIPT_PATH` recording tool calls and error conditions.
   - **REST Contract**: `docs/qa/KANBA-139/contract-sample.json` captures all 3 REST endpoints with success and error wire exchanges.
   - **Specialist Reviews**: Signed `api-specialist-review.md` and `ui-specialist-review.md` both certifying `Verdict: APPROVED`.
   - **Screenshots**: `Screenshots: N/A - Non-UI Ticket`.
