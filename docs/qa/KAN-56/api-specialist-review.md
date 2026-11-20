# Clean-Room API Specialist Review: KAN-56

**Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
**Date:** 2026-11-20  
**Branch:** `feat/KAN-56`  
**Main Commit:** `70b7738259366bf1fb3b91849dc37154ec5637a7`  
**Wiki Commit:** `c646b342bd5352cfb221d31b086e07aac68f51cd`  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit verifies the deliverables for **KAN-56** (`[KB-BRAND-CLEAN-03] Rename Wiki Scripted-Workflows-and-Transition-Helpers.md & Add Brand Audit CI Gate`).

The ticket enforces complete brand hygiene across documentation and codebase:
1. Renaming the canonical workflows wiki article from `ScriptRunner-Workflows-and-Transition-Interceptors.md` to `Scripted-Workflows-and-Transition-Helpers.md` and synchronizing all inbound wiki links, prose terminology, and Mermaid diagram node labels.
2. Introducing automated CI brand audit gates in `kanban/tests/platform/test_brand_terminology_audit.py` and `kanban/tests/docs/test_wiki_media_audit.py` to prevent regression of legacy competitor self-descriptions.
3. Updating Workflow Studio UI documentation links in `AttachHookDialog.tsx` and `WorkflowStudioPage.tsx` to reference the canonical slug.
4. Updating `scripts/sync_wiki_bundle.py` description and aliases.

All architectural boundaries, test coverage standards, static analysis gates, and typography invariants are verified and approved.

---

## 2. Detailed Technical & Architectural Audit

### 2.1. Brand Terminology CI Gate (`kanban/tests/platform/test_brand_terminology_audit.py`)
- **Coverage & Scope**: Scans all frontend files (`.ts`, `.tsx`), style files (`.css`), backend Python files (`.py`), manifests (`.toml`, `.json`, `.md`), repository documentation (`docs/`), and wiki articles (`thumbs-up-kanban.wiki/*.md`).
- **Banned Terminology Regex**: Matches case-insensitive `scriptrunner`, `transition interceptor`, `plane-parity`, `plane-calm`, `plane-style`, `jira/plane`, and `jira-surpassing`.
- **Allowed Exception Boundaries**:
  * Spec-mandated comparison documents (`docs/FEATURE_COMPARISON.md`, `docs/CUTOVER.md`, wiki comparison/cutover tables).
  * Data importers (`kanban/importer/plane_*`).
  * Historical audit records in `docs/qa/` and `docs/tickets/`.
  * Wire-protocol and database schema identifiers (`agent_interceptor`, `manage_workflow_interceptors`).
- **Assertion Robustness**: Produces clear diagnostics detailing offending file, line number, matched text, and rule name.
- **Coverage**: Achieves 98% statement and branch coverage (128 statements, 1 miss, 44 branches, 2 branch parts).

### 2.2. Wiki Document & Media Asset Audit (`kanban/tests/docs/test_wiki_media_audit.py`)
- **Document Existence**: Confirms `Scripted-Workflows-and-Transition-Helpers.md` exists and obsolete `ScriptRunner-Workflows-and-Transition-Interceptors.md` has been deleted.
- **Internal Markdown Link Integrity**: Scans every internal link across all 27 wiki articles. Verifies 0 broken links (`assert not broken_links`).
- **Media Asset Verification**: Extracts every image reference `![alt](src)` and asserts the target file exists on disk under `images/` or canonical paths (0 broken images).
- **Mermaid & Heading Validation**: Confirms canonical node labels `HelperEngine["Transition Helper Engine"]` and participant labels in sequence diagrams.

### 2.3. Workflow Studio and Script Alignment
- `kanban/web/src/features/workflows/AttachHookDialog.tsx`:
  * Updated `docHref` in line 230 to `/docs/scripted-workflows-and-transition-helpers#helper-architecture`.
  * Updated `docHref` in line 375 to `/docs/scripted-workflows-and-transition-helpers#failure-policies`.
- `kanban/web/src/features/workflows/WorkflowStudioPage.tsx`:
  * Updated `href` in line 286 to `/docs/scripted-workflows-and-transition-helpers`.
- `scripts/sync_wiki_bundle.py`:
  * Updated alias map: `"workflows": "scripted-workflows-and-transition-helpers"`.
  * Updated role description to "Project workflows, transition helpers, and custom fields."

### 2.4. Sibling Isolation & Collision Avoidance
- Zero touches to `Sidebar.tsx` (owned by `KAN-52`).
- Zero touches to `DocsCenterPage.tsx` or `wikiManifest.ts` (owned by `KAN-16-rc1`).
- Untracked files `.backup_schedule.json` and `backups/` strictly unstaged.

---

## 3. Test Suites and Static Analysis Verification

| Check / Gate | Target / Command | Result |
| :--- | :--- | :--- |
| **Pytest Suite** | `kanban/tests/platform/test_brand_terminology_audit.py`, `kanban/tests/docs/test_wiki_media_audit.py` | 7 passed in 4.52s, 98% coverage |
| **Ruff Linter** | `uv run ruff check kanban/tests/ scripts/` | Clean (0 errors, 0 warnings) |
| **Ruff Formatter** | `uv run ruff format --check kanban/tests/ scripts/` | Clean (1984 files already formatted) |
| **MyPy Typecheck** | `uv run mypy kanban/tests/platform/ kanban/tests/docs/ scripts/` | Clean (Success: 1130 source files) |
| **Import Layering** | `uv run lint-imports` | Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`) |
| **Typography Check** | `python3 -m scripts.check_no_dashes --all` | 0 em-dashes and 0 en-dashes in repository |
| **Wiki Typography** | `python3 -m scripts.check_no_dashes /home/adamoutler/kanban/thumbs-up-kanban.wiki` | 0 em-dashes and 0 en-dashes in wiki |

---

## 4. Certification & Signoff

STATUS: APPROVED

All requirements for KAN-56 have been audited and certified. The wiki documentation is clean, internal links and media resolve cleanly, the brand terminology CI gate enforces future hygiene, and zero regressions or collisions were introduced. KAN-56 is certified ready for reality-checker QA.
