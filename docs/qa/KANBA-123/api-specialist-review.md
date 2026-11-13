# API & Architecture Specialist Gate Review: KANBA-123 (KB-P3-42)

- **Ticket**: `KANBA-123` (`KB-P3-42`: `[Phase 3 / Frontend] Ticket properties rail (8b-8i): State, hybrid Assignees (🏷️), Priority, Created-by (🔄), Dates, conditional Modules, Cycle, Parent (🔒) & Labels`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-123`
- **Branch**: `feat/KANBA-123` (commit `606fb5e`)
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Gate Evaluation

As Systems/Backend Architect & API Specialist, I have conducted an exhaustive forensic audit of the implementation of `KANBA-123` (`KB-P3-42`), covering the client-side API contracts, security invariants, anti-enumeration protections, DAG hierarchy validation, conditional DOM unmounting, and AAL2 step-up handling across `kanban/web/src/features/drawer-rail/`.

The implementation fulfills all architectural, API contract, and security requirements defined in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 7.1, 7.2 8b-8i, 6.1, 6.2, 3.4):
- **Hybrid Assignees (8b, S7.2)**: Debounced combobox querying suggestions with strict 120ms debounce; clear distinction between `@user` principals, `🤖 agent` principals, and `🏷️` free-text collaborator pills; client caps enforced at 20 total and 10 free-text collaborators; external collaborator pills carry the exact non-access tooltip text.
- **Created-by & Provenance (8d, S7.2)**: Read-only presentation for standard members; `🔄` popover rendering full provenance trail while strictly masking redacted principals as `"1 External Collaborator"`; administrative override modal enforcing 10-500 character audit reasons and handling `403 AAL2_REQUIRED` step-up challenges.
- **Schedule Clamping & Overdue Logic (8e, S7.2)**: Client-side validation preventing `due_date < start_date` before any network dispatch; overdue badge suppressed on completed and cancelled states.
- **Conditional Modules Invariant (8f, S7.2)**: When `project.modules_enabled === false`, the Modules row is 100% unmounted from the DOM (`null`), never hidden via CSS `display: none`, and zero network requests to `/modules` are initiated.
- **Parent DAG & Privacy Masking (8h, S7.2, S3.4)**: When `parent.restricted === true`, the parent chip renders `🔒` with literal text `"Restricted Parent Issue"` without exposing key, ID, title, or clickable hyperlink; backend `409 PARENT_CYCLE` and `409 PARENT_DEPTH_EXCEEDED` errors are mapped to human-readable actionable alert messages.
- **Exclusive Label Mutex (8i, S7.2)**: Selecting a label within an `exclusive_group` automatically and atomically evicts any existing label sharing that group in the optimistic mutation payload.

---

## 2. API Contract & Security Invariant Audits

### 2.1 Hybrid Assignees & Anti-Enumeration (S7.2 8b, KB-P3-03, S3.4)
- **Debounced Suggestion Wire Traffic**: `AssigneesRow.tsx` binds the input combobox to `fetchAssigneeSuggestions(projectKey, query, 10)` with a strict 120ms debounce timer and cleanup on unmount/re-query. Queries are scoped strictly to the current `projectKey`.
- **Principal vs Free-Text Segregation**:
  * Authenticated user accounts render `@handle`.
  * Autonomous agent accounts render with `<EmojiHint kind="agent">` displaying `🤖` alongside `@handle`.
  * External collaborator tags render `.assignee-pill--external` with dashed border (`border: 1px dashed var(--border-strong)`) and `<EmojiHint kind="externalAssignee">` with verbatim tooltip: `"External free-text label - grants zero access and sends zero notifications"`.
- **Client Defense-in-Depth Caps**: Limits are enforced before network dispatch:
  * Maximum 20 total assignees (`MAX_TOTAL_ASSIGNEES = 20`).
  * Maximum 10 free-text assignees (`MAX_FREE_TEXT_ASSIGNEES = 10`).
  * Rejections render immediate `role="alert"` messages without sending futile requests to the backend.
- **XSS & Hostile Input Immunity**: Free-text assignee strings are rendered exclusively via React text child nodes (`{asg.free_text}`), ensuring payloads such as `<img src=x onerror=alert(1)>` remain harmless plain text.

### 2.2 Creator Provenance & AAL2 Step-Up Integrity (S7.2 8d, KB-P3-04, S4.2)
- **Role-Based Surface Gating**: The `Change...` trigger for creator reassignment is conditionally mounted only when `isAdmin === true` (`capabilities.includes('ADMIN')`). Standard members with `EDIT` access see only the immutable creator display.
- **Anti-Enumeration Redaction Masking**: When `provenance.created_by.redacted === true` or `provenance.original_created_by.redacted === true`, `formatPrincipal()` outputs `"1 External Collaborator"`, preventing private handle or user UUID leakage to unauthorized viewers.
- **Audit Reason Invariant**: The `OverrideCreatorModal` enforces strict length bounds (`10..500` characters) on `reason` before allowing submission.
- **AAL2 Step-Up Handling**: Catches HTTP `403` with error code `AAL2_REQUIRED` and displays an explicit step-up prompt informing the administrator of the second-factor requirement.

### 2.3 Conditional Modules DOM & Network Invariant (S7.2 8f, KB-P3-10b)
- **Zero-DOM Unmounting**: `DatesCycleModulesRows.tsx` implements:
  ```tsx
  {modulesEnabled ? (
    <div className="prop-row" data-prop="modules">...</div>
  ) : null}
  ```
  When `modules_enabled === false`, the row evaluates to `null`. Computed DOM query `document.querySelector('[data-prop="modules"]')` returns `null`.
- **Zero Network Egress**: `PropertiesRail.tsx` conditionally wraps `fetchProjectModules(projectKey)` inside `if (modulesEnabled)`. When `modules_enabled === false`, zero HTTP requests to `/api/v1/projects/{project_ref}/modules` are dispatched.

### 2.4 Parent DAG Hierarchy & Restricted Masking (S7.2 8h, KB-P3-02, S3.4)
- **Restricted Object Masking**: If `issue.parent?.restricted === true`, the component renders:
  * `<EmojiHint kind="restricted" content="Parent issue is in a restricted scope outside your visibility." />` (`🔒`)
  * Verbatim text node: `"Restricted Parent Issue"`
  * Zero `<a>` links, zero issue keys (`KAN-xxx`), and zero UUIDs are rendered in the DOM.
- **DAG Conflict Mapping**: Catches and translates RFC 7807/API error payloads:
  * `409 PARENT_CYCLE` -> `"Cannot set parent: this would create a parent cycle."`
  * `409 PARENT_DEPTH_EXCEEDED` -> `"Cannot set parent: maximum hierarchy depth (6) exceeded."`
- **Sub-Issues Rollup**: Renders progress bar and completion fraction `(doneSub/totalSub Done) percent%` per S7.1 lines 539-541.

### 2.5 Exclusive Label Mutex Invariant (S7.2 8i, KB-P3-01b)
- **Atomic Mutex Replacement**: In `ParentLabelsRows.tsx`, when toggling a label possessing an `exclusive_group` (e.g., `type:bug` vs `type:feature`), the existing label in that group is atomically filtered out of `updatedIds` and the new label appended.
- **Accessibility Announcement**: Surfaces `aria-live="polite"` status message: `"Replaced <old> with <new> (exclusive group: <group>)"`.

---

## 3. Test Suite & Verification Results

### 3.1 Unit Test Coverage (`vitest`)
Executed `pnpm --dir kanban/web exec vitest run --coverage --coverage.include="src/features/drawer-rail/**" src/features/drawer-rail`:
- **Test Files**: 7/7 passed (68 tests total, 0 failures, 3.06s runtime).
- **Statements**: **99.53%** (exceeds >= 95% threshold).
- **Branches**: **96.36%** (exceeds >= 95% threshold).
- **Functions**: **99.13%** (exceeds >= 95% threshold).
- **Lines**: **100.00%** (exceeds >= 95% threshold).

### 3.2 Production Build, Typecheck, and Lint
Executed `pnpm --dir kanban/web typecheck && pnpm --dir kanban/web lint && pnpm --dir kanban/web build`:
- `tsc -b --noEmit`: 0 errors.
- `eslint . --max-warnings 0`: 0 warnings, 0 errors.
- `vite build`: Clean client build in 934ms (exit code 0).

### 3.3 Playwright E2E Suite
Executed `e2e/drawer/properties-rail.spec.ts` across `desktop`, `tablet`, and `mobile`:
- 15/15 tests passed in 17.6s.
- Verified visual screenshots and computed style probes in `docs/qa/KANBA-123/screenshots/` and `docs/qa/KANBA-123/computed-styles-*.json`.
- Confirmed `.surface__rail` width 320px and padding 24px.
- Confirmed `.prop-row` height and min-height exactly 38px.
- Confirmed `.emoji-hint` dimensions exactly 24px x 24px.

### 3.4 Repo-Wide Dash Compliance
Executed `python3 scripts/check_no_dashes.py --all`:
- 0 non-ASCII dashes detected across the entire codebase.

---

## 4. Final Architectural Sign-Off

The `KANBA-123` implementation satisfies all backend architecture, API consumption, anti-enumeration, and security requirements. The dual specialist gate criteria for API/Architecture are fully satisfied.

**VERDICT: APPROVED**
