# API Specialist Review: KAN-352

**Ticket:** `KAN-352` (`[KB-DOCS-FEATURE-02] Author End-to-End Multi-Source Migration, Key Alias Redirects, and Cross-Project Merge Guide (KAN-77, KAN-82, KAN-316)`)
**Reviewer:** `@api-spec` (Backend Architect & API Specialist)
**Status:** `APPROVED`

---

## 1. Scope Evaluation

This ticket authors the comprehensive migration, alias routing, and CSV governance architecture guide (`thumbs-up-kanban.wiki/Multi-Source-Migration-and-Key-Alias-Redirects.md` and `kanban/tests/test_docs_migration_guide.py`), documenting features shipped across `KAN-77`, `KAN-82`, and `KAN-316`.

The chapter provides comprehensive, rigorous technical coverage of:
1. **Multi-Source Importer Architecture:**
   - Ingestion contracts for Jira (Cloud and Server/DC JSON bundles), Atlassian Document Format (ADF) AST traversal, HTML parsing into canonical Markdown, and user account mapping.
   - GitHub Issues import mapping labels (`ProjectLabel` / `IssueLabel`), milestones to `Cycle`, pull requests, and hierarchical issue links.
   - Linear JSON/CSV imports mapping cycles, modules, and relation kinds.
   - Plane-DB extraction script (`scripts/export_plane_db.py`) and direct MinIO attachment streaming.
2. **Deterministic Key Alias Routing (`IssueKeyAlias`):**
   - Database model `IssueKeyAlias` and table `issue_key_aliases` (migration `p6_03_multi_source_imports_and_aliases`).
   - HTTP 308 Permanent Redirection API flow from legacy keys (`JIRA-101`, `KANBA-15`) to canonical keys (`KAN-42`).
3. **Cross-Project Merge Mode:**
   - Sequential re-keying logic, automatic alias generation, `object_links` rewiring, and activity ledger continuity.
4. **Canonical CSV Governance & WinZip AE-2 Encryption (`KAN-316`):**
   - 16 canonical CSV columns (`key`, `project_key`, `summary`, `description_markdown`, etc.).
   - CWE-1236 Formula Injection defense (neutralizing triggers on export with `'` and stripping on import).
   - WinZip AE-2 AES-256 CTR encryption (`kanban/csv/aes_zip.py`), PBKDF2-HMAC-SHA256 derivation, 12-character minimum password policy, and volatile memory zeroization (`zeroize(aes_key, hmac_key)`).

---

## 2. API Contract & Invariant Verification

- **Schema Parity:** All REST endpoints (`/api/v1/issues/{key}`, `/api/v1/projects/{project_ref}/issues/import-template.csv`, `/api/v1/admin/imports`) match the runtime implementation.
- **Security Invariants:** Accurately documents UTF-16 lone surrogate validation (`validate_no_surrogates()`) and synchronous secret push-protection (`PushProtectionMode.BLOCK`) on all import paths.

---

## 3. Verdict

**`APPROVED`** (Multi-source import pipeline, HTTP 308 redirection semantics, and CSV security models verified).
