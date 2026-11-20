# KAN-12 Verification Proof Packet: Air-Gap Topbar Event Sync, Auth Studio Group Reset-Password & @slug Display, and Workspace Settings #tab-* Hash Anchors

## Executive Summary
This packet provides passive forensic proof for Wave P3-6 ticket **KAN-12** (`[KB-P3-AUDIT-06] Fix Air-Gap Topbar Event Sync, Auth Studio Group Reset-Password & @slug Display, and Workspace Settings #tab-* Hash Anchors`).

All 4 scoped problems are completely resolved with zero regressions, >=95% test coverage on all touched files, zero inline styles, and zero em/en-dashes.

---

## Scoped Problems and Implementation Breakdown

### Problem 1: Sync Topbar Air-Gap Indicator on `kb:system-status-changed`
- **Hook Listener Registration:** In `kanban/web/src/app/useSystemStatus.ts` and `kanban/web/src/features/system/useSystemStatus.ts`, registered a `window.addEventListener('kb:system-status-changed', ...)` listener with full cleanup on unmount (`return () => window.removeEventListener(...)`).
- **Query Cache Invalidation:** The event listener invalidates `queryClient.invalidateQueries({ queryKey: ['system', 'status'] })` so that any updates to system air-gap settings immediately refresh the query cache across the app without pressing F5.
- **Settings Dispatch & Mutation:** In `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx`, saving Workspace Settings with modified Air-Gap Mode immediately invalidates `['system', 'status']` and dispatches `new CustomEvent('kb:system-status-changed')`.
- **Topbar Display:** In `kanban/web/src/app/Topbar.tsx`, the air-gap badge `📴 Air-Gap Active` consumes `useSystemStatus()`, rendering reactively upon event dispatch.

### Problem 2: Hide `Reset Password` on Group and Agent Principals
- **Strict Role / Kind Guarding:** In `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`, the `Reset Password` action button and table action column strictly check `(u.type ?? (u as unknown as { kind?: string }).kind ?? 'USER').toUpperCase() === 'USER'`.
- **Zero Actions for Groups and Agents:** Neither `GROUP` nor `AGENT` principals ever render a Reset Password button.
- **Modal Dialog Protection:** The Reset Password dialog modal is additionally guarded to ensure it only renders when the active target principal is a user.

### Problem 3: Group `@slug` Handle Formatting and UUID Sanitization
- **Backend Slug Generation:** In `kanban/admin/principal_service.py`, added `_slugify_or_default()` to derive clean slugs from group names or display names (e.g. `@infra-team` from `Infrastructure Team`), avoiding RFC 4122 UUID leaks in `handle`.
- **Frontend Handle Formatter:** In `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`, `formatHandle()` handles raw slugs, strips leading/trailing hyphens and @ prefixes, checks against UUID regexes to prevent raw UUID display, and formats as `@<slug>`.

### Problem 4: Add `id="tab-*"` Attributes and URL Fragment Hash Navigation to Workspace Settings Tabs
- **Tab Element Attributes:** In `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx`, added `id="tab-general"`, `id="tab-members"`, and `id="tab-groups"` attributes alongside existing `data-testid` and `aria-controls` attributes on tab buttons.
- **Bidirectional Hash Synchronization:**
  - Initial active tab parsed from `window.location.hash` or router `location.hash` (`#tab-general`, `#tab-members`, `#tab-groups`).
  - `window.addEventListener('hashchange', ...)` registered with unmount cleanup to update active tab on browser back/forward or external anchor clicks.
  - Clicking any tab button updates `window.location.hash` (`#tab-general`, `#tab-members`, `#tab-groups`) without full page reloads.

---

## Verification and Coverage Metrics

### Test Suite Execution
- **Backend Coverage:** `kanban/admin/principal_service.py` achieves **96%** coverage (433 stmts, 9 missed, 164 branches, 14 missed).
  - 16/16 tests passing in `kanban/tests/api/test_admin_principals.py`.
- **Frontend Coverage:** All touched frontend files achieve **>= 95%** coverage across statements, branches, functions, and lines:
  - `src/app/useSystemStatus.ts`: 100% Statements, 100% Branches, 100% Functions, 100% Lines.
  - `src/features/system/useSystemStatus.ts`: 100% Statements, 100% Branches, 100% Functions, 100% Lines.
  - `src/features/admin-auth/AuthStudioPage.tsx`: 98.28% Statements, 95.68% Branches, 99.00% Functions, 100% Lines.
  - `src/features/settings/WorkspaceSettingsPage.tsx`: 99.67% Statements, 95.47% Branches, 100% Functions, 100% Lines.
  - 72/72 tests passing across all 4 frontend test suites (`useSystemStatus.test.tsx`, `WorkspaceSettingsPage.test.tsx`, `AuthStudioPage.test.tsx`).

### Static Analysis and Gate Verification
- **Ruff Check:** Passed with 0 errors (`uv run ruff check kanban/admin/principal_service.py kanban/tests/api/test_admin_principals.py`).
- **MyPy:** Passed with 0 issues (`uv run mypy kanban/admin/principal_service.py kanban/tests/api/test_admin_principals.py`).
- **Lint Imports:** 2 kept, 0 broken (`uv run lint-imports`).
- **TypeScript:** Clean compilation (`pnpm --dir kanban/web exec tsc -b`).
- **ESLint:** Passed with 0 warnings (`pnpm --dir kanban/web run lint`).
- **CSS Design Tokens Audit:** Passed 4/4 tests (`pnpm --dir kanban/web run test:unit src/styles/__tests__/cssTokensAudit.test.ts`), with 0 inline `style={...}` attributes.
- **Punctuation Check:** 0 em-dashes or en-dashes (`python3 -m scripts.check_no_dashes --all`).

---

## Verbatim Artifact References
- Unit test and coverage logs: [unit-test-results.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan12-257137e5/docs/qa/KAN-12/unit-test-results.txt)
- Static analysis and typecheck logs: [build-or-typecheck.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan12-257137e5/docs/qa/KAN-12/build-or-typecheck.txt)
- Changed files manifest: [changed-files-manifest.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan12-257137e5/docs/qa/KAN-12/changed-files-manifest.txt)
- Full diff: [git-diff.patch](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan12-257137e5/docs/qa/KAN-12/git-diff.patch)
