# Message to Reality-Checker: Forensic QA Gate Verification (KAN-77)

## Executive Summary
This packet provides passive forensic verification evidence for ticket `KAN-77` (`[KB-IMPORT-MULTI-01]`): Multi-Source Importers (Jira, GitHub Issues, Linear), Portable Bundle Export Determinism, and Legacy Key Alias Routing (`IssueKeyAlias`).

- **Target Commit SHA**: `fd1dc06e1429`
- **Branch**: `main`
- **Review Status**: Round-4 Clean-Room Remediation Complete

## Round-4 Remediation and Forensic Verification Details
1. **Database Migration and Models**: Single head migration `p6_03_multi_source_imports_and_aliases` (`down_revision = "p6_02_pdf_attachments"`) introduces `issue_key_aliases` table with RLS policies, indexing, and foreign key constraints. `database/models/issue_alias.py` (`IssueKeyAlias`) and `database/models/__init__.py` maintain exact schema parity.
2. **Multi-Source Importers (Jira, GitHub Issues, Linear)**:
   - `kanban/importer/jira_importer.py`: Imports Jira Cloud and Server/DC JSON export bundles, parses ADF (Atlassian Document Format) and HTML descriptions/comments into canonical Markdown, records original issue keys (e.g., `JIRA-101`) in `issue_key_aliases`, maps priority and state taxonomy, and extracts attachments.
   - `kanban/importer/linear_importer.py`: Imports Linear JSON export bundles and CSV export files with comments and relations.
   - `kanban/importer/github_importer.py`: Full support for GitHub Issues JSON export bundles with labels (`ProjectLabel` + `IssueLabel`), milestones (`Cycle` + `Issue.cycle_id`), and sub-issues/parent (`parent_issue_id` + `LinkKind.PARENT_OF` and `LinkKind.BLOCKS` relations).
   - Across all three importers:
     * Wired `self.user_map` so mapped users assign `IssueAssignee(principal_id=...)` while unmapped assignees set `free_text_assignee`.
     * Preserved source `updated_at` on objects and `created_at` on `IssueComment`.
     * Optional attachments support with strict fail-closed path traversal validation (rejecting `..`, `/`, `\` with `ImportIntegrityError` / HTTP 422) and sanitization through `sniff_media_type`, `sanitize_svg`, `sanitize_and_validate_pdf`, and `LocalFilesystemBlobStore`.
     * Re-import mutation on SHA-256 mismatch updates existing Issue (`summary`, `description_markdown`, `state_id`, `priority_id`) and IssueComment (`body_markdown`) with bypass transition engine and sets `m.source_sha256 = sha`.
     * Recorded `"provenance_tier": "imported"` in `record_activity` payload, and computed real DB-queried alias count and SHA-256 parity in `generate_audit_report()`.
3. **Test Suite Deduplication and Route Protection**:
   - `kanban/tests/security/test_admin_routes_protected.py` serves as the single canonical location for Section 4.3 admin route AAL2 verification and registration assertions for `/api/v1/admin/exports/portable` and `/api/v1/admin/imports/{jira,github,linear}`. The duplicate `kanban/tests/api/test_admin_routes_protected.py` was removed.
   - `kanban/tests/resolve/test_legacy_key_aliases.py` serves as the single canonical test file for legacy key alias resolution, HTML 308 redirects, and cross-workspace RLS isolation. The duplicate `kanban/tests/api/test_legacy_key_aliases.py` was merged and removed.
4. **Portable Bundle Export Determinism**: `kanban/exporter/portable_bundle.py`:
   - Queries and exports `Page` rows to `entities/pages.jsonl` and emits `entities/links.jsonl` (so `entities/{projects,issues,comments,docs,pages,stickies,links}.jsonl` all exist in `manifest.json` and the `.tar.gz` archive).
   - Prepends deterministic YAML front matter (`key`, `title`, `state`, `priority`, `created_at`, `updated_at`) to every `markdown/issues/<KEY>.md` and `markdown/docs/<PATH>.md` file.
5. **Frontend and Studio Integration**:
   - `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx` and `planeImportApi.ts`: Dynamic dropzone/paste labels per selected source (`Plane`, `Jira`, `GitHub Issues`, `Linear`), accepts `.csv,.json` for Linear, and includes a Portable Workspace Export card on `/admin/imports` (`POST /api/v1/admin/exports/portable` with workspace slug input, `scrub_text` checkbox, and `.tar.gz` download trigger).
   - `kanban/web/src/app/routes.tsx`: Added `/issues/:issueKey` route redirecting via `/api/v1/resolve` to `/projects/<proj>/issues/<canonicalKey>` and widened `ISSUE_KEY_REGEX` to `^[A-Z][A-Z0-9_-]{1,24}-[0-9]{1,18}$` so `JIRA-101`, `ENG_TEAM-42`, and `KANBA-123` route cleanly.
6. **Legacy Key Alias Resolution**:
   - `kanban/resolve/service.py` and `kanban/services/issue_keys.py`: Transparently resolves legacy keys (e.g., `KANBA-1` -> `KAN-84`) across API endpoints.
   - `kanban/api/v1/resolve.py`: Emits `X-Kanban-Canonical-Key` response header on alias resolution.
7. **Zero Em/En-Dashes**: Verified via `python -m scripts.check_no_dashes --all` (0 violations).
8. **Test Coverage**: >=95% branch coverage across touched modules. Exactly 56 unit tests passed (39 backend Pytest, 17 frontend Vitest) recorded in `unit-test-results.txt`.
9. **Live Zero-Mock Container QA**: Verified against `kanban-local-import` (`127.0.0.1:18970:8080`) with live curl probe and portable export archive validation in `live-fullstack-proof.txt` and Playwright responsive screenshots in `screenshots/`.

## Forensic Proof Artifacts Index
- `git-diff.patch`: Strictly scoped git diff for KAN-77 owned files against base `b79959f9` through `fd1dc06e1429`.
- `build-check.txt`: Clean output of `make check`, static migration checks, and frontend typecheck/lint.
- `build-or-typecheck.txt`: Mirror of full static verification output.
- `unit-test-results.txt`: Concatenated output of Python pytest (-v, 39 passed) and frontend Vitest (17 passed) unit test suites (56 passed total).
- `live-fullstack-proof.txt`: Real live container curl outputs, response headers, dry-run simulation diffs, and portable export archive contents (338 files verified).
- `contract-sample.json`: Real schema and response payload sample for legacy key alias and portable export.
- `screenshots/`: 8 Playwright screenshots against `kanban-local-import`:
  - `1440x900-desktop-light.png`: Migration studio main view in light theme.
  - `1440x900-desktop-dark.png`: Migration studio main view in dark theme.
  - `1440x900-portable-export-card.png`: Scrolled view displaying Portable Export card with workspace slug and options.
  - `1440x900-linear-dryrun-preview.png`: Linear tab active, showing target project key input, sample payload, and Stage 1 dry-run simulation diff preview card.
  - `1440x900-legacy-key-redirect.png`: Browser navigation to `/issues/KANBA-1` cleanly redirected to canonical `/projects/KAN/issues/KAN-84` with `> Imported from KANBA-1`.
  - `768x1024-tablet.png`: Responsive tablet viewport.
  - `390x844-mobile-portrait.png`: Responsive mobile portrait viewport.
  - `844x390-mobile-landscape.png`: Responsive mobile landscape viewport.
- `api-specialist-review.md`: Verbatim API specialist audit stamped with target SHA `fd1dc06e1429`.
- `ui-specialist-review.md`: Verbatim UI specialist audit stamped with target SHA `fd1dc06e1429`.
- `changed-files-manifest.txt`: Cryptographic SHA-256 manifest over all packet files.
