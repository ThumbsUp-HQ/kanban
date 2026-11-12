# Message to Reality-Checker: KANBA-54 (KB-P6-05)

## Executive Summary
This packet provides passive forensic verification evidence for Wave W09 ticket `KANBA-54` (`KB-P6-05`: `[Phase 6 / Operations] Encrypted backup/restore CLI & lossless standalone-to-production PG16 promotion`).

All deliverables and technical constraints mandated by Authoritative Specification Sections 2.2, 2.4, and 4.1 have been implemented, tested, and validated with zero regressions and zero warnings.

---

## Deliverables & Technical Architecture

### 1. Streaming Chunked AEAD Archive Format (`kanban/ops/backup_crypto.py`)
- **Binary Header (`KBBAK1\x00\x01`):** 37-byte magic and configuration header:
  - `magic`: 6 bytes (`b"KBBAK1"`)
  - `kdf_mode`: 1 byte (`0x01` = raw 256-bit key; `0x02` = Argon2id derived key)
  - `version`: 2 bytes (`0x0001`)
  - `kdf_salt`: 16 bytes CSPRNG salt
  - `base_nonce`: 12 bytes CSPRNG nonce
- **Streaming 4 MiB Chunks:** Payloads are encrypted and decrypted in 4 MiB (4,194,304-byte) frames using `AESGCM`.
- **Cryptographic Nonce & Framing:**
  - Per-chunk nonce XORs the 64-bit monotonic chunk counter into the base nonce.
  - Per-chunk AAD binds `b"KBBAK1:" + uint64_be(chunk_idx) + is_final_byte`.
  - Any chunk reordering, modification, substitution, or EOF truncation immediately raises `BackupIntegrityError` without buffering multi-GB databases in memory.
- **KDF Implementations:**
  - `RawKeySource`: 256-bit key supplied via base64url or raw 32 bytes (`KB_BACKUP_KEY`).
  - `PassphraseKeySource`: RFC 9106 Argon2id key derivation (`m=64 MiB, t=3, p=4`) using `argon2-cffi`.

### 2. Backup, Verify, and Restore Service (`kanban/ops/backup_service.py`)
- **`create_backup`:**
  - Produces deterministic tarball bundling `manifest.json`, `database.pgdump` (PostgreSQL 16 custom format), `attachments/`, and `secrets_carryover.json` (when `--include-secrets` is set).
  - Zero-shell subprocess invocation with native parameter lists.
  - Atomic write via `.tmp` file with strict `0600` file permissions and `0700` directory permissions.
- **`verify_backup`:**
  - Decrypts all frames in streaming mode verifying AES-GCM tags and `database.pgdump` SHA-256 without requiring database access.
- **`restore_backup`:**
  - Safety check: refuses to restore into a non-empty target database unless `confirm_overwrite=True` (`--confirm-overwrite`).
  - Clean target preparation: when overwrite is confirmed, resets schema cleanly to prevent PostgreSQL inherited partition constraint conflicts on `activity_records`.
  - Executes `pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error`.
  - Post-restore verification:
    1. Re-asserts role attributes (`kanban_app NOBYPASSRLS`, `app_rls_reader NOBYPASSRLS`).
    2. Validates current Alembic revision matches backup manifest.
    3. Executes `verify_activity_chain()` across every restored workspace, asserting SHA-256 hash chains are unbroken.
    4. Executes `audit_object_links()` across every restored workspace, asserting 0 newly broken links.
    5. Asserts `FORCE ROW LEVEL SECURITY` (`relrowsecurity=True` and `relforcerowsecurity=True`) across all public tenant tables.
    6. Restores `attachments/` and `secrets_carryover.json` with mode `0600`.

### 3. Standalone to Production Compose Exporter (`kanban/ops/compose_export.py`)
- Exports production bundle containing:
  - Hardened 5-network `docker-compose.yml`:
    * `edge_net`: Caddy reverse proxy to `kanban-api`
    * `app_net`: `kanban-api` to `agent-runtime`, `mcp-server`, `valkey`
    * `data_net` (`internal: true`): `kanban-api` and `postgres` only (`mcp-server` strictly isolated from `data_net`)
    * `sandbox_net` (`internal: true`): ephemeral code execution sandboxes
    * `egress_llm_net`: outbound egress to LLM endpoints
  - Caddy reverse proxy configuration (`Caddyfile`) with automatic TLS.
  - Production environment configuration (`.env.production`, mode `0600`):
    * Carries over `KB_MASTER_KEK_B64` and `KB_AUTH_PEPPER_B64` from standalone keyring.
    * Rotates `KB_SESSION_HMAC_KEY_B64` to a new distinct 32-byte CSPRNG secret (forcing clean re-authentication).
    * Generates fresh PostgreSQL credentials and Valkey ACL password.

### 4. CLI Entrypoints (`kanban/cli/ops.py` & `kanban/cli/ctl.py`)
- Subcommands registered under `kanban-ctl`:
  - `kanban-ctl backup create`
  - `kanban-ctl backup verify`
  - `kanban-ctl restore`
  - `kanban-ctl promote export-compose`
- Secret Hygiene: Rejects any literal `--key` or `--passphrase` argument on `sys.argv` with exit `2` (`SECRET_IN_ARGV_FORBIDDEN`).

### 5. Operator Runbook (`docs/PROMOTION_AND_BACKUP.md`)
- Comprehensive operator guide covering single-container standalone backup, integrity verification, test-restore validation, PG16 external promotion, and 5-network production compose deployment.
- Clean text formatting with zero unicode dash characters.

---

## Forensic Verification Ledger

| Check | Requirement | Result |
| :--- | :--- | :--- |
| **Unit Test Pass Rate** | 100% pass across all test cases | **33/33 PASSED** in 2.23s |
| **Test Coverage** | `>= 95%` branch and line coverage | **95.67% TOTAL** (`ops=100%`, `crypto=100%`, `compose=98%`, `cli=97%`, `service=93%`) |
| **Static Type Checking** | Zero type errors under `mypy --strict` | **PASSED** (0 errors in 27 source files) |
| **Linter Validation** | Zero lint violations under `ruff check` | **PASSED** (All checks passed) |
| **Architecture Boundaries** | Module layer isolation via `lint-imports` | **PASSED** (1 contract kept, 0 broken) |
| **License Compliance** | Permissive SPDX licenses only via `make license` | **PASSED** (python=94, node=1, violations=0) |
| **Unicode Dash Hygiene** | Zero `U+2014` / `U+2013` unicode dashes | **PASSED** (0 unicode dashes found) |
| **CLI & Promotion Proof** | Raw terminal output & exit codes | **PASSED** (`docs/qa/KANBA-54/cli-run.txt`) |
| **Compose Export Validation** | Docker compose config & network isolation | **PASSED** (`docs/qa/KANBA-54/compose-export-check.txt`) |
| **Dependency Evaluation** | Permissive licenses pre-approved on board | **PASSED** (`docs/qa/KANBA-54/dependency-evaluation.md`) |

---

## Handoff Protocol
As mandated by swarm protocol:
1. Worktree branch `feat/KANBA-54` is cleanly committed with zero unicode dashes.
2. `KANBA-54` remains OPEN on Kanban (builder agents must never close tickets directly).
3. Handoff notification is addressed strictly to `@builder-w00` and `@coordinator`.
