# API Specialist Forensic QA Review: KAN-336

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KAN-336 ([KB-REDTEAM-05] Enforce Secret Push Protection and Taint Scanning on Importer Payloads and Custom Field Ingestion)
Branch: feat/KAN-329-336
Review Date: 2026-11-23

## 1. Architectural and Security Assessment

### 1.1 Threat Model & Supply Chain Ingestion Vulnerabilities
External integrations and user-defined scripts present substantial supply chain and data leakage risks:
- Importers (Jira, GitHub, Linear, Plane) accept payloads from external sources that may contain leaked credentials (AWS access keys, GitHub tokens, Slack webhooks, PEM private keys, high-entropy API tokens).
- Custom field script execution (Wasm and QuickJS sandboxes) could emit secret tokens into custom field outputs.
- Custom field definition and test execution endpoints could accept malicious or contaminated source payloads containing embedded secrets.

### 1.2 Remediations Implemented
1. Secret Push Protection on All 4 Importers:
   - `kanban/importer/jira_importer.py`: Scans issue summary, description, and comment bodies. Sets `provenance_tier="imported"` on `Issue` and `IssueComment`.
   - `kanban/importer/github_importer.py`: Scans issue title, body, and comment bodies. Sets `provenance_tier="imported"`.
   - `kanban/importer/linear_importer.py`: Scans issue title, description, and comment bodies. Sets `provenance_tier="imported"`.
   - `kanban/importer/plane_importer.py`: Scans issue name, description, and comment bodies. Sets `provenance_tier="imported"`.
   - Any secret detected in an incoming payload triggers `ProblemException(code="SECRET_PUSH_PROTECTED", status=422)` or blocks the import item, preventing secret propagation into the database ledger.
2. Custom Field Execution Output Scanning (`kanban/custom_fields/executor.py`):
   - In `execute_for_issue` and `test_execute`, all computed return values are recursively inspected via `_scan_value_for_secrets(val, location)`.
   - If a script attempts to output a secret token or high-entropy key, execution fails with `SECRET_PUSH_PROTECTED`.
3. Custom Field Definition & Test Endpoints:
   - In `kanban/api/v1/custom_field_execution.py` and `kanban/custom_fields/service.py`, `upload_wasm_module` scans `body.name` for secrets.
   - `test_execute_custom_field` scans `body.name` and scans `body.script_source` (exempting compiled base64 wasm bytecode payloads starting with `AGFzbQ`).
4. Push Protection False-Positive Reduction (`kanban/security/push_protection.py`):
   - Added path-based token exemption in `is_exempt_token` to ensure valid attachment and media URLs (such as `![proof](/api/v1/attachments/<UUID>)`) containing UUIDs or hex digests are not falsely rejected as high-entropy secrets.

---

## 2. Requirement-to-Evidence Verification Matrix

| Requirement | Implementation Artifacts | Verification Tests | Verdict |
| :--- | :--- | :--- | :--- |
| **Jira Importer Push Protection** | `kanban/importer/jira_importer.py` | `kanban/tests/security/test_importer_push_protection.py::test_jira_importer_blocks_secret_in_description`, `test_jira_importer_blocks_secret_in_comments` | PASS |
| **GitHub Importer Push Protection** | `kanban/importer/github_importer.py` | `kanban/tests/security/test_importer_push_protection.py::test_github_importer_blocks_secret_in_body` | PASS |
| **Linear Importer Push Protection** | `kanban/importer/linear_importer.py` | `kanban/tests/security/test_importer_push_protection.py::test_linear_importer_blocks_secret_in_description` | PASS |
| **Plane Importer Push Protection** | `kanban/importer/plane_importer.py` | `kanban/tests/security/test_importer_push_protection.py::test_plane_importer_blocks_secret_in_description` | PASS |
| **Custom Field Execution Push Protection** | `kanban/custom_fields/executor.py` | `kanban/tests/security/test_importer_push_protection.py::test_custom_field_executor_blocks_secret_output` | PASS |
| **Custom Field Test Execute Script Scan** | `kanban/api/v1/custom_field_execution.py` | `kanban/tests/security/test_importer_push_protection.py::test_custom_field_test_execute_blocks_secret_source` | PASS |
| **Custom Field Definition Name Scan** | `kanban/custom_fields/service.py` | `kanban/tests/security/test_importer_push_protection.py::test_custom_field_definition_blocks_secret_in_name_and_source` | PASS |
| **Full Importer Regression Suite** | All 4 importers | 108/108 regression tests pass in `kanban/tests/importer/` | PASS |
| **Zero Em/En-Dashes Rule** | All touched files use plain ASCII hyphens | `uv run python -m scripts.check_no_dashes --all` exits 0 | PASS |

---

## 3. Specialist Verdict

Secret push protection and taint scanning are comprehensively implemented across all external data ingestion surfaces and custom field runtime environments.

STATUS: APPROVED
