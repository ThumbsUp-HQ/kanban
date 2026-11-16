# UI Specialist Review: KANBA-174

- **Reviewer:** UI / UX Design Specialist (`ui-specialist`)
- **Date:** 2026-11-16
- **Ticket:** KANBA-174 ([KB-UX-04] Jira-Style 3-Pane Split List View (|Nav|issue list|<---issue view--->|) with Sidebar Views, Single-Card Filter, and New-Tab Action)
- **Scope Inspected:**
  - `kanban/web/src/app/Sidebar.tsx`
  - `kanban/web/src/app/Sidebar.css`
  - `kanban/web/src/app/Sidebar.test.tsx`
  - `kanban/web/src/app/Topbar.tsx`
  - `kanban/web/src/app/AppShell.tsx`
  - `kanban/web/src/app/AppShell.css`
  - `kanban/web/src/features/list/ListView.tsx`
  - `kanban/web/src/features/list/ListView.test.tsx`
  - `kanban/web/src/features/list/ListRow.tsx`
  - `kanban/web/src/features/views/listTable.css`
  - `kanban/web/src/features/views/viewRegistry.tsx`
  - `kanban/web/src/features/drawer/IssueSurface.tsx`
  - `kanban/web/src/features/drawer/IssueSurface.css`
  - `docs/qa/KANBA-174/screenshots/list-3-pane-split-view.png`
  - `docs/qa/KANBA-174/screenshots/list-3-pane-split-view-tablet.png`
  - `docs/qa/KANBA-174/screenshots/list-3-pane-split-view-mobile.png`
  - `docs/qa/KANBA-174/unit-test-results.txt`
  - `docs/qa/KANBA-174/build-check.txt`
  - `docs/qa/KANBA-174/git-diff.patch`
  - `docs/qa/KANBA-174/changed-files-manifest.txt`
  - `docs/qa/KANBA-174/message-to-reality-checker.md`

---

## 1. Visual & UX Design Evaluation

### A. Compact `|Nav|` Pane with Project View Links (`Sidebar.tsx`)
- **View Switcher Relocation:** The view switcher (`List`, `Board`, `Table`, `Calendar`, `Timeline` with `KanbanIcons`) has been removed from the topbar and nested cleanly under the active project tree in `Sidebar.tsx`.
- **Compact Desktop Spatial Token:** Width is standardized to 200px (`--sidebar-w: 200px`) via CSS classes with zero inline styles.
- **Synchronized 1-Click Hide/Show Toggle:** The `Hide Nav` / `Show Nav` toggle is accessible both via the collapse button in the sidebar footer and directly inside the split view header (`⇤` / `⇥`), with state synchronized across `sessionStorage` and custom window events (`kb:toggle-sidebar`).

### B. `|issue list|` Single-Card Filter Dropdown & Row Cards (`ListView.tsx` & `listTable.css`)
- **Single-Card Filter Dropdown (`🔍 Filter & Group ▾`):** Replaces cluttered multi-row toolbars with a single, elegant popover card containing Search, State, Priority, Group-By, and Reset controls, adjacent to a primary `+ New` button.
- **Card Metadata Ergonomics:** Each issue card cleanly renders its color-coded `<StateBadge>`, corporate `<PriorityIcon>`, issue key (`KAN-X`), assignee avatar/name, and summary title.

### C. 50%-Width Docked `|<---issue view--->|` Split Layout & Zero-Remount
- **Master-Detail Flow:** When `layout === 'list'`, the page renders a 3-pane master-detail split layout (`|Nav|issue list|<---issue view--->|`).
- **50% Width Allocation:** `.surface--split` allocates 50% screen width (`flex: 1 1 50%`), automatically selecting the first issue if `?peek=` is not present in the URL.
- **Split Header Actions:** Includes the synchronized `Hide Nav` / `Show Nav` toggle, `#KAN-X` key badge, and a clean `Open in new tab (↗)` action link (`target="_blank" rel="noopener noreferrer"`).

### D. Verification of Post-Audit Layout Defect Fixes
- **Screen Reader Text Spilling (Defect #1 - Fixed):** Added the missing `.sr-only` utility in CSS (`position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;`). In the re-captured screenshots, zero text overflows from the 28px `↗` button.
- **Mobile Vertical Stacking (Defect #2 - Fixed):** On `@media (max-width: 768px)`, `.kb-split-layout` stacks vertically (`flex-direction: column`). The issue title `Enforce PostgreSQL 16 FORCE RLS across all tenant tables` now wraps normally with full readable width on 375px mobile viewports, entirely eliminating vertical letter-by-letter squishing.
- **Tablet & Container Rail Responsiveness (Defect #3 - Fixed):** Added `@media (max-width: 1024px)` and `@container issue-surface (max-width: 600px)` rules collapsing the properties rail below the prose body (`grid-template-columns: 1fr`). On 768px tablet viewports, headings and prose have full breathing room without awkward 4-letter breaks.
- **List Row Metadata Collisions (Defect #4 - Fixed):** Applied `white-space: nowrap; flex-shrink: 0;` to due date pills and assignee chips, preventing collisions in list rows under split mode.

### E. Content Security Policy (CSP) & Accessibility Compliance
- **Zero Inline Styles:** Verified that all styling across `Sidebar.css`, `AppShell.css`, `listTable.css`, and `IssueSurface.css` uses pure CSS classes and design tokens; zero inline `style={{...}}` attributes.
- **Keyboard Navigation:** All view tabs, filter popovers, row selections, and header buttons support logical keyboard navigation and focus rings.

---

## 2. Test Suite & Verification Results

- **Unit Tests:** 66/66 tests passed in 6.52s across 7 test files (`AppShell.test.tsx`, `Sidebar.test.tsx`, `Topbar.test.tsx`, `IssueSurface.test.tsx`, `ListRow.test.tsx`, `ListView.test.tsx`, `viewRegistry.test.tsx`).
- **TypeScript & Lint:** `tsc -b --noEmit` exit 0; `eslint` clean with 0 errors and 0 warnings.
- **Production Build:** Vite production build (`pnpm run build`) completed cleanly in 1.25s.
- **Visual Artifacts:** Verified re-captured Playwright screenshots across desktop, tablet, and mobile in `docs/qa/KANBA-174/screenshots/`.

---

## 3. Specialist Conclusion

The 3-pane split view delivers an exceptional, Jira-surpassing spatial experience. All previously flagged responsive and typography defects have been completely resolved, and the implementation strictly adheres to CSP and design system standards.

**Verdict:** APPROVED
