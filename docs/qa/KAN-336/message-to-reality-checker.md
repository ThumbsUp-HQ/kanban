# Message to Reality-Checker: KAN-336 (`[KB-REDTEAM-05]`)

## Ticket Scope & Browser Screenshot Classification
- **Ticket:** `KAN-336` - `[KB-REDTEAM-05] Enforce Secret Push Protection and Taint Scanning on Importer Payloads and Custom Field Ingestion`
- **Branch:** `feat/KAN-329-336`
- **Browser Screenshots:** `N/A - Non-UI Security Ticket` (Importer Sanitization, Custom Field Security, and Push Protection)
- **Owned Slice Modified:**
  - `kanban/security/push_protection.py`
  - `kanban/importer/github_importer.py`
  - `kanban/importer/jira_importer.py`
  - `kanban/importer/linear_importer.py`
  - `kanban/importer/plane_importer.py`
  - `kanban/custom_fields/executor.py`
  - `kanban/custom_fields/service.py`
  - `kanban/api/v1/custom_field_execution.py`
  - `kanban/tests/security/test_importer_push_protection.py`
  - `docs/qa/KAN-336/*`

## Requirement-to-Evidence Mapping

1. **Enforce Push Protection Across All 4 Importers:**
   - **Implementation:** Added secret push protection scanning and `provenance_tier="imported"` tagging on `Issue` and `IssueComment` in Jira, GitHub, Linear, and Plane importers.
   - **Evidence:** `docs/qa/KAN-336/git-diff.patch` and `kanban/tests/security/test_importer_push_protection.py` (Jira, GitHub, Linear, Plane tests all pass).

2. **Custom Field Execution & Definition Scanning:**
   - **Implementation:** Added `_scan_value_for_secrets` in `kanban/custom_fields/executor.py`, secret scanning on `body.name` in `upload_wasm_module`, and scanning on `body.script_source` (with wasm base64 bytecode exemption) in `test_execute_custom_field`.
   - **Evidence:** `test_custom_field_executor_blocks_secret_output`, `test_custom_field_test_execute_blocks_secret_source`, and `test_custom_field_definition_blocks_secret_in_name_and_source`.

3. **Prevent False Positives on Attachment Paths:**
   - **Implementation:** Added UUID/hex path token exemption in `kanban/security/push_protection.py`.
   - **Evidence:** All 108 existing importer tests pass in `kanban/tests/importer/`.

4. **Mandatory Quality & Code Hygiene:**
   - Zero em-dashes or en-dashes (`uv run python -m scripts.check_no_dashes --all` exits 0).
   - Full static validation passed (`make check` exits 0).

All artifacts and checksums are verified in `docs/qa/KAN-336/changed-files-manifest.txt`.
