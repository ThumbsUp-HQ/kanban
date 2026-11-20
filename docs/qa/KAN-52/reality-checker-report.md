# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Passive forensic audit only (`read_file` across `docs/qa/KAN-52/` verification artifacts, all 8 PNG screenshots in `docs/qa/KAN-52/screenshots/`, and on-disk implementation/test files; zero shell commands run, zero URLs visited, zero files modified).
**Evidence Captured**:
- Verification packet: `docs/qa/KAN-52/message-to-reality-checker.md`, `docs/qa/KAN-52/changed-files-manifest.txt`, `docs/qa/KAN-52/git-diff.patch`, `docs/qa/KAN-52/unit-test-results.txt`, `docs/qa/KAN-52/build-or-typecheck.txt`, `docs/qa/KAN-52/live-fullstack-proof.txt`, `docs/qa/KAN-52/api-specialist-review.md`, `docs/qa/KAN-52/ui-specialist-review.md`.
- Visual evidence (8 live screenshots from `kanban-liveqa-2` at commit `7913c2c8`): `live-navigator-desktop-light.png`, `live-navigator-desktop-dark.png`, `live-navigator-assign-to-me-desktop.png`, `live-navigator-query-jql-desktop.png`, `live-navigator-collapsed-rail-desktop.png`, `live-navigator-tablet.png`, `live-navigator-mobile-list.png`, `live-navigator-mobile-detail.png`.
- Code inspection: `kanban/web/src/features/views/IssueNavigatorBar.tsx`, `kanban/web/src/features/views/IssueNavigatorBar.css`, `kanban/web/src/features/list/ListView.tsx`, `kanban/web/src/features/drawer/IssueSurface.tsx`, `kanban/web/src/features/drawer/IssueSurface.css`, `kanban/web/src/features/views/listTable.css`, `kanban/web/src/features/views/viewRegistry.tsx`, `kanban/web/src/features/views/predicateParser.ts`, `kanban/web/src/app/LayoutSwitcher.tsx`, `kanban/web/src/app/Sidebar.tsx`, `kanban/api/v1/schemas/issues.py`, `kanban/services/issues.py`.
**QA Cross-Validation**:
- **Challenged `ui-specialist-review.md` and `live-fullstack-proof.txt` findings**: Both documents certified `APPROVED` / `PASS` while missing two concrete defects directly visible in the submitted screenshots:
  1. In `live-navigator-collapsed-rail-desktop.png`, collapsing the left sidebar widens `.surface--split` past `879px`, causing `.surface__quick-props` (`display: none` above 879px in `IssueSurface.css` lines 509-535) to hide all content inside the open `DETAILS` card, leaving an empty white box.
  2. In `live-navigator-query-jql-desktop.png`, filtering via JQL (`project = "KAN" AND status = "Purple Review"`) narrows the left rail to `KAN-5`, `KAN-4`, `KAN-3`, yet the right detail pane remains on `#KAN-1` (`In Progress`) and displays `1 of 3` in the pager with `^` and `v` disabled.
- **Confirmed `api-specialist-review.md` API contract fixes**: `handleAssignToMe` in `IssueSurface.tsx` calls `railApi.addAssignee` (`POST /api/v1/issues/{issue_ref}/assignees`), surfaces HTTP errors via `conflictError` / `conflict-banner`, and `safeCopyToClipboard` prevents unhandled `NotAllowedError` rejections. `created_at` and `updated_at` are present on `IssueResponse` (`kanban/api/v1/schemas/issues.py` lines 294-295).
- **Packet hygiene mismatch**: `docs/qa/KAN-52/message-to-reality-checker.md` still cites stale Round 0 details (`151/151` frontend tests, `62` migrations / `p4_23_oidc_link_intent_fk`), whereas `unit-test-results.txt` (`161` passed across 10 targeted Vitest files, `16` passed in `test_issues.py`) and `build-or-typecheck.txt` (`63` migrations / `p4_24_agent_safe_sequences` at `7913c2c8`) reflect later commits. Also note `IssueNavigatorBar.tsx` and `IssueNavigatorBar.css` live under `kanban/web/src/features/views/`, not `kanban/web/src/features/list/`.

## 📸 Complete System Evidence
**Visual Documentation**:
- Desktop Light (`1440x900` inferred from aspect): `live-navigator-desktop-light.png`
- Desktop Dark: `live-navigator-desktop-dark.png`
- Desktop Assign-to-Me interaction: `live-navigator-assign-to-me-desktop.png`
- Desktop JQL Query interaction: `live-navigator-query-jql-desktop.png`
- Desktop Collapsed Sidebar: `live-navigator-collapsed-rail-desktop.png`
- Tablet (`768x1024`): `live-navigator-tablet.png`
- Mobile List (`390x844`): `live-navigator-mobile-list.png`
- Mobile Detail (`390x844`): `live-navigator-mobile-detail.png`

**What System Actually Delivers**:
- **Desktop Light & Dark (`live-navigator-desktop-light.png`, `live-navigator-desktop-dark.png`)**: Sidebar shows `📋 Issues` under `Work Items`; top `IssueNavigatorBar` renders Search, Basic/Query toggle, 5 dropdowns (`All States`, `All Priorities`, `All Assignees`, `All Labels`, `All Cycles`), `☆ Favorites only`, and `VIEWS: Active Review Queue`. Left master rail shows `Order by Updated`, sort direction `↓`, refresh, `+`, and 2-line cards `KAN-6` through `KAN-1`. Right split detail pane renders breadcrumb `Kanban Core / KAN-1`, `#KAN-1`, `6 of 6`, action toolbar, collapsible sections (`DETAILS`, `DESCRIPTION`, `ATTACHMENTS`, `SUB-ISSUES & LINKED ISSUES`, `ACTIVITY / COMMENTS`), and right column (`PEOPLE`, `DATES`, `DEVELOPMENT`). Note: three separate `In Progress` state `<select>` controls appear simultaneously on desktop (`header-state-select`, `split-state-select`, `quick-props-state-select`).
- **Assign-to-Me (`live-navigator-assign-to-me-desktop.png`)**: Clicking `Assign to me` updates both `DETAILS` (`Assignee: Server Administrator`) and `PEOPLE` (`Server Administrator`), though the `Assign to me` button wraps awkwardly onto two lines (`Assign to` / `me`) inside the 280px right column.
- **JQL Query (`live-navigator-query-jql-desktop.png`)**: Entering `project = "KAN" AND status = "Purple Review"` filters the left rail to 3 cards (`KAN-5`, `KAN-4`, `KAN-3`), while the right pane stays on `#KAN-1` (`In Progress`) showing `1 of 3` and `✓ Copied link!` / `✓ Copied!`.
- **Collapsed Sidebar (`live-navigator-collapsed-rail-desktop.png`)**: Left navigation collapses cleanly, but the `DETAILS` section body becomes completely empty/blank, and `✓ Copied link!` from an earlier action remains stuck active alongside `✓ Copied!`.
- **Tablet & Mobile (`live-navigator-tablet.png`, `live-navigator-mobile-list.png`, `live-navigator-mobile-detail.png`)**: At 768px and 390px, `?peek=KAN-1` expands `.surface--split` as a full-screen overlay (`position: fixed; inset: 0`), hiding `header-state-select` at `<= 768px`, while `mobile-list.png` (without `?peek=`) preserves the scrollable card list without trapping the user. In `tablet.png` and `mobile-detail.png`, `DETAILS` still renders an oversized 44px `In Progress` `<select>` duplicating `split-state-select` directly above it because `.split-side-col` in `IssueSurface.css` line 874 matches nothing.

## 🧪 Integration Testing Results
- **End-to-End User Journeys**: **FAIL**
  - *Journey 1 (Basic Render & Assign-to-Me)*: PASS visually (`live-navigator-desktop-light.png` -> `live-navigator-assign-to-me-desktop.png`, HTTP 201 on `POST /api/v1/issues/KAN-1/assignees`).
  - *Journey 2 (JQL Filter + Master-Detail Sync)*: **FAIL** (`live-navigator-query-jql-desktop.png` shows `#KAN-1` remaining open with bogus `1 of 3` counter when filtered to `KAN-5`, `KAN-4`, `KAN-3`).
  - *Journey 3 (Collapsed Sidebar Triage)*: **FAIL** (`live-navigator-collapsed-rail-desktop.png` shows `DETAILS` section body disappearing completely).
- **Cross-Device Consistency**: **NEEDS WORK** (Desktop wide / collapsed sidebar breaks `DETAILS` visibility; tablet/mobile detail retains duplicate `quick-props-state-select` due to nonexistent `.split-side-col` selector; `Assign to me` wraps to two lines).
- **Performance Validation**: **PASS** (Measured in `live-fullstack-proof.txt`: Desktop 898 ms, Tablet 874 ms, Mobile List 840 ms, all `< 3000ms`; 0 JS console errors, 0 page errors, 0 5xx responses, 0 CSP violations in scoped run).
- **Specification Compliance**: **FAIL**
  - *Spec (`message-to-reality-checker.md`)*: "2-Column Collapsible Detail Layout: Left / Main column: Details panel..." -> **FAIL** on wide/collapsed desktop where `DETAILS` is blank (`live-navigator-collapsed-rail-desktop.png`).
  - *Spec (`message-to-reality-checker.md`)*: "sequential position indicator `1 of N` (`data-testid="issue-navigator-position"`) with `^` previous and `v` next, fully synced with `J`/`K` and `ArrowUp`/`ArrowDown`" -> **FAIL** when filtered (`live-navigator-query-jql-desktop.png` shows `1 of 3` for non-matching `KAN-1`) and when sorted via `Order by` (because `ListView.tsx` sorts `sortedIssues` locally in component state while `viewRegistry.tsx` line 1072 passes unsorted `filteredIssues` to `IssueSurfaceRoot`).

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
- None of the previously reported HTTP 422 assignee errors or `NotAllowedError` clipboard crashes remain; those two remediations are verified fixed in code and live screenshots.

**New Issues Discovered**:
1. **Critical - Empty `DETAILS` Section on Wide / Collapsed Desktop (`live-navigator-collapsed-rail-desktop.png`)**:
   - `IssueSurface.tsx` lines 1473-1511 place `<div className="surface__quick-props">` inside `<details open data-testid="split-section-details">`.
   - `IssueSurface.css` lines 509-535 set `.surface__quick-props { display: none; }` by default and only show it under `@container issue-surface (max-width: 879px)` or `@media (max-width: 879px)`. When the sidebar collapses on 1440px (or on wider monitors), `.surface--split` exceeds `879px` and `DETAILS` renders completely empty.
2. **Critical - Master-Detail & Sequential Pager Desync on Filter and Sort (`live-navigator-query-jql-desktop.png`)**:
   - `viewRegistry.tsx` lines 951-962 keep `activePeekKey = peekParam` even when `peekParam` (`KAN-1`) is excluded from `filteredIssues`.
   - `IssueSurface.tsx` lines 276-278 fall back to `displayIndex = 1` when `currentIndex === -1`, displaying `1 of 3` for an issue (`#KAN-1`) not in the 3-item list while disabling `^` and `v`.
   - `ListView.tsx` lines 75-76 and 136-189 manage `sortBy` and `sortDir` in local state without lifting sorted order to `IssuesWorkspaceRoute`, so `IssueSurfaceRoot` (`issuesList={filteredIssues}` at `viewRegistry.tsx` line 1072) paginates in unsorted order whenever the user changes `Order by` or direction.
3. **Medium - Broken CSS Selector Leaves Duplicate State Select on Mobile/Tablet (`IssueSurface.css` lines 874-876)**:
   - `.surface--split .split-side-col [data-testid="quick-props-state-select"]` targets `.split-side-col`, which does not exist in `IssueSurface.tsx` (uses `.split-main-col` / `.split-right-column`). Consequently `tablet.png` and `mobile-detail.png` still show a tall 44px State select inside `DETAILS` right below `split-state-select`, and desktop shows 3 separate State dropdowns simultaneously.
4. **Medium - Shared `copyTimeoutRef` Leaves Feedback Labels Stuck (`IssueSurface.tsx` lines 163, 1238-1258)**:
   - `handleShareExport` and `handleCopyBranch` overwrite the same `copyTimeoutRef.current`, cancelling the first timer when both are clicked within 2s (visible in `live-navigator-collapsed-rail-desktop.png`, where `✓ Copied link!` remains stuck alongside `✓ Copied!`).
5. **Medium - `favoritesOnly` Filter Does Not React to `kb:favorites-changed` (`viewRegistry.tsx` lines 563-574, 590)**:
   - `filteredIssues` reads `localStorage.getItem('kb_favorite_issues')` inside `useMemo` without subscribing to `kb:favorites-changed`, so toggling a star while `Favorites only` is active leaves stale cards in the rail.
6. **Medium - Missing "Save View" Action & Layout Polish**:
   - `IssueNavigatorBar` in `layout === 'list'` (`viewRegistry.tsx` lines 972-991) provides no "Save View" trigger (unlike `FilterDisplayBar` on line 1005), and `viewRegistry.list.name` (`viewRegistry.tsx` line 64) remains `'List'` instead of `'Issues'`.
   - `.split-assign-to-me-btn` lacks `white-space: nowrap; flex-shrink: 0;`, causing `"Assign to me"` to wrap across two lines in `live-navigator-assign-to-me-desktop.png`.
   - `unit-test-results.txt` covers only 10 targeted frontend test files and `test_issues.py` (no coverage report proving the `>=95%` project invariant), and `message-to-reality-checker.md` contains stale counts/paths.

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: C+
**Design Implementation Level**: Basic-to-Good (clean card typography and light/dark token parity, undermined by broken wide-viewport `DETAILS` visibility, triple state dropdowns, and master-detail desync)
**System Completeness**: 80% of KAN-52 specification working end-to-end
**Production Readiness**: NEEDS WORK

## 🔄 Deployment Readiness Assessment
**Status**: NEEDS WORK

**Required Fixes Before Production**:
1. **Fix `DETAILS` visibility at `> 879px`**: Ensure `.surface--split .split-section-body .surface__quick-props` (or dedicated split details layout) is always visible (`display: flex`) regardless of container/viewport width, verified with a collapsed-sidebar 1440px+ screenshot (`live-navigator-collapsed-rail-desktop.png` currently shows an empty box).
2. **Synchronize Master Rail Filtering & Sorting with Detail Pane and Pager**:
   - Lift `sortBy` and `sortDir` state out of `ListView.tsx` into `IssuesWorkspaceRoute` (`viewRegistry.tsx`) so `IssueSurfaceRoot` receives the exact sorted `filteredIssues` array as `issuesList`.
   - When filters/JQL exclude the active `activePeekKey`, auto-select the first matching issue (on desktop) or show an explicit empty/unmatched state instead of keeping `#KAN-1` open with a false `1 of 3` pager (`live-navigator-query-jql-desktop.png`).
3. **Clean Up Split-Mode CSS & Interaction Bugs**:
   - Fix or remove the dead `.split-side-col` selector in `IssueSurface.css` line 874 and eliminate redundant duplicate state dropdowns (`tablet.png` / `mobile-detail.png` / desktop).
   - Separate `copyBranchTimeoutRef` and `copyShareTimeoutRef` in `IssueSurface.tsx` so `✓ Copied link!` resets properly (`live-navigator-collapsed-rail-desktop.png`).
   - Add `white-space: nowrap; flex-shrink: 0;` to `.split-assign-to-me-btn` (`live-navigator-assign-to-me-desktop.png`).
   - Subscribe `IssuesWorkspaceRoute` to `kb:favorites-changed` so `favoritesOnly` updates live.
4. **Refresh Packet & Test Evidence**: Update `docs/qa/KAN-52/message-to-reality-checker.md` to match HEAD (`7913c2c8`), add unit tests covering filtered-out `peekParam`, lifted sort order + pager sync, and wide-viewport `DETAILS` rendering, and include full Vitest/Pytest + coverage verification.

**Timeline for Production Readiness**: 1 focused remediation cycle (2-4 hours for fixes, unit tests, live Playwright re-capture, and re-audit).
**Revision Cycle Required**: YES

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Collapsed-sidebar and wide-desktop `DETAILS` rendering must display State, Priority, and Assignee cleanly without disappearing.
- JQL/Basic filter application must reconcile `activePeekKey` and sequential pager counts (`1 of N`) with the filtered and sorted rail.
- Both `ui-specialist-review.md` and live QA proofs must verify visual contents of every card/section in screenshots rather than checking only DOM testids.

**Quality Targets**:
- 0 empty collapsible sections across 390px, 768px, 1440px (sidebar open and collapsed), and 1920px viewports.
- 100% order and membership parity between `ListView` cards and `IssueSurfaceRoot` pager (`1 of N`, `^`, `v`, `J`/`K`).
- `>=95%` unit test coverage on changed modules with 0 skipped/stale assertions and synchronized verification artifacts.

**Evidence Requirements**:
- Updated `live-navigator-collapsed-rail-desktop.png` showing populated `DETAILS` and non-stuck Share/Copy buttons.
- Updated `live-navigator-query-jql-desktop.png` showing the right detail pane synced to one of the 3 matching `Purple Review` issues (e.g., `KAN-5` at `1 of 3`) plus a screenshot/test proving `Order by` sort changes update `1 of N` navigation order.
- Updated `live-navigator-tablet.png`, `live-navigator-mobile-detail.png`, and `live-navigator-assign-to-me-desktop.png` showing no duplicate state select inside `DETAILS` and no wrapped `Assign to me` button.
- Fresh `unit-test-results.txt`, `build-or-typecheck.txt`, and `message-to-reality-checker.md` aligned to the exact commit SHA under test.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-52/
**Re-assessment Required**: After fixes implemented
