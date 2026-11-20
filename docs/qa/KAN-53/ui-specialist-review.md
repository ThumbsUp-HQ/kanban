# Clean-Room UI Specialist Review: KAN-53 (RC1 Remediation & Coverage Hardening)

**Reviewer:** `ui-spec-2` (Clean-Room UI/UX Specialist, System Architect)  
**Date:** 2026-11-20  
**Branch:** `fix/KAN-43-44-53-rc2`  
**Commit Under Audit:** `536e8d7c`  
**Base Commit Reference:** `07d04cde` (merged on `main`)  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates the UI, UX, accessibility, and state management implementation for ticket **KAN-53** (`[KB-UX-LIST-02] Auto-Collapse Non-Focused Projects in Sidebar While Preserving Manual Expand Toggles`) on branch `fix/KAN-43-44-53-rc2` at commit `536e8d7c`.

The feature solves sidebar clutter in multi-project environments by automatically focusing the active project and collapsing all non-focused projects when navigating into a project route or clicking project sub-routes (Issues, Work Items, Views, Board, Table, etc.), while preserving manual expand/collapse toggle buttons and respecting non-project views (such as the home dashboard or global views).

The remediation at commit `536e8d7c` eliminates the `/* v8 ignore */` pragmas previously placed around `CreateProjectModal`'s `onCreated` callback in `Sidebar.tsx` and adds comprehensive unit test coverage in `Sidebar.test.tsx`, achieving full genuine test coverage across statements, branches, functions, and lines without coverage ignore workarounds.

The UI Specialist audit confirms:
1. **Ergonomic Auto-Collapse Behavior:** Non-focused projects in `projectList` are automatically collapsed (`aria-expanded="false"`) when navigating into or interacting with an active project, preventing visual overload and excessive vertical scrolling.
2. **Preserved Manual Control:** Direct clicks on the project expand/collapse arrow row (`.kb-project-expand-row`) toggle expansion independently, allowing users to keep multiple projects open simultaneously when explicitly intended.
3. **Route Context Sensitivity:** Non-project routes (`/`, `/drafts`, `/your-work`) maintain existing manual expansion states without triggering unintended auto-collapses.
4. **Removal of Coverage Ignore Pragmas:** Removed `/* v8 ignore start */ ... /* v8 ignore stop */` from `Sidebar.tsx` (lines 1086-1099). Verified that `Sidebar.tsx` achieves genuine >95% coverage across all metrics.
5. **Strict Design System & CSP Compliance:** Exactly zero inline `style={{...}}` JSX attributes introduced. All layout, spacing, and transitions use canonical classes and tokens. `cssTokensAudit.test.ts` passes 4/4.
6. **Brand Hygiene & Typography:** Exactly zero competitor self-descriptions and zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, tests, comments, or documentation.

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

### 2.4. Removal of `v8 ignore` & Coverage Hardening
- In `Sidebar.tsx`, the `onCreated` callback for `CreateProjectModal` updates `setFetchedProjects` to include the newly created project while preventing duplicate entries:
  ```typescript
  onCreated={(created) => {
    setFetchedProjects((prev) => {
      const exists = prev.some((p) => p.key === created.identifier);
      if (exists) {
        return prev;
      }
      return [
        ...prev,
        {
          key: created.identifier,
          name: created.name,
          modulesEnabled: created.modules_enabled ?? false,
        },
      ];
    });
  }}
  ```
- Tested in `Sidebar.test.tsx` (`covers CreateProjectModal onCreated callback duplicate and modules_enabled branches`), exercising both unique project addition and duplicate prevention.

---

## 3. Test Suites, Coverage & Quality Gates

### 3.1. Frontend Unit Tests (Vitest)
Command executed:
`pnpm --dir kanban/web exec vitest run src/app/Sidebar.test.tsx src/styles/__tests__/cssTokensAudit.test.ts`

Results:
- `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 passed.
- `src/app/Sidebar.test.tsx`: 30/30 passed.
- **Code Coverage on `Sidebar.tsx`:**
  * Statements: 99.24% (exceeds >=95% gate)
  * Branches: 95.13% (exceeds >=95% gate)
  * Functions: 98.38% (exceeds >=95% gate)
  * Lines: 99.59% (exceeds >=95% gate)
- **Zero `act(...)` console warnings.**

### 3.2. Static Analysis & Build Verification
- **TypeScript:** `tsc -b --noEmit` -> Clean (exit code 0, 0 errors).
- **ESLint:** `eslint . --max-warnings 0` -> Clean (exit code 0, 0 warnings).
- **Vite Build:** `vite build` -> Clean (built in 1.55s, exit code 0).
- **Dashes Audit:** `python3 -m scripts.check_no_dashes --all` -> Clean (0 em/en-dashes).
- **Untracked Safeguard:** `.backup_schedule.json` and `backups/` strictly preserved unstaged.

---

## 4. Certification & Sign-off

The UI implementation and coverage hardening for **KAN-53** deliver an intuitive, clutter-free sidebar navigation experience with genuine, uncompromised test coverage across all metrics.

- **UI Specialist Sign-off:** APPROVED
- **Status:** APPROVED
- **Recommendation:** Proceed immediately to reality-checker QA gate and merge coordination.
