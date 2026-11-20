# Clean-Room API Specialist Review: KAN-33

- **Ticket:** KAN-33
- **Title:** [KB-P3-AUDIT-27] Reorganize Wiki & /docs Information Architecture with [Guide], [Informational], and [Architectural] Labels, 4 Audience Tracks, and Field Config Reference
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
- **Date:** 2026-11-20  
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-33`
- **Branch:** `fix/KAN-33-45-liveqa`  
- **Main Commit:** `75d4cfcb`  
- **Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-33** (`[KB-P3-AUDIT-27] Reorganize Wiki & /docs Information Architecture with [Guide], [Informational], and [Architectural] Labels, 4 Audience Tracks, and Field Config Reference`) on branch `fix/KAN-33-45-liveqa` at commit `75d4cfcb`.

The implementation delivers a structured taxonomy and verification framework across the documentation platform:
1. Enforces mandatory `# [Guide] `, `# [Informational] `, and `# [Architectural] ` H1 title prefixes across all 26 non-exempt wiki chapters while preserving 100% URL continuity (zero markdown files renamed).
2. Updates `scripts/sync_wiki_bundle.py` to parse title classifications and generate structured category metadata (`category: 'guide' | 'informational' | 'architectural'`, `track`, `subtrack`, `audience`) in `wikiManifest.ts`.
3. Restructures navigation into 4 audience tracks (Step-by-Step Guides, Feature & Field Reference, Security & Adoption Overview, Engineering & Security Architecture), adds category filter tabs, and formats badge pills.
4. Addresses live QA layout findings:
   - Configured `.docs-category-filter-bar` / `.kb-docs-filter-tabs` in a 2x2 grid layout inside the 256px sidebar, eliminating category tab clipping and ensuring `scrollWidth <= clientWidth`.
   - Implemented `stripCategoryPrefix` in `DocsCenterPage.tsx` so chapter links in the sidebar and mobile drawer display clean titles without duplicating category prefixes alongside the badge pill (e.g. avoiding `[Guide] ... [Guide]`).
   - Strips raw empty `<a id="..."></a>` anchor tags in `DocMarkdownViewer.tsx` and renders heading inline code spans via `renderInlineMarkdown`.
   - Renders `[Informational]` badge pill on `Home.md` in the left sidebar.
   - Restores keyboard focus to `docs-mobile-chapters-btn` upon closing the mobile drawer.
5. Authors `Studio-Configuration-Reference.md` covering all 11 Studios with standardized 5-column `#anchor` tables without touching any Studio `.tsx` files.
6. Implements `scripts/check_docs_taxonomy.py` (`python3 -m scripts.check_docs_taxonomy`) with 21 unit tests in `kanban/tests/docs/test_check_docs_taxonomy.py` achieving 98% coverage.

All architectural boundaries, test coverage gates, static analysis checks, and typography invariants are verified and approved.

---

## 2. Technical and Architectural Audit

### 2.1 Automated Taxonomy & Link Lint Gate (`scripts/check_docs_taxonomy.py`)
- **CLI / Module Entrypoint**: Executable as `python3 -m scripts.check_docs_taxonomy` and functions as a fast CI gate.
- **Verification Capabilities**:
  1. Title Classification: Asserts that every non-exempt markdown chapter in `thumbs-up-kanban.wiki/` has an H1 heading starting with `# [Guide] `, `# [Informational] `, or `# [Architectural] `.
  2. Manifest Metadata Integrity: Validates that every chapter in `wikiManifest.ts` declares valid `title`, `category`, `track`, `subtrack`, and `audience` fields.
  3. Internal Markdown Links & Anchors: Validates internal wiki links (`[text](Page#anchor)` and `[text](#anchor)`) against GitHub-compatible anchor slugs derived from destination page headings and `<a id="...">` tags.
  4. Web Source Code Deep Links: Scans `kanban/web/src/` for `<FieldHelpHint />` `moreInfoHref` and `<StudioDocLink />` references, verifying target slug and `#anchor` resolution.
  5. Dash Guard: Validates 0 em-dashes and 0 en-dashes across documentation files.
- **Unit Test Coverage**: `kanban/tests/docs/test_check_docs_taxonomy.py` (21 unit tests) covers anchor slug generation, heading extraction, directory taxonomy validation, manifest validation, web link checking, dash checking, and CLI runner execution with 98% statement and branch coverage (223 statements, 3 miss, 110 branches).

### 2.2 Wiki Bundle Generation (`scripts/sync_wiki_bundle.py`)
- **Classification Parsing**: Extracts category from title prefixes (`[Guide]`, `[Informational]`, `[Architectural]`) and maps to `'guide' | 'informational' | 'architectural'`.
- **Track Assignment**: Correctly assigns chapters to their respective audience tracks and subtracks.
- **TypeScript Manifest Emission**: Emits `wikiManifest.ts` with updated interfaces `WikiChapterCategory`, `WikiChapter`, `WikiCategory`, and `WikiSection`.

### 2.3 Studio Configuration Reference (`Studio-Configuration-Reference.md`)
- **Standardized Schema**: Formats all 11 Studio configuration tables with exact 5-column specification (`Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact`).
- **Anchor Consistency**: Provides explicit `#anchor` targets matching web frontend links (`#workspace-studio-configuration`, `#project-studio-configuration`, `#workflow-transitions-studio-configuration`, etc.).
- **Zero Collision Guarantee**: Studio `.tsx` components (`ProjectSettingsPage.tsx`, `CreateProjectModal.tsx`, `Sidebar.tsx`, `WorkspaceSettingsPage.tsx`) were strictly untouched.
- **Brand Hygiene**: Zero occurrences of forbidden competitor terminology (`test_brand_terminology_audit.py` clean).

---

## 3. Test Suites, Coverage, and Static Analysis Verification

### 3.1 Backend Pytest Suite
- Command: `uv run pytest kanban/tests/docs/test_check_docs_taxonomy.py --cov=scripts/check_docs_taxonomy --cov-report=term-missing`
- Results: 21/21 tests passed in 0.89s.
- Coverage: 98% statement and branch coverage on `scripts/check_docs_taxonomy.py` (223 statements, 3 missed, 110 branches).
- Taxonomy Audit Tool: `python3 -m scripts.check_docs_taxonomy` verified clean (0 violations).

### 3.2 Frontend Vitest Suite
- Command: `vitest run src/features/docs-center/__tests__/DocsCenter.test.tsx`
- Results: 38/38 tests passed with 0 `act(...)` warnings.

### 3.3 Static Gates & Security Checks
- `uv run ruff check scripts/check_docs_taxonomy.py scripts/sync_wiki_bundle.py kanban/tests/docs/test_check_docs_taxonomy.py`: Clean (All checks passed).
- `uv run ruff format --check scripts/check_docs_taxonomy.py scripts/sync_wiki_bundle.py kanban/tests/docs/test_check_docs_taxonomy.py`: Clean.
- `uv run mypy scripts/check_docs_taxonomy.py scripts/sync_wiki_bundle.py kanban/tests/docs/test_check_docs_taxonomy.py`: Clean (Success: 3 source files).
- `uv run lint-imports`: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint . --max-warnings 0`: Clean (0 warnings).
- `vite build`: Clean production build completed in 1.22s.
- `python3 -m scripts.check_no_dashes --all`: Clean (0 em/en-dashes across codebase and wiki).

---

## 4. Security & Architecture Invariants

| Invariant / Check | Specification Requirement | Verification Result |
| :--- | :--- | :--- |
| **URL Continuity** | 0 markdown files renamed | All `.md` filenames preserved |
| **Taxonomy Gate** | Automated lint tool for chapter titles & anchors | `scripts/check_docs_taxonomy.py` passes 0 violations |
| **Category Layout** | 2x2 grid in 256px sidebar | `.docs-category-filter-bar` `scrollWidth <= clientWidth` |
| **Title Prefix Parity** | Strip redundant prefix next to badge pill | Handled in `stripCategoryPrefix` |
| **Studio Reference** | 5-column tables for all 11 Studios | Authored in `Studio-Configuration-Reference.md` |
| **Zero Studio Touches** | Zero edits to Studio `.tsx` files | Confirmed via git diff |
| **Brand Hygiene** | 0 occurrences of banned competitor terms | Verified by `test_brand_terminology_audit.py` |
| **Import Layering** | Unidirectional module layering | `agent -> mcp -> kanban -> database` maintained |
| **Typography Standards** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` |

---

## 5. Certification Signoff

STATUS: APPROVED

All requirements for KAN-33 have been audited and certified on disk on branch `fix/KAN-33-45-liveqa` at commit `75d4cfcb`. Documentation taxonomy, title prefixes, audience track restructuring, Studio Configuration Reference, and automated taxonomy link linting are fully verified. Certified ready for reality-checker QA gate.
