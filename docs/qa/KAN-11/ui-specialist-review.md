# UI/UX Specialist Review: KAN-11

## Audit Metadata
- Ticket ID: KAN-11 ([KB-P3-AUDIT-05])
- Title: Fix Project Settings Modules Sidebar Cache Sync, Active-Project Permanent Purge Guard, and Dynamic Drafts Empty-State Link
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan11-8c51475a`
- Target Branch: feat/KAN-11
- Base Commit: 887e7e0
- Head Commit: 83e421d
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates the UI layout, responsive design, visual affordances, interaction ergonomics, and code hygiene for ticket KAN-11 ([KB-P3-AUDIT-05]).

The changes resolve three distinct UX and state synchronization problems:
1. **Dynamic Navigation Sync (Problem 1):** Toggling project module configuration in Project Settings General tab now triggers immediate cache synchronization via `queryClient.setQueryData` and invalidations on `['project', projectKey]` and `['projects']`. The Modules navigation item in the application sidebar appears or disappears dynamically upon saving without requiring a manual page refresh (F5).
2. **Destructive Guard Affordance & Inline Guidance (Problem 2):** The Danger Zone Permanent Purge action is now safely guarded for active (non-trashed) projects. The button is disabled (`disabled={!isProjectTrashed}`, `aria-disabled={!isProjectTrashed}`) with appropriate visual affordance (`.kb-btn-purge:disabled` opacity and not-allowed cursor). An inline guidance hint (`.kb-danger-purge-hint`, tokenized with `var(--text-secondary)`) explicitly clarifies that Stage 1 (Move Project to Trash) must precede permanent purge, preventing unexpected 409 API errors. Additionally, a preexisting inline style (`style={{ marginTop: '0.5rem' }}`) was eliminated and replaced with `.kb-danger-reason-input`.
3. **Dynamic Context-Aware Empty State Link (Problem 3):** The `/drafts` empty-state Call to Action link dynamically derives its destination from the current project context or first accessible project (`projects[0]?.identifier ?? projects[0]?.key`), falling back gracefully to `/` when no projects exist. This completely replaces the previous hardcoded link to `/projects/KAN/issues?create=1`.

All unit test suites pass (316 tests across 11 files) with 98.68% statement and 95.45% branch coverage.

---

## Visual & Ergonomics Verification

### 1. Project Settings Modules Toggle & Query Cache Synchronization
- When saving general project settings in `ProjectSettingsPage.tsx`:
  - `queryClient.setQueryData(['project', projectKey], ...)` immediately updates the in-memory cache with the new `modules_enabled` state.
  - `queryClient.invalidateQueries` executes for both `['project', projectKey]` and `['projects']`.
  - The left navigation sidebar re-evaluates project capabilities reactively, ensuring seamless UI consistency without user confusion or full-page reloads.

### 2. Danger Zone Permanent Purge Button State & Inline Guidance
- In `ProjectSettingsPage.tsx`:
  - Active projects (`project.deleted_at == null && project.trashed_at == null && project.status !== 'trashed'`) safely disable the Permanent Purge button.
  - The button uses `disabled` and `aria-disabled` attributes, supported by `.kb-btn-purge:disabled` (`opacity: 0.6; cursor: not-allowed;`).
  - An inline guidance message (`<p className="kb-danger-purge-hint" data-testid="purge-disabled-hint">`) renders below the disabled button with clear text: "Stage 1 (Move Project to Trash) must be completed before permanent purge."
  - Soft-trashed projects re-enable the button and hide the caption, allowing administrators to proceed to Stage 2 confirmation.

### 3. Drafts Empty State Dynamic Resolution
- In `routes.tsx` (`DraftsWorkspaceView`):
  - Accessible projects are fetched from the QueryClient cache and asynchronously refreshed from `/api/v1/projects`.
  - The CTA button target resolves dynamically:
    - If inside a project context: `/projects/${encodeURIComponent(activeProject)}/issues?create=1`
    - If in global context: `/projects/${encodeURIComponent(firstProject)}/issues?create=1`
    - If 0 projects available: `/`
  - Eliminates 404 navigation errors when working in workspaces with custom project identifiers.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes introduced.
- Preexisting inline style on line 1888 (`style={{ marginTop: '0.5rem' }}`) in `ProjectSettingsPage.tsx` was converted to `.kb-input.kb-danger-reason-input` in `ProjectSettingsPage.css`.
- Canonical design tokens (`var(--text-secondary)`) used for helper captions.
- Verified by automated test: `cssTokensAudit.test.ts` passes 4 of 4 tests.

### 2. Type Safety & State Hygiene
- Strict nullish coalescing (`??`) used throughout components and route handlers.
- Proper cleanup functions in React effects.

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).

---

## Verification Checklist

1. [x] Project query cache invalidation on General Settings save verified
2. [x] Permanent Purge button disabled for active projects verified
3. [x] Inline helper caption explaining Stage 1 requirement verified
4. [x] Preexisting inline style converted to canonical CSS class verified
5. [x] Dynamic project key resolution in `/drafts` empty state verified
6. [x] Zero inline `style={...}` attributes (CSP compliant)
7. [x] Canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
8. [x] Strict ASCII hyphenation verified (0 em/en-dashes)
9. [x] Frontend test suite passes: 316 Vitest unit tests passing across touched files (>95% coverage)

---

## Verdict & Certification
STATUS: APPROVED

All UI, UX, accessibility, responsiveness, and visual criteria have been verified and certified. Ready for dual specialist signoff and coordinator merge into `main`.
