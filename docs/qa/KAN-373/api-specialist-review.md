# API & Backend Specialist Gate Review: KAN-373

## Review Overview
- **Ticket ID:** KAN-373
- **Feature Name:** Replace "WinZip" Trademark Copy with "Password-Protected ZIP (AES-256)" Across UI, API & OpenAPI Docs
- **Auditor Role:** Backend & API Architecture Specialist
- **Specification:** [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan373-2dfe0705/docs/ARCHITECTURE_AND_PRODUCT_SPEC.md) Section 1.2 (Brand & Permissive Licensing Hygiene)
- **Verdict:** APPROVED (PASS)

---

## 1. Scope of Backend & API Verification

1. **`kanban/api/v1/issue_csv.py`:**
   - Field `IssueExportRequest.format` description updated from `"Output format: csv or WinZip AES-256 zip_csv"` to `"Output format: csv or Password-protected ZIP (AES-256) zip_csv"`.
   - Route `POST /api/v1/projects/{project_ref}/issues/export`:
     - Summary: `"Export issues in project to CSV or Password-protected ZIP (AES-256)"`
     - Docstring: `"""Export project issues matching filters to CSV or Password-protected ZIP (AES-256)."""`
   - Route `POST /api/v1/workspaces/{workspace_ref}/issues/export`:
     - Summary: `"Export issues in workspace to CSV or Password-protected ZIP (AES-256)"`
     - Docstring: `"""Export workspace issues matching filters to CSV or Password-protected ZIP (AES-256)."""`
   - Route `POST /api/v1/projects/{project_ref}/issues/import`:
     - Summary: `"Import issues from CSV or Password-protected ZIP (AES-256) into project"`
     - Docstring: `"""Import issues from CSV or Password-protected ZIP (AES-256) archive into project."""`

2. **`kanban/csv/aes_zip.py` & `kanban/reports/zip_packaging.py`:**
   - Exception message in `kanban/csv/aes_zip.py:402` updated to `"Unsupported AES-256 password-protected ZIP (method 99) compression method: {extra_method}"`.
   - Exception message in `kanban/reports/zip_packaging.py:251` updated to `"Archive is not encrypted with AES-256 password-protected ZIP (method 99)."`.
   - Binary standard compatibility preserved 100%:
     - Method 99 (`COMPRESSION_METHOD_WINZIP_AES = 99`).
     - Extra field tag `0x9901` (`EXTRA_FIELD_WINZIP_AES = 0x9901`).
     - PBKDF2 key derivation, 128-bit CTR counter starting at 1, and 10-byte truncated HMAC authentication tag intact.

3. **OpenAPI Specification (`kanban/web/openapi.json`):**
   - Regenerated via `uv run python -m kanban.tools.export_openapi kanban/web/openapi.json`.
   - Zero occurrences of user-facing `"WinZip"` strings remaining in OpenAPI specifications.

4. **Automated Unit & Regression Tests:**
   - `kanban/tests/test_issue_csv_import_export.py` adds `test_openapi_and_api_zero_winzip_trademark()`.
   - `kanban/tests/test_jinja_reports.py` validates `read_aes256_zip` rejects non-AES method with `"Archive is not encrypted with AES-256 password-protected ZIP (method 99)."` and zero `"WinZip"` copy.
   - All 58 test cases pass in 16.11 seconds.

---

## 2. Security & Architectural Invariants
- **Permissive Licensing Hygiene:** Eliminates 3rd-party trademark risk from user-visible contracts without altering binary format interoperability.
- **Memory Zeroization:** Mutable cryptographic buffers continue to be actively destroyed via `zeroize(aes_key, hmac_key)` in `finally` blocks.
- **Backward Compatibility:** All existing archives and format parsers retain identical cryptographic behavior.

## 3. Certification
The API and OpenAPI changes meet all enterprise quality, legal brand hygiene, and security architecture criteria. Approved for merge.
