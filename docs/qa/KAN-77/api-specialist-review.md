# API Specialist Review (KAN-77 / KB-MIGRATION-MULTI-01)

## Overview & Architecture Verification

- **Ticket**: KAN-77 (`[KB-MIGRATION-MULTI-01]`)
- **Module**: `kanban.importer`, `kanban.exporter`, `kanban.api.v1.admin.imports`, `kanban.api.v1.admin.exports`, `kanban.resolve`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Commit SHA**: `fe37fd7a604012af520cab1053051ede876a96cb` (`fe37fd7a`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The Round-2 remediation resolves all clean-room reality-checker findings across multi-source ingestion, portable workspace export bundling, and legacy alias routing.

### 1. Multi-Source Importer Architecture
- **Adapter Coverage**: Hardened native adapters for Jira (`jira_importer.py`), GitHub (`github_importer.py`), and Linear (`linear_importer.py`) without external SDK dependencies.
- **GitHub Hierarchy Mapping**: Full mapping support for labels (`ProjectLabel` + `IssueLabel`), milestones (`Cycle` + `Issue.cycle_id`), and sub-issues/parent relationships (`parent_issue_id` with `LinkKind.PARENT_OF` and `LinkKind.BLOCKS`).
- **User Mapping**: `self.user_map` maps registered principals to `IssueAssignee(principal_id=...)` while preserving unmapped external assignees in `free_text_assignee`.
- **Timestamp Fidelity**: Preserves original source `created_at` and `updated_at` timestamps on database objects and comments.
- **Attachment Ingestion Security**: Enforces 25 MiB attachment limit, strict fail-closed path traversal validation (rejecting `..`, `/`, `\`), and sanitization through media type sniffers, SVG sanitizers, raster re-encoders, and the PDF security scanner.
- **SHA-256 Mutation & Idempotency**: Correctly identifies content updates via SHA-256 comparison and updates existing issues and comments without creating duplicates.
- **Audit Reports**: Computes real database-queried alias counts and SHA-256 parity in `generate_audit_report()`.

### 2. Deterministic Portable Workspace Exporter
- **Format**: `kanban/exporter/portable_bundle.py` generates deterministic `.tar.gz` gzip-compressed archives.
- **Manifest & Entity Streams**: Emits `manifest.json`, `entities/pages.jsonl`, `entities/links.jsonl`, `entities/issues.jsonl`, `entities/comments.jsonl`, `entities/docs.jsonl`, and `entities/stickies.jsonl`.
- **Markdown Front Matter**: Prepends deterministic YAML front matter (`key`, `title`, `state`, `priority`, `created_at`, `updated_at`) to exported issue and doc markdown files.
- **Archive Integrity**: SHA-256 integrity checksums recorded for all exported entities and attachment files.

### 3. Database Schema, RLS & Migration Invariants
- **Migration**: `p6_03_multi_source_imports_and_aliases` cleanly chained onto `p6_02_pdf_attachments`. Single linear Alembic migration head verified.
- **Table Definition**: `issue_key_aliases` table provisioned with composite unique constraints on `(workspace_id, legacy_key)` and `(issue_id, legacy_key)`.
- **Kernel-Level Isolation**: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` active with `workspace_id = app_current_workspace_id()`. Explicit table grants restricted to `kanban_app` and `app_rls_reader`.
- **ORM Parity**: Synchronized with DeclarativeBase model `database.models.issue_alias.IssueKeyAlias`.

### 4. API Contracts & Admin AAL2 Enforcement
- **Admin Boundaries**:
  - `POST /api/v1/admin/imports` enforces `Depends(require_admin_aal2)`.
  - `POST /api/v1/admin/exports/portable` enforces `Depends(require_admin_aal2)`.
  - Verified by comprehensive route security tests in `kanban/tests/security/test_admin_routes_protected.py`.
- **Alias Resolution**:
  - `GET /api/v1/resolve` and `GET /api/v1/issues/{key}` resolve both canonical keys and legacy aliases (`KANBA-1` -> canonical `KAN-84`).
  - Response emits `X-Kanban-Canonical-Key: <canonical_key>` header for seamless client route redirection.
- **MCP Integration**: `mcp/resolver.py` updated to resolve entity identifiers across legacy key aliases.

### 5. Specialist Verdict
The backend API, CLI, and data layer changes for KAN-77 satisfy all performance, isolation, and security invariants.
**STATUS: APPROVED**
