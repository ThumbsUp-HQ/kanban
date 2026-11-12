# Forensic QA Proof Dossier: KANBA-108 (KB-P2-09)

## Executive Summary
- Ticket ID: `KANBA-108` (`KB-P2-09`)
- Epic: `KB-E2` (Phase 2 Authentication & Identity)
- Title: `[Phase 2 / Auth] LOCKOUT_PREVENTED 3-layer safeguards & kanban-ctl auth emergency-unlock --enable-local-admin`
- Requirements Traceability: `S4.3` (Three-Layer Anti-Lockout Safeguards items 1-3), `S4.1` (`auth_provider_cards`), `S12.2` (hash-chained `activity_records`), requirement `#6`
- Gates: `[reality-checker]` (Non-UI Ticket, zero frontend dependencies)
- Typography: Zero `U+2014` (em-dash) or `U+2013` (en-dash) characters; strictly plain ASCII hyphens (`U+002D`).

---

## Technical Implementations by Anti-Lockout Layer

### 1. Layer 1: PostgreSQL Constraint Triggers (`db_trigger`, S4.3 Item 1)
- Migration: `database/migrations/sql/p2_09_lockout_prevented_safeguards.up.sql`
- Revision: `database/migrations/versions/p2_09_lockout_prevented_safeguards.py` (`revision = "p2_09_lockout_prevented"`)
- Security Definer Function: `kb_auth.card_can_authenticate_active_server_admin(p_card_id, p_provider_kind, p_workspace_id)`
  - Returns `TRUE` for `LOCAL_ADMIN` if an active `SERVER_ADMIN` principal has credentials in `local_admin_credentials`.
  - Returns `TRUE` for `OIDC`/`OAUTH2`/`LDAP` if an active `SERVER_ADMIN` principal has an identity in `user_identities` mapped to `p_card_id`.
- Concurrency Serialization: Trigger `trg_auth_cards_prevent_lockout` acquires `pg_advisory_xact_lock(hashtextextended('auth_lockout:' || COALESCE(NEW.workspace_id, OLD.workspace_id)::text, 0))` to prevent concurrent dual-disable races across parallel transactions.
- Lockout Abort: If remaining enabled admin-capable cards `= 0` in an active admin workspace, aborts with:
  `SQLSTATE 'P0001'`, `LOCKOUT_PREVENTED: zero enabled cards can authenticate an active SERVER_ADMIN`, `DETAIL = 'db_trigger'`.
- Deletion Protection: Added triggers `trg_local_admin_prevent_lockout` on `local_admin_credentials` and `trg_user_identities_prevent_lockout` on `user_identities` (`AFTER DELETE`) preventing deletion of the sole active admin credential.
- Bootstrap Allowance: If a workspace contains zero active `SERVER_ADMIN` principals, card modifications are permitted.

### 2. Layer 2: 15-Minute Live External Handshake Probe Gate (`handshake_probe_15m`, S4.3 Item 2)
- Added `last_admin_handshake_at TIMESTAMPTZ` to `auth_provider_cards`.
- Function `kb_auth.card_record_admin_handshake(p_card_id uuid)` records verified logins by `SERVER_ADMIN` principals on external cards.
- Trigger `trg_local_admin_disable_probe` (`BEFORE UPDATE OF is_enabled, provider_kind, workspace_id OR DELETE ON auth_provider_cards`):
  Prevents disabling or deleting `LOCAL_ADMIN` unless an enabled external card in the workspace has `last_admin_handshake_at >= clock_timestamp() - interval '15 minutes'`.
  Aborts with `SQLSTATE 'P0001'`, `LOCKOUT_PREVENTED: disabling LOCAL_ADMIN requires a verified external SERVER_ADMIN login within 15 minutes`, `DETAIL = 'handshake_probe_15m'`.
- Dual Enforced in Python: `assert_local_admin_disable_allowed()` in `kanban/auth/cards/lockout.py` performs equivalent pre-validation before SQL execution.
- RFC 7807 Error Mapping: `map_sqlstate_to_lockout_error()` parses `P0001` details and maps to `LockoutPreventedError(layer, detail)`, which exports to `ProblemException(status=409, code="LOCKOUT_PREVENTED", type_uri="urn:kanban:problem:lockout-prevented", extra={"layer": layer})` with zero internal SQL leakage.

### 3. Layer 3: Host CLI Emergency Break-Glass (`emergency-unlock`, S4.3 Item 3)
- CLI Command: `kanban-ctl auth emergency-unlock --enable-local-admin [--workspace <slug_or_uuid>] [--reason <text>]`
- Implemented in `kanban/cli/auth.py` and registered via `kanban/cli/ctl.py`.
- Validation:
  - Requires explicit `--enable-local-admin` flag (exits `2` without write).
  - Enforces `--reason` max length 256 characters (exits `2` if exceeded).
  - Sanitizes control characters from reason string.
- Privilege Wall:
  `REVOKE ALL ON FUNCTION kb_auth.emergency_enable_local_admin FROM PUBLIC, kanban_app;`
  `GRANT EXECUTE ON FUNCTION kb_auth.emergency_enable_local_admin TO kanban_migrator;`
  Calling as `kanban_app` raises `42501 insufficient_privilege`.
- Atomic Break-Glass:
  - Re-enables the workspace's `LOCAL_ADMIN` card (`is_enabled = TRUE`).
  - Appends an indelible audit row to `activity_records` with `event_type = 'EMERGENCY_BREAK_GLASS_INVOKED'`.
  - Verifies cryptographic ledger integrity via `verify_activity_chain(ws_id)`.
  - Protects against ledger tampering: attempts to `UPDATE` or `DELETE` the break-glass activity record raise `ACTIVITY_LEDGER_IMMUTABLE`.

---

## Automated Verification & DoD Compliance

1. **Unit & Integration Test Suite:**
   - 19 test cases across 3 test suites:
     - `database/tests/test_lockout_safeguards.py` (7 tests: sole admin disable/delete, non-admin card bypass prevention, concurrent dual-disable serialization, 15m handshake probe, member login non-satisfaction, credential delete prevention, bootstrap allowance).
     - `kanban/tests/auth/test_lockout_mapping.py` (4 tests: RFC 7807 ProblemException 409 mapping, SQLSTATE parsing, record handshake update, assert_local_admin_disable_allowed).
     - `kanban/tests/cli/test_emergency_unlock.py` (8 tests: privilege wall 42501, CLI negative validation, CLI positive run + hash chain integrity, immutable trigger verification, DSN resolution, workspace auto-detection/ambiguity, error handling, loop dispatch).
   - Test Results: 19 passed in 0.81s.
   - Code Coverage: 97.95% total across `kanban.auth.cards.lockout` (99%) and `kanban.cli.auth` (97%), exceeding the `>= 95%` gate.

2. **Migration Reversibility:**
   - Validated: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` completes cleanly with zero errors.

3. **Static Analysis & Linters:**
   - `ruff check .` -> All checks passed.
   - `ruff format --check .` -> 860 files formatted.
   - `mypy --strict kanban database` -> Success: no issues found.
   - `lint-imports` -> Contracts: 2 kept, 0 broken.
   - `make license` -> SUMMARY python=112 node=1 violations=0.
   - `python3 scripts/check_no_dashes.py --all` -> 0 violations.

---

## Passive Verification Proof Bundle
1. `docs/qa/KANBA-108/git-diff.patch` - Full unified git diff against base commit `af23306`.
2. `docs/qa/KANBA-108/unit-test-results.txt` - Verbose pytest execution output and coverage report.
3. `docs/qa/KANBA-108/build-check.txt` - Output of ruff check, ruff format, mypy --strict, lint-imports, license_gate, and check_no_dashes.
4. `docs/qa/KANBA-108/schema-dump.sql` - Trigger catalog dump for all 4 anti-lockout triggers and privilege grants confirming `kanban_app` lacks `EXECUTE` on `emergency_enable_local_admin`.
5. `docs/qa/KANBA-108/cli-run.txt` - Execution log of `kanban-ctl auth emergency-unlock --enable-local-admin --reason "QA verification"`, resulting card status, ledger entry with SHA-256 row hashes, and `verify_activity_chain()` confirmation (`is_valid = True`).
