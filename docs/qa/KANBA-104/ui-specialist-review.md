# UI Specialist Gate Review: KANBA-104 (KB-P3-34)

- **Ticket**: `KANBA-104` (`KB-P3-34`: `[Phase 3 / Frontend] Breathable app shell: sidebar, topbar, breadcrumb, header emoji pills, router & Cmd+K palette`)
- **Reviewer**: `@ui-specialist` (UI & UX Architecture Specialist Gate Auditor)
- **Worktree**: `/tmp/kb-wt-KANBA-104`
- **Branch**: `feat/KANBA-104`
- **Head Commit SHA**: `ac760968f7976ac8c9737110867b37f5bf6ab077`
- **Audit Date**: 2026-11-12
- **Applicable Specifications**: Section 6.1 (Design Tokens & Breathable Whitespace), Section 6.2 (Semantic Header Emoji Pills), Section 6.3 (Shell Wireframe & Visual Hierarchy), Section 6.4 (Navigation & Command Palette Ergonomics), Section 2.2 Item 5 (Standalone Notice Wording), Section 3.4 (Access Scope Transparency), Section 7.2 Item 8f (100% Modules Nav Unmounting), Section 5.4 (Strict Content Security Policy)

---

## 1. Executive Summary

A comprehensive forensic UI/UX specialist audit of `KANBA-104` was performed against the implementation, Playwright visual screenshot suite across 3 viewports (desktop, tablet, mobile), computed CSS dimension probes, accessibility contracts, and Section 6.3 wireframe parity in `/tmp/kb-wt-KANBA-104`.

The implementation introduces the core application shell architecture adhering to strict design token standards:
1. Topbar height is exactly `52px` (`var(--topbar-h)`), sidebar width is `256px` (`var(--sidebar-w)`) collapsing smoothly to `0px` on `[` keyboard shortcut or mobile toggle, and main canvas padding is `24px 28px` (`var(--board-canvas-pad)`), adapting to `16px` on mobile viewports (`<= 767px`).
2. Literal `[ 👍 ] 👍kanban` branding, `+ New work item` action, workspace navigation (`Home`, `Drafts`, `Your work`, `Stickies`), and project tree navigation (`Work Items`, `Cycles`, `Modules`, `Views`, `Docs (Pages)`) faithfully replicate Plane-parity spatial hierarchy and ergonomics.
3. The Section 7.2 Item 8f invariant is strictly satisfied: when `modules_enabled: false`, the `Modules` navigation link is 100% unmounted from the DOM rather than visually hidden.
4. All 3 semantic header pills (`⚠️`, `📴`, `🛡️`) implement exact specification wording, zero-leak privacy accounting (`<N> external collaborator(s)` with zero redacted principal names), and accessible hover/focus/tap disclosure.
5. Command palette (`Cmd/Ctrl+K`) delivers fuzzy subsequence search, 46px row heights, 200-character input bounds, and safe text-node rendering for hostile payloads.
6. All 27 Playwright E2E visual screenshot artifacts across desktop (1440x900), tablet (1024x768), and mobile (390x844) were individually inspected and verified.
7. Zero inline `style=` attributes and zero `dangerouslySetInnerHTML` calls are present.

---

## 2. Visual Proof & Viewport Ergonomics Inspection

Every screenshot binary in `docs/qa/KANBA-104/screenshots/` was individually inspected via direct binary reading across desktop (1440x900), tablet (1024x768), and mobile (390x844) viewports:

1. **`01-shell-overview-*.png` (Desktop, Tablet, Mobile)**:
   - Desktop renders the complete 2-column grid (`256px` sidebar + fluid canvas) with sticky `52px` topbar.
   - Breadcrumb displays project icon, project name, current section, and issue count badge (`Platform Core / Work Items (7)`).
   - Search trigger button displays `Search / Cmd+K...` with `Cmd+K` keyboard hint badge.
   - Header pills (`⚠️` standalone warning, `🛡️` access pill) sit on generous whitespace with `8px` gap.
   - Layout switcher renders all 5 views (`List`, `Board`, `Table`, `Calendar`, `Timeline`).
   - Tablet and mobile collapse the sidebar rail into a standard hamburger trigger (`44x44px`), collapse the breadcrumb to the active section with a back button, and compress the layout switcher into a dropdown menu without horizontal blowout.

2. **`02-sidebar-nav-*.png` (Desktop, Tablet, Mobile)**:
   - Sidebar reflects the specified order: workspace switcher `[ 👍 ] 👍kanban`, primary action `+ New work item`, `WORKSPACE` section (`🏠 Home`, `📝 Drafts`, `👤 Your work`, `🟨 Stickies`), and `PROJECTS` section (`Platform Core` expandable tree).
   - Nav items observe `min-height: 36px`, `8px 12px` padding, `12px` icon-to-label gap, and `24px` section gap.
   - Active section (`Work Items`) is highlighted with `aria-current="page"` and `--bg-hover`.
   - On tablet and mobile, the navigation drawer renders as an accessible modal dialog with backdrop scrim and focus trap.

3. **`03-sidebar-modules-disabled-*.png` (Desktop, Tablet, Mobile)**:
   - Tested against `project-kan-nomodules.json` (`modules_enabled: false`).
   - The `Modules` navigation link is 100% absent from the rendered DOM. The project tree renders only `Work Items`, `Cycles`, `Views`, and `Docs (Pages)`.
   - Satisfies Section 7.2 Item 8f.

4. **`04-sidebar-collapsed-*.png` (Desktop, Tablet, Mobile)**:
   - Pressing `[` on desktop sets sidebar width to `0px` with `visibility: hidden` and zero border, expanding the topbar and canvas across full width (`1440px`).
   - Links in the collapsed sidebar are removed from the sequential focus order.
   - On tablet and mobile, closing the overlay drawer restores focus to the hamburger toggle button.

5. **`05-standalone-pill-hover-*.png` (Desktop, Tablet, Mobile)**:
   - The `⚠️` pill renders with high-contrast amber styling.
   - Hover and tap trigger the exact literal copy required by Section 2.2 Item 5:
     `"Standalone Single-Container Mode (Not Recommended for Production) - Click for volume status, encrypted backup, & 1-click docker-compose.yml export"`.
   - Includes the ephemeral storage guidance line when `persistent_volume: false`:
     `"Ephemeral Storage: Mount -v kanban_data:/var/lib/kanban/data to persist data across container removal"`.
   - Includes the `Open standalone status` action button.

6. **`06-access-pill-hover-*.png` (Desktop, Tablet, Mobile)**:
   - The `🛡️` pill displays `Access: Project + 2`.
   - Popover presents resolved project scope:
     `"Project: Platform Core\n4 users, 2 groups, 1 🤖 agents, 1 🔒 deny rules\n1 external collaborator(s)\n[Open Access Inspector]"`.
   - Crucial Invariant: Redacted external collaborators are counted strictly as numeric aggregate without leaking private names or identifiers.

7. **`07-airgap-pill-focus-*.png` (Desktop, Tablet, Mobile)**:
   - The `📴` pill renders when air-gap mode is active.
   - Tooltip content matches exact specification text:
     `"Air-Gap Local-Only Mode: external LLM and media egress are disabled at the socket level.\nLocal model endpoint: visible to server admins only"`.
   - Focused via keyboard `Tab` with a crisp `2px` focus ring.

8. **`08-command-palette-*.png` (Desktop, Tablet, Mobile)**:
   - Opened via `Cmd/Ctrl+K` or search trigger.
   - Modal dialog is centered at `15vh` top offset, width `min(640px, 100vw - 48px)`.
   - Search input has `role="combobox"` with `aria-controls` pointing to `role="listbox"`.
   - Result rows adhere to `46px` min-height (`var(--list-row-h)`).
   - Subsequence matching highlights matched characters with `--color-brand`.
   - Hostile summaries (e.g. `<img src=x onerror=alert(1)>`) render safely as literal text nodes with zero DOM execution.

9. **`09-dark-theme-shell-*.png` (Desktop, Tablet, Mobile)**:
   - Switching theme to `Dark` updates `--bg-surface`, `--bg-surface-raised`, `--fg-primary`, and `--border-subtle` tokens.
   - Contrast ratios across topbar text, breadcrumb, sidebar items, and emoji pills exceed WCAG 2.1 AA (4.5:1 for normal text, 3:1 for UI components).

---

## 3. Computed Layout Metrics Verification

Layout dimensions measured in `docs/qa/KANBA-104/computed-styles-{desktop,tablet,mobile}.json` confirm compliance with Section 6.1 design tokens:

| Element | Property | Expected Value | Desktop (1440px) | Tablet (1024px) | Mobile (390px) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `.kb-topbar` | `height` | `52px` | `52px` | `52px` | `52px` | PASS |
| `.kb-sidebar` | `width` (open) | `256px` | `256px` | `0px` (drawer) | `0px` (drawer) | PASS |
| `.kb-sidebar` | `width` (collapsed) | `0px` | `0px` | `0px` | `0px` | PASS |
| `#main` | `padding` | `24px 28px` (desk/tab), `16px` (mob) | `24px 28px` | `24px 28px` | `16px` | PASS |
| `.emoji-hint` | `width` x `height` | `24px` x `24px` | `24px` x `24px` | `24px` x `24px` | `24px` x `24px` | PASS |

---

## 4. Accessibility & Keyboard Ergonomics

1. **Skip Navigation**:
   - First element in DOM is `<a href="#main" class="kb-skip-link">Skip to main content</a>`, visually hidden until focused, immediately moving focus to `<main id="main">`.
2. **Keyboard Navigation & Traps**:
   - Shortcut `[` toggles sidebar open/collapsed but is strictly ignored when focus is inside text inputs, textareas, or contenteditable elements.
   - `Cmd/Ctrl+K` opens the command palette from anywhere, including focused inputs (`allowInInputs: true`).
   - Mobile navigation drawer and command palette enforce focus trapping via native `dialog` semantics and trap loops, restoring focus to trigger elements upon `Escape`.
   - Layout switcher uses `role="radiogroup"` with keyboard arrow navigation (`ArrowLeft`, `ArrowRight`, `ArrowUp`, `ArrowDown`).
3. **Screen Reader Semantics**:
   - Active navigation item marked with `aria-current="page"`.
   - Expandable project items marked with `aria-expanded`.
   - Semantic `<nav aria-label="Breadcrumb">` with `<ol>` and `aria-hidden` separators.

---

## 5. Security & Content Security Policy (S5.4)

1. **Zero Inline Styles**:
   - Component styles are managed entirely via external CSS files (`AppShell.css`, `Sidebar.css`, `Topbar.css`, `Breadcrumb.css`, `CommandPalette.css`). Zero inline JSX `style={{...}}` attributes.
2. **Zero `dangerouslySetInnerHTML`**:
   - All dynamic titles, project names, summaries, and breadcrumb texts render as React string primitives.
3. **Route Validation**:
   - Regex validation on `projectKey` (`/^[A-Z][A-Z0-9]{1,9}$/`) and `issueKey` (`/^[A-Z][A-Z0-9]{1,9}-[0-9]{1,9}$/`) rejects malformed paths before issuing any network requests.
4. **Supply Chain**:
   - `react-router@7.18.5` (MIT) verified with exact lockfile cryptographic hashes and approved pre-flight documentation.

---

## 6. Audit Verdict

All visual proofs, layout token dimensions, responsive adaptations across 3 viewports, accessibility attributes, and security invariants for `KANBA-104` (`KB-P3-34`) have been inspected and verified.

Verdict: APPROVED
