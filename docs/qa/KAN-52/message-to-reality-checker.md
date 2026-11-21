# KAN-52: Verification Evidence & Reality-Checker Certification Packet

## Ticket Details
- **Ticket ID:** `KAN-52`
- **Title:** `[KB-ISSUE-NAVIGATOR] Replace X/Y-Flipped List View with Master-Detail Issue Navigator View`
- **Branch:** `main` (commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`)
- **Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`

---

## 1. Executive Summary & Problem Resolution

### Problem 1: Unified Top `IssueNavigatorBar` (`data-testid="issue-navigator-bar"`)
- Replaced double-stacked bars when `layout === 'list'` with a single unified `IssueNavigatorBar`:
  * Basic Mode: Structured filter selects for State, Priority, Assignee, Label, Cycle, Module (gated on `modulesEnabled`), plus quick `⭐ Favorites only` toggle button (`data-testid="filter-favorites-toggle"`), text search input (`data-testid="navigator-search-input"`), Search submit button, and Basic / Query mode toggle.
  * Query Mode: Monospace structured query input (`data-testid="navigator-query-input"`) supporting both JQL/SQL predicates (`project = "KAN" AND status = "Todo"`) and tokenized key-value predicates (`state:started priority:high "mars"`), evaluated via hermetic parser in `predicateParser.ts`.
  * JQL Synchronization: Executing JQL `project = "KAN" AND status = "Purple Review"` filters rail to `["KAN-5", "KAN-4", "KAN-3"]` and automatically updates `activePeekKey` to `KAN-5` with pager `1 of 3` and next enabled (not stuck on `KAN-1`).
  * Favorites Support: Persistent favorites tracking synced via localStorage key `kb_favorite_issues` and custom event `kb:favorites-changed`, Saved Views quick-access chip strip (`navigator-saved-views-strip`), and per-issue `⭐` toggle (`data-testid="favorite-issue-toggle"`).

### Problem 2: Left Master Rail (`300px`, `Order by` + 2-Line Issue List Cards)
- Removed legacy x/y-flipped Kanban status folding sections from `ListView.tsx`.
- Updated `.kb-split-list-pane` in `listTable.css` to `flex: 0 0 300px; min-width: 260px; max-width: 340px;` on desktop (`> 768px`) with `.surface--split` taking `flex: 1 1 0; min-width: 0;`.
- Implemented Rail Header with `Order by` sort selector (`data-testid="issue-sort-select"`) supporting Updated, Created, Priority, State, Key, Due Date, and Rank sorting, sort direction toggle (`data-testid="issue-sort-dir-btn"`), and refresh button (`data-testid="issue-rail-refresh-btn"`).
- Verified ascending Key sort traversal: clicking `issue-next-btn` traverses `KAN-1 -> KAN-2 -> KAN-3` (`exactMatch=true`).
- Rendered compact 2-line Issue List Cards (`data-testid="issue-list-card-${issue.key}"`):
  * Line 1: Priority/type icon, monospace issue key (`mono issue-card-key`), selection checkbox when selectable, right-aligned interactive state pill (`data-testid="list-row-state-btn-${issue.key}"`), and `⭐` favorite toggle button.
  * Line 2: Issue summary title (`issue-card-summary`), with active selection highlight (`list-row--active`).
- Mobile Guard: Preserved full-width card list rail when `?peek=` is absent on mobile viewports (`<= 768px`), never auto-trapping user in split surface. When an issue is opened, rendered `← Back to list` (`data-testid="split-surface-close-btn"`) to return cleanly to rail.

### Problem 3: Right Master-Detail Issue View Canvas (`IssueSurface.tsx` `mode === 'split'` & `IssueSurface.css`)
- Header & Sequential Pager: Project breadcrumb (`<ProjectName> / <KEY>` in `data-testid="split-breadcrumb"`), large editable Summary title (`SummaryField`), and right-aligned sequential position indicator `1 of N` (`data-testid="issue-navigator-position"`) with `^` previous and `v` next, fully synced with `J`/`K` and `ArrowUp`/`ArrowDown` keyboard navigation.
- Action Toolbar: Quick action buttons for `✎ Edit`, `💬 Add comment`, `👤 Assign`, inline state select (`data-testid="split-state-select"`), `⭐` Favorite toggle button, and `🔗 Share`.
- Single-Line Assign-to-Me & Assignee API Contract:
  * Button styling enforces `white-space: nowrap` and `flex-shrink: 0` (`btnHeight=29`, `btnWidth=99`, `singleLine=true`).
  * `handleAssignToMe` hits `railApi.addAssignee(currentIssue.key, { principal: myId })` via `POST /api/v1/issues/{issue_ref}/assignees` with `{ principal: myId }`, returning HTTP 201 Created and updating DETAILS ("Priority: High Assignee: Server Administrator") and PEOPLE immediately.
- Collapsed Sidebar Rail (>879px) & 12px DETAILS Flex Gap:
  * `splitWidth=1084px`, `quickPropsDisplay="flex"`, `detailsBodyHeight=46px`, `horizontalGapPx=12`. Priority and Assignee render cleanly with 12px gap inside DETAILS.
- Independent Copy Feedback Timers:
  * Separated `copyBranchTimeoutRef` and `copyShareTimeoutRef`. Branch copy displays `✓ Copied!` while Share button displays `🔗 Share / Export` without timer collision or button freeze.
- Single State Select in Split Mode:
  * Tablet and mobile viewports render only single `split-state-select` (quick props state select hidden).
- Tablet 768x1024 Side-by-Side Split View:
  * In `IssueSurface.css:265`: changed `@media (max-width: 768px)` to `@media (max-width: 767px)`. At 768x1024 tablet, `.surface--split` renders side-by-side next to the 300px master rail (`sideBySide: true`, 284px left rail + 412px right detail pane).

### Problem 4: `created_at` & `updated_at` Serialization & View Label Parity
- Added `created_at: datetime` and `updated_at: datetime` to `IssueResponse` (`kanban/api/v1/schemas/issues.py`).
- Added serialization in `serialize_issue` in `kanban/services/issues.py` (strictly respecting module boundaries and never touching `create_issue`).
- Added optional `created_at?: string` and `updated_at?: string` to `IssueItem` in `kanban/web/src/features/views/viewsApi.ts`.
- Updated user-facing view label in `LayoutSwitcher.tsx` and `Sidebar.tsx` to `Issues` (`📋 Issues`) while preserving `?layout=list` URL query parameter compatibility.

---

## 2. Invariants & Guardrails Compliance

- Mobile Touch & Popover Controls: Zero regressions to KAN-44 mobile touch controls and popovers. `QuickFieldPopover` portal integration and mobile bottom-sheet ergonomics preserved.
- CSS Tokens: 100% canonical CSS tokens across `IssueNavigatorBar.css`, `listTable.css`, `IssueSurface.css`, and `LayoutSwitcher.css`. Verified by `cssTokensAudit.test.ts` (4/4 passed).
- Zero Inline JSX Styles: Zero inline JSX `style={{...}}` properties introduced.
- Strict File Boundaries: In `kanban/services/issues.py`, ONLY touched `serialize_issue` and top-level datetime import. Zero touches to `create_issue`.
- Untracked Files Safety: Untracked `.backup_schedule.json` and `backups/` directories were strictly excluded from staging.
- No Em/En-Dashes: Clean execution of `python3 -m scripts.check_no_dashes` across the entire repository.

---

## 3. Test Suites & Verification Metrics

- Frontend Unit Tests (`docs/qa/KAN-52/unit-test-results.txt`):
  * 8/8 test files passed, 156/156 unit tests passed with 0 `act(...)` warnings in 15.26s.
  * Every single touched file individually exceeds >=95.0% branch coverage:
    - `LayoutSwitcher.tsx`: 100% stmts, **97.05%** branch
    - `IssueSurface.tsx`: 99.37% stmts, **95.40%** branch
    - `ListView.tsx`: 100% stmts, **96.03%** branch
    - `IssueNavigatorBar.tsx`: 100% stmts, **100%** branch
    - `viewPredicateParser.ts`: 100% stmts, **96.66%** branch
    - `viewRegistry.tsx`: 99.02% stmts, **95.30%** branch
    - `viewsApi.ts`: 100% stmts, **98.52%** branch
    - **TOTAL: 99.44% statements, 96.04% branch, 99.71% functions, 100% lines**
- Backend Pytest Suite: 16/16 passed in `kanban/tests/api/test_issues.py` in 8.40s.
- TypeScript Typecheck: `tsc -b --noEmit` exited with code 0 (0 errors).
- ESLint: `eslint . --max-warnings 0` exited with code 0 (0 errors, 0 warnings).
- Production Build: `vite build` succeeded with exit code 0 in 1.13s.
- Database Migrations & Architecture Contracts: `kanban-ctl db check-migrations` confirmed all 63 migrations valid with single head (`p4_24_agent_safe_sequences`). `lint-imports` confirmed 2 contracts kept, 0 broken.

---

## 4. Verification Evidence Files

- `docs/qa/KAN-52/live-fullstack-proof.txt`: Round 5 live black-box execution telemetry against `kanban-liveqa-2` (`:18962`, commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`)
- `docs/qa/KAN-52/unit-test-results.txt`: Verbatim execution outputs for Vitest (156 passed) and Pytest (16 passed)
- `docs/qa/KAN-52/build-or-typecheck.txt`: Verbatim static check and build outputs
- `docs/qa/KAN-52/api-specialist-review.md`: Dual-specialist API and security audit signoff
- `docs/qa/KAN-52/ui-specialist-review.md`: Dual-specialist UI and layout audit signoff
- `docs/qa/KAN-52/screenshots/live-navigator-desktop-light.png`: Desktop Light mode master-detail layout
- `docs/qa/KAN-52/screenshots/live-navigator-desktop-dark.png`: Desktop Dark mode master-detail layout
- `docs/qa/KAN-52/screenshots/live-navigator-assign-to-me-desktop.png`: Single-line Assign to me button and updated Details
- `docs/qa/KAN-52/screenshots/live-navigator-query-jql-desktop.png`: JQL query sync to first matching issue (KAN-5)
- `docs/qa/KAN-52/screenshots/live-navigator-collapsed-rail-desktop.png`: Collapsed rail with Priority/Assignee in Details (12px gap) and independent copy timers
- `docs/qa/KAN-52/screenshots/live-navigator-tablet.png`: Tablet viewport with side-by-side split master-detail
- `docs/qa/KAN-52/screenshots/live-navigator-mobile-list.png`: Mobile full-width list view
- `docs/qa/KAN-52/screenshots/live-navigator-mobile-detail.png`: Mobile detail view with back button
