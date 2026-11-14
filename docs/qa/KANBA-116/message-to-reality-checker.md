# Reality-Checker Verification Packet: KANBA-116 (KB-P3-51)

- **Ticket:** `KANBA-116` (`KB-P3-51`: `[Phase 3 / Frontend] Project Stickies 6-palette grid, 1000ms idle complexity heuristic, promotion banner & Doc stub`)
- **Branch:** `feat/KANBA-116`
- **Worktree:** `/tmp/kb-wt-KANBA-116`
- **Unit Test Coverage:** 100% Statements, 97.19% Branches, 100% Functions, 100% Lines (58/58 passing tests, exceeding mandatory >=95% threshold)
- **Static Analysis & Builds:** All clean (TypeScript typecheck exit 0, ESLint exit 0 with 0 warnings, Vite build exit 0, Check-no-dashes 0 violations)
- **Playwright E2E Tests:** 12/12 passing across desktop, tablet, and mobile projects in Playwright

---

### 1. Verification Matrix & Scoped DoD Criteria

| Requirement / Criterion | Status | Evidence File / Command |
| :--- | :--- | :--- |
| **Component Files:** `stickyHeuristic.ts`, `stickiesApi.ts`, `StickiesGrid.tsx`, `StickiesGrid.css`, `StickyCard.tsx`, `StickyPromotionBanner.tsx`, `PromotedStickyStub.tsx`, `ProjectOverviewView.tsx`, `WorkspaceStickiesView.tsx`, `StickiesStory.tsx` | PASS | `kanban/web/src/features/stickies/` and `src/dev/` |
| **Routes Integration:** Wired `/projects/:projectKey/overview`, `/stickies`, and dev story `/__dev/stickies` | PASS | `kanban/web/src/app/routes.tsx` |
| **Unit Test Coverage (>=95%):** 58 tests passing with 100% stmts, 97.19% branch, 100% funcs, 100% lines | PASS | `docs/qa/KANBA-116/unit-test-results.txt` |
| **Build / Type / Lint Clean:** `typecheck`, `lint`, and `build` exit 0 with 0 errors | PASS | `docs/qa/KANBA-116/build-check.txt` |
| **Playwright E2E:** 12/12 tests passed across desktop, tablet, and mobile | PASS | `docs/qa/KANBA-116/e2e-results.txt` |
| **Computed Whitespace Proof:** Grid gap = `20px` (`--space-5`), card padding = `16px 18px` (`--card-pad`), `💡📄` pill = `24px x 24px`, WCAG AA contrast across 6 palettes | PASS | `docs/qa/KANBA-116/computed-styles-*.json` |
| **Annotated Screenshots:** 12 responsive screenshots (4 scenarios x 3 viewports) | PASS | `docs/qa/KANBA-116/screenshots/` |
| **Contract Sample:** Recorded mock `PATCH` (`promotion_snoozed_at_length`) and `POST /api/v1/stickies/:id/promote-to-doc` | PASS | `docs/qa/KANBA-116/contract-sample.json` |
| **Specialist Gates:** UI and API specialist reviews | PENDING | `docs/qa/KANBA-116/ui-specialist-review.md`<br>`docs/qa/KANBA-116/api-specialist-review.md` |

---

### 2. Core Invariants Preserved

1. **Exact S8.2 Complexity Heuristic & >= 1.5x Snooze Math (`stickyHeuristic.ts`):**
   - Pure evaluator outside code fences:
     - `charLength > 600` (`[...bodyMarkdown].length > 600`) -> `<N> chars (> 600)`
     - `lineCount > 10` (`bodyMarkdown.split('\n').length > 10`) -> `<N> lines (> 10)`
     - `headingCount >= 2` (`^#{1,6}\s+`) -> `<N> headings (>= 2)`
     - Structured block (GFM table, `mermaid`, `svg`, or `> 6` lines code fence) -> `table, diagram, or >6-line code block`
     - `outboundLinkCount >= 3` -> `<N> links (>= 3)`
   - Snooze suppression: when `promotion_snoozed_at_length` is set, banner stays hidden until `charLength >= Math.ceil(snoozeLength * 1.5)`.
   - `STICKY_IDLE_DEBOUNCE_MS = 1000` evaluates only after 1000ms idle period.
2. **Responsive CSS Grid & 6-Palette Surfaces (`StickiesGrid.tsx`, `StickyCard.tsx`):**
   - Grid layout: `repeat(auto-fill, minmax(300px, 1fr))` with `gap: var(--space-5)` (20px), card `padding: var(--card-pad)` (16px 18px), `border-radius: var(--radius-lg)`. Zero inline `style=` attributes.
   - 6 palette tokens (`amber`, `mint`, `sky`, `lavender`, `coral`, `slate`) bound to semantic CSS classes `.sticky-card--*` referencing `var(--sticky-*)` tokens from `theme.css`.
   - Accessible keyboard-operable swatch radiogroup (`role="radiogroup" aria-label="Sticky color"`).
3. **Non-Modal Promotion Banner (`StickyPromotionBanner.tsx`):**
   - `<EmojiHint kind="stickyPromotion">` (`💡📄`) with hover/focus popover detailing exact exceeded reasons.
   - Non-modal card footer with concise `Growing into a spec` hint, `[Promote to Doc ->]`, and `[Snooze]` actions.
   - Snooze updates `promotion_snoozed_at_length` with zero modal interruption.
4. **Promoted Doc Stub (`PromotedStickyStub.tsx`):**
   - Compact muted card with `📄 Promoted to Doc` badge, 2-line plain-text preview, `[📄 Open Doc]` direct link, and `[Unarchive Copy]` button (`POST /api/v1/stickies/{id}/unarchive-copy`).
5. **Security & Input Sanitization:**
   - Hostile input with `<img src=x onerror=alert(1)>` sanitized by `MarkdownEditor`.
   - Payload byte limit enforced at 65,536 bytes (`maxBytes={65536}`).
   - CSRF protection header `X-CSRF-Token` attached to mutation requests.
