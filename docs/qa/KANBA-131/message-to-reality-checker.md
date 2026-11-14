# Reality Checker Forensic Audit Packet: KANBA-131 (KB-P4-09a)

## Ticket Overview
- **Ticket ID**: `KANBA-131`
- **Ticket File**: `docs/tickets/KB-P4-09a.md`
- **Title**: `[Phase 4 / MCP] /mcp/admin tools 1-2: configure_workspace & manage_auth_cards (+ workspace settings API)`
- **Branch**: `feat/KANBA-131` in worktree `/tmp/kb-wt-KANBA-131`
- **Base Commit**: `32bce388164d9e3f404b3636c68acd3082ef4366`
- **Status**: Ready for Verification / Forensic QA Audit

---

## 1. Deliverables & Component Architecture

1. **Alembic Migration & Schema DDL (`database/migrations/`)**:
   - `database/migrations/sql/p4_09a_workspace_settings.up.sql`
   - `database/migrations/sql/p4_09a_workspace_settings.down.sql`
   - `database/migrations/versions/p4_09a_workspace_settings.py`
   - Creates `workspace_settings` table with strict CHECK constraints, Row-Level Security (`FORCE ROW LEVEL SECURITY`), `initialize_workspace_settings()` trigger for automatic row creation on `workspaces` insert, and synchronizes `trash_retention_days` with `workspaces`.

2. **SQLAlchemy ORM Model (`database/models/workspace_settings.py`)**:
   - `WorkspaceSettings` ORM model registered in `database/models/__init__.py`.

3. **REST API Endpoints (`kanban/api/v1/admin/workspace_settings.py`)**:
   - `GET /api/v1/admin/workspace-settings`: Reads workspace configuration under admin scope.
   - `PATCH /api/v1/admin/workspace-settings`: Updates configuration with boundary validation (`trash_retention_days` 1..365, `session_idle_timeout_min` 5..720, `session_absolute_timeout_min` 60..10080, `absolute >= idle`), requires AAL2 for `air_gap_mode` (`403 AAL2_REQUIRED`), and logs `WORKSPACE_SETTINGS_CHANGED` and `AIR_GAP_MODE_CHANGED` activity entries. Mounted via `kanban/api/v1/__init__.py`.

4. **Dynamic Key TTL Capping (`kanban/security/mcp_keys.py`)**:
   - Dynamic query against `workspace_settings.mcp_key_max_ttl_days` when minting MCP API keys.

5. **MCP Admin Surface Tools (`mcp/surfaces/admin/`)**:
   - `configure_workspace.py`: Implements `get`, `update`, `help` actions with S11.4 summary projection and `admin:read` / `admin:write` scope checks.
   - `manage_auth_cards.py`: Implements `list`, `get`, `create`, `update`, `enable`, `disable`, `reorder`, `test_handshake`, `delete`, `help` actions with `admin:read` / `admin:write` / `admin:destructive` scope checks, `confirm_slug` delete verification, fractional reordering via `after`, and S11.4 card summary formatting.
   - `create_admin_registry()`: Mounted on `/mcp/admin` in `mcp/app.py`.

6. **Error Codes & Handling (`mcp/errors.py`, `mcp/internal_client.py`)**:
   - Added canonical error codes: `LOCKOUT_PREVENTED`, `CONFIRM_PHRASE_MISMATCH`, and `AAL2_REQUIRED`.
   - Propagates lockout layer hints (`db_trigger` and `handshake_probe_15m`).

7. **Secret Scrubbing & Redaction (`mcp/yaml_out.py`)**:
   - Automated redaction of sensitive credentials (`secret`, `client_secret`, `bind_dn_password`, `encrypted_secret_blob`, `wrapped_dek`) to `'***'`.

---

## 2. Forensic Verification Matrix

| Verification Item | Target Requirement | Audit Evidence / Verification File | Status |
| :--- | :--- | :--- | :--- |
| **Workspace Settings DDL & RLS** | Dedicated table, FORCE RLS, sync triggers | `docs/qa/KANBA-131/schema-dump.sql` | PASS |
| **Unit Test Coverage** | >= 95% line & branch coverage across touched modules | `docs/qa/KANBA-131/unit-test-results.txt` (24/24 passed, **97%** coverage) | PASS |
| **Static Analysis & Linters** | Zero warnings/errors across ruff, mypy strict, lint-imports | `docs/qa/KANBA-131/build-check.txt` (clean) | PASS |
| **Secret Canary Grep** | `grep -c 's3cr3t-canary-91' mcp-transcript.txt` == 0 | `docs/qa/KANBA-131/secret-canary-grep.txt` (0 hits) | PASS |
| **MCP Transcript** | Captured session containing both LOCKOUT_PREVENTED variants & reorder | `docs/qa/KANBA-131/mcp-transcript.txt` | PASS |
| **Dual Specialist Gate Reviews** | Independent API & UI specialist sign-offs | `api-specialist-review.md` & `ui-specialist-review.md` (both APPROVED) | PASS |
| **Typography Standards** | Plain ASCII hyphens `-` only (zero em/en dashes) | `check_no_dashes.py` (0 violations) | PASS |
| **QA Packet Verification** | `validate-qa-packet --deterministic-only` | Grade: A | Readiness: READY (7/7 passed) | PASS |

---

## 3. Key Invariants & Test Coverage Summary

- `kanban/tests/api/test_workspace_settings.py`: 10 passed (99% coverage).
- `mcp/tests/admin/test_configure_workspace.py`: 8 passed (98% coverage).
- `mcp/tests/admin/test_manage_auth_cards.py`: 6 passed (95% coverage).
- Total Test Suite: 24 tests passed in 4.79s with **97%** line and branch coverage across touched modules.

Ready for integration and passive forensic audit.
