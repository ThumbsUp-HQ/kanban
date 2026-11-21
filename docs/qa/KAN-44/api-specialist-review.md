# Clean-Room API Specialist Review: KAN-44

- **Ticket:** KAN-44 (`[KB-SURFACE-VIEW-PARITY]`)
- **Title:** Comprehensive Board, List, Table, and Single-Issue Multi-Layout Polish, Mobile Bottom Sheets & VIEWER RBAC Read-Only Invariants
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-44`
- **Branch:** `main` (integrated at commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`)
- **Commit Under Audit:** `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`
- **Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Verification Scope

A clean-room API, Security, and RBAC architecture audit was conducted for ticket **KAN-44** on branch `main` at commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`. The audit incorporates empirical verification from Round 5 zero-mock Live Full-Stack QA on container `kanban-liveqa-2` (`http://127.0.0.1:18962`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-44/live-fullstack-proof.txt`, all 16 Playwright visual screenshots in `docs/qa/KAN-44/screenshots/`, unit test results (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

KAN-44 delivers mobile and touch ticket state transition controls, multi-layout consistency across Board, Swimlane, List, Table, and Issue surfaces, mobile bottom sheet state transitions, and strict multi-view VIEWER RBAC read-only enforcement.

The audit inspects and certifies:
1. **API State Transition Contracts & Concurrency (`POST /api/v1/issues/{key}/transition`, `POST /api/v1/issues/{key}/move`, `PATCH /api/v1/issues/{key}`):**
   - Direct transitions executed from interactive header, card, row, and table controls integrate with backend workflow transition gates, WIP limit validations, and ETag optimistic locking.
   - Live stack verified: HTTP 200 responses with latency between 56ms and 144ms on `kanban-liveqa-2`.
2. **Strict Multi-View VIEWER RBAC Enforcement:**
   - Evaluated under `viewer2` holding Workspace Guest + Project Viewer role on project `KAN`:
     * Interactive state transition buttons are completely omitted on Board and Swimlane surfaces (`stateBtnCount: 0`).
     * In List View, interactive state selectors are replaced with static `<StateBadge>` components (`readOnlyStateBadgeCount: 6`).
     * In Table View, interactive dropdowns are replaced with static `.state-badge` pills (`readOnlyStateBadgeCount: 6`, `interactiveStateSelectCount: 0`, all labels untruncated).
     * In Single Issue View, state controls render static read-only header badge without interactive select inputs.
3. **Responsive Geometry & Touch Target Standards:**
   - On Table View (`390x844`), `.issues-table` has `min-width: 580px`, and Summary header and cells maintain `min-width: 180px` (`summaryCellWidth: 235px >= 180px`), completely eliminating title truncation.
   - On `<= 879px` viewports, duplicate state select controls are hidden via `:is(.surface--full, .surface--drawer, .surface:not(.surface--split))`, ensuring exactly one visible State `<select>` (`visibleStateSelectCount === 1`).
   - `.activity-tablist` wraps cleanly (`flex-wrap: wrap; gap: 4px; padding-right: 12px;`), positioning `Gates (0)` at `gatesBtnRight === 151px <= 378px` without horizontal viewport overflow (`390px === 390px`).
4. **Unit Test Coverage & Quality Gates:**
   - 13 test files passed, 247/247 tests passed in 15.91s with zero `act(...)` warnings.
   - Every single touched file individually exceeds >=95.0% branch coverage (99.5% stmts, 95.68% branch, 99.8% funcs, 99.95% lines overall).
   - TypeScript `tsc -b --noEmit` clean, ESLint clean, and zero em/en-dashes across codebase.

---

## 2. API Contract & Security Verification

### 2.1 Transition API & State Synchronization
- **Endpoints:**
  * `POST /api/v1/issues/{key}/transition`: Transitions state while checking workflow gates.
  * `POST /api/v1/issues/{key}/move`: Handles board drag-and-drop or state move pill clicks.
  * `PATCH /api/v1/issues/{key}`: Updates issue properties.
- **Security & RBAC Enforcement:**
  * Requires `TRANSITION`, `EDIT`, or `ADMIN` capability.
  * Callers with only `VIEW` capability receive HTTP 403 Forbidden on transition attempts and have interactive transition controls stripped from the UI.
- **Live Container Proof (`kanban-liveqa-2`, `:18962`, commit `2b542d7f`):**
  * Admin user: Transition status 200 OK across Board, Swimlane, Table, and Single Issue views.
  * Viewer user: Exactly 0 interactive select controls present across all surfaces.

### 2.2 Table View Geometry & Scroll Wrap Telemetry
- Telemetry from live container:
  * `issuesTableMinWidth`: `580px`
  * `scrollWrapOverflowX`: `auto`
  * `summaryHeaderMinWidth`: `180px` (`summaryHeaderWidth`: 235px)
  * `summaryCellMinWidth`: `180px` (`summaryCellWidth`: 235px)
  * `pageScrollWidth`: 390px, `innerWidth`: 390px (no global horizontal page blowout)
  * All 6 interactive state `<select>` controls measure width=127px, height=44px (>= 44px touch target) inside horizontal scroll container.

### 2.3 Single Issue & Activity Tab Telemetry
- Tablet (768x1024, `/projects/KAN/issues/KAN-1`):
  * `visibleStateSelectCount`: 1 (`header-state-select`)
  * `quickPropsGroupDisplay`: `none`
  * `railStateRowDisplay`: `none`
- Mobile (390x844, `/projects/KAN/issues/KAN-1`):
  * `visibleStateSelectCount`: 1 (`header-state-select`)
  * `scrollWidth`: 390px, `innerWidth`: 390px (`noHorizontalOverflow`: true)
  * `gatesBtnRight`: 151px (<= 378px)

---

## 3. Test Suites & Coverage Verification

### 3.1 Vitest Unit Test Results (`unit-test-results.txt`)
- 13 test files passed, 247/247 tests passed in 15.91s with 0 `act(...)` console warnings.
- Individual File Coverage Breakdown (all >= 95.0% branch):
  * `AppShell.tsx`: 99.12% stmts, **95.14%** branch
  * `BoardCard.tsx`: 100% stmts, **97.01%** branch
  * `BoardColumn.tsx`: 100% stmts, **100%** branch
  * `BoardView.tsx`: 100% stmts, **96.57%** branch
  * `IssueHeader.tsx`: 100% stmts, **95.00%** branch
  * `IssueSurface.tsx`: 99.37% stmts, **95.40%** branch
  * `ListRow.tsx`: 98.55% stmts, **95.55%** branch
  * `ListView.tsx`: 100% stmts, **96.03%** branch
  * `TableView.tsx`: 99.6% stmts, **95.63%** branch
  * `QuickFieldPopover.tsx`: 100% stmts, **96.15%** branch
  * `SwimlaneBoardGrid.tsx`: 100% stmts, **95.10%** branch
  * `viewRegistry.tsx`: 99.02% stmts, **95.30%** branch
  * **TOTAL: 99.5% statements, 95.68% branch, 99.8% functions, 99.95% lines**

### 3.2 Static Quality Gates (Commit `2b542d7f`)
- `kanban-ctl db check-migrations`: OK (63 migrations valid)
- `ruff check .`: All checks passed
- `ruff format --check .`: Clean across 2027 files
- `mypy database kanban mcp agent`: Clean across 997 source files
- `lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database` KEPT)
- `tsc -b --noEmit`: Clean (0 errors)
- `eslint . --max-warnings 0`: Clean (0 warnings)
- `vite build`: Clean production build in 1.13s
- `scripts.check_no_dashes`: Clean (0 em/en-dashes)

---

## 4. Security & RBAC Matrix

| Surface / Action | ADMIN / MEMBER | VIEWER (Guest) | Implementation |
| :--- | :--- | :--- | :--- |
| **Board Card State Move** | Interactive button + Popover (HTTP 200) | Button omitted (0 in DOM) | `BoardCard.tsx` / `SwimlaneBoardGrid.tsx` |
| **List Row State Select** | Interactive button + Bottom Sheet | Static `<StateBadge>` pill | `ListRow.tsx` |
| **Table View State Column** | Interactive `<select>` (127x44px) | Static `.state-badge` pill (0 selects) | `TableView.tsx` |
| **Single Issue State** | Interactive header `<select>` | Static header `<StateBadge>` | `IssueHeader.tsx` / `IssueSurface.tsx` |
| **Table Scroll Wrap** | 580px min-width, 180px summary | 580px min-width, 180px summary | `TableView.css` |
| **Full-Page <= 879px Select** | Exactly 1 visible State select | Exactly 0 visible State selects | `IssueSurface.css` |
| **Activity Tablist Wrap** | Gates (0) wrapped at 151px <= 378px | Gates (0) wrapped at 151px <= 378px | `activity.css` |

---

## 5. Certification Signoff

STATUS: APPROVED

All API contracts, state transition routes, VIEWER RBAC permissions, mobile geometry constraints, and test suites for KAN-44 on branch `main` at commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd` have been thoroughly audited, verified against all architectural and security invariants, and certified on container `kanban-liveqa-2` (`:18962`, `OVERALL LIVE_STACK_VERDICT: PASS`). Ready for Clean-Room Reality-Checker QA.
