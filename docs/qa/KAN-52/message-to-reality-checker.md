# KAN-52: Verification Evidence & Reality-Checker Certification Packet

## Ticket Details
- Ticket ID: `KAN-52`
- Title: `[KB-ISSUE-NAVIGATOR] Replace X/Y-Flipped List View with Master-Detail Issue Navigator View`
- Branch: `feat/KAN-52`

---

## 1. Executive Summary & Problem Resolution

### Problem 1: Unified Top `IssueNavigatorBar` (`data-testid="issue-navigator-bar"`)
- Replaced the double-stacked `FilterDisplayBar` + `ListView` `Filter & Group` bar when `layout === 'list'` with a single unified `IssueNavigatorBar`:
  * Basic Mode: Structured filter selects for State, Priority, Assignee, Label, Cycle, Module (gated on `modulesEnabled`), plus quick `⭐ Favorites only` toggle button (`data-testid="filter-favorites-toggle"`), text search input (`data-testid="navigator-search-input"`), Search submit button, and Basic / Query mode toggle.
  * Query Mode: Monospace structured query input (`data-testid="navigator-query-input"`) supporting both JQL/SQL predicates (`project = "KAN" AND status = "Todo"`) and tokenized key-value predicates (`state:started priority:high "mars"`), evaluated via hermetic parser in `predicateParser.ts`.
  * Favorites Support: Persistent favorites tracking synced via localStorage key `kb_favorite_issues` and custom event `kb:favorites-changed`, Saved Views quick-access chip strip (`navigator-saved-views-strip`) hydrating `?view=<id>` and view grouping parameters, and per-issue `⭐` toggle (`data-testid="favorite-issue-toggle"`).

### Problem 2: Left Master Rail (`300px`, `Order by` + 2-Line Issue List Cards)
- Removed legacy x/y-flipped Kanban status folding sections (`.list-section`) from `ListView.tsx`.
- Updated `.kb-split-list-pane` in `listTable.css` to `flex: 0 0 300px; min-width: 260px; max-width: 340px;` on desktop (`> 768px`) with `.surface--split` taking `flex: 1 1 0; min-width: 0;`.
- Implemented Rail Header with `Order by` sort selector (`data-testid="issue-sort-select"`) supporting Updated, Created, Priority, State, Key, Due Date, and Rank sorting, sort direction toggle (`data-testid="issue-sort-dir-btn"`), and refresh button (`data-testid="issue-rail-refresh-btn"`).
- Rendered compact 2-line Issue List Cards (`data-testid="issue-list-card-${issue.key}"`):
  * Line 1: Priority/type icon, monospace issue key (`mono issue-card-key`), selection checkbox when selectable, right-aligned interactive state pill (`data-testid="list-row-state-btn-${issue.key}"` preserving KAN-44 touch/mobile popover support), and `⭐` favorite toggle button.
  * Line 2: Issue summary title (`issue-card-summary`), with active selection highlight (`list-row--active`).
- Mobile Guard: Preserved full-width card list rail when `?peek=` is absent on mobile viewports (`<= 768px`), never auto-trapping user in split surface. When an issue is opened, rendered `← Back to list` (`data-testid="split-surface-close-btn"`) to return cleanly to rail.

### Problem 3: Right Master-Detail Issue View Canvas (`IssueSurface.tsx` `mode === 'split'` & `IssueSurface.css`)
- Header & Sequential Pager: Project breadcrumb (`<ProjectName> / <KEY>` in `data-testid="split-breadcrumb"`), large editable Summary title (`SummaryField`), and right-aligned sequential position indicator `1 of N` (`data-testid="issue-navigator-position"`) with `^` previous (`data-testid="issue-prev-btn"`) and `v` next (`data-testid="issue-next-btn"`), fully synced with `J`/`K` and `ArrowUp`/`ArrowDown` keyboard navigation.
- Action Toolbar: Quick action buttons for `✎ Edit` (`data-testid="split-edit-btn"`), `💬 Add comment` (`data-testid="split-add-comment-btn"`), `👤 Assign` (`data-testid="split-assign-btn"`), inline state select (`data-testid="split-state-select"`), `⭐` Favorite toggle button, and `🔗 Share` (`data-testid="split-share-btn"`).
- 2-Column Collapsible Detail Layout:
  * Left / Main column: Details panel, Description editor with Markdown/Mermaid support, Attachments section, Sub-issues & Linked Issues section, and Activity / Comments stream.
  * Right column: People section with 1-click `Assign to me` button (`data-testid="split-assign-to-me-btn"`) authenticated against `/api/v1/auth/me`, Dates section (`data-testid="split-section-dates"`) displaying Created, Updated, Start Date, and Due Date, and Development section (`data-testid="split-section-dev"`) with Git branch copy helper (`data-testid="split-git-branch-copy"`).

### Problem 4: `created_at` & `updated_at` on `IssueResponse` + View Label Update
- Added `created_at: datetime` and `updated_at: datetime` to `IssueResponse` (`kanban/api/v1/schemas/issues.py`).
- Added `created_at` and `updated_at` serialization to `serialize_issue` in `kanban/services/issues.py` (strictly respecting module boundaries and never touching `create_issue`).
- Added optional `created_at?: string` and `updated_at?: string` to `IssueItem` in `kanban/web/src/features/views/viewsApi.ts`.
- Updated user-facing view label in `LayoutSwitcher.tsx` and `Sidebar.tsx` to `Issues` (`📋 Issues`) while preserving `?layout=list` URL query parameter compatibility.
- Fixed keyboard navigation in `useIssueKeyboardMap.ts` (`Enter`/`Space` opens peek modal, `J`/`K` navigates cleanly).
- Cleaned line 3 docstring in `Sidebar.tsx` to remove competitor reference.

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

- Frontend Unit Tests: 10/10 test files passed, 151/151 unit tests passed with 0 `act(...)` warnings:
  * `predicateParser.test.ts`: 4/4 passed
  * `IssueNavigatorBar.test.tsx`: 5/5 passed
  * `ListView.test.tsx`: 8/8 passed
  * `IssueSurface.test.tsx`: 38/38 passed
  * `IssueSurfaceSplitMasterDetail.test.tsx`: 3/3 passed
  * `useIssueKeyboardMap.test.tsx`: 11/11 passed
  * `LayoutSwitcher.test.tsx`: 7/7 passed
  * `Sidebar.test.tsx`: 25/25 passed
  * `cssTokensAudit.test.ts`: 4/4 passed
  * `viewRegistry.test.tsx`: 46/46 passed
- Backend Pytest Suite: 16/16 passed in `kanban/tests/api/test_issues.py` with isolated worker DB prefix (`KB_TEST_DB_PREFIX=kanban_test_kan52`).
- TypeScript Typecheck: `tsc -b --noEmit` exited with code 0 (0 errors).
- ESLint: `eslint src/... --max-warnings 0` exited with code 0 (0 errors, 0 warnings).
- Production Build: `vite build` succeeded with exit code 0.
- Database Migrations & Architecture Contracts: `kanban-ctl db check-migrations` confirmed all 62 migrations valid with single head (`p4_23_oidc_link_intent_fk`). `lint-imports` confirmed 2 contracts kept, 0 broken.

---

## 4. Verification Evidence Files
- `docs/qa/KAN-52/git-diff.patch`
- `docs/qa/KAN-52/changed-files-manifest.txt`
- `docs/qa/KAN-52/unit-test-results.txt`
- `docs/qa/KAN-52/build-or-typecheck.txt`
- `docs/qa/KAN-52/message-to-reality-checker.md`
