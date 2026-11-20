# Verification Evidence Packet: KAN-53

## Ticket Metadata
- **Ticket ID**: `KAN-53`
- **Title**: `[KB-UX-LIST-02] Auto-Collapse Non-Focused Projects in Sidebar While Preserving Manual Expand Toggles`
- **Branch**: `main` (integrated at commit `7913c2c8`)
- **Target Container**: `kanban-liveqa-2` (`http://127.0.0.1:18962`, PostgreSQL 16 + FORCE RLS)
- **Live Stack Verdict**: `LIVE_STACK_VERDICT: PASS`
- **Component**: `kanban/web/src/app/Sidebar.tsx` and `kanban/web/src/app/Sidebar.test.tsx`

---

## 1. Summary of Changes

### `kanban/web/src/app/Sidebar.tsx`
- **Project Key Extraction (`extractProjectKeyFromPath`)**:
  - Implemented and exported pure utility `extractProjectKeyFromPath(path: string): string | null` supporting canonical project route structures:
    - `/projects/:projectKey` (and subpaths e.g. `/projects/:projectKey/issues`, `/projects/:projectKey/views`)
    - `/w/:workspaceSlug/p/:projectKey` (and subpaths)
    - `/w/:workspaceSlug/projects/:projectKey` (and subpaths)
  - Complies with strict regex execution standards (`RegExp#exec()` and `??`).
- **Focused Project State Tracking**:
  - Derived `focusedProjectKey = useMemo(() => extractProjectKeyFromPath(currentPath), [currentPath])`.
  - Implemented `focusProject(targetKey)` with `useCallback` depending on `[projectList, setExpandedProjects]`. Setting `expandedProjects` guarantees `[targetKey]: true` and all other registered projects in `projectList` are mapped to `false`.
  - Added route navigation synchronization via `useEffect` tracking `prevFocusedKeyRef`, expanding the active route's project and collapsing others whenever navigating into a different project route.
- **Display Resolution & Non-Project Route Preservation**:
  - Evaluated expansion state via:
    `const isProjExpanded = expandedProjects[proj.key] ?? (focusedProjectKey ? proj.key === focusedProjectKey : true);`
    Ensures immediate, flicker-free rendering of focused project on initial deep link while collapsing non-focused projects.
  - On non-project routes (such as `/`, `/stickies`, `/workspaces`), `focusedProjectKey` is `null` and existing expansion states are preserved.
- **Manual Toggle vs Sub-Route Click Independence**:
  - Clicking the arrow button (`.kb-project-expand-row`) toggles expansion independently for that specific project without collapsing others:
    `toggleProjectExpanded(proj.key)` flips `!isProjExpanded`.
  - Clicking `.kb-project-subitems` (containing Work Items, Issues, Views, Board, Table, Calendar, Timeline, Cycles, Modules, and Custom Fields) triggers `focusProject(proj.key)`, auto-focusing the selected project and collapsing all others.
- **Design & Quality Standards**:
  - 0 inline JSX `style={{...}}` properties.
  - 100% canonical CSS tokens (`cssTokensAudit.test.ts` 4/4 PASS).
  - 0 competitor self-descriptions or terminology.
  - 0 em/en dashes.

### `kanban/web/src/app/Sidebar.test.tsx`
- Added comprehensive unit tests covering:
  - `extractProjectKeyFromPath` path handling across standard, workspace-scoped, and non-project paths.
  - Multi-project sidebar rendering (`KAN` and `SEC`).
  - Auto-collapsing of non-focused projects (`KAN` collapses when navigating to or clicking `SEC` subitems).
  - Preserving independent manual expand/collapse toggles via arrow button clicks.
  - Preserving manual toggles when on non-project routes (`/`).
  - Strict absence of `act(...)` warnings through complete async lifecycle wrapping with `waitFor`.

---

## 2. Test & Coverage Evidence

### Unit Test Execution Output (`docs/qa/KAN-53/unit-test-results.txt`)
Command:
```bash
pnpm --dir kanban/web exec vitest run src/app/Sidebar.test.tsx src/styles/__tests__/cssTokensAudit.test.ts --coverage
```

Result:
```
Test Files  2 passed (2)
     Tests  35 passed (35)
  Duration  5.21s

% Coverage report from v8
-------------|---------|----------|---------|---------|-------------------
File         | % Stmts | % Branch | % Funcs | % Lines | Uncovered Line #s 
-------------|---------|----------|---------|---------|-------------------
All files    |   99.24 |    95.13 |   98.38 |   99.59 |                   
 Sidebar.tsx |   99.24 |    95.13 |   98.38 |   99.59 | 1091              
-------------|---------|----------|---------|---------|-------------------
```

Coverage achieves:
- Statements: 99.24% (>=95% required)
- Branch: 95.13% (>=95% required)
- Functions: 98.38% (>=95% required)
- Lines: 99.59% (>=95% required)
- `act(...)` warnings: Exactly 0.

### Static Verification Gates (`docs/qa/KAN-53/build-or-typecheck.txt` at HEAD `7913c2c8`)
1. **TypeScript Typecheck (`tsc -b --noEmit`)**: Clean (Exit code 0, 0 errors).
2. **ESLint (`eslint . --max-warnings 0`)**: Clean (Exit code 0, 0 warnings).
3. **CSS Tokens Audit (`cssTokensAudit.test.ts`)**: 4 passed (100% token compliance).
4. **Production Build (`vite build`)**: Clean (Built in 1.22s, exit code 0).
5. **No Dashes Audit (`python3 -m scripts.check_no_dashes --all`)**: Clean (0 em/en-dashes).

---

## 3. Live Full-Stack Proof & Visual Artifacts

Zero-mock Playwright testing against `kanban-liveqa-2` (`http://127.0.0.1:18962`, commit `7913c2c8`) confirmed:
- Page load and navigation timings < 3000ms threshold (list 857ms, clicking SEC 279ms, clicking Home 285ms).
- Live screenshots captured and verified:
  1. `docs/qa/KAN-53/screenshots/live-sidebar-kan-focused-desktop-light.png`
  2. `docs/qa/KAN-53/screenshots/live-sidebar-kan-focused-desktop-dark.png`
  3. `docs/qa/KAN-53/screenshots/live-sidebar-sec-focused-desktop-light.png`
  4. `docs/qa/KAN-53/screenshots/live-sidebar-both-expanded-desktop-light.png`
  5. `docs/qa/KAN-53/screenshots/live-sidebar-home-preserved-desktop-light.png`
  6. `docs/qa/KAN-53/screenshots/live-sidebar-kan-focused-tablet.png`
  7. `docs/qa/KAN-53/screenshots/live-sidebar-kan-focused-mobile.png`
- Runtime telemetry: 0 console JS errors, 0 page errors, 0 5xx responses, 0 CSP violations.
- `OVERALL LIVE_STACK_VERDICT: PASS`
