# API and Security Specialist Review: KAN-73

- **Ticket:** KAN-73 ([KB-SEC-SHRED-01]) - Add Envelope-Encrypted activity_records Payloads & AAL2 Two-Stage Crypto-Shredding Without Chain Breakage
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-73-crypto-shred-activity`
- **Commit Under Audit:** `24fb0e07ad1bd912a7d9fc9fe0c7e10eadfdee3e (24fb0e07)` (`feat(security): implement envelope-encrypted activity records & AAL2 crypto-shredding (KAN-73)`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan73-ff2d6362`
- **Status:** APPROVED

---

## 1. Executive Cryptographic & Security Architecture Evaluation

Ticket KAN-73 implements envelope encryption for sensitive activity record delta payloads and establishes an AAL2 two-stage cryptographic shredding framework while guaranteeing immutable SHA-256 hash-chain continuity.

Key cryptographic and architectural invariants audited:
1. **Schema & Hash-Chain Continuity Invariant (Alembic `p6_06`):**
   - Chains linearly onto `p6_05_issue_leases_and_fencing` with clean `.down.sql` rollback.
   - Preserves strict immutability on `activity_records` via `activity_records_immutable_bud_trg`.
   - Adds `encryption_ver SMALLINT NOT NULL DEFAULT 0`, `payload_ciphertext BYTEA NULL`, `payload_nonce BYTEA NULL`, and `payload_aad_sha256 BYTEA NULL` to `activity_records`.
   - Creates `activity_record_keys` with primary key `(workspace_id, activity_id)` storing `wrapped_dek`, `dek_nonce`, and `dek_kid`, governed by `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
   - Updated Postgres procedures `compute_activity_row_hash()` and `verify_activity_chain()`:
     - `encryption_ver = 0`: preserves identical hashing for legacy plaintext payloads.
     - `encryption_ver = 1`: hashes the encrypted tuple: `p_prev_hash || metadata || encode(digest(p_payload_ciphertext || p_payload_nonce || p_payload_aad_sha256, 'sha256'), 'hex')`.
     - Overwriting `wrapped_dek = NULL` and `dek_nonce = NULL` permanently eliminates decryption keys while leaving the immutable row hash and chain verification 100% valid.
2. **Payload Sealing and Activity Feed Decryption (`kanban/services/crypto_shred.py`):**
   - `seal_activity_payload()` and `unwrap_activity_payload()` use authenticated envelope encryption.
   - `record_activity()` persists sealed payloads and inserts the wrapped DEK into `activity_record_keys` in the same database transaction.
   - `kanban/services/activity_feed.py` batch unwrap keys on read, returning `{"redacted": true, "reason": "CRYPTO_SHREDDED", "shredded_at": ...}` tombstones whenever the DEK is destroyed.
3. **AAL2 Two-Stage Administration & Permanent Purge Integration:**
   - Routes in `kanban/api/v1/admin/audit_shred.py` are strictly protected with `Depends(require_admin_aal2)`.
   - Stage 1 (`POST /api/v1/admin/audit-ledger/request-shred`) calculates the blast radius and returns a single-use 5-minute confirmation token and explicit confirmation phrase.
   - Stage 2 (`POST /api/v1/admin/audit-ledger/execute-shred`) validates phrase and token, consumes the token fail-closed, nullifies key material in `activity_record_keys`, and records an immutable `CRYPTO_SHRED_EXECUTED` activity event.
   - `permanent_purge` in `kanban/services/destructive_lifecycle.py` automatically triggers crypto-shredding for all activity records linked to purged objects.

---

## 2. Wire Contracts & Security Invariants

### A. Admin Endpoints Wire Contracts
- `POST /api/v1/admin/audit-ledger/request-shred`: Returns `200 OK` with `stage: "confirmation_required"`, blast hash, single-use token, and confirm phrase.
- `POST /api/v1/admin/audit-ledger/execute-shred`: Returns `200 OK` with `status: "shredded"`, count, and shred audit record ID.
- Missing AAL2 credentials or invalid session tokens trigger standard HTTP 401/403 ProblemDetails responses.

### B. Hash-Chain Tamper Detection
- Tampering with `payload_ciphertext`, `payload_nonce`, or `payload_aad_sha256` is forensically detected by `verify_activity_chain()`, returning `is_valid: false` with `failure_reason: "ROW_HASH_MISMATCH"`.

---

## 3. Unit Test Coverage & Verification Metrics

- **Backend Pytest Results:** 20 passed in 7.02s (`database/tests/test_crypto_shred_activity_chain.py`, `kanban/tests/security/test_audit_crypto_shred.py`, `kanban/tests/security/test_admin_routes_protected.py`, `database/tests/test_p1_17_models.py`, `kanban/tests/api/test_activity_feed.py`).
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2228 files formatted.
  - `mypy`: 0 issues found in 1236 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.
  - `check-migrations`: Valid single head `p6_06_crypto_shredded_activity_ledger` (68 valid migrations).
  - `check_no_dashes`: Clean across repository (0 violations).

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
