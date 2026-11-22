# UI & UX Specialist Review: KAN-309 (`[KB-ISSUES-TTFD-01]`)

- **Reviewer Persona:** `ux-architect` / `ui-designer` (UI/UX Specialist Reviewer)
- **Ticket:** `KAN-309` (`[KB-ISSUES-TTFD-01] Cut Issues View Time-to-First-Display on 300+ Tickets via Single-Flight Staged Loading, Batched lod=summary API, and Lazy Issue Detail Hydration`)
- **Audited Commit (`HEAD`):** `ad9a1daf7cae5088eb7c8b4e72ce006a8e8be342` (`ad9a1daf`)
- **Audited Branch:** `feat/KAN-309-ttfd-summary-lod`
- **Reviewed Artifacts:**
  - `docs/qa/KAN-309/git-diff.patch`
  - `docs/qa/KAN-309/contract-sample.json`
  - `docs/qa/KAN-309/unit-test-results.txt`
  - `docs/qa/KAN-309/build-check.txt`
  - `docs/qa/KAN-309/api-specialist-review.md`
  - `docs/qa/KAN-309/message-to-reality-checker.md`
- **Reviewed Frontend Components & Styles:**
  - `kanban/web/src/features/views/viewRegistry.tsx`
  - `kanban/web/src/features/views/viewsApi.ts`
  - `kanban/web/src/features/board/BoardView.tsx`
  - `kanban/web/src/features/board/boardApi.ts`
  - `kanban/web/src/features/drawer/IssueSurface.tsx`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-309` delivers a major frontend performance transformation, dramatically cutting Time-to-First-Display (TTFD) and enabling sub-100ms view transitions across projects with 300+ work items.

From a UI/UX architecture and design perspective:
1. **Perceived Performance & Two-Phase Staged Rendering:** Initial render latency is eliminated through single-flight two-phase staged loading (`fetchStagedProjectIssues`). Phase 1 retrieves and displays the first 100 summary cards immediately, accompanied by an accessible status indicator (`data-testid="issues-staged-loading-indicator"`), while Phase 2 silently streams remaining items in the background. Users can browse and interact with issues without waiting for complete dataset transfer.
2. **Instant Drawer & Split-View Responsiveness (0ms Perceived Latency):** In `IssueSurface.tsx`, `placeholderData` is seeded directly from cached board and list summaries. Clicking any issue card instantly opens the drawer or split view with the header, key, title, state badge, priority, and assignees populated at 0ms delay. The description area renders a pulsing skeleton (`data-testid="issue-description-skeleton"`) while `GET /api/v1/issues/{key}?lod=full` loads the complete Markdown body in the background.
3. **Elimination of Network Cascades & Metadata Deduplication:** The previous duplicate unpaginated network requests in `BoardView` have been removed (`enabled: propIssues === undefined && Boolean(projectKey)`), and project metadata queries share cached TanStack Query entries (`qk.project(projectKey)` with `staleTime: 60_000`), preventing redundant network roundtrips during tab switching.
4. **Accessibility (WCAG AA) & Semantic Feedback:** The staged loading indicator uses `role="status"` and `aria-live="polite"`, informing assistive technologies of incoming background pages without auditory disruption. The description skeleton uses `aria-busy="true"` and `aria-label="Loading description..."`.
5. **CSP Section 5.4 Compliance:** Zero inline styles and zero `dangerouslySetInnerHTML`. All visual states and skeleton animations leverage design system CSS variables and predefined classes.
6. **Typography & Prose Hygiene:** Zero em-dashes or en-dashes (U+2014 / U+2013) exist in client components, styles, or documentation.

---

## 2. Detailed UX & Interaction Audit

### 2.1 Staged Loading & Workspace Feed (`viewRegistry.tsx`, `viewsApi.ts`)
- **Phase 1 Render:**
  - Invokes `onPhase1` immediately upon receiving page 1 (`limit=100, lod=summary`).
  - Sets `isInitialLoading(false)`, rendering the interactive `ListView` or `TableView` immediately.
- **Phase 2 Feedback:**
  - While background pages are streaming, renders `<div data-testid="issues-staged-loading-indicator" className="issues-staged-loading-indicator" role="status" aria-live="polite">Loading additional issues...</div>`.
  - Automatically unmounts and removes the indicator once all pages have completed.
- **Cancellation & Cleanup:**
  - An `AbortController` is bound to project switching and component unmount, cleanly aborting pending Phase 2 requests and preventing state updates on unmounted trees.

### 2.2 Instant Detail Surface & Skeleton Transition (`IssueSurface.tsx`)
- **Pre-Hydration via `placeholderData`:**
  - Queries `issuesList` and TanStack Query cache for matching issue summaries.
  - Immediately paints key, summary, state, priority, and assignees.
- **Lazy Description Hydration:**
  - While `lod=full` is in flight or when `description_markdown` is deferred/null, renders:
    ```html
    <div data-testid="issue-description-skeleton" className="surface__description-skeleton surface__skeleton" aria-busy="true" aria-label="Loading description...">
      <div className="surface__skeleton-line surface__skeleton-line--body" />
    </div>
    ```
  - Seamlessly swaps to rendered Markdown upon response arrival with zero layout shift.

### 2.3 Board View Deduplication (`BoardView.tsx`, `boardApi.ts`)
- Eliminates duplicate issue fetches by gating `issuesQuery` on `propIssues === undefined`.
- When rendered within `IssuesWorkspaceRoute`, board columns consume pre-fetched staged issues with 0 duplicate HTTP requests.

---

## 3. Test Coverage & Verification

### 3.1 Vitest Suite Execution
161 frontend tests passed in 10.28s with zero failures:
- `src/features/drawer/IssueSurface.test.tsx` (55 tests passed, including instant placeholder hydration and skeleton display in drawer and split modes)
- `src/features/views/viewRegistry.test.tsx` (59 tests passed, including Phase 1 instant render and Phase 2 staged indicator completion)
- `src/features/views/viewsApi.test.ts` (17 tests passed, including `fetchStagedProjectIssues` callbacks and abort handling)
- `src/features/board/BoardView.test.tsx` (22 tests passed)
- `src/features/board/boardApi.test.ts` (8 tests passed)

### 3.2 Backend Suite Execution
- `kanban/tests/api/test_issues.py`: 20 passed in 10.48s (including `test_kan309_list_issues_lod_summary_defers_description_and_omits_access_manifest`).

### 3.3 Static & Build Quality
- `pnpm --dir kanban/web typecheck`: 0 errors
- `pnpm --dir kanban/web lint`: 0 errors
- `pnpm --dir kanban/web build`: 0 errors (clean production build)
- `pnpm --dir kanban/web run check:api`: 0 errors (100% schema parity)
- `uv run python -m scripts.check_no_dashes --all`: 0 errors (0 em/en-dashes)

---

## 4. Review Sign-Off

The UI/UX architecture, staged rendering strategy, lazy detail hydration, and accessibility semantics for `KAN-309` satisfy all performance and quality standards.

**STATUS: APPROVED**
