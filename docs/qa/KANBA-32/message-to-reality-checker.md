# Reality-Checker QA Dossier: KANBA-32 (KB-P3-31)

## Ticket Overview
- Ticket ID: KANBA-32 (Authoritative spec: `docs/tickets/KB-P3-31.md`)
- Title: [Phase 3 / Frontend] <EmojiHint> component, hover/focus timing engine & typed 21-emoji registry
- Worktree: `/tmp/kb-wt-KANBA-32`
- Branch: `feat/KANBA-32`
- Implementing Author: `builder-17`

---

## 1. Traceability & Definition of Done Verification

All scoped deliverables from `docs/tickets/KB-P3-31.md` and Section 6.2 / Section 6.1 of the Product Spec have been fully implemented:

1. **Typed 21-Emoji Registry (`kanban/web/src/components/emoji/emojiRegistry.ts`):**
   - Strictly typed `EmojiKey` union and `EmojiDefinition` interface.
   - Frozen immutable `EMOJI_REGISTRY` record containing all 21 status emojis from Section 6.2: `access`, `restricted`, `warning`, `airGap`, `priorityUrgent`, `priorityHigh`, `priorityMedium`, `priorityLow`, `agent`, `gatePending`, `gateVetoed`, `gateApproved`, `externalAssignee`, `creatorOverride`, `sparkle`, `sanitized`, `rawMarkdown`, `stickyPromotion`, `brokenLink`, `scriptedField`, `mediaBackdrop`.
   - Each entry defines exact glyph, human label, semantic tone (`danger`, `warning`, `accent`, `mint`, `sky`, `lavender`, `muted`, `slate`), and detailed hover elaboration copy.
   - Helper functions: `getEmojiDefinition()` (with fallback to `warning`) and `isValidEmojiKey()`.

2. **Hover / Focus Timing Engine (`kanban/web/src/components/emoji/hintTiming.ts`):**
   - Headless state machine supporting custom injected clock (`Clock` interface) for sub-millisecond deterministic testing without real timeouts.
   - Hover open delay: 180ms.
   - Neighbor warmup window: 400ms (subsequent emoji hint hovers within 400ms open immediately at 0ms).
   - Tab focus open delay: 0ms (immediate).
   - Bridge grace period: 120ms (allows moving cursor from trigger to popup over diagonal gaps without dismissing).
   - Dismiss grace period: 80ms on hover out.

3. **Geometric Position Engine (`kanban/web/src/components/emoji/positionHint.ts`):**
   - Pure mathematical calculation with zero layout side effects.
   - Viewport edge collision detection: prefers bottom placement with 6px gap (`offset = 6`).
   - Edge flip: flips to top if bottom space would collide with viewport boundary (`top + popupHeight > viewportHeight - 8`).
   - Viewport clamping: clamps horizontal position within `[8, viewportWidth - popupWidth - 8]`.

4. **Singleton Portal (`kanban/web/src/components/emoji/HintPortal.tsx`):**
   - Mounts dynamically into `#kb-hint-root`, creating the DOM node if absent.
   - Prevents popup clipping by overflow containers (`overflow: hidden` / `overflow: auto`).

5. **Design-Token Styled Sheet (`kanban/web/src/components/emoji/EmojiHint.css`):**
   - Trigger badge: exactly 24x24px pill matching S6.1 specifications.
   - Coarse hit area: 44x44px hit target on touch devices via `::before` pseudo-element.
   - Popup container: max-width 360px, padding 12px 14px, border radius `--radius-md` (8px), background `var(--bg-surface)`, border `1px solid var(--border)`.
   - Subtle elevation drop shadow: `0 8px 24px rgba(0, 0, 0, 0.12)`.
   - Tone pill indicators: semantic background tints matching registry tones.

6. **Core Accessible Component (`kanban/web/src/components/emoji/EmojiHint.tsx`):**
   - Supports both `tooltip` (default) and `interactive` variants.
   - Zero inline `<style>` or `style="..."` attribute injection: positioning coordinates applied via CSSOM `element.style.top = ...` and `element.style.left = ...`.
   - WCAG accessibility: `aria-describedby` for tooltips, `role="dialog"` + `aria-haspopup="dialog"` + `aria-expanded` for interactive popovers.
   - Keyboard interaction: Escape key dismisses open popups and restores focus to trigger badge.
   - Touch screen handling: tapping toggles popup open cleanly without synthetic blur dismiss races.

7. **Interactive Story & Dev Route (`kanban/web/src/dev/EmojiStory.tsx` + `EmojiStory.css`):**
   - Mounted at `/__dev/emoji` in `src/App.tsx`.
   - Visual showcase containing:
     * 21-emoji responsive status grid with live hover tooltips.
     * Interactive popover demo with audit actions and child button focus.
     * Boundary edge flip test station demonstrating automatic flip to top placement.

---

## 2. Verification Artifacts & Test Results

The following raw proof artifacts are populated in `docs/qa/KANBA-32/`:

1. `unit-test-results.txt`:
   - 159/159 Vitest unit tests passed (exceeding >= 95% threshold across all metrics).
   - Global coverage: Statements 99.72%, Branches 95.85%, Functions 100%, Lines 99.72%.
   - Touched `src/components/emoji/` modules: Statements 99.65%, Branches 92.55%, Functions 100%, Lines 99.64%.
2. `build-check.txt`:
   - Typecheck (`tsc -b --noEmit`): 0 errors, exit 0.
   - Lint (`eslint . --max-warnings 0`): 0 warnings, exit 0.
   - Build (`vite build`): Clean production bundle with SRI hashes and precompressed `.br` and `.gz` assets, exit 0.
3. `e2e-results.txt`:
   - 22 passed, 2 skipped, 0 failed across Desktop (1440x900), Tablet (820x1180), and Mobile (390x844).
   - Tests cover: registry grid, hover delay (180ms), neighbor warmup (0ms), keyboard tab focus, bridge cursor transfer, escape key dismissal, edge flip placement, and mobile touch tap-to-open.
4. `computed-styles-{desktop,tablet,mobile}.json`:
   - Validates live browser computed styles for trigger dimensions (`width: 24px`, `height: 24px`), popup sizing (`max-width: 360px`), and popup padding (`12px 14px`).
5. `screenshots/`:
   - 15 annotated PNG screenshots covering all 5 test scenarios across desktop, tablet, and mobile.
   - Inspected via `read_file` to confirm all red boxes and numeric badges tightly frame their targets with zero visual distortion.
   - `screenshots/ANNOTATIONS.md`: Documents each screenshot, bounding boxes, and verified features.
6. `ui-specialist-review.md`:
   - Verbatim audit and `APPROVED` verdict from `@ui-specialist` (message #200).
7. `git-diff.patch`:
   - Full unified patch against `feat/KANBA-26` (excluding `dist/`).

---

## 3. Security & Invariant Compliance

- Unicode Dashes: Zero `U+2014` or `U+2013` dashes exist across all source files, documentation, and commit messages (validated via `check_no_dashes.py`).
- License Gate: `make license` exits 0 with 0 violations across all Python and Node dependencies.
- Zero Dependencies Added: Implemented strictly using existing React 19 + TypeScript + Vite stack.
- CSP Hardening: Zero inline `<style>` injection and zero HTML string evaluation. Pure CSSOM geometric positioning.
