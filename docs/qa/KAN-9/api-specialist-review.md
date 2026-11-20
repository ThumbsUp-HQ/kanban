# API Specialist Review: KAN-9 (KB-P3-AUDIT-03)

- Ticket: KAN-9
- Title: [KB-P3-AUDIT-03] Fix Auto-Created Root Doc Creator NULL 500, Air-Gapped Sticky Promotion Preview Fallback, /stickies Route Alias, and Mobile Docs Tap Trap (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan9-b71e4461`
- Target Branch: `feat/KAN-9`
- Base Commit: `5998e9ab`
- Head Commit: `98809ebd`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-9 on branch `feat/KAN-9` (commit `98809ebd`). The ticket resolves 4 distinct problems spanning document spine initialization, resilient AI sticky promotion preview under air-gapped and offline conditions, URL route aliasing, and mobile viewport interaction traps.

All API contracts, security invariants, transaction boundaries, air-gap fallbacks, and test coverage requirements are verified and approved:
1. Auto-Created Root Doc Creator 500 Fix (Problem 1): In `kanban/services/docs.py` (`_auto_create_root_doc`), eliminated the passing of `:creator: None` to `register_object`, which caused a NOT NULL database exception on fresh projects lacking docs. Established a robust three-tier creator resolution hierarchy (`caller_principal_id` -> session GUC `app.principal_id` -> project `created_by_id`).
2. Air-Gapped Sticky Promotion Preview Fallback (Problem 2): In `kanban/api/v1/sticky_promo_ai.py`, guarded provider execution against `ProviderError`, `EgressDenied`, `ProviderSchemaError`, and error codes including `ALL_PROVIDERS_UNAVAILABLE`, `NO_PROVIDER_IN_RESIDENCY_TIER`, `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, and `AIR_GAP_EGRESS_DENIED`. Returns a deterministic 200 OK preview via `deterministic_fallback_structuring` in `agent/sticky_promo/structurer.py` without violating module layering (`agent -> mcp -> kanban -> database`).
3. Stickies Route Alias (Problem 3): In `kanban/web/src/app/routes.tsx`, mounted `/projects/:projectKey/stickies` and `/w/:workspaceSlug/p/:projectKey/stickies` routing to `ProjectOverviewRoute`, maintaining URL parity across navigation links.
4. Mobile Docs Tap Trap (Problem 4): In `kanban/web/src/features/docs/DocsWorkspaceView.tsx`, initialized `isRailSheetOpen = false` on mobile viewports (<= 1024px) and conditioned `.docs-sheet-backdrop` rendering strictly on active drawer state, preventing background touch interception.
5. Clean Architecture & Boundaries: Strict unidirectional layering maintained (`agent -> mcp -> kanban -> database`). Dynamic import `importlib.import_module("agent.sticky_promo.structurer")` ensures kanban endpoints invoke fallback structuring without compile-time cyclic dependencies.
6. Test Coverage: 55/55 backend Pytest tests passing with 96% coverage across touched files (`kanban.services.docs` 95%, `kanban.api.v1.sticky_promo_ai` 100%, `agent.sticky_promo.structurer` 97%). 261/261 frontend Vitest tests passing.
7. Zero Em/En-Dashes: Clean verification under `check_no_dashes` (0 em/en-dashes).

---

## 2. Detailed Contract & Security Verification

### 2.1 Auto-Created Root Doc Creator Resolution (`kanban/services/docs.py`)
- Problem: Calling `GET /api/v1/projects/:key/docs/tree` or `POST /api/v1/projects/:key/docs/pages` on a newly created project with 0 docs triggered `_resolve_doc_id` -> auto-create default root doc. The previous implementation passed `:creator: None` into `SELECT register_object(...)`, violating the NOT NULL constraint on `objects.created_by_id` and raising a 500 error.
- Solution:
  ```python
  creator_id = caller_principal_id
  if creator_id is None:
      guc_res = (
          await session.execute(
              text("SELECT nullif(current_setting('app.principal_id', true), '')::uuid")
          )
      ).scalar_one_or_none()
      if guc_res is not None:
          creator_id = guc_res
  if creator_id is None and proj_creator is not None:
      creator_id = proj_creator
  ```
- Route Handlers Updated: `get_doc`, `update_doc`, `delete_doc`, `get_doc_tree`, and `create_page` explicitly forward `caller_principal_id=caller.principal_id`.
- Test Verification: `kanban/tests/api/test_auto_created_root_doc.py` proves:
  - Fresh project with 0 docs returns 200 OK on `GET /api/v1/projects/:key/docs/tree` and registers root doc with valid creator UUID.
  - Page creation on fresh project returns 201 Created under auto-created root doc.
  - Repeated calls idempotently reuse existing root doc without duplicate object registrations.

### 2.2 Air-Gapped Sticky Promotion Preview Fallback (`kanban/api/v1/sticky_promo_ai.py` & `agent/sticky_promo/structurer.py`)
- Problem: In air-gapped, isolated, or offline deployments where LLM providers are disabled, unreachable, or encounter timeout/egress blocks, calling `POST /api/v1/projects/:key/stickies/:id/preview-promotion` failed with 500 or 502 errors instead of gracefully rendering a preview.
- Solution:
  - Error Detection: `_is_provider_unavailable_error(exc)` catches provider offline, egress denial, timeout, and schema mismatch exceptions.
  - Architectural Boundary: `_get_fallback_structurer()` dynamically imports `deterministic_fallback_structuring` from `agent.sticky_promo.structurer` so `kanban/` depends on `agent/` only through runtime abstraction, preventing cyclic or prohibited imports.
  - Deterministic Fallback Logic:
    1. Mandatory Outbound Secret Scrubber runs first (`outbound_secret_scrubber`).
    2. Code Block Preservation: verifies all fenced code blocks (`verify_fenced_blocks_preserved` and `append_missing_fenced_blocks`).
    3. Structural Parsing: extracts title from first heading, parse sections (H2/H3), and markdown checkbox action items up to bounded caps (`_MAX_ACTION_ITEMS = 25`, `_MAX_SECTIONS = 20`).
    4. Read-Only Invariant: Zero database mutations executed (read-only preview).
    5. Returns 200 OK `StickyPromotePreviewResponse` with `proposal`, `rendered_markdown`, `original_sha256`, and `warnings`.
- Test Verification: `kanban/tests/stickies/test_sticky_promo_ai_api.py` and `agent/tests/sticky_promo/test_structurer.py` verify preview returns 200 OK when providers throw `AllProvidersUnavailable`, `EgressDenied`, `ProviderTimeout`, or `AIR_GAP_EGRESS_DENIED`.

### 2.3 Route Alias & Mobile Backdrop Verification
- Stickies URL Aliasing:
  - `/projects/:projectKey/stickies` and `/w/:workspaceSlug/p/:projectKey/stickies` mounted in `routes.tsx` pointing to `ProjectOverviewRoute`.
  - Tested in `routes.test.tsx` and `routesDeepCoverage.test.tsx`.
- Mobile Tap Trap:
  - In `DocsWorkspaceView.tsx`, `isRailSheetOpen` initializes to `false` when `window.innerWidth <= 1024`.
  - Backdrop conditionally rendered only when `isTreeSheetOpen || (isMobile && isRailSheetOpen)`.
  - Verified in `DocsWorkspaceView.test.tsx` that viewport 390x844 loads with 0 blocking backdrops.

### 2.4 Test Suite & Coverage Verification
- Backend Pytest Suites:
  - `kanban/tests/api/test_auto_created_root_doc.py`: 5/5 PASSED.
  - `kanban/tests/stickies/test_sticky_promo_ai_api.py`: 9/9 PASSED.
  - `agent/tests/sticky_promo/test_structurer.py`: 16/16 PASSED.
  - Full suite: 55/55 PASSED in 53.38s.
  - Coverage: `agent.sticky_promo.structurer` (97%), `kanban.api.v1.sticky_promo_ai` (100%), `kanban.services.docs` (95%).
- Frontend Vitest Suites:
  - 261/261 tests passing across `routes.test.tsx`, `routesDeepCoverage.test.tsx`, `DocsWorkspaceView.test.tsx`, and `cssTokensAudit.test.ts`.

### 2.5 Security, Boundary, and Code Style Compliance
- Dependency Invariant: Zero external packages added (`Apache-2.0` compliant).
- Boundary Invariant: `lint-imports` confirms strict unidirectional layering (`agent -> mcp -> kanban -> database`).
- Static Checks: `tsc -b` (0 errors), `eslint` (0 warnings), `mypy` (0 errors), `ruff check` (clean), `check_no_dashes` (0 em/en-dashes).

---

## 3. Specialist Checklist

1. [x] Root doc auto-creation resolves valid non-null creator UUID from caller, GUC, or project
2. [x] `register_object` executes with non-null creator parameter, preventing 500 errors
3. [x] Fresh project `GET .../docs/tree` and `POST .../docs/pages` succeed with 200/201
4. [x] Sticky promo preview catches provider offline/air-gap/egress exceptions
5. [x] Deterministic fallback structurer scrubs secrets and preserves code blocks
6. [x] Zero database writes executed during sticky promo preview
7. [x] `/projects/:projectKey/stickies` route alias resolves cleanly to ProjectOverviewRoute
8. [x] Mobile docs backdrop tap trap eliminated on <= 1024px viewports
9. [x] All 55 backend tests passing with >= 95% coverage on touched services
10. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

The KAN-9 implementation on branch `feat/KAN-9` (commit `98809ebd`) resolves all 4 scoped problems with exemplary reliability, defensive fallback handling, and robust test coverage. Ready for dual specialist signoff and merge into `main`.
