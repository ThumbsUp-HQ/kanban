# UI Specialist Gate Review: KANBA-113 (KB-P3-41)

- **Ticket**: `KANBA-113` (`KB-P3-41`: `[Phase 3 / Frontend] Ticket drawer shell (640px prose + 320px rail) & zero-remount full screen`)
- **Reviewer**: `@ui-specialist` (UI & UX Architecture Specialist Gate Auditor)
- **Worktree**: `/tmp/kb-wt-KANBA-113`
- **Branch**: `feat/KANBA-113`
- **Audit Date**: 2026-11-12
- **Applicable Specifications**: Section 6.1 (Design Tokens & Breathable Whitespace), Section 6.2 (Semantic Header Emoji Hints), Section 7.1 (Drawer Wireframe & Spatial Architecture), Section 7.2 Item 8a (Summary Field Ergonomics), Section 7.2 Item 8o (Zero-Remount Full-Screen Toggle)

---

## 1. Executive Summary

A comprehensive forensic UI/UX specialist audit of `KANBA-113` was performed across implementation files, component styling, Playwright visual screenshot suite across 3 viewports (desktop, tablet, mobile), computed CSS dimension probes, accessibility contracts, and Section 7.1/7.2 wireframe parity in `/tmp/kb-wt-KANBA-113`.

The ticket establishes the core ticket reading and editing surface for the platform:
1. **Zero-Remount Persistent Surface**: The `<IssueSurface />` is mounted once in `#kb-issue-surface-host` within `<AppShell>`. Toggling between drawer mode (`?peek=KAN-142`) and full-screen mode (`/projects/KAN/issues/KAN-142`) switches `.surface--drawer` and `.surface--full` CSS classes on the surface root without unmounting the React tree. `data-mount-id` and `data-mount-seq` remain identical across 5 round-trip toggles, preserving active input focus, unsaved summary drafts, and scroll position.
2. **Design Tokens & Spatial Ergonomics (S6.1)**:
   - On Desktop (1440x900): Drawer width matches `var(--drawer-w)` (`min(960px, 68vw)` = 960px). The surface body renders a 2-column grid with a `640px` editorial prose column (`minmax(0, 640px)`) and a `320px` property rail.
   - On Tablet (1024x768): Drawer width is `696px`. The rail automatically stacks below the prose column via container query `@container issue-surface (max-width: 879px)`.
   - On Mobile (390x844): Full-viewport sheet (`inset: 0; width: 100vw; height: 100dvh`), `aria-modal="true"`, with `useFocusTrap` keeping focus constrained within the sheet.
   - Fixed spacing tokens `--prose-pad` (32px 40px), `--section-gap` (32px), `--text-body` (15px), `--leading-prose` (25.95px), and `--prop-row-h` (38px) are strictly preserved across all breakpoints with zero compact/dense overrides.
3. **Semantic EmojiHints & Header Elements (S6.2, S7.1)**:
   - Priority hint renders high/urgent/medium/low emoji with tooltip displaying sort order and SLA target.
   - Access hint (`AccessPill`) renders `🛡️ <scope_label> + <count>` pill with interactive popup detailing users, groups, agents, and deny rules, plus `Open Access Inspector` button dispatching `kb:open-access-inspector`.
   - Header controls (`→` collapse, `↗` full screen toggle) maintain standard 24px icon sizes, 44px tap targets on mobile, and explicit `aria-label` / `aria-keyshortcuts`.
4. **Summary Editing (S7.2 8a)**:
   - Inline auto-growing textarea replaces summary text on edit button click.
   - C0/C1 control characters and newlines are sanitized on input and paste.
   - Character count is calculated in Unicode code points (`1..500` bounds).
   - Clean RFC 7807 problem details and `412 Precondition Failed` optimistic rollback with non-blocking conflict alert and `Reload` action.
5. **Quality & Security**:
   - Zero inline `style=` attributes and zero `dangerouslySetInnerHTML` in UI components.
   - All server strings rendered as plain text nodes, neutralizing XSS vectors.
   - Equalized `403` / `404` error boundaries preventing resource existence enumeration.

---

## 2. Visual Proof & Viewport Ergonomics Inspection

All 21 Playwright visual screenshot artifacts in `docs/qa/KANBA-113/screenshots/` across Desktop (`1440x900`), Tablet (`1024x768`), and Mobile (`390x844`) were inspected:

1. **`01-drawer-open-*.png` (Desktop, Tablet, Mobile)**:
   - Desktop: Right-docked drawer occupies exactly 960px. Side-by-side grid cleanly separates the 640px editorial prose container from the 320px rail.
   - Tablet: Rail stacks below prose container in a single breathable column, maintaining `--prose-pad` (32px 40px) and `--section-gap` (32px).
   - Mobile: Surface occupies full viewport (390x844) as an accessible modal sheet with backdrop blur.

2. **`02-access-hint-open-*.png` (Desktop, Tablet, Mobile)**:
   - Interactive access popup opens with exact wording: `Project: Platform Core - 14 users, 2 groups, 1 agent, 0 deny rules. Inherited from Project.`.
   - Action button `Open Access Inspector` is rendered with accessible hover and focus styling.

3. **`03-priority-hint-open-*.png` (Desktop, Tablet, Mobile)**:
   - Tooltip popup displays `Priority: High - sort weight 2. SLA target: not configured. Press P to change.`.
   - Neighbor warmup timing and hover bridge operate cleanly without flickering.

4. **`04-full-screen-*.png` (Desktop, Tablet, Mobile)**:
   - Full-screen mode expands surface to occupy the area to the right of the sidebar (`left: var(--sidebar-w)`).
   - Inner prose container centers with `max-width: 640px; margin-inline: auto;`, preserving reading comfort and line-length ergonomics.
   - Header button shifts glyph to return arrow with label `Return to side panel`.

5. **`05-summary-validation-*.png` (Desktop, Tablet, Mobile)**:
   - Inline alert appears cleanly below textarea when empty (`Summary cannot be empty.`) or exceeding 500 code points (`Summary must be 500 characters or fewer (currently 501).`).
   - Accessible role `role="alert"` and `aria-describedby` linkage validated.

6. **`06-not-found-*.png` (Desktop, Tablet, Mobile)**:
   - Equalized error state renders `Issue KAN-999 was not found or you do not have access.` with standard close button.

7. **`07-focus-return-*.png` (Desktop, Tablet, Mobile)**:
   - Closing the drawer returns keyboard focus cleanly to the trigger link element that opened it.

---

## 3. Computed Styles & Token Compliance

Computed CSS values captured in `docs/qa/KANBA-113/computed-styles-*.json`:
- **Desktop (1440x900)**:
  * `.surface--drawer`: `width: 960px` (matches `min(960px, 68vw)`).
  * `.surface__prose`: `padding: 32px 40px` (matches `var(--prose-pad)`), `row-gap: 32px` (matches `var(--section-gap)`), `font-size: 15px`, `line-height: 25.95px`.
  * `.surface__rail`: `padding: 24px`, `border-left: 1px solid var(--border-subtle)`.
  * `.surface__header`: `min-height: 56px`, `padding: 12px 24px`.
- **Tablet (1024x768)**:
  * `.surface--drawer`: `width: 696.312px` (matches `68vw` at 1024px).
  * `.surface__body`: `grid-template-columns: 1fr` (stacked layout via container query).
- **Mobile (390x844)**:
  * `.surface--drawer`: `width: 390px`, `height: 844px`, `inset: 0px`.

---

## 4. Specialist Gate Sign-Off

The ticket drawer shell implementation, zero-remount route integration, S6.1 token adherence, semantic emoji hint popups, inline summary editor, and responsive viewport ergonomics satisfy all UI and UX architecture requirements.

Verdict: APPROVED
