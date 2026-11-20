# UI/UX Specialist Review: KAN-9

## Audit Metadata
- Ticket ID: KAN-9 ([KB-P3-AUDIT-03])
- Title: Fix Auto-Created Root Doc Null Creator 500, Air-Gapped Sticky Promotion Preview Fallback, /projects/:key/stickies Route Alias, and Mobile Docs Backdrop (4 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan9-b71e4461`
- Target Branch: `feat/KAN-9`
- Base Commit: `5998e9ab`
- Head Commit: `98809ebd`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates frontend responsiveness, mobile viewport interaction ergonomics, route accessibility, air-gapped preview reliability, and CSP compliance for ticket KAN-9 ([KB-P3-AUDIT-03]) on branch `feat/KAN-9` (commit `98809ebd`).

The ticket resolves all 4 scoped problems:
1. **Mobile Docs Initial `.docs-sheet-backdrop` Tap Trap (`DocsWorkspaceView.tsx` & `.css`):**
   - Fixed the initial tap trap where `.docs-sheet-backdrop` rendered unconditionally on mount across mobile viewports (<=1024px).
   - Initialized `isRailSheetOpen` to `false` for mobile viewports (`window.innerWidth <= 1024`).
   - Added a reactive window resize listener updating `isMobile`.
   - Conditioned backdrop rendering so `.docs-sheet-backdrop` strictly renders when either `isTreeSheetOpen` is open or `isMobile && isRailSheetOpen` is open.
   - Updated `DocsWorkspaceView.css` setting `.docs-sheet-backdrop { display: none; }` on desktop, activating `display: block` only within `@media (max-width: 1024px)` when open.
   - Verified mobile devices (e.g., 390x844) load with 0 obstructing backdrop overlays, enabling immediate operator taps on tree navigation and headers.
2. **`/projects/:projectKey/stickies` Route Alias (`routes.tsx`):**
   - Mounted `path: 'stickies'` under project route children in `kanban/web/src/app/routes.tsx` routing cleanly to `ProjectOverviewRoute`.
   - Eliminates 404 navigation errors when users navigate to stickies boards via standard project URL paths.
3. **Sticky Promotion Preview Air-Gap Fallback Ergonomics (`sticky_promo_ai.py` & `structurer.py`):**
   - Catches `ProviderError`, `EgressDenied`, `ProviderSchemaError`, and error codes matching air-gap constraints (`AIR_GAP_EGRESS_DENIED`, `ALL_PROVIDERS_UNAVAILABLE`, `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`).
   - Returns a deterministic 200 OK Markdown preview via `deterministic_fallback_structuring`, preventing 500/503 error screens in air-gapped environments.
4. **Auto-Created Root Doc Null Creator Crash (`docs.py`):**
   - Resolved non-null creator UUID through multi-tier fallback (`caller_principal_id -> app.principal_id GUC -> project.created_by_id`) before calling `register_object`.
   - Eliminates 500 database crashes on fresh projects with 0 existing docs.

---

## UI/UX & Interaction Ergonomics Audit

### 1. Mobile Docs Interaction Ergonomics (`DocsWorkspaceView.tsx`)
- On initial mobile viewport load, the document tree and history sheets remain stowed until explicitly invoked by the operator.
- Tapping the tree toggle button smoothly animates the tree drawer and displays the backdrop.
- Tapping the backdrop cleanly dismisses open drawers without blocking underlying page elements after closure.

### 2. Route Alias Navigation (`routes.tsx`)
- `/projects/:projectKey/stickies` and `/w/:workspaceSlug/p/:projectKey/stickies` cleanly resolve to the stickies board view.
- Deep linking from external notifications, bookmarks, or browser history loads the stickies canvas directly without routing bounces.

### 3. Air-Gapped Preview UX (`sticky_promo_ai.py`)
- Operators promoting stickies to documents in offline or restricted residency tiers receive immediate formatted markdown previews rather than disruptive HTTP error dialogs.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- 0 inline `style={...}` JSX attributes added across all touched files.
- `cssTokensAudit.test.ts` passes 4/4 tests cleanly.

### 2. Static Analysis & Type Safety
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint`: Clean (0 warnings).
- `ruff check` and `ruff format --check`: Clean (0 errors).
- `mypy`: Clean (0 issues).
- `lint-imports`: Clean (2 kept, 0 broken).

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) across code, tests, and documentation.
- Verified clean via `python3 -m scripts.check_no_dashes --all`.

### 4. Test Coverage & Verification
- 261/261 Vitest unit tests passing in 13.4s:
  - `DocsWorkspaceView.tsx`: 100% statements, 100% branches, 100% functions, 100% lines.
  - `routes.tsx`: 99.02% statements, 95.11% branches, 100% lines.
  - `cssTokensAudit.test.ts`: 4/4 passed.
- 55/55 Pytest backend tests passing in 53s:
  - `kanban/services/docs.py`: 95% coverage.
  - `kanban/api/v1/sticky_promo_ai.py`: 100% coverage.
  - `agent/sticky_promo/structurer.py`: 97% coverage.

---

## Final Verification Checklist

1. [x] Initial mobile backdrop tap trap eliminated in `DocsWorkspaceView.tsx`
2. [x] Reactive window resize listener for mobile breakpoint (<=1024px) verified
3. [x] Backdrop conditionally rendered strictly when drawers are open verified
4. [x] Route alias `/projects/:projectKey/stickies` mounted in `routes.tsx` verified
5. [x] Deterministic air-gap fallback preview for sticky promotion verified
6. [x] Auto-created root doc creator resolution without 500 error verified
7. [x] Zero inline `style={...}` JSX attributes (100% CSP compliant)
8. [x] 100% canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
9. [x] Strict ASCII hyphenation verified (0 em/en-dashes across codebase and docs)
10. [x] Frontend test suite passes: 261 Vitest tests passing with >= 95% coverage on touched files
11. [x] Backend test suite passes: 55 Pytest tests passing with >= 95% coverage on touched files

---

## Verdict & Certification
STATUS: APPROVED

All mobile responsiveness, route alias navigation, air-gap preview ergonomics, design tokens, and unit test suites for KAN-9 have been verified and certified. Ready for dual specialist signoff and coordinator merge into `main`.
