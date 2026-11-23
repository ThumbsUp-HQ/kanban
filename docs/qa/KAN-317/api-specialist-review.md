# API Specialist Review (KAN-317 / KB-JINJA-REPORTS)

## Overview & Architecture Verification

- **Ticket**: KAN-317 (`[EPIC][KB-JINJA-REPORTS] Sandboxed Jinja2 Report Templates & Multi-Format Export Engine with Search Screen Integration & 3-Tier Governance`)
- **Module**: `kanban.reports`, `kanban.api.v1.reports`, `database.models.report_template`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The report template and export engine introduces a secure, high-performance report generation subsystem adhering strictly to Priority #0 Security-First and Priority #1 Agent-First architecture.

### 1. Hardened SSTI Sandboxing (`kanban/reports/sandbox.py`)
- **SandboxedEnvironment Hardening**: `HardenedSandboxedEnvironment` intercepts both attribute and item access via `getattr` and `getitem`, blocking all private attributes (`_`), and forbidding introspection gadgets: `mro`, `subclasses`, `globals`, `builtins`, `gi_`, `cr_`, `ag_`, `f_`, `format`, `format_map`.
- **Callable Guard**: `is_safe_callable` and `is_safe_attribute` reject any Python class/type objects, functions, methods, and modules.
- **Data Boundary**: Only frozen, plain-data dataclasses (`ReportContext`, `ReportIssueRow`, `ReportStats`) are exposed into template execution context.
- **Resource Limits**: Strict 128 KiB template size cap, 5,000 issue limit, 10 MiB output size cap, and bounded execution timeout (3.0s ceiling) running in an isolated thread worker.

### 2. Multi-Format Renderers & Formula Injection Defense (`kanban/reports/renderers.py`)
- **Zero-Copyleft Compliance**: Implements native pure-Python OOXML (`.xlsx`, `.docx`), ODF (`.odt`), and PDF (`.pdf`) builders using existing installed permissive dependencies (`jinja2`, `markdown-it-py`, `nh3`, `defusedxml`, `cryptography`, `zlib`, `zipfile`). Zero copyleft (`GPL`, `LGPL`, `AGPL`, `SSPL`) packages added.
- **CWE-1236 Neutralization**: `neutralize_formula` automatically escapes dangerous leading spreadsheet characters (`=`, `+`, `-`, `@`, `\t`, `\r`) with a single apostrophe (`'`) across CSV and XLSX cell generations.
- **HTML Sanitization**: HTML output is cleaned via `nh3.clean` with strict tag allowlist, safe URI protocols (`https`, `http`, `mailto`), and `noopener noreferrer` link attributes.
- **PDF Security Invariant (KAN-81)**: Generated PDF binary streams pass `kanban.attachments.pdf:sanitize_and_validate_pdf` validation with zero errors.
- **XML Parsing Safety**: All OOXML and ODF XML payloads parse through `defusedxml.ElementTree` preventing entity expansion (Billion Laughs) and external entity retrieval (XXE).

### 3. Password-Protected AES-256 ZIP Packaging (`kanban/reports/zip_packaging.py`)
- **WinZip AE-2 Specification**: Implements standard WinZip AE-2 AES-256 encrypted zip archives using PBKDF2-HMAC-SHA1 key derivation (1000 iterations), AES-256-CTR payload encryption, HMAC-SHA1-10 authentication code, and extra field ID `0x9901`.
- **Cryptographic Verification**: Validates password check bytes and full HMAC authentication codes on decryption, rejecting truncated, tampered, or corrupted headers.

### 4. REST API & 3-Tier Governance (`kanban/api/v1/reports.py`)
- **CRUD Operations**: Complete template management endpoints (`GET`, `POST`, `PATCH`, `DELETE` on `/api/v1/workspaces/{workspace_ref}/report-templates`) supporting built-in and workspace-custom templates.
- **Live Sandboxed Preview**: `POST /api/v1/workspaces/{workspace_ref}/reports/preview` returns rendered template output for instant UI feedback.
- **Document Generation**: `POST /api/v1/workspaces/{workspace_ref}/reports/generate` and `/projects/{project_ref}/reports/generate` export binary streams with correct `Content-Type` and `Content-Disposition: attachment; filename="..."` headers.
- **3-Tier Governance**:
  - System setting: `enable_report_templates` in `kanban/settings.py` (HTTP 403 `REPORT_TEMPLATES_DISABLED_SYSTEM` when false).
  - Workspace setting: `report_export_enabled` in `WorkspaceSettings` (HTTP 403 `REPORT_EXPORT_DISABLED_WORKSPACE` when false).
  - Role permissions: `report_export_allowed_roles` in `WorkspaceSettings` (HTTP 403 `INSUFFICIENT_WORKSPACE_PERMISSIONS` if caller role not allowed).
- **Security Context**: Integrates `FORCE RLS` session scoping, `CredentialBoundary`, `TaintRecorder`, and immutable audit ledger via `record_activity`.

### 5. Specialist Verdict
The API endpoints, sandboxed Jinja2 evaluation engine, and multi-format renderers meet all security and architectural requirements.
**STATUS: APPROVED**
