# Forensic Verification Proof Packet: KAN-316

## Audited Branch & Visual Proof Summary
- **Branch:** `feat/KAN-316`
- **Ticket ID:** KAN-316
- **Feature Summary:** `[KB-CSV-IMPORT-EXPORT] Default CSV Import, Export & "Download Template" + WinZip AES-256 Password-Protected ZIP from Search/Issue Navigator with System, Workspace & Role Governance`
- **Visual Proof Artifacts (`docs/qa/KAN-316/screenshots/`):**
  - `01-desktop-light-export-modal.png`: 1440x900 Light theme, showing Export Tab, format radio cards with WinZip AES-256 ZIP selected, live password policy indicator (green check for >= 12 chars), filter count banner, and clean design system tokens.
  - `02-desktop-dark-import-preview.png`: 1440x900 Dark theme, showing Import Tab, Download Template button, uploaded file card, Dry-Run preview stats (12 to Create, 3 to Update, 0 Errors), and scrollable diff table with CREATE/UPDATE badges.
  - `03-tablet-csv-modal.png`: 768x1024 Tablet viewport, responsive centered modal with comfortable touch targets.
  - `04-mobile-portrait-csv-modal.png`: 390x844 Mobile portrait viewport, responsive single-column layout, unclipped action buttons.
  - `05-mobile-landscape-csv-modal.png`: 844x390 Mobile landscape viewport, scrollable modal body with fixed header/footer.

---

## Scoped Definition of Done Mapping

### 1. 3-Tier Governance & Schema Migration (`p6_13_csv_import_export_governance`)
- **System Admin Tier:** Controlled by `enable_issue_export` and `enable_issue_import` on `kanban/settings.py` and exposed via `GET/PATCH /api/v1/admin/system-settings` under `Depends(require_admin_aal2)` and `require_server_admin`. When disabled at system level, requests return `403 EXPORT_DISABLED_BY_SYSTEM_ADMIN` or `403 IMPORT_DISABLED_BY_SYSTEM_ADMIN`.
- **Workspace Admin & Role Tier:** Mapped columns `issue_export_enabled` (boolean, default True), `issue_import_enabled` (boolean, default True), and `issue_export_allowed_roles` (text[], default `['workspace_admin', 'project_admin', 'member']`) added to `database/models/workspace_settings.py` via forward migration `database/migrations/versions/p6_13_csv_import_export_governance.py` and reversible SQL scripts (`up.sql`/`down.sql`).
- **Proof:** `database/tests/migrations/test_p6_13_csv_import_export_governance_migration.py` passed in 0.71s; `uv run kanban-ctl db check-migrations` confirmed 72 valid migrations with single head `p6_13_csv_import_export_governance`.

### 2. Canonical RFC 4180 CSV Schema, CWE-1236 Defense & Download Template
- **16 Canonical Columns:** `key`, `project_key`, `summary`, `description_markdown`, `state`, `priority`, `assignees`, `labels`, `cycle`, `modules`, `parent_key`, `start_date`, `due_date`, `created_at`, `updated_at`, `custom_fields_json`.
- **CWE-1236 Defense:** Formula triggers (`=`, `+`, `-`, `@`, `\t`, `\r`) neutralized on export by prepending single-quote (`'`). Stripped upon import via `desanitize_cell_from_import`.
- **Download Template Endpoints:** `GET /api/v1/projects/{project_ref}/issues/import-template.csv` and `GET /api/v1/workspaces/{workspace_ref}/issues/import-template.csv` return CSV pre-populated with actual project workflow states and priorities.
- **Input Sanitization:** UTF-16 lone surrogate rejection via `validate_no_surrogates()` and secret push-protection enforcement via `enforce_secret_push_protection(..., mode=PushProtectionMode.BLOCK)` on import.
- **Proof:** `kanban/tests/test_issue_csv_import_export.py` tests `test_cwe_1236_formula_injection_defense`, `test_utf16_lone_surrogate_rejection`, `test_generate_issue_import_template`, and `test_api_import_secret_detection`.

### 3. WinZip AE-2 (AES-256) Password-Protected ZIP Packaging (`kanban/csv/aes_zip.py`)
- **Standards Compliance:** Full WinZip AE-2 implementation using standard library `zlib`, `struct`, `hmac` and existing `cryptography` (PBKDF2-HMAC-SHA256 1000 iter, 66 bytes derived key material, AES-256-CTR, 10-byte HMAC-SHA256 auth tag, extra field `0x9901`).
- **Memory Zeroization:** Mutable key buffers zeroed out using `zeroize(aes_key, hmac_key)` in mandatory `finally` blocks. Read-only buffers handled without uncaught exceptions.
- **Password Policy:** Minimum 12 characters enforced on export (`PasswordTooShortError`).
- **Safety Guards:** Path traversal protection (`PathTraversalError`), Zip-bomb ratio/size limits (`ZipBombError`), and corrupt archive validation (`CorruptZipError`).
- **Proof:** `kanban/tests/test_issue_csv_import_export.py` tests covering encryption/decryption roundtrips, invalid password, missing password, tampered ciphertext, traversal, zipbomb, zeroize, corrupt headers, and unencrypted extraction.

### 4. Export & Import Endpoints with Dry-Run Savepoint & Concurrency Control
- **Export Endpoints:** `POST /api/v1/projects/{project_ref}/issues/export` and `POST /api/v1/workspaces/{workspace_ref}/issues/export` filter issues via active Navigator parameters, format as plain CSV or encrypted ZIP, and emit `ISSUE_BULK_EXPORTED` activity records.
- **Import Endpoint:** `POST /api/v1/projects/{project_ref}/issues/import` accepts multipart/form-data via standard library email parser (zero external dependencies).
- **Atomic Savepoint Isolation:** `dry_run=True` validates all rows inside a transaction `SAVEPOINT` and rolls back, returning `CsvImportDiffReport` preview. `dry_run=False` commits valid rows atomically or rolls back on errors.
- **Concurrency Control:** Issue updates verify `description_sha256.hex()` as `if_match` precondition to prevent lost updates.
- **Proof:** `kanban/tests/test_issue_csv_import_export.py` tests `test_api_export_csv_and_zip`, `test_api_import_csv_dry_run_and_commit`, `test_api_import_winzip_aes256_encrypted_zip`, `test_api_import_update_existing_and_validation_errors`, and `test_api_import_with_labels_and_modules`.

### 5. Frontend UI Implementation
- **Modal Dialog:** `kanban/web/src/features/views/CsvImportExportModal.tsx` and `.css` implementing Export and Import tabs, format selection, >= 12 character password policy indicator, dropzone, dry-run diff preview table, and atomic commit confirmation.
- **Navigator Integration:** `IssueNavigatorBar.tsx` renders Export and Import trigger buttons (`navigator-export-btn`, `navigator-import-btn`). `FilterDisplayBar.tsx` exposes triggers in Display popover.
- **Workspace Settings:** `WorkspaceSettingsPage.tsx` provides workspace admins with export/import toggles and allowed export roles multi-select.
- **Zero Inline Styles:** All CSS authored in external stylesheets with design system CSS tokens.
- **Proof:** `kanban/web/src/features/views/__tests__/CsvImportExportModal.test.tsx` (7 passed); `IssueNavigatorBar.test.tsx` and `viewRegistry.test.tsx` (67 passed).

---

## Coverage & Quality Summary
- **Backend Coverage (`kanban/csv/*`):** 98% overall (408 of 412 statements, 122 of 130 branches).
  - `kanban/csv/__init__.py`: 100%
  - `kanban/csv/aes_zip.py`: 96%
  - `kanban/csv/issue_csv.py`: 99%
- **Backend Tests:** 30 passed in 8.12s (`kanban/tests/test_issue_csv_import_export.py`).
- **Frontend Tests:** 74 passed across 3 test files in 9.15s (`vitest`).
- **Typecheck & Build:** `tsc -b --noEmit` and `vite build` completed with 0 errors.
- **Alembic Single Head:** Single head `p6_13_csv_import_export_governance` verified.
- **Zero Dashes Standard:** `uv run python -m scripts.check_no_dashes --all` passed with 0 errors.
