# API & Architecture Specialist Gate Review: KAN-316

## Review Overview
- **Ticket ID:** KAN-316
- **Feature Name:** Default CSV Import, Export & "Download Template" + WinZip AES-256 Password-Protected ZIP from Search/Issue Navigator with System, Workspace & Role Governance
- **Auditor Role:** Backend & Security Architecture Specialist
- **Specification:** KB-CSV-IMPORT-EXPORT, KAN-316, KAN-72, KANBA-162
- **Verdict:** APPROVED (PASS)

---

## 1. Architectural Surface & Endpoints Audited

1. **`GET /api/v1/projects/{project_ref}/issues/import-template.csv`**
   - Returns RFC 4180 compliant UTF-8 CSV pre-populated with actual project workflow state names and project priority labels.
   - Enforces read capability on the target project (`PROJECT_VIEW`).
   - Zero hardcoded fallback assumptions; accurately mirrors active database state for the project.

2. **`GET /api/v1/workspaces/{workspace_ref}/issues/import-template.csv`**
   - Returns canonical CSV template populated with default workflow states and priorities across the workspace.

3. **`POST /api/v1/projects/{project_ref}/issues/export` and `POST /api/v1/workspaces/{workspace_ref}/issues/export`**
   - Respects active Search and Issue Navigator filter parameters (`q`, `project_id`, `state_ids`, `priorities`, `assignee_ids`, `label_ids`, `cycle_id`, `module_id`, `issue_ids`).
   - Formats: `format="csv"` (RFC 4180) and `format="zip_csv"` (WinZip AE-2 AES-256 encrypted ZIP).
   - Enforces 3-tier governance:
     - System Admin: checks `enable_issue_export` in `SystemSettings` under `Depends(require_admin_aal2)`.
     - Workspace Admin: checks `issue_export_enabled` on `WorkspaceSettings`.
     - Role/Capability: checks user membership against `issue_export_allowed_roles`.
   - Emits structured activity ledger record `ISSUE_BULK_EXPORTED` with issue count and format metadata.

4. **`POST /api/v1/projects/{project_ref}/issues/import`**
   - Accepts multipart/form-data upload using standard library `email.message_from_bytes` for zero-dependency parsing.
   - Supports plain `.csv` and password-protected WinZip AE-2 `.zip`.
   - `dry_run=True`: executes import inside an isolated transaction `SAVEPOINT` and returns `CsvImportDiffReport` (creates count, updates count, error count, row-level items, and validation errors). Rollback ensures zero side effects.
   - `dry_run=False`: atomically commits all valid creates and updates. If any row has a fatal validation error, transaction rolls back cleanly.
   - Emits structured activity ledger record `ISSUE_BULK_IMPORTED`.

5. **`GET/PATCH /api/v1/admin/system-settings`**
   - Enforces `Depends(require_admin_aal2)` and `require_server_admin`.
   - Governs `enable_issue_export` and `enable_issue_import`.

---

## 2. Security Invariants Verification

### A. WinZip AE-2 (AES-256) Cryptographic Engine (`kanban/csv/aes_zip.py`)
- **Key Derivation:** PBKDF2-HMAC-SHA256 (1000 iterations, 16-byte random salt, 66 bytes derived: 32-byte AES key, 32-byte HMAC key, 2-byte password verification code). Fallback PBKDF2-HMAC-SHA1 supported for archive extraction compatibility.
- **Payload Encryption:** AES-256 in CTR mode with little-endian 128-bit block counter starting at 1 per WinZip AE-2 specification.
- **Authentication:** 10-byte truncated HMAC-SHA256 authentication tag appended after ciphertext.
- **Extra Field:** `0x9901` WinZip AES extra field header accurately packaged in local header and central directory records.
- **Memory Zeroization:** Mutable `bytearray` key buffers zeroed via `zeroize(aes_key, hmac_key)` inside mandatory `finally` blocks on all paths. Read-only buffers handled cleanly without uncaught exceptions.
- **Password Policy:** Minimum 12 characters strictly enforced on export (`PasswordTooShortError`).
- **Archive Safety Guards:** Path traversal detection (`..`, absolute paths, leading slashes), zip-bomb limits (`MAX_UNCOMPRESSED_SIZE` 50 MiB and `MAX_COMPRESSION_RATIO` 100.0), and corrupt header bounds checking.

### B. CWE-1236 Formula Injection Defense (`kanban/csv/issue_csv.py`)
- Any cell value beginning with dangerous spreadsheet formula triggers (`=`, `+`, `-`, `@`, `\t`, `\r`) is neutralized on export by prepending a single quote (`'`).
- On import, `desanitize_cell_from_import` restores the original text by stripping the defense prefix.

### C. Hostile Input Sanitization & Secret Protection
- UTF-16 lone surrogate rejection: `validate_no_surrogates()` scans all text columns, rejecting codepoints in `0xD800` through `0xDFFF`.
- Secret push protection: `enforce_secret_push_protection(..., mode=PushProtectionMode.BLOCK)` blocks imported rows containing leaked API keys, tokens, or private credentials before database persistence.

### D. Concurrency & Concurrency ETag Verification
- Updates by issue key utilize `description_sha256.hex()` as `if_match` precondition to guarantee optimistic concurrency control and eliminate lost updates.

---

## 3. Test Coverage & Verification Evidence

- Backend Unit Test Suite: `kanban/tests/test_issue_csv_import_export.py` (30 tests, 100% passed in 8.12s).
- Database Migration Test: `database/tests/migrations/test_p6_13_csv_import_export_governance_migration.py` (passed in 0.71s).
- Alembic Migration Check: `uv run kanban-ctl db check-migrations` verified single head `p6_13_csv_import_export_governance`.
- Line & Branch Coverage (`kanban/csv/*`):
  - `kanban/csv/__init__.py`: 100%
  - `kanban/csv/issue_csv.py`: 99%
  - `kanban/csv/aes_zip.py`: 96%
  - Total Module Coverage: 98% (exceeds 95% project threshold).

---

## 4. Certification
The API, database schema, and cryptographic implementations for KAN-316 satisfy all security invariants, zero-guesswork standards, and Definition of Done criteria. Approved for production merge.
