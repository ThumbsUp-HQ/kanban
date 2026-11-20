# Message to Reality-Checker QA Gate: KAN-9

## Overview
Ticket: **KAN-9** (`[KB-P3-AUDIT-03] Fix Auto-Created Root Doc Null Creator 500, Air-Gapped Sticky Promotion Preview Fallback, /projects/:key/stickies Route Alias, and Mobile Docs Backdrop (4 Problems)`)
Branch: `feat/KAN-9`
Status: READY FOR AUDIT

## Problem Manifest & Technical Solutions

### Problem 1: Fix Auto-Created Root Doc `register_object` Null `:creator` 500 Crash
- **Root Cause:** When `_resolve_doc_id` in `kanban/services/docs.py` attempted to auto-create a root doc for a project with 0 existing docs, it called PostgreSQL stored function `register_object(CAST('doc' AS object_kind), :ws, :proj, :ckey, :title, :creator)` without providing a non-null creator principal. If the caller was anonymous, had no principal header, or `caller_principal_id` was None, Postgres raised `REGISTER_OBJECT_NULL_ARGUMENT` (`500 Internal Server Error`).
- **Remediation:**
  - Extracted helper `_auto_create_root_doc` in `kanban/services/docs.py` with multi-tier fallback resolution:
    1. Explicit `caller_principal_id` if provided and valid.
    2. Postgres session GUC `current_setting('app.principal_id', true)` if set and non-empty.
    3. Project `created_by_id` resolved from `projects` table for the given project.
  - Updated all `register_object` invocations in `docs.py` (`_auto_create_root_doc`, `create_doc`, `create_project_page`) to ensure `:creator` is always a valid non-null UUID.
  - Added full test suite in `kanban/tests/api/test_auto_created_root_doc.py` verifying that both `GET /api/v1/projects/:key/docs/tree` and `POST /api/v1/projects/:key/docs/pages` on a fresh project with 0 existing docs succeed with 200/201 and 0 database crashes.

### Problem 2: Catch `AllProvidersUnavailable` in `POST /api/v1/stickies/:id/preview-promotion`
- **Root Cause:** When an air-gapped instance had no online LLM providers configured in the workspace residency tier, `POST /api/v1/stickies/:id/preview-promotion` raised unhandled `AllProvidersUnavailable` or `EgressDenied` exceptions resulting in `500` or `503` errors.
- **Remediation:**
  - In `kanban/api/v1/sticky_promo_ai.py`, caught `ProviderError`, `EgressDenied`, `ProviderSchemaError`, and error codes matching `("ALL_PROVIDERS_UNAVAILABLE", "NO_PROVIDER_IN_RESIDENCY_TIER", "PROVIDER_UNAVAILABLE", "PROVIDER_TIMEOUT", "AIR_GAP_EGRESS_DENIED")`.
  - Implemented dynamic fallback resolution via `deterministic_fallback_structuring` in `agent/sticky_promo/structurer.py` (respecting `lint-imports` module layering).
  - Returns a deterministic 200 OK Markdown section preview response with structured warnings (`ALL_PROVIDERS_UNAVAILABLE_FALLBACK`), preserving all fenced code blocks, checklists, and titles without throwing a 500/503.
  - Tested in `kanban/tests/stickies/test_sticky_promo_ai_api.py` and `agent/tests/sticky_promo/test_structurer.py`.

### Problem 3: Add `/projects/:projectKey/stickies` Route Alias
- **Root Cause:** Navigation to `/projects/:projectKey/stickies` resulted in a 404 or unhandled route, confusing users attempting to access the stickies board via standard project URLs.
- **Remediation:**
  - In `kanban/web/src/app/routes.tsx`, mounted `/projects/:projectKey/stickies` and `/w/:workspaceSlug/p/:projectKey/stickies` mapped cleanly to `ProjectOverviewRoute` (stickies overview).
  - Verified route matching and redirect in `src/app/routes.test.tsx` and `src/app/routesDeepCoverage.test.tsx`.

### Problem 4: Fix Mobile Docs Initial `.docs-sheet-backdrop` Tap Trap
- **Root Cause:** In `kanban/web/src/features/docs/DocsWorkspaceView.tsx`, `isRailSheetOpen` was initialized to true or improperly conditioned on mobile viewports (<=1024px). The backdrop `.docs-sheet-backdrop` intercepted initial taps on mobile devices (e.g. 390x844), preventing immediate clicks on header buttons and pages tree navigation.
- **Remediation:**
  - Initialized `isRailSheetOpen` to false whenever `typeof window !== 'undefined' && window.innerWidth <= 1024`.
  - Added reactive window resize listener updating `isMobile`.
  - Conditioned backdrop rendering so `.docs-sheet-backdrop` ONLY renders when either `isTreeSheetOpen` is true or both `isMobile && isRailSheetOpen` are true.
  - Updated `DocsWorkspaceView.css` to ensure touch targets on mobile remain unobstructed.
  - Verified zero backdrop elements on initial mobile load in `src/features/docs/DocsWorkspaceView.test.tsx`.

## Quality & Gate Verification

1. **Unit Test Coverage (All Touched Files >= 95%):**
   - `kanban/services/docs.py`: **95%** (439 Stmts, 14 Miss, 148 Branches, 16 BrPart)
   - `kanban/api/v1/sticky_promo_ai.py`: **100%** (77 Stmts, 0 Miss, 16 Branches, 0 BrPart)
   - `agent/sticky_promo/structurer.py`: **97%** (189 Stmts, 1 Miss, 58 Branches, 7 BrPart)
   - `DocsWorkspaceView.tsx`: **100% Stmts, 100% Branch, 100% Funcs, 100% Lines**
   - `routes.tsx`: **99.02% Stmts, 95.11% Branch, 100% Funcs, 100% Lines**
   - Total backend Pytest: 55 passed in 53s.
   - Total frontend Vitest: 261 passed in 13.4s.

2. **Static Analysis & Standards:**
   - `uv run ruff check`: All checks passed (0 errors).
   - `uv run ruff format --check`: 5 files already formatted (0 differences).
   - `uv run mypy`: Success: no issues found in 3 source files (0 errors).
   - `uv run lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database` strictly preserved).
   - `(cd kanban/web && pnpm tsc -b)`: Clean build (0 TypeScript errors).
   - `(cd kanban/web && pnpm eslint src/app/routes.tsx src/features/docs/DocsWorkspaceView.tsx src/app/routes.test.tsx)`: Clean (0 errors, 0 warnings).
   - `(cd kanban/web && pnpm vitest run src/styles/__tests__/cssTokensAudit.test.ts)`: 4/4 passed (100% CSS token compliance).
   - `python3 -m scripts.check_no_dashes --all`: Clean (0 forbidden em-dashes or en-dashes).

3. **Security Invariants & Non-Destructive Compliance:**
   - 0 inline React `style={...}` props (CSP `style-src 'self'` compliant).
   - UTF-16 lone-surrogate validation enforced.
   - Isolated hermetic test fixtures used exclusively (`KB_TEST_PGSOCKET_DIR="/tmp/kb-pgsock-kan9"`).
