# Forensic QA Verification Packet: Ticket Properties Rail 8b-8i (KB-P3-42)

- **Ticket:** `KANBA-123` (`KB-P3-42`: `[Phase 3 / Frontend] Ticket properties rail (8b-8i): State, hybrid Assignees (🏷️), Priority, Created-by (🔄), Dates, conditional Modules, Cycle, Parent (🔒) & Labels`)
- **Git Worktree:** `/tmp/kb-wt-KANBA-123`
- **Branch:** `feat/KANBA-123` (base: `origin/main`)
- **Author:** `builder-23` (Swarm Implementation Author)
- **Target Audience:** `@reality-checker` (Passive Forensic QA Gate), `@ui-specialist`, `@arch-reviewer`

---

## 1. Executive Summary & Verification Matrix

Ticket `KANBA-123` (`KB-P3-42`) implements the `320px` right properties rail for issue drawer and full screen views with Plane parity across all 8 property rows (State, hybrid Assignees, Priority, Created by, Start/Due dates, conditional Modules, Cycle, Parent, and Labels). It delivers breathable 38px row rhythm (`--prop-row-h`), a trailing `<div data-slot="custom-fields-rail" />` extension hook, debounced combobox autocomplete, non-authenticated collaborator dashed external pills with literal S7.2 8b tooltip copy, admin-only creator override with AAL2 step-up retry handling, conditional Modules unmounting, DAG cycle error mapping, masked restricted parents, and exclusive label group replacement.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Properties Rail Geometry** | 320px width, 24px padding, 38px row height | Verified via `computed-styles-{desktop,tablet,mobile}.json` and Playwright | PASS |
| **Trailing Custom Fields Slot** | `<div data-slot="custom-fields-rail" />` | Mounted directly after Labels row in `PropertiesRail.tsx` | PASS |
| **State & Priority Rows (8c)** | Grouped states, custom priorities, emoji hints | Implemented in `StatePriorityRows.tsx`, updates optimistically | PASS |
| **Hybrid Assignees (8b)** | Debounced 120ms, agent hints, dashed external pill | Combobox debounced 120ms; `.assignee-pill--external` with `🏷️` exact copy | PASS |
| **Assignee Caps & Error Mapping** | Max 20 total / 10 free text; 422 / 409 handling | Client-side guards enforce limits; catches `422 ASSIGNEE_LIMIT` / `409` | PASS |
| **Created by & Provenance (8d)** | Immutable member view, `🔄` popover, admin modal | Provenance popover with exact copy, 10..500 char reason, AAL2 step-up retry | PASS |
| **Dates & Overdue Badge (8e)** | ISO dates, client `due < start` alert, overdue pill | `due < start` alert rejected before network; overdue hidden when done | PASS |
| **Conditional Modules (8f)** | 100% unmounted when `modules_enabled === false` | Returns `null` (`document.querySelector('[data-prop="modules"]') === null`) | PASS |
| **Cycle Row (8g)** | Status badge, completed counts, clear affordance | Single-select cycle selector with active/upcoming status pills | PASS |
| **Parent & Sub-issues (8h)** | `🔒` masked parent, `409` DAG errors, rollup bar | Restricted parent masks key; maps `409 PARENT_CYCLE` / `DEPTH_EXCEEDED` | PASS |
| **Labels Row (8i)** | Multi-select, exclusive group replacement | Replaces conflicting group label; announces swap | PASS |
| **Slot Registration** | Register `issueSurfaceSlots.rail = PropertiesRail` | Registered in `kanban/web/src/features/drawer/slotRegistry.ts` | PASS |
| **Zero Inline Styles** | S5.4 / UI Specialist rule: 0 `style=` attributes | Validated across all production components and dev harness | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95% all 4 metrics) | 71 test files passed; `drawer-rail`: 99.53% stmts, 96.36% branch, 100% lines | PASS |
| **Playwright E2E Suite** | 5 specs x 3 viewports (desktop, tablet, mobile) | 15/15 passed in 17.6s; 15 annotated PNG screenshots captured | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Typecheck clean (0 errors), ESLint clean (0 warnings), Vite build clean | PASS |

---

## 2. Mandatory Specialist Review Gates

1. **API Specialist Gate (`arch-reviewer`):** Audited REST endpoint contracts, debounce behavior, anti-enumeration principal masking, AAL2 challenge recovery, and DAG error codes.
2. **UI Specialist Gate (`ui-specialist`):** Audited 38px row rhythm, responsive desktop/tablet/mobile stacking, dashed external pill affordance, and semantic emoji hints.

---

## 3. Forensic Evidence Manifest (`docs/qa/KANBA-123/`)

- `git-diff.patch`: Complete unified git diff against base `origin/main`.
- `unit-test-results.txt`: Full Vitest execution log with v8 coverage report (71 test files, 478 tests passed, exit code 0).
- `build-check.txt`: Clean output from `pnpm typecheck && pnpm lint && pnpm build` (exit code 0).
- `e2e-results.txt`: Playwright E2E run output across desktop, tablet, and mobile viewports (15 passed, exit code 0).
- `computed-styles-desktop.json`, `computed-styles-tablet.json`, `computed-styles-mobile.json`: Measured layout geometry verifying `.surface__rail` padding `24px`, `.prop-row` min-height `38px`, dashed external pill border, and `24px x 24px` emoji hints.
- `contract-sample.json`: Wire contracts recording `assignee_add_principal_200`, `assignee_add_free_text_200`, `creator_override_admin_200`, `modules_put_200`, `labels_patch_exclusive_group_200`, and `parent_cycle_409`.
- `screenshots/`: 15 annotated PNG screenshots across desktop (1440x900), tablet (1024x768), and mobile (390x844):
  - `01-rail-all-properties-{desktop,tablet,mobile}.png`
  - `02-external-assignee-hint-{desktop,tablet,mobile}.png`
  - `03-creator-override-provenance-{desktop,tablet,mobile}.png`
  - `04-rail-modules-unmounted-{desktop,tablet,mobile}.png`
  - `05-restricted-parent-masked-{desktop,tablet,mobile}.png`
