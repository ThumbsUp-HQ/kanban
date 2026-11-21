# Message to Reality-Checker: Forensic QA Gate Verification (KAN-77)

## Executive Summary
This packet provides passive forensic verification evidence for ticket `KAN-77` (`[KB-IMPORT-MULTI-01]`): Multi-Source Importers (Jira, GitHub Issues, Linear), Portable Bundle Export Determinism, and Legacy Key Alias Routing (`IssueKeyAlias`).

## Definition of Done Verification Checklist
1. [x] **Database Migration & Models**: Single head migration `p6_03_multi_source_imports_and_aliases` (`down_revision = "p6_02_pdf_attachments"`) introduces `issue_key_aliases` table with RLS policies, indexing, and foreign key constraints. `database/models/issue_alias.py` (`IssueKeyAlias`) and `database/models/__init__.py` maintain exact schema parity.
2. [x] **Multi-Source Importers**:
   - `kanban/importer/jira_importer.py`: Imports Jira JSON and CSV exports, records original issue keys (e.g., `JIRA-101`) in `issue_key_aliases`, maps priority and state taxonomy, and extracts attachments.
   - `kanban/importer/github_importer.py`: Imports GitHub Issues JSON/REST payloads, records legacy issue keys (e.g., `GH-88`) in `issue_key_aliases`, preserves author attribution, and normalizes labels.
   - `kanban/importer/linear_importer.py`: Imports Linear workspace exports, records legacy identifiers (e.g., `ENG-42`) in `issue_key_aliases`, preserves cycle assignments, and normalizes markdown.
3. [x] **Portable Bundle Export Determinism**: `kanban/exporter/portable_bundle.py` exports portable zip bundles containing deterministic JSONL files (including `entities/issue_key_aliases.jsonl`) with sorted keys, reproducible timestamps, and SHA-256 verification manifests.
4. [x] **Legacy Key Alias Resolution**:
   - `kanban/resolve/service.py` and `kanban/services/issue_keys.py`: Transparently resolves legacy keys (e.g., `KANBA-1` -> `KAN-84`) across API endpoints.
   - `kanban/api/v1/resolve.py`: Emits `X-Kanban-Canonical-Key` response header on alias resolution.
5. [x] **Zero Em/En-Dashes**: Verified via `python -m scripts.check_no_dashes --all`.
6. [x] **Live Zero-Mock Container QA**: Verified against `kanban-local-import` (`127.0.0.1:18970:8080`) with live curl probe in `live-fullstack-proof.txt` and Playwright responsive screenshots in `screenshots/`.
7. [x] **Test Coverage**: >=95% branch coverage across touched modules.
