# Reality-Checker Verification Dossier: KAN-73

## Ticket Metadata
- Ticket ID: KAN-73
- Component: Security / Audit Ledger / Crypto-Shredding
- Title: [KB-SEC-SHRED-01] Add Envelope-Encrypted activity_records Payloads & AAL2 Two-Stage Crypto-Shredding Without Chain Breakage
- Branch: feat/KAN-73-crypto-shred-activity

## Summary of Completed Work

This change implements envelope encryption on activity records payloads and AAL2 two-stage crypto-shredding without breaking activity hash chain continuity.

### Problem 1: Schema & Hash-Chaining Invariant
1. Added `encryption_ver SMALLINT NOT NULL DEFAULT 0`, `payload_ciphertext BYTEA NULL`, `payload_nonce BYTEA NULL`, and `payload_aad_sha256 BYTEA NULL` to `activity_records`.
2. Created `activity_record_keys` table with primary key `(workspace_id, activity_id)` storing `wrapped_dek`, `dek_nonce`, and `dek_kid` alongside `shredded_at`, `shredded_by_id`, and `shred_reason`.
3. Enforced `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on `activity_record_keys` with workspace isolation policies.
4. Updated Postgres procedures `compute_activity_row_hash()` and `verify_activity_chain()`:
   - Rows with `encryption_ver = 0` hash legacy payload identically.
   - Rows with `encryption_ver = 1` hash `p_prev_hash || metadata || encode(digest(p_payload_ciphertext || p_payload_nonce || p_payload_aad_sha256, 'sha256'), 'hex')`.
   - Shredding `wrapped_dek` and `dek_nonce` in `activity_record_keys` destroys data decryption capability while leaving the hash chain 100% intact and valid.

### Problem 2: Sealing & Activity Feed Unwrapping
1. Created `kanban/services/crypto_shred.py` providing `seal_activity_payload()` and `unwrap_activity_payload()`.
2. Updated `record_activity()` (`kanban/services/activity.py`) to seal sensitive delta payloads, persisting the wrapped DEK in `activity_record_keys` in the same transaction.
3. Updated `kanban/services/activity_feed.py` to batch unwrap non-shredded records on read and emit a `{"redacted": true, "reason": "CRYPTO_SHREDDED", "shredded_at": ...}` tombstone whenever `wrapped_dek IS NULL`.

### Problems 3 & 4: Two-Stage Shredding & Permanent Purge Integration
1. Implemented administrative endpoints in `kanban/api/v1/admin/audit_shred.py` guarded by `Depends(require_admin_aal2)`:
   - `POST /api/v1/admin/audit-ledger/request-shred`: computes blast radius, returns single-use 5-minute confirmation token and confirmation phrase.
   - `POST /api/v1/admin/audit-ledger/execute-shred`: single-use token consumption (fail-closed), overwriting `wrapped_dek = NULL`, `dek_nonce = NULL`, setting `shredded_at = now()`, and recording an immutable `CRYPTO_SHRED_EXECUTED` event.
2. Hooked `permanent_purge` in `kanban/services/destructive_lifecycle.py` to automatically cascade crypto-shredding across all `activity_record_keys` tied to purged object IDs.

## Verification Proof Artifacts

The following proof files are located in `docs/qa/KAN-73/`:
1. `git-diff.patch`: Complete git diff of all changes against latest `main`.
2. `unit-test-results.txt`: Verbatim Pytest execution log (20 passed in 7.02s).
3. `build-check.txt`: Verbatim `make check` log demonstrating passing Ruff, format, Mypy, lint-imports, no-dashes, and single-head Alembic check.
4. `contract-sample.json`: Representative lifecycle snapshot showing sealed row, active key, Stage 1 token request, Stage 2 execution, shredded key state, activity feed tombstone, and hash chain verification before and after crypto-shredding.

## Verification Checklist
- [x] Zero warnings, strict typing (mypy checked 1236 files with 0 errors).
- [x] Zero dashes rule satisfied (checked via `python -m scripts.check_no_dashes --all`).
- [x] 100% of required unit tests passing locally in hermetic DB transactions.
- [x] Hash chain continuity verified before and after key shredding (`verify_activity_chain() -> is_valid: true`).
- [x] Tamper detection verified (`ROW_HASH_MISMATCH` triggered on modified ciphertext or nonce).
- [x] All admin routes guarded by `Depends(require_admin_aal2)`.
