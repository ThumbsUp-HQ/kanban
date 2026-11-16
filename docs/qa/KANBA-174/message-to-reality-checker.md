# Forensic QA Submission: KANBA-174

**Ticket:** KANBA-174 ([KB-UX-04] Jira-Style 3-Pane Split List View (`|Nav|issue list|<---issue view--->|`) with Sidebar Views, Single-Card Filter, and New-Tab Action)  
**Worker:** `worker-172`  
**Date:** 2026-11-16  
**Status:** READY FOR FORENSIC QA AUDIT  

---

## Executive Summary

KANBA-174 transitions the 👍kanban platform into a Jira-competing 3-pane split list view experience (`|Nav|issue list|<---issue view--->|`):
1. **Sidebar Navigation Views & 200px Desktop Footprint:** Moved layout view links (`📋 List`, `📊 Board`, `📑 Table`, `📅 Calendar`, `📈 Timeline`) with curated `KanbanIcons` directly into the project navigation sidebar. Reduced sidebar width to 200px (`--sidebar-w: 200px`), and added a 1-click `Hide Nav` / `Show Nav` toggle button in both the sidebar footer and split issue view header, coordinated via `kb:toggle-sidebar` and `kb:sidebar-changed` window events.
2. **Compact Single Filter Card Dropdown Popover:** Replaced cluttered multi-row filter toolbars with a single compact button (`🔍 Filter & Group ▾`) opening a dropdown popover (search query, state, priority, group-by, reset filters) paired with a `+ New` issue creation action.
3. **Docked 50%-Width Split Issue Surface:** In list layout (`layout === 'list'`), rendered `<IssueSurfaceRoot mode="split" />` side-by-side with the issue list (`flex: 1 1 50%`), auto-selecting the first issue if `?peek=` is not specified.
4. **Header Enhancements:** Included `Open in new tab (↗)` link (`target="_blank" rel="noopener noreferrer"`) pointing to `/projects/:projectKey/issues/:issueKey` and nav-toggle trigger in the issue surface header.
5. **Zero Inline Styles (Strict CSP Invariant):** All layouts, dimensions, popovers, and split panes are 100% powered by CSS classes with zero inline `style={{...}}` attributes.
6. **Responsive Layout Hardening:**
   - Screen-reader `.sr-only` class added to keep assistive text hidden without spilling.
   - Mobile (375px) vertical stacking (`flex-direction: column`) with scrollable list pane and docked full-width issue view.
   - Tablet/narrow container responsiveness (`@media (max-width: 1024px)` and `@container issue-surface (max-width: 600px)`) stacking the rail below prose (`grid-template-columns: 1fr`).
   - List row metadata collisions resolved via `white-space: nowrap; flex-shrink: 0;` on pills and collapsed secondary tags in split view.

---

## Verification Artifacts & Deliverables

1. **Unit Test Execution Log:**
   - [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-174/unit-test-results.txt): 66/66 unit tests passing across all 7 affected test files (`AppShell.test.tsx`, `Sidebar.test.tsx`, `Topbar.test.tsx`, `IssueSurface.test.tsx`, `ListRow.test.tsx`, `ListView.test.tsx`, `viewRegistry.test.tsx`).

2. **Build, Typecheck, and Lint Verification:**
   - [build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-174/build-check.txt): Full `tsc -b --noEmit` exit 0, ESLint exit 0 with 0 errors and 0 warnings, Vite production build (`pnpm run build`) exit 0.

3. **Changed Files Manifest & Git Patch:**
   - [changed-files-manifest.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-174/changed-files-manifest.txt): Strict boundary of 11 owned files.
   - [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-174/git-diff.patch): Verifiable unified diff of all changes.

4. **Specialist Sign-off:**
   - [ui-specialist-review.md](file:///home/adamoutler/kanban/docs/qa/KANBA-174/ui-specialist-review.md): Formal review and approval by `ui-specialist`.

5. **Visual Playwright Screenshot Proof:**
   - [list-3-pane-split-view.png](file:///home/adamoutler/kanban/docs/qa/KANBA-174/screenshots/list-3-pane-split-view.png): Desktop 1440x900 3-pane split list view displaying `|Nav (200px)|issue list (50%)|<---issue view (50%)--->|`.
   - [list-3-pane-split-view-tablet.png](file:///home/adamoutler/kanban/docs/qa/KANBA-174/screenshots/list-3-pane-split-view-tablet.png): Tablet 1024x768 responsive layout with rail stacked beneath prose.
   - [list-3-pane-split-view-mobile.png](file:///home/adamoutler/kanban/docs/qa/KANBA-174/screenshots/list-3-pane-split-view-mobile.png): Mobile 375x667 vertical stacked layout.

---

## Forensic Compliance & Invariant Checklist

- [x] **File Ownership Discipline:** Strictly edited only owned files (`Sidebar.tsx`, `Sidebar.css`, `Sidebar.test.tsx`, `Topbar.tsx`, `AppShell.tsx`, `ListView.tsx`, `ListView.test.tsx`, `ListRow.tsx`, `listTable.css`, `viewRegistry.tsx`, `IssueSurface.tsx`, `IssueSurface.css`). Did not touch `routes.tsx`, `QuickCreateIssueModal.tsx`, `TimelineView.tsx`, `calendarTimeline.css`, `viewRegistry.test.tsx`, or `admin-auth/*`.
- [x] **Sidebar View Switcher:** Layout view links (`📋 List`, `📊 Board`, `📑 Table`, `📅 Calendar`, `📈 Timeline`) integrated with `KanbanIcons` directly in the active project section of `Sidebar.tsx`.
- [x] **Compact 200px Width & 1-Click Toggle:** Set `--sidebar-w: 200px` in `Sidebar.css`. 1-click `Hide Nav` / `Show Nav` toggle button in both sidebar footer and split issue surface header, synchronized via custom events.
- [x] **Single-Card Filter Dropdown Popover:** `🔍 Filter & Group ▾` card popover with search query, state, priority, and group-by filters, paired with `+ New` button.
- [x] **Jira-Style 3-Pane Split View:** Docked 50%-width `<IssueSurfaceRoot mode="split" />` side-by-side with issue list in `viewRegistry.tsx` when `layout === 'list'` (auto-selecting `filteredIssues[0]?.key` if `?peek=` is not present).
- [x] **Open in New Tab Link:** Rendered `.issue-header__new-tab-link` (`↗`) pointing to `/projects/:projectKey/issues/:issueKey` with `target="_blank" rel="noopener noreferrer"`.
- [x] **Strict Content Security Policy (CSP):** Zero inline styles (`style={{...}}`); all dimensions, flex splits, and popover styles are driven by CSS classes.
- [x] **Multi-Device Responsive Hardening:** Stacked layouts on mobile (375px), container/tablet rail stacking (1024px & <= 600px), `.sr-only` containment, and metadata collision prevention.
- [x] **Test & Quality Perfection:** 66/66 unit tests passing; 0 tsc errors; 0 eslint errors or warnings; production Vite build passes in 1.25s.
