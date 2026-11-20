# Forensic QA Verification Packet: KAN-13 ([KB-P3-AUDIT-07])

## 1. Executive Summary & Verification Context
- **Ticket ID:** KAN-13 ([KB-P3-AUDIT-07])
- **Repository Root:** `/home/adamoutler/kanban`
- **Status:** READY FOR CLEAN-ROOM AUDIT

This packet provides indisputable zero-mock forensic proof for all 4 scoped KAN-13 problems plus clean-room CSP, editor, and mobile viewport polish:
1. **Render Fenced Mermaid Diagrams in `SafeMarkdownPreview` & `IssueSurface` (`Problem 1`):**
   - `SafeMarkdownPreview.tsx` normalizes CRLF (`\r\n` -> `\n`) and renders fenced ` ```mermaid ` blocks via `<MermaidBlockView readOnly={true} />` in issue descriptions, comment previews, and activity comments.
   - `mermaid.worker.ts` and `safeSvg.ts` convert Mermaid styles to pure SVG XML presentation attributes and strip `<style>` / `style="..."` before `DOMPurify.sanitize()`, eliminating all Chromium `style-src 'self'` CSP console violations.
2. **Mermaid Toolbar Fence Insertion & Disabled Code Ligatures (`Problem 2`):**
   - `CommentComposer.tsx`, `IssueSurface.tsx`, and `MarkdownEditor.tsx` all insert valid `'```mermaid\ngraph TD\n  A[Start] --> B[End]\n```'` (zero trailing semicolons) with `\n\n` separation and place the cursor after the closing fence (`newCursor = start + replacement.length`), verified via consecutive 2x click unit tests and live Playwright tests.
   - `base.css` disables code font ligatures (`font-variant-ligatures: none; font-feature-settings: "liga" 0, "calt" 0;`).
3. **Move `Hide Nav` Off Ticket Header onto Global Workspace Header / Topbar (`Problem 3`):**
   - Removed `.issue-header__nav-toggle` from `IssueSurface.tsx` and `.kb-sidebar-footer` from `Sidebar.tsx`.
   - Lifted `isSidebarCollapsed` + `[` shortcut into `AppShell.tsx`, placing `<PanelLeftClose />` in `Sidebar.tsx` header and `<PanelLeftOpen />` in `Topbar.tsx` when collapsed on desktop (`>=1280px`).
4. **Replace `[👍]` Workspace Prefix with `<WorkspaceBadge />` Monogram (`Problem 4`):**
   - Implemented `WorkspaceBadge.tsx` + `WorkspaceBadge.css` (`0` inline `style={...}` props) across `Sidebar.tsx` and `Breadcrumb.tsx`.
5. **Mobile `390x844` `MediaViewport` Controls Non-Occlusion:**
   - `MediaViewport.css` docks `.media-viewport__controls` cleanly below the canvas (`position: static`) on `<=640px`, keeping Mermaid SVG diagrams 100% unobstructed on mobile.

## 2. Unit Test & Static Quality Proof
- **Frontend Unit Tests (`docs/qa/KAN-13/unit-test-results.txt`):** `18` test suites passed (`315` tests), achieving **`99.28%` Stmts, `95.18%` Branch, `98.25%` Funcs, `99.53%` Lines** across all 14 touched source files (`AppShell.tsx`, `Sidebar.tsx`, `Topbar.tsx`, `Breadcrumb.tsx`, `WorkspaceBadge.tsx`, `MarkdownEditor.tsx`, `MediaViewport.tsx`, `safeSvg.ts`, `MermaidBlockView.tsx`, `mermaid.worker.ts`, `CommentComposer.tsx`, `SafeMarkdownPreview.tsx`, `PropertiesRail.tsx`, `IssueSurface.tsx`).
- **Static Checks (`docs/qa/KAN-13/build-or-typecheck.txt`):** `tsc -b --noEmit`, `eslint . --max-warnings 0`, `vite build`, `ruff check`, `mypy` (`0` errors across 1131 files), `lint-imports` (`2 kept, 0 broken`), and `check_no_dashes` (`0` em/en-dashes) all exit `0`.

## 3. Zero-Mock Live Full-Stack Proof (`docs/qa/KAN-13/live-fullstack-proof.txt`)
Verified against live standalone container `kanban-liveqa-2` (`thumbs-up-kanban:local-qa` on `http://localhost:18952`, **zero** `mockApi` / `page.route` stubs):
- Consecutive 2x click of `[aria-label="Insert Mermaid diagram"]` in BOTH `IssueSurface` (`PATCH /api/v1/issues/KAN-1` -> `200`) and `CommentComposer` (`POST` comment -> `201`) rendered 4 loaded `blob:` SVG diagrams (`complete: true`, `naturalWidth: 150`, `naturalHeight: 202`) with `0` error banners.
- At `390x844` mobile, all 4 `.media-viewport__controls` had `position === "static"` and `controlsRect.top === diagramRect.bottom` (`0` occlusion/overlap), `main.scrollWidth === 390`.
- `console.error` count = `0`, `pageerror` count = `0`.

## 4. Live Zero-Mock Screenshots (`docs/qa/KAN-13/screenshots/`)
- `live-kan13-issue-desktop-light.png`
- `live-kan13-issue-desktop-dark.png`
- `live-kan13-issue-expanded-desktop-light.png`
- `live-kan13-issue-collapsed-desktop-light.png`
- `live-kan13-issue-mobile-light.png`
- `live-kan13-issue-mobile-dark.png`
