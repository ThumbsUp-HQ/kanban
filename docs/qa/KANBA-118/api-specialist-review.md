# API Specialist Gate Final Audit: APPROVED for KANBA-114 (KB-P5-12)

- Reviewer: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-114`
- Branch: `feat/KANBA-114`
- Head Commit SHA: `ca9b4dd`
- Ticket: `KANBA-114` (`KB-P5-12`: `[Phase 5 / Database + API] Cryptographic manifest_sha256 escalation approvals (Scope x Principal matrix, AAL2 & tamper auto-revocation)`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive systems architecture, database schema, cryptographic protocol, and REST API specialist audit was conducted for `KANBA-114` (`KB-P5-12`) in `/tmp/kb-wt-KANBA-114`. This ticket implements the cryptographic escalation approval subsystem governing custom field scope and principal escalations beyond the default `(PROJECT, INVOKING_USER)` boundary according to Section 13.2, Section 4.2, and Section 3.2 specifications.

All architectural invariants, database constraints, tamper auto-revocation triggers, dual-control workflows, and timing safety gates have been rigorously inspected and verified.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **S13.2 Scope x Principal Matrix** | 4 valid escalated rows; disallow invalid combos | Enforced in DB CHECK constraint & service layer (`422 ESCALATION_COMBO_INVALID`) | PASS |
| **Database DDL & Named Constraints** | Strict CHECKs on scope, principal, AAL, and dual control | `custom_field_approvals_scope_principal_combo_check` & `dual_approver_distinct_check` verified | PASS |
| **FORCE Row-Level Security** | `ENABLE` + `FORCE RLS` on `custom_field_approvals` | `relforcerowsecurity = t`; SELECT for admins; INSERT/UPDATE require AAL >= 2 | PASS |
| **Tamper Auto-Revocation Trigger** | Auto-revoke approvals on `manifest_sha256` update | Trigger `custom_field_manifest_tamper_revoke` marks rows `REVOKED` (`MANIFEST_SHA256_CHANGED`) | PASS |
| **Dual-Control Enforcement** | Distinct Server Admins for SERVER scope approvals | Multi-step `PENDING -> PENDING_SECOND_APPROVER -> APPROVED`; self-second approval rejected | PASS |
| **AAL2 Step-Up & Freshness Gate** | AAL level >= 2 verified within <= 900 seconds | Rejects AAL1 and expired AAL2 (>900s) with RFC 7807 403 `AAL2_REQUIRED` | PASS |
| **Service Principal Warning** | Explicit `sp_warning_acknowledged` required for SP modes | Rejects approval without acknowledgement with RFC 7807 422 `SP_WARNING_ACK_REQUIRED` | PASS |
| **Cryptographic HMAC Signature** | 32-byte HMAC-SHA256 bound to manifest and approvers | `compute_approval_signature_hmac` using subkey `custom-field-approval/v1`; constant-time check | PASS |
| **Fail-Closed Execution Gate** | `assert_execution_authorized` fails closed on tamper | Raises `ApprovalRevokedError(code="APPROVAL_REVOKED")` if manifest or HMAC tampered | PASS |
| **Cache Partitioning Isolation** | Scope-aware key generation preventing cross-tenant leaks | `user_access_hash` for user OBO; `b""` for SP; `should_cache=False` for SERVER scope | PASS |
| **REST Endpoints & Timing Floor** | Wrapped in 25.0ms timing floor; anti-enumeration | `timing_floor(floor_ms=25.0)` on request, approve, and list routes; uniform 404s | PASS |
| **Audit Ledger Recording** | Immutable audit records on lifecycle transitions | Emits `CUSTOM_FIELD_APPROVAL_REQUESTED`, `APPROVED_PRIMARY`, `APPROVED`, `REVOKED` | PASS |
| **Test Coverage & Metrics** | >= 95% line + branch coverage across target modules | 20/20 passed in 4.88s; **96.95%** total branch + line coverage | PASS |
| **Static Code Quality** | Zero compiler, typing, formatting, or contract errors | Ruff clean, Ruff format clean (795 files), Mypy strict clean, Lint-imports clean | PASS |
| **Typography Standard** | Strictly plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 2. Deep Technical & Security Invariant Audits

#### A. S13.2 Scope x Principal Escalation Matrix & Database Constraints
1. **Scope x Principal Permitted Combinations:**
   - Section 13.2 mandates that custom fields execute strictly within specific permission tiers:
     * `(PROJECT, INVOKING_USER)`: Default execution boundary. No escalation approval required.
     * `(PROJECT, PROJECT_ADMIN_SP)`: Project scope under elevated Service Principal. Requires `PROJECT_ADMIN` tier approval and explicit acknowledgement of `sp_warning_acknowledged = True`.
     * `(WORKSPACE, INVOKING_USER)`: Workspace-wide scope under invoking user credentials. Requires `WORKSPACE_ADMIN` tier approval.
     * `(WORKSPACE, PROJECT_ADMIN_SP)`: Workspace-wide scope under elevated Service Principal. Requires `WORKSPACE_ADMIN` tier approval and `sp_warning_acknowledged = True`.
     * `(SERVER, INVOKING_USER)`: Server-wide scope under invoking user credentials. Requires `SERVER_ADMIN_DUAL` dual-control approval.
     * `(SERVER, SERVER_ADMIN_SP)`: Server-wide scope under elevated Service Principal. Requires `SERVER_ADMIN_DUAL` dual-control approval and `sp_warning_acknowledged = True`.
2. **PostgreSQL Named CHECK Constraints (`p5_12_custom_field_approvals.up.sql`):**
   - The PostgreSQL migration enforces the matrix directly at the storage layer via named constraint `custom_field_approvals_scope_principal_combo_check`:
     ```sql
     CONSTRAINT custom_field_approvals_scope_principal_combo_check CHECK (
         (target_scope = 'PROJECT'   AND credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP')) OR
         (target_scope = 'WORKSPACE' AND credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP')) OR
         (target_scope = 'SERVER'    AND credential_mode IN ('INVOKING_USER', 'SERVER_ADMIN_SP'))
     )
     ```
   - Invalid combinations (e.g. `(PROJECT, SERVER_ADMIN_SP)` or `(SERVER, PROJECT_ADMIN_SP)`) fail at both the REST API layer (`422 ESCALATION_COMBO_INVALID`) and the database storage layer.
3. **Dual Approver Distinctness:**
   - Named constraint `custom_field_approvals_dual_approver_distinct_check`:
     ```sql
     CONSTRAINT custom_field_approvals_dual_approver_distinct_check CHECK (
         secondary_approver_id IS NULL OR secondary_approver_id <> primary_approver_id
     )
     ```
   - Guarantees that a single administrator can never satisfy dual-control requirements through self-approval.

#### B. PostgreSQL Tamper Auto-Revocation Trigger
1. **Trigger Architecture (`custom_field_manifest_tamper_revoke`):**
   - Attached to `custom_field_definitions` as:
     ```sql
     CREATE TRIGGER custom_field_manifest_tamper_revoke
     AFTER UPDATE OF manifest_sha256 ON custom_field_definitions
     FOR EACH ROW
     EXECUTE FUNCTION custom_field_manifest_tamper_revoke_tf();
     ```
   - When any update to a custom field definition modifies `manifest_sha256` (`NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256`), the trigger executes within the same atomic transaction:
     ```sql
     UPDATE custom_field_approvals
     SET status = 'REVOKED',
         revoked_at = clock_timestamp(),
         revoked_reason = 'MANIFEST_SHA256_CHANGED'
     WHERE field_id = NEW.id
       AND status IN ('PENDING', 'PENDING_SECOND_APPROVER', 'APPROVED');
     ```
2. **Single-Byte Tamper Verification:**
   - Verified via unit test `test_custom_field_approvals_trigger.py`: modifying a single byte in `script_source` or `output_format_metadata` changes the SHA-256 manifest hash, immediately tripping the trigger and updating active approvals to `REVOKED`.
   - Verified that `assert_execution_authorized` fails closed with `ApprovalRevokedError(code="APPROVAL_REVOKED")`.

#### C. Cryptographic HMAC Signature & Execution Authorization Gate
1. **Subkey Derivation & Signature Computation:**
   - `compute_approval_signature_hmac` derives a purpose-bound cryptographic key via HKDF:
     `subkey = derive_subkey(auth_pepper, "custom-field-approval/v1")`.
   - The HMAC-SHA256 signature is computed over the canonical binary concatenation:
     `field_id.bytes + manifest_sha256 + target_scope.encode() + credential_mode.encode() + primary_approver_id.bytes + (secondary_approver_id.bytes if present else 16 zero-bytes)`.
2. **Fail-Closed Execution Gate (`assert_execution_authorized`):**
   - For `(PROJECT, INVOKING_USER)` fields, returns `None` immediately without database overhead.
   - For escalated fields:
     * Queries `custom_field_approvals` for an `APPROVED` record matching `field_id` and `manifest_sha256`.
     * Rejects missing or non-approved records with `ApprovalRevokedError`.
     * Validates that `approval_signature_hmac` matches the recomputed HMAC using constant-time `hmac.compare_digest`.
     * Defends against direct database tampering: even if an attacker directly updates `status = 'APPROVED'` in PostgreSQL, execution remains blocked because the cryptographic signature check fails closed.

#### D. Dual-Control Approval Workflow & AAL2 Freshness Gates
1. **Multi-Step Approval Lifecycle for SERVER Tier:**
   - Step 1: First Server Administrator submits approval. Row status transitions from `PENDING` to `PENDING_SECOND_APPROVER`, recording `primary_approver_id`, `primary_approver_aal`, and `primary_approved_at`. Activity record `CUSTOM_FIELD_APPROVED_PRIMARY` is emitted.
   - Step 2: Second distinct Server Administrator submits approval. Service layer verifies `caller.principal_id != row.primary_approver_id` (rejecting self-approval with `409 DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED`). Status transitions to `APPROVED`, recording `secondary_approver_id`, `secondary_approver_aal`, and `secondary_approved_at`, and generates the HMAC signature. Activity record `CUSTOM_FIELD_APPROVED` is emitted.
2. **AAL2 Freshness Verification:**
   - Both request and approval actions require `caller.aal_level >= 2`.
   - On approval, the service calculates `(datetime.now(UTC) - caller.aal2_verified_at).total_seconds()`. If greater than 900 seconds (`AAL2_FRESHNESS_SECONDS`), the request is rejected with `403 AAL2_REQUIRED`, enforcing mandatory step-up re-authentication.

#### E. Cache Partitioning Invariants
1. **Scope-Aware Isolation (`compute_cache_partition_key`):**
   - `(SERVER, *)`: Returns `(False, b"")` (`should_cache = False`), completely bypassing cross-request result caching to ensure that server-wide scripts are evaluated fresh on every invocation.
   - `(*, PROJECT_ADMIN_SP | SERVER_ADMIN_SP)`: Returns `(True, b"")`. Service principal execution results are cached uniformly across users because the script executes under standard service principal permissions.
   - `(*, INVOKING_USER)`: Returns `(True, caller_user_access_hash)`. User On-Behalf-Of execution results are partitioned by the caller's 32-byte access hash, ensuring that User A cannot read cached values computed under User B's distinct permissions.

#### F. REST API Endpoints & Timing Equalization
1. **Mounted Endpoints (`kanban/api/v1/custom_field_approvals.py`):**
   - `POST /api/v1/custom-fields/{field_id}/approval-requests` (status 201 Created)
   - `POST /api/v1/custom-field-approvals/{approval_id}/approve` (status 200 OK)
   - `GET /api/v1/custom-fields/{field_id}/approvals` (status 200 OK)
2. **Timing Floor Protection:**
   - All three endpoints execute within `async with timing_floor(floor_ms=25.0):`, equalizing response timing and preventing timing side-channel leaks.
3. **TOCTOU Defense:**
   - The approval endpoint requires the caller to submit `manifest_sha256` in the request body. If the definition was modified after the administrator opened the approval UI, the submitted hash will not match the active manifest, rejecting the request with `409 MANIFEST_MISMATCH`.

---

### 3. Test Coverage & Verification Evidence

1. **Automated Unit & Feature Test Results:**
   - Command: `uv run pytest database/tests/test_custom_field_approvals_trigger.py kanban/tests/custom_fields/test_approvals_matrix.py kanban/tests/custom_fields/test_custom_field_approvals_api.py -q -p no:cacheprovider --cov=kanban.custom_fields.approvals --cov=kanban.api.v1.custom_field_approvals --cov=database.models.custom_field_approval --cov-branch --cov-report=term-missing --cov-fail-under=95`
   - Results: **20 passed in 4.88s**.
   - Code Coverage across target modules:
     * `database/models/custom_field_approval.py`: **100%** (31/31 stmts)
     * `kanban/api/v1/custom_field_approvals.py`: **100%** (24/24 stmts)
     * `kanban/custom_fields/approvals.py`: **96%** (201 stmts, 72 branches)
     * Combined Target Module Coverage: **96.95%** (exceeds mandatory >= 95% threshold).
2. **Schema Dump Verification:**
   - `docs/qa/KANBA-114/schema-dump.sql` confirms `FORCE ROW LEVEL SECURITY`, named check constraints, indexes, foreign keys, and trigger `custom_field_manifest_tamper_revoke`.
3. **Contract Sample Verification:**
   - `docs/qa/KANBA-114/contract-sample.json` records live HTTP wire exchanges for dual-control primary approval, secondary approval, manifest mismatch, invalid escalation combos, and approval listing.
4. **Static Code Quality:**
   - Ruff Linter: 0 issues across entire codebase.
   - Ruff Formatter: 795 files formatted cleanly.
   - Mypy Strict: 0 issues across 348 source files.
   - Import Linter: 2 contracts kept, 0 broken. Module hierarchy `agent -> mcp -> kanban -> database` strictly maintained.
   - License Gate: 0 violations reported by `scripts/license_gate.py`.
   - Typography Linter: 0 violations reported by `scripts/check_no_dashes.py`.

---

### 4. Final Architectural Verdict

The implementation of `KANBA-114` (`KB-P5-12`) delivers uncompromising, enterprise-grade cryptographic security for custom field escalation approvals. The combination of storage-level CHECK constraints, PostgreSQL trigger-based tamper auto-revocation, fail-closed HMAC signature verification, strict AAL2 freshness gates, and dual-control enforcement satisfies all architectural and product specification invariants.

VERDICT: APPROVED
