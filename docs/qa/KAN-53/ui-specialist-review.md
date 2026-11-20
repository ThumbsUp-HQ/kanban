# Clean-Room UI Specialist Review: KAN-53

**Reviewer:** `ui-spec-2` (Clean-Room UI/UX Specialist, System Architect)  
**Date:** 2026-11-20  
**Branch:** `feat/KAN-53`  
**Commit Under Audit:** `c9f80f38a9624c509e8cc6c40de7f7e5797b44c4`  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates the UI, UX, accessibility, and state management implementation for ticket **KAN-53** (`[KB-UX-LIST-02] Auto-Collapse Non-Focused Projects in Sidebar While Preserving Manual Expand Toggles`) on branch `feat/KAN-53`.

The feature solves sidebar clutter in multi-project environments by automatically focusing the active project and collapsing all non-focused projects when navigating into a project route or clicking project sub-routes (Issues, Work Items, Views, Board, Table, etc.), while preserving manual expand/collapse toggle buttons and respecting non-project views (such as the home dashboard or global views).

The UI Specialist audit confirms:
1. **Ergonomic Auto-Collapse Behavior:** Non-focused projects in `projectList` are automatically collapsed (`aria-expanded="false"`) when navigating into or interacting with an active project, preventing visual overload and excessive vertical scrolling.
2. **Preserved Manual Control:** Direct clicks on the project expand/collapse arrow row (`.kb-project-expand-row`) toggle expansion independently, allowing users to keep multiple projects open simultaneously when explicitly intended.
3. **Route Context Sensitivity:** Non-project routes (`/`, `/drafts`, `/your-work`) maintain existing manual expansion states without triggering unintended auto-collapses.
4. **Strict Design System & CSP Compliance:** Exactly zero inline `style={{...}}` JSX attributes introduced. All layout, spacing, and transitions use canonical classes and tokens. `cssTokensAudit.test.ts` passes 4/4.
5. **Brand Hygiene & Typography:** Exactly zero competitor self-descriptions and zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, tests, comments, or documentation.
6. **High Test Coverage & Quality Gates:** 34/34 Vitest tests passed with 99.61% statements and 95.77% branch coverage on `Sidebar.tsx`, with exactly 0 `act(...)` warnings. Complete TypeScript build (`tsc -b --noEmit`), ESLint (`--max-warnings 0`), and production Vite bundling passed cleanly.

---

## 2. Technical and UX Audit

### 2.1. Route Parsing and Project Key Extraction (`extractProjectKeyFromPath`)
- **Regular Expression Patterns:**
  ```typescript
  const PROJECT_ROUTE_PATTERN = /^\/projects\/([^/?#]+)/;
  const WORKSPACE_P_ROUTE_PATTERN = /^\/w\/[^/?#]+\/p\/([^/?#]+)/;
  const WORKSPACE_PROJECTS_ROUTE_PATTERN = /^\/w\/[^/?#]+\/projects\/([^/?#]+)/;
  ```
- **Implementation:**
  `extractProjectKeyFromPath(path)` resolves the project identifier across all three URL conventions (`/projects/:projectKey/...`, `/w/:workspaceSlug/p/:projectKey/...`, and `/w/:workspaceSlug/projects/:projectKey/...`).
- **Safety Invariant:** Uses linear RegExp matching without catastrophic backtracking. Returns `null` for root and global paths (`/`, `/drafts`, `/your-work`), ensuring non-project routes do not trigger spurious project focus changes.

### 2.2. Focus State Management (`focusProject` & Route Sync)
- **State Transition Helper:**
  ```typescript
  const focusProject = useCallback(
    (targetKey: string) => {
      setExpandedProjects(() => {
        const next: Record<string, boolean> = {};
        for (const proj of projectList) {
          next[proj.key] = proj.key === targetKey;
        }
        next[targetKey] = true;
        return next;
      });
    },
    [projectList, setExpandedProjects],
  );
  ```
  Sets the targeted project to `true` while explicitly setting all other projects in `projectList` to `false`.
- **Navigation Synchronization:**
  A `prevFocusedKeyRef` tracks the active project key across route changes in `useEffect`. When `focusedProjectKey` transitions between projects, `focusProject(focusedProjectKey)` triggers cleanly without infinite re-render loops.
- **Subitem Click Integration:**
  Attached an `onClick` handler on `.kb-project-subitems` that invokes `focusProject(proj.key)`. Clicking `Issues`, `Work Items`, `Board`, or `Views` under a project immediately focuses that project and collapses others.

### 2.3. Preservation of Manual Expand/Collapse
- **Chevron Toggle Integrity:**
  Clicking `.kb-project-expand-row` directly executes `toggleProjectExpanded(proj.key)`:
  ```typescript
  const toggleProjectExpanded = (pKey: string) => {
    setExpandedProjects((prev) => ({
      ...prev,
      [pKey]: !isProjExpanded,
    }));
  };
  ```
  This preserves the user's explicit intent: if a user clicks the chevron to peek into an adjacent project, that adjacent project opens without forcibly closing the currently active project.
- **Initial Fallback Calculation:**
  ```typescript
  const isProjExpanded =
    expandedProjects[proj.key] ??
    (focusedProjectKey ? proj.key === focusedProjectKey : true);
  ```
  If `expandedProjects[proj.key]` is not yet set in state, the project defaults to expanded if it matches `focusedProjectKey` (or expands all if no project is focused).

### 2.4. Accessibility & DOM Invariants
- `aria-expanded` attributes on project toggle buttons dynamically reflect current expansion state (`aria-expanded={isProjExpanded ? 'true' : 'false'}`).
- `.kb-project-subitems` lists cleanly unmount or collapse when not expanded, maintaining a minimal accessible DOM tree.
- Touch targets on `.kb-project-expand-row` and subitem links meet WCAG AA requirements (>44px height).

---

## 3. Test Suites, Coverage & Quality Gates

### 3.1. Frontend Unit Tests (Vitest)
Command executed:
`pnpm --dir kanban/web exec vitest run src/app/Sidebar.test.tsx src/styles/__tests__/cssTokensAudit.test.ts --coverage --coverage.include="src/app/Sidebar.tsx"`

Results:
- `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 passed (15ms)
- `src/app/Sidebar.test.tsx`: 30/30 passed (3645ms)
- **Total:** 2 test files, 34 tests passed, 0 failed, 0 warnings.
- **Code Coverage on `Sidebar.tsx`:**
  * Statements: 99.61% (exceeds >=95% gate)
  * Branches: 95.77% (exceeds >=95% gate)
  * Functions: 98.33% (exceeds >=95% gate)
  * Lines: 100.0% (exceeds >=95% gate)
- **Verified Test Scenarios:**
  1. `extractProjectKeyFromPath` correctly resolves project keys from standard `/projects/KEY/...`, short `/w/SLUG/p/KEY/...`, and full `/w/SLUG/projects/KEY/...` routes, while returning `null` for non-project routes.
  2. Auto-collapses non-focused projects when navigating between `/projects/SEC/issues` and `/projects/KAN/issues`.
  3. Clicking project subitems (`.kb-project-subitems`) triggers `focusProject`, collapsing other projects.
  4. Manual chevron arrow clicks toggle expansion independently without closing the active project.
  5. Preserves manual expansion states when navigating on non-project routes (`/`).
  6. Exactly zero `act(...)` console warnings during state transitions and event dispatches.

### 3.2. Static Analysis & Build Verification
- **TypeScript:** `pnpm --dir kanban/web exec tsc -b --noEmit` -> Clean (exit code 0, 0 errors).
- **ESLint:** `pnpm --dir kanban/web exec eslint . --max-warnings 0` -> Clean (exit code 0, 0 warnings).
- **Vite Build:** `pnpm --dir kanban/web run build` -> Clean (built in 1.11s, exit code 0).
- **Dashes Audit:** `python3 -m scripts.check_no_dashes` -> Clean (exit code 0, 0 em/en-dashes across all code and review files).
- **Untracked Safeguard:** `.backup_schedule.json` and `backups/` strictly preserved unstaged.

---

## 4. Certification & Sign-off

The UI implementation for **KAN-53** delivers an intuitive, clutter-free sidebar navigation experience while preserving user autonomy through manual toggle controls. All quality, coverage, accessibility, and architectural standards are fully met.

- **UI Specialist Sign-off:** APPROVED
- **Specialist Gate Status:** COMPLETE (UI Specialist review authored and signed off for this frontend-only ticket).
- **Recommendation:** Proceed immediately to reality-checker QA gate and merge coordination.
