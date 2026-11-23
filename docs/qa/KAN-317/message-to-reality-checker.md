# Message to Reality-Checker: Forensic QA Gate Verification (KAN-317)

## Executive Summary
This packet provides passive forensic verification evidence for Epic `KAN-317` (`[EPIC][KB-JINJA-REPORTS] Sandboxed Jinja2 Report Templates & Multi-Format Export Engine (PDF, XLSX, CSV, DOCX, ODT, HTML, MD) with Search Screen Integration & 3-Tier Governance`).

- **Target Ticket**: `KAN-317`
- **Branch**: `feat/KAN-317`
- **Spawned Child Tickets on Project KAN**:
  1. `KAN-330`: `[KB-JINJA-REPORTS-SANDBOX] Hardened SSTI SandboxedEnvironment & Multi-Format Export Engine`
  2. `KAN-331`: `[KB-JINJA-REPORTS-SCHEMA-API] Report Templates Table Migration, RLS Policies, REST API & 3-Tier Governance`
  3. `KAN-332`: `[KB-JINJA-REPORTS-UI] ReportExportModal & ReportTemplateStudioModal Search Screen Integration`
- **Review Status**: Complete Forensic Verification Packet Ready for QA Audit

---

## Architecture & Implementation Overview

1. **Database Schema & Migrations (`database/models/report_template.py`, migration `p6_14_jinja_report_templates`)**:
   - Table `report_templates` with `ENABLE/FORCE ROW LEVEL SECURITY`, tenant isolation via `app_current_workspace_id()`, check constraints, and workspace seeds.
   - 3-Tier Governance fields: `enable_report_templates` in `kanban/settings.py` (system), `report_export_enabled` and `report_export_allowed_roles` in `WorkspaceSettings` (workspace/role).
   - 3 Built-in seeded templates: Security Assessment Report, Sprint & Release Notes Report, Executive Status & Risk Report.

2. **Hardened SSTI Sandbox (`kanban/reports/sandbox.py`)**:
   - `HardenedSandboxedEnvironment` intercepting `getattr` and `getitem`, blocking all private attributes (`_`) and forbidden introspection targets (`mro`, `subclasses`, `globals`, `builtins`, `gi_`, `cr_`, `ag_`, `f_`, `format`, `format_map`).
   - Caps: 128 KiB template size ceiling, 5,000 issue limit, 10 MiB output ceiling, 3.0s timeout.

3. **Multi-Format Export Engine (`kanban/reports/renderers.py`)**:
   - Pure Python builders for all 7 formats (MD, HTML, CSV, XLSX, DOCX, ODT, PDF) using zero copyleft dependencies.
   - Mandatory KAN-81 PDF validation: Generated PDFs pass `sanitize_and_validate_pdf` cleanly.
   - CWE-1236 defense: Neutralizes spreadsheet formula injection (`=`, `+`, `-`, `@`, `\t`, `\r`) with apostrophes.
   - HTML sanitization via `nh3.clean` with strict tag and protocol allowlists.
   - OOXML & ODF XML validated with `defusedxml.ElementTree`.

4. **WinZip AE-2 AES-256 ZIP Packaging (`kanban/reports/zip_packaging.py`)**:
   - Implements WinZip AE-2 specification with PBKDF2-HMAC-SHA1 key derivation, AES-256-CTR encryption, and HMAC-SHA1-10 authentication codes.

5. **REST API (`kanban/api/v1/reports.py`) & UI Integration**:
   - CRUD endpoints on `/api/v1/workspaces/{workspace_ref}/report-templates`.
   - Live preview on `/api/v1/workspaces/{workspace_ref}/reports/preview`.
   - Export generation on `/api/v1/workspaces/{workspace_ref}/reports/generate` and `/projects/{project_ref}/reports/generate`.
   - Frontend modals `ReportExportModal.tsx` and `ReportTemplateStudioModal.tsx` integrated into `IssueNavigatorBar.tsx`.

---

## Forensic Proof Artifacts Index

- `git-diff.patch`: Patch file capturing all repository diffs against upstream base.
- `build-check.txt`: Full output of ruff, mypy, migrations check, tsc, check_no_dashes, SBOM test, and Vitest.
- `pytest-jinja-reports.txt`: Verbose pytest output with 97% branch coverage across `kanban/reports`.
- `unit-test-results.txt`: Combined backend pytest (27 passed) and frontend Vitest (7 passed) test results.
- `sample-exports/`: Real generated Security Assessment Reports in all 7 formats:
  - `security-assessment-report.pdf`
  - `security-assessment-report.xlsx`
  - `security-assessment-report.csv`
  - `security-assessment-report.docx`
  - `security-assessment-report.odt`
  - `security-assessment-report.html`
  - `security-assessment-report.md`
- `screenshots/`: 5 responsive Playwright screenshots across viewports:
  - `01-desktop-light-report-export.png` / `1440x900-desktop-light.png`
  - `02-desktop-dark-report-export.png` / `1440x900-desktop-dark.png`
  - `03-tablet-report-export.png` / `768x1024-tablet.png`
  - `04-mobile-portrait-report-export.png` / `390x844-mobile-portrait.png`
  - `05-mobile-landscape-report-export.png` / `844x390-mobile-landscape.png`
- `api-specialist-review.md`: Signed review from API Specialist (`@api-spec`, STATUS: APPROVED).
- `ui-specialist-review.md`: Signed review from UI Specialist (`@ui-spec`, STATUS: APPROVED).
- `changed-files-manifest.txt`: Cryptographic SHA-256 manifest of all files in `docs/qa/KAN-317/`.
