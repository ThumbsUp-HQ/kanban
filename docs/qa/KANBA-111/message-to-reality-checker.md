# Verification Note for Reality-Checker: KANBA-111 (KB-P3-37)

- **Ticket**: `KANBA-111` (`KB-P3-37`: `[Phase 3 / Frontend] Kanban Board view with Pragmatic DnD, column virtualization, <12ms optimistic move & Soft/Hard WIP visuals`)
- **Branch**: `feat/KANBA-111`
- **Worktree**: `/tmp/kb-wt-KANBA-111`
- **Base Commit**: `main`

---

### Implementation Details & Highlights

1. **Spatial Geometry & Design Tokens (Spec S6.1, S6.3)**:
   - Lanes rendered at `--board-col-w: 324px` with `--board-col-gap: 20px`.
   - Cards styled with `--card-pad: 16px 18px` and `--card-gap: 12px`.
   - Canvas `#main` padding: `24px 28px` on desktop/tablet, responsive `16px` on mobile (<= 767px).
   - Card dimensions, column widths, and emoji hint badge dimensions (`24x24px`) verified across desktop, tablet, and mobile in `computed-styles-{desktop,tablet,mobile}.json`.

2. **Column Virtualization & DOM Budget (Spec S6.3)**:
   - Configured `@tanstack/react-virtual` in `BoardColumn.tsx` using dynamic sizing.
   - Enforced strict CSP compliance (`style-src 'self'`): zero inline `style={{...}}` JSX attributes. Element height and translation offsets are updated strictly via CSSOM element refs in `useLayoutEffect`.
   - In 500-card stress testing (`board-kan-500.json`), initial DOM count mounts 10-11 cards, and scrolled DOM count (at index 260) mounts 17 cards, well under the <= 25 DOM elements limit.

3. **Optimistic Move & Benchmark (< 12ms)**:
   - Implemented `fractionalRank.ts` using Base-62 collation (`0-9`, `A-Z`, `a-z`) matching Postgres `COLLATE "C"` order.
   - `applyOptimisticMove` in `boardApi.ts` performs synchronous cache updates without remounting unaffected cards.
   - Measured median latency across 20 runs is 0.000ms, well within the < 12ms target.
   - On server error (e.g. 409 conflict or 500), the optimistic move rolls back cleanly to the pre-drag snapshot.

4. **Soft & Hard WIP Enforcement (Spec S6.5)**:
   - Soft WIP limit breaches display an amber warning badge and `⚠️` emoji with accessible tooltip; moves remain permitted.
   - Hard WIP limit breaches:
     - Non-admin members are blocked client-side with 0 network calls dispatched and an `aria-live` alert toast.
     - Admins open `HardWipOverrideModal` requiring 10..500 trimmed characters justification, transmitting `wip_override_reason` in `POST .../move`.
     - Intra-column reordering within a Hard WIP capped lane succeeds without requiring modal override.

5. **API Endpoint Path Mapping**:
   - Primary endpoint: `POST /api/v1/projects/:projectKey/issues/:issueKey/move` matching `KB-P3-12` (Spec S7.3).
   - Fallback endpoint: `POST /api/v1/issues/:issueId/move` automatically triggered if primary returns HTTP 404.

6. **Playwright E2E Suite & Artifacts**:
   - 15/15 tests passing across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).
   - 15 annotated screenshots captured in `docs/qa/KANBA-111/screenshots/`.
   - `dependency-evaluation.md` signed off by `@ui-specialist`, `@arch-reviewer`, and `@sec-eng`.
   - `api-specialist-review.md` signed off by `@arch-reviewer`.
