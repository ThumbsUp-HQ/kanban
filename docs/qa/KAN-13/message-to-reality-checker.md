# Forensic QA Proof Packet for KAN-13 ([KB-P3-AUDIT-07])

## Task Overview
Ticket: KAN-13 ([KB-P3-AUDIT-07])
Title: Render Mermaid outside Docs, fix fence newlines & ligatures, move Hide Nav to Workspace/Topbar header, and replace [👍] workspace prefix with WorkspaceBadge.
Branch: feat/KAN-13

## 4 Scoped Problems & Solutions Implemented

### 1. Render Fenced Mermaid in SafeMarkdownPreview & IssueSurface
- In `kanban/web/src/features/activity/SafeMarkdownPreview.tsx`: Normalized CRLF (`\r\n` -> `\n`) and lowercased `codeLang`. When `codeLang === 'mermaid'`, renders live interactive vector SVGs via `<MermaidBlockView source={codeLines.join('\n')} readOnly={true} />`.
- In `kanban/web/src/features/drawer/IssueSurface.tsx`: Removed redundant raw `<pre className="surface__mermaid-code">` code block dump, ensuring issue descriptions and comments render crisp, styled vector Mermaid diagrams without raw syntax leaks.

### 2. Fix Mermaid & Code Toolbar Fence Newlines & Suppress Ligatures
- In `CommentComposer.tsx`, `IssueSurface.tsx`, and `MarkdownEditor.tsx`: Added smart newline prepending whenever `start > 0 && current[start - 1] !== '\n'`, and trailing newline append after closing ``` fence so repeated toolbar insertions never glue markdown blocks together.
- In `kanban/web/src/styles/base.css`, `activity.css`, `MermaidBlockView.css`, and `MarkdownEditor.css`: Applied strict ligature suppression:
  `font-variant-ligatures: none; font-feature-settings: "liga" 0, "calt" 0;`
  ensuring sequence syntax like `-->` or `->` renders as distinct characters without browser ligature substitution into Unicode arrows (`→`).

### 3. Move Hide Nav Off Ticket Header onto Global Workspace Header / Topbar
- In `kanban/web/src/features/drawer/IssueSurface.tsx`: Completely removed `isNavHidden`, `kb:sidebar-changed` window listeners, `handleToggleNav`, and `.issue-header__nav-toggle`. Set `.surface--full { left: 0 }` for full-width presentation when collapsed or on tablet/mobile screens (`<=1279px`).
- In `kanban/web/src/app/AppShell.tsx`: Lifted `isSidebarCollapsed` state and keyboard shortcut `[` into `AppShell` as single source of truth without side effects during render.
- In `kanban/web/src/app/Sidebar.tsx`: Rendered collapse toggle button `<PanelLeftClose size={16} />` with `aria-label="Collapse navigation sidebar"` directly adjacent to the Workspace Switcher in the sidebar header row. Removed legacy `Hide Nav` link from the sidebar footer.
- In `kanban/web/src/app/Topbar.tsx`: Rendered `<PanelLeftOpen size={16} />` button with `aria-label="Expand navigation sidebar"` in the Topbar header on desktop (`>=1280px`) when the sidebar is collapsed. Retained hamburger menu (`☰`) on mobile viewports (`<=1279px`).

### 4. WorkspaceBadge Monogram Replacing [👍] Prefix
- Created `kanban/web/src/components/workspace/WorkspaceBadge.tsx` and `WorkspaceBadge.css`:
  - Renders 1 to 2 uppercase monogram initials computed deterministically via `getWorkspaceInitials(name)`.
  - Maps workspace name to 6 theme-safe CSS tone classes (`workspace-badge--tone-0` through `workspace-badge--tone-5`) using canonical theme variables (`--accent-subtle`, `--accent`, `--tone-*-bg`, `--tone-*-fg`).
  - Zero inline styles (`style={{...}}`), fully compliant with `cssTokensAudit`.
- In `kanban/web/src/app/Sidebar.tsx` and `kanban/web/src/app/Breadcrumb.tsx`: Replaced every hardcoded `[👍]` emoji and `'👍kanban'` fallback with `<WorkspaceBadge name={...} />` and clean `'kanban'` fallback.

## Verification Proofs & Forensic Evidence

### 1. Visual Verification (Playwright E2E Screenshots)
Captured 12 comprehensive screenshots in `docs/qa/KAN-13/screenshots/` across Desktop (1440x900) and Mobile (390x844) viewports in both Light and Dark themes:
- `01-desktop-light-mermaid-issue.png`: Live Mermaid diagram rendered in issue description and comment on desktop light theme.
- `02-desktop-dark-mermaid-issue.png`: Live Mermaid diagram rendered in issue description and comment on desktop dark theme.
- `03-mobile-light-mermaid-issue.png`: Live Mermaid diagram rendered in mobile issue surface light theme.
- `04-mobile-dark-mermaid-issue.png`: Live Mermaid diagram rendered in mobile issue surface dark theme.
- `05-desktop-light-workspace-badge.png`: `<WorkspaceBadge />` monogram in Breadcrumb and Workspace Switcher (Desktop light).
- `06-desktop-dark-workspace-badge.png`: `<WorkspaceBadge />` monogram in Breadcrumb and Workspace Switcher (Desktop dark).
- `07-desktop-light-sidebar-collapsed.png`: Desktop light theme with collapsed navigation sidebar and topbar expand button.
- `08-desktop-dark-sidebar-collapsed.png`: Desktop dark theme with collapsed navigation sidebar and topbar expand button.
- `09-desktop-light-sidebar-expanded.png`: Desktop light theme with expanded sidebar and sidebar header collapse button.
- `10-desktop-dark-sidebar-expanded.png`: Desktop dark theme with expanded sidebar and sidebar header collapse button.
- `11-mobile-light-workspace-badge.png`: Mobile light theme displaying `<WorkspaceBadge />` in Topbar breadcrumb.
- `12-mobile-dark-workspace-badge.png`: Mobile dark theme displaying `<WorkspaceBadge />` in Topbar breadcrumb.

### 2. Unit Test Coverage Proof (Vitest)
Unit tests across all touched components pass with 209 passing tests and >= 95% line and branch coverage:
- `All files`: 99.28% Statements, 95.46% Branches, 98.44% Functions, 99.5% Lines
- `SafeMarkdownPreview.tsx`: 100% Lines, 95.65% Branches
- `CommentComposer.tsx`: 100% Lines, 97.29% Branches
- `MarkdownEditor.tsx`: 99.56% Lines, 95.19% Branches
- `WorkspaceBadge.tsx`: 100% Lines, 100% Branches
- `Breadcrumb.tsx`: 100% Lines, 95.0% Branches
- `AppShell.tsx`: 99.01% Lines, 97.4% Branches
- `Sidebar.tsx`: 99.55% Lines, 92.91% Branches
- `IssueSurface.tsx`: 100% Lines, 96.11% Branches
- `Topbar.tsx`: 96.47% Lines, 96.22% Branches
Raw log saved in `docs/qa/KAN-13/unit-test-results.txt`.

### 3. Static Analysis & Build Verification
Full logs captured in `docs/qa/KAN-13/build-or-typecheck.txt`:
- TypeScript: `pnpm --dir kanban/web typecheck` (tsc -b --noEmit) -> 0 errors.
- ESLint: `pnpm --dir kanban/web lint` (eslint . --max-warnings 0) -> 0 errors, 0 warnings.
- CSS Tokens Audit: `pnpm --dir kanban/web exec vitest run src/styles/__tests__/cssTokensAudit.test.ts` -> 4/4 passed.
- Dash Sanitization: `python3 -m scripts.check_no_dashes --all` -> 0 em/en-dashes detected.
- Zero new dependencies introduced in `package.json`.
- Zero inline styles (`style={{...}}`) used in JSX.
