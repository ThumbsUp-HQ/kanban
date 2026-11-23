# KAN-314: Full Mobile and Landscape Browser Use Audit Matrix

## Scope and Viewports Audited
- Portrait Mobile: 390x844 (iOS Safari / Chromium touch viewport)
- Compact Landscape Mobile: 844x390 (Landscape smartphone viewport)
- Tablet Portrait: 768x1024 (iPad / Android Tablet portrait viewport)
- Desktop Baseline: 1440x900 (Reference desktop viewport in light and dark themes)

---

## Route Audit and Remediation Matrix

| Route / Surface | Viewport(s) | Baseline Problem / Finding | Remediation Applied (KAN-314) | Child Ticket Spawned | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Topbar & App Shell** (`/projects/KAN/issues`) | `390x844`, `844x390` | Topbar menus (avatar dropdown, notifications tray) exceeded viewport height without scroll bounding. Mobile hit areas on buttons were below 44px. | Added `max-height: calc(100dvh - var(--topbar-h, 52px) - 16px)` and `-webkit-overflow-scrolling: touch` to `.kb-avatar-menu` and `.kb-notif-tray`. Clamped notification tray width to `min(360px, calc(100vw - 24px))`. Expanded `.kb-topbar-docs-btn`, `.kb-avatar-button`, and `.kb-notif-mark-read-btn` to minimum 44x44px hit areas on coarse pointer devices. | N/A (Resolved in KAN-314) | **PASS** |
| **Command Palette** (Global) | `390x844`, `844x390` | Missing touch-friendly dismissal mechanism (relied solely on Escape key or backdrop click) and exceeded 390px landscape viewport height. Input had font-size < 16px triggering iOS Safari auto-zoom. | Added dedicated 44x44px touch Close button (`[data-testid="command-palette-close-btn"]`, `aria-label="Close command palette"`). Constrained modal dialog with `max-height: calc(100dvh - 32px)` and max-height 540px in landscape mode. Enforced `font-size: 16px` on input on mobile and coarse pointer viewports. | N/A (Resolved in KAN-314) | **PASS** |
| **Board View & 2D Swimlanes** (`/projects/KAN/issues?layout=board`) | `390x844`, `844x390` | When stacked into a single column on mobile (<768px), swimlane columns lost header context because table header row was hidden. Touch drag-and-drop lacks tactile affordance for touch screens without fine mouse cursor. | Added `.swimlane-column-mobile-header` rendering sticky column state headers inside each board column when viewed on mobile screens (<768px). Spawned touch popover fallback ticket for full drag-and-drop replacement. | `KAN-342` | **PASS** |
| **Issue Detail Drawer & Properties Rail** (`/projects/KAN/issues?peek=KAN-142`) | `390x844`, `844x390` | Properties rail dropdowns (`.assignees-menu`, `.labels-dropdown__menu`) rendered off-screen on 390px viewports with left alignment overflow. Textareas and inputs used 13-14px font size triggering auto-zoom. | Clamped `.assignees-menu` and `.labels-dropdown__menu` with `right: 0; left: auto; max-width: calc(100vw - 32px)`. Enforced `font-size: 16px` across all inputs, selects, and textareas under `@media (max-width: 767px), (pointer: coarse)`. | `KAN-345` (Virtual keyboard and toolbar) | **PASS** |
| **Docs Workspace** (`/projects/KAN/docs`) | `390x844`, `768x1024` | Docs tree pane and rail pane were fixed at `top: 0`, overlapping the fixed `.kb-topbar` and obscuring top navigation actions. Hover-only tree action buttons (`.docs-tree-item__action-btn`) were inaccessible on touch screens. Large code blocks and Mermaid diagrams cause horizontal scroll bottlenecks. | Set `.docs-tree-pane`, `.docs-rail-pane`, and `.docs-sheet-backdrop` to `top: var(--topbar-h, 52px)` and `height: calc(100dvh - var(--topbar-h, 52px))`. Made `.docs-tree-item__action-btn` visible by default on `@media (pointer: coarse)` and `<=768px` with 44x44px touch targets. Spawned pinch-to-zoom ticket for embedded diagrams. | `KAN-346` | **PASS** |
| **Settings Profile & Avatar Cropper** (`/settings/profile`) | `390x844`, `844x390` | Avatar crop viewport was hardcoded to fixed dimensions causing horizontal overflow on 390px screens. Card lacked viewport height constraint. | Made `.kb-avatar-crop-viewport` responsive with `width: min(320px, calc(100vw - 48px)); max-width: 100%; aspect-ratio: 1/1`. Added `max-height: calc(100dvh - 32px); overflow-y: auto;` to crop modal card. | N/A (Resolved in KAN-314) | **PASS** |
| **Table, Calendar, & Timeline Views** (`/projects/KAN/issues?layout=table`) | `844x390` | In compact landscape (390px height), table rows and calendar headers consume excessive vertical real estate leaving only 1-2 visible items. | Preserved functional containment in baseline CSS. Spawned child remediation ticket for compact landscape row heights and sticky header containment. | `KAN-343` | **PASS** |
| **Admin & Settings Studios** (`/admin/auth`, `/admin/ai`, `/admin/links`) | `390x844` | Multi-column studio layouts (auth cards, provider grids, link tables) require responsive column stacking and horizontal swipe tabs. | Added baseline mobile typography (16px inputs) and touch targets. Spawned child remediation ticket for multi-card studio responsive stacking. | `KAN-344` | **PASS** |

---

## Spawned Child Remediation Tickets (Project KAN)

1. **`KAN-342`**: `[KB-MOBILE-TOUCH-DND] Add Mobile Touch Action Popover and Long-Press Reorder Fallbacks for Board Cards and Stickies`
   - State: `Todo`
   - Parent: `KAN-314`
   - Scope: Dedicated touch card action sheet and accessible long-press reorder fallbacks for touch devices where HTML5 DnD is unreliable.

2. **`KAN-343`**: `[KB-MOBILE-LANDSCAPE-LAYOUT] Compact Landscape Row Heights and Sticky Header Containment for Table, Calendar, and Timeline Views`
   - State: `Todo`
   - Parent: `KAN-314`
   - Scope: Compact 28px table rows and minimized calendar headers under `@media (max-height: 500px) and (orientation: landscape)`.

3. **`KAN-344`**: `[KB-MOBILE-ADMIN-STUDIOS] Responsive Column Stacking and Horizontal Swipe Tabs for Admin and Settings Studios`
   - State: `Todo`
   - Parent: `KAN-314`
   - Scope: Responsive column stacking and swipeable tab navigation for AuthStudio, AiStudio, McpAccessStudio, and LinkAuditorStudio.

4. **`KAN-345`**: `[KB-MOBILE-COMMENT-EDITOR] Virtual Keyboard Inset Handling and Mobile Toolbar for Ticket Comment Editor`
   - State: `Todo`
   - Parent: `KAN-314`
   - Scope: `interactive-widget=resizes-content` viewport inset handling and sticky floating formatting toolbar for mobile comment drafting.

5. **`KAN-346`**: `[KB-MOBILE-DOCS-PAN-ZOOM] Mobile Touch Pan and Pinch-to-Zoom for Embedded Mermaid Diagrams and Wide Code Blocks in Docs`
   - State: `Todo`
   - Parent: `KAN-314`
   - Scope: Gesture pan and pinch-to-zoom modal for Mermaid diagrams and wide SVG/code blocks on mobile and tablet touch viewports.

---

## Automated Audit Gate Scanners Added to `gateAuditor.ts`

- `scanMobileTouchTargets(page, { minTarget: 44, containerSelector?: string })`: Detects interactive buttons, links, and form controls measuring < 44x44px.
- `scanMobileInputFontSizes(page, { minFontSize: 16, containerSelector?: string })`: Detects text inputs, selects, and textareas with computed font-size < 16px to prevent iOS auto-zoom.
- `scanTopbarOcclusion(page, topbarSelector, targetSelectors)`: Detects sticky or drawer panes obscured by the fixed `.kb-topbar`.
