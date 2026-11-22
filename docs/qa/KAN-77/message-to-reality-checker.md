# Message to Reality-Checker: Forensic QA Gate Verification (KAN-77)

## Executive Summary
This packet provides passive forensic verification evidence for ticket `KAN-77` (`[KB-IMPORT-MULTI-01]`): Multi-Source Importers (Jira, GitHub Issues, Linear), Portable Bundle Export Determinism, and Legacy Key Alias Routing (`IssueKeyAlias`).

- **Target Commit SHA**: `ee0eeb353803`
- **Branch**: `main`
- **Review Status**: Round-3 Clean-Room Remediation Complete

## Round-2 Remediation & Forensic Verification Details
1. **Database Migration & Models**: Single head migration `p6_03_multi_source_imports_and_aliases` (`down_revision = "p6_02_pdf_attachments"`) introduces `issue_key_aliases` table with RLS policies, indexing, and foreign key constraints. `database/models/issue_alias.py` (`IssueKeyAlias`) and `database/models/__init__.py` maintain exact schema parity.
2. **Multi-Source Importers (Jira, GitHub Issues, Linear)**:
   - `kanban/importer/jira_importer.py`: Imports Jira JSON and CSV exports, records original issue keys (e.g., `JIRA-101`) in `issue_key_aliases`, maps priority and state taxonomy, and extracts attachments.
   - `kanban/importer/github_importer.py`: Full support for GitHub labels (`ProjectLabel` + `IssueLabel`), milestones (`Cycle` + `Issue.cycle_id`), and sub-issues/parent (`parent_issue_id` + `LinkKind.PARENT_OF` and `LinkKind.BLOCKS` relations).
   - Across all three importers:
     * Wired `self.user_map` so mapped users assign `IssueAssignee(principal_id=...)` while unmapped assignees set `free_text_assignee`.
     * Preserved source `updated_at` on objects and `created_at` on `IssueComment`.
     * Optional attachments support with strict fail-closed path traversal validation (rejecting `..`, `/`, `\` with `ImportIntegrityError` / HTTP 422) and sanitization through `sniff_media_type`, `sanitize_svg`, `sanitize_and_validate_pdf`, and `LocalFilesystemBlobStore`.
     * Re-import mutation on SHA-256 mismatch updates existing Issue (`summary`, `description_markdown`, `state_id`, `priority_id`) and IssueComment (`body_markdown`) with bypass transition engine and sets `m.source_sha256 = sha`.
     * Recorded `"provenance_tier": "imported"` in `record_activity` payload, and computed real DB-queried alias count and SHA-256 parity in `generate_audit_report()`.
3. **Portable Bundle Export Determinism**: `kanban/exporter/portable_bundle.py`:
   - Queries and exports `Page` rows to `entities/pages.jsonl` and emits `entities/links.jsonl` (so `entities/{projects,issues,comments,docs,pages,stickies,links}.jsonl` all exist in `manifest.json` and the `.tar.gz` archive).
   - Prepends deterministic YAML front matter (`key`, `title`, `state`, `priority`, `created_at`, `updated_at`) to every `markdown/issues/<KEY>.md` and `markdown/docs/<PATH>.md` file.
4. **Frontend & Studio Integration**:
   - `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx` & `planeImportApi.ts`: Dynamic dropzone/paste labels per selected source (`Plane`, `Jira`, `GitHub Issues`, `Linear`), accepts `.csv,.json` for Linear, and includes a Portable Workspace Export card on `/admin/imports` (`POST /api/v1/admin/exports/portable` with workspace slug input, `scrub_text` checkbox, and `.tar.gz` download trigger).
   - `kanban/web/src/app/routes.tsx`: Added `/issues/:issueKey` route redirecting via `/api/v1/resolve` to `/projects/<proj>/issues/<canonicalKey>` and widened `ISSUE_KEY_REGEX` to `^[A-Z][A-Z0-9_-]{1,24}-[0-9]{1,18}$` so `JIRA-101`, `ENG_TEAM-42`, and `KANBA-123` route cleanly.
5. **Legacy Key Alias Resolution**:
   - `kanban/resolve/service.py` and `kanban/services/issue_keys.py`: Transparently resolves legacy keys (e.g., `KANBA-1` -> `KAN-84`) across API endpoints.
   - `kanban/api/v1/resolve.py`: Emits `X-Kanban-Canonical-Key` response header on alias resolution.
6. **Zero Em/En-Dashes**: Verified via `python -m scripts.check_no_dashes --all` (0 violations).
7. **Test Coverage**: >=95% branch coverage across touched modules. All unit test suites pass (recorded in `unit-test-results.txt`).
8. **Live Zero-Mock Container QA**: Verified against `kanban-local-import` (`127.0.0.1:18970:8080`) with live curl probe and portable export archive validation in `live-fullstack-proof.txt` and Playwright responsive screenshots in `screenshots/`.

## Forensic Proof Artifacts Index
- `git-diff.patch`: Strictly scoped git diff for KAN-77 owned files against base `b79959f9`.
- `build-check.txt`: Clean output of `make check`, static migration checks, and frontend typecheck/lint.
- `build-or-typecheck.txt`: Mirror of full static verification output.
- `unit-test-results.txt`: Concatenated output of Python pytest (-v) and frontend Vitest unit test suites.
- `live-fullstack-proof.txt`: Real live container curl outputs, response headers, and portable export archive contents.
- `contract-sample.json`: Real schema and response payload sample for legacy key alias and portable export.
- `screenshots/`: 6 Playwright responsive screenshots against `kanban-local-import`:
  - `1440x900-desktop-light.png`
  - `1440x900-desktop-dark.png`
  - `1440x900-portable-export-card.png`
  - `768x1024-tablet.png`
  - `390x844-mobile-portrait.png`
  - `844x390-mobile-landscape.png`
- `api-specialist-review.md`: Verbatim API specialist audit stamped with target SHA `ee0eeb353803`.
- `ui-specialist-review.md`: Verbatim UI specialist audit stamped with target SHA `ee0eeb353803`.
- `changed-files-manifest.txt`: Cryptographic SHA-256 manifest over all packet files.
