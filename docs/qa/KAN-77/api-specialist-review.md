# API Specialist Review (KAN-77 / KB-MIGRATION-MULTI-01)

## Overview & Architecture Verification

- **Ticket**: KAN-77 (`[KB-MIGRATION-MULTI-01]`)
- **Module**: `kanban.importer`, `kanban.exporter`, `kanban.api.v1.admin.imports`, `kanban.api.v1.admin.exports`, `kanban.resolve`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Commit SHA**: `a9c0c303737352e61ba5660d3f6e9e9182e26a95` (`a9c0c3037373`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The multi-source importer and portable workspace exporter architecture fulfills all requirements for cross-platform migration, legacy key resolution, and hardened admin boundaries.

### 1. Importer Architecture & Zero-New-Dependency Standards
- **Multi-Source Ingestion**: Implemented native adapters for Jira (`kanban/importer/jira_importer.py`), GitHub (`kanban/importer/github_importer.py`), and Linear (`kanban/importer/linear_importer.py`) without introducing any external SDK dependencies.
- **Sanitization & Markdown Conversion**: All HTML/Jira markup is converted to canonical Markdown using existing `nh3` and `defusedxml` filters. Zero raw HTML or proprietary AST residue is stored.
- **Attachment Ingestion**: Respects the 25 MiB attachment cap and integrates with `kanban/attachments/sniff.py` for content verification.

### 2. Database Schema, RLS & Migration Invariants
- **Migration**: `p6_03_multi_source_imports_and_aliases` cleanly chained onto `p6_02_pdf_attachments`. Single linear Alembic migration head verified.
- **Table Definition**: `issue_key_aliases` table provisioned with composite unique constraints on `(workspace_id, legacy_key)` and `(issue_id, legacy_key)`.
- **Kernel-Level Isolation**: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` active with `workspace_id = app_current_workspace_id()`. Explicit table grants restricted to `kanban_app` and `app_rls_reader`.
- **ORM Parity**: Synchronized with DeclarativeBase model `database.models.issue_alias.IssueKeyAlias`.

### 3. API Contracts & Admin AAL2 Enforcement
- **Admin Boundaries**:
  - `POST /api/v1/admin/imports` enforces `Depends(require_admin_aal2)`.
  - `POST /api/v1/admin/exports` enforces `Depends(require_admin_aal2)`.
  - Verified by comprehensive route security suite in `kanban/tests/api/test_admin_routes_protected.py`.
- **Alias Resolution**:
  - `GET /api/v1/resolve` and `GET /api/v1/issues/{key}` resolve both canonical issue keys and legacy aliases (`KANBA-1` -> canonical `KAN-84`).
  - Response emits `X-Kanban-Canonical-Key: <canonical_key>` header for seamless client route redirection and browser URL updates.
- **MCP Integration**: `mcp/resolver.py` updated to resolve entity identifiers across legacy key aliases.

### 4. Deterministic Portable Workspace Exporter
- **Package**: `kanban/exporter/portable_bundle.py` generates deterministic `.tar.zst` bundles with sorted manifest order and canonical JSON formatting.
- **Integrity**: Bundles include SHA-256 integrity checksums for all objects and attachments.

### 5. Specialist Verdict
The backend API, CLI, and data layer changes for KAN-77 satisfy all performance, isolation, and security invariants.
**STATUS: APPROVED**
