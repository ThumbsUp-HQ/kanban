# Reality-Checker Verification Packet: KANBA-114 (KB-P5-12)

- **Ticket:** `KANBA-114` (`KB-P5-12`: `[Phase 5 / Database + API] Cryptographic manifest_sha256 escalation approvals (Scope x Principal matrix, AAL2 & tamper auto-revocation)`)
- **Branch:** `feat/KANBA-114`
- **Linear Alembic Chain:** `p5_11_custom_fields` -> `p5_12_custom_field_approvals`
- **Module Coverage:** 96.95% branch + line (exceeds mandatory >=95% threshold)
- **Static Analysis:** All clean (Ruff, Ruff format, Mypy strict, Lint-imports, License gate, Check-no-dashes)

---

### 1. Verification Matrix & Scoped DoD Criteria

| Requirement / Criterion | Status | Evidence File / Command |
| :--- | :--- | :--- |
| **DDL & Migration:** `custom_field_approvals` with ENABLE & FORCE RLS | PASS | `docs/qa/KANBA-114/schema-dump.sql`<br>`database/migrations/versions/p5_12_custom_field_approvals.py` |
| **Database Constraints:** Scope x Principal matrix & dual approver distinct | PASS | `database/tests/test_custom_field_approvals_trigger.py` |
| **PostgreSQL Trigger:** `custom_field_manifest_tamper_revoke` auto-revocation | PASS | `database/tests/test_custom_field_approvals_trigger.py`<br>`docs/qa/KANBA-114/schema-dump.sql` |
| **Escalation Policy & Tier Enforcement:** S13.2 Scope x Principal matrix | PASS | `kanban/custom_fields/approvals.py`<br>`kanban/tests/custom_fields/test_approvals_matrix.py` |
| **HMAC Signature & Tamper Detection:** HKDF-derived key & fail-closed execution check | PASS | `kanban/custom_fields/approvals.py`<br>`kanban/tests/custom_fields/test_approvals_matrix.py` |
| **Cache Partition Key:** Scope-aware partition keys & user_access_hash | PASS | `kanban/custom_fields/approvals.py`<br>`kanban/tests/custom_fields/test_approvals_matrix.py` |
| **REST Router & Endpoints:** POST request, POST approve, GET history with 25.0ms floor | PASS | `kanban/api/v1/custom_field_approvals.py`<br>`kanban/tests/custom_fields/test_custom_field_approvals_api.py` |
| **AAL2 Freshness & Dual-Control:** <=900s AAL2 freshness & two distinct Server Admins | PASS | `kanban/tests/custom_fields/test_custom_field_approvals_api.py` |
| **Activity Ledger:** APPROVAL_REQUESTED, APPROVED_PRIMARY, APPROVED, APPROVAL_REVOKED | PASS | `kanban/services/activity.py` |
| **Wire Sample Capture:** RFC 7807 problem details & wire exchanges | PASS | `docs/qa/KANBA-114/contract-sample.json` |
| **Specialist Gates:** API & UI reviews | PENDING | `docs/qa/KANBA-114/api-specialist-review.md`<br>`docs/qa/KANBA-114/ui-specialist-review.md` |

---

### 2. Security Invariants Preserved
1. **Scope x Principal Escalation Matrix:** Validates all combinations per S13.2:
   - `(PROJECT, INVOKING_USER)`: Baseline passthrough, zero extra approval needed.
   - `(PROJECT, PROJECT_ADMIN_SP)`: Requires `PROJECT_ADMIN` with AAL2 and `sp_warning_acknowledged=True`.
   - `(WORKSPACE, INVOKING_USER)`: Requires `WORKSPACE_ADMIN` with AAL2.
   - `(WORKSPACE, PROJECT_ADMIN_SP)`: Requires `WORKSPACE_ADMIN` with AAL2 and `sp_warning_acknowledged=True`.
   - `(SERVER, INVOKING_USER)`: Requires dual-control `SERVER_ADMIN_DUAL` (two distinct Server Admins with AAL2).
   - `(SERVER, SERVER_ADMIN_SP)`: Requires dual-control `SERVER_ADMIN_DUAL` (two distinct Server Admins with AAL2 and `sp_warning_acknowledged=True`).
   - All invalid combinations (such as `(PROJECT, SERVER_ADMIN_SP)`) are rejected at API (422) and database CHECK constraint.
2. **Dual-Control Distinct Approvers:** When approving SERVER tier fields, primary and secondary approvers must be distinct principals (`secondary_approver_id <> primary_approver_id`). Both the service layer and database CHECK constraint enforce this strictly.
3. **AAL2 Freshness Gate:** Approvals require an active AAL2 session verified within the last 900 seconds (`aal2_verified_at >= now() - 900s`). Stale sessions or AAL1 sessions fail with `403 AAL2_REQUIRED`.
4. **Trigger-Based Tamper Auto-Revocation:** The database trigger `custom_field_manifest_tamper_revoke` executes `AFTER UPDATE OF manifest_sha256 ON custom_field_definitions`. Any change to manifest_sha256 immediately updates all active approvals (`PENDING`, `PENDING_SECOND_APPROVER`, `APPROVED`) to `REVOKED` with `revoked_reason = 'MANIFEST_SHA256_CHANGED'`.
5. **Cryptographic Signature Verification:** `assert_execution_authorized` independently recalculates HMAC-SHA256 over `(field_id, manifest_sha256, target_scope, credential_mode, primary_approver_id, secondary_approver_id)` using an HKDF-derived subkey `auth/custom_field_approvals`. If signature verification fails, execution fails closed with `tamper detected`.
6. **Timing Equalization:** All approval endpoints execute inside `timing_floor(floor_ms=25.0)` to eliminate timing side-channels.

---

### 3. Test & Verification Artifacts
- `unit-test-results.txt`: 20/20 tests passing with 96.95% branch+line coverage across target modules.
- `build-check.txt`: Ruff clean, Ruff format clean, Mypy strict clean (348 files), Lint-imports clean (2 kept, 0 broken), License gate clean (0 violations), Check-no-dashes clean (0 non-ASCII dashes).
- `schema-dump.sql`: Complete DDL, `relforcerowsecurity = t`, CHECK constraints, and trigger definition.
- `contract-sample.json`: Wire exchanges for request 201, 403 AAL2_REQUIRED, dual-control primary/secondary, 409 MANIFEST_MISMATCH, and post-edit REVOKED state.
- `git-diff.patch`: Full unified diff for KANBA-114.
