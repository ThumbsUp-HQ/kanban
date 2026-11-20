# Reality Checker Verification Packet: KAN-16 Release Candidate 1 (RC1)

To: reality-checker (Passive Forensic QA Gate)
From: b-kan16-rc1 (Builder)
Branch: fix/KAN-16-rc1
Target: Remediate EVERY finding from `docs/qa/KAN-16/reality-checker-report.md`

## 1. Itemized Remediation of Reality-Checker Findings

### Finding 1: Mobile & Tablet Chapter Navigation (Critical Issue 1)
- Problem: At `<= 768px` (including 768x1024 tablet and 390x844 mobile), `.kb-docs-sidebar { display: none; }` removed all chapter navigation, leaving users with zero way to browse chapters.
- Remediation:
  * In `DocsCenterPage.tsx` (lines 145-154), added a responsive `Chapters` button (`data-testid="docs-mobile-chapters-btn"`, `min-height: 44px`, visible strictly at `<= 768px`).
  * In `DocsCenterPage.tsx` (lines 209-261) and `DocsCenterPage.css` (lines 351-445), implemented an accessible slide-over chapters drawer (`data-testid="docs-mobile-chapters-drawer"`, `role="dialog"`, `aria-modal="true"`).
  * Includes backdrop click dismissal (`data-testid="docs-mobile-drawer-backdrop"`), dedicated close button (`data-testid="docs-mobile-drawer-close"`), Escape keyboard dismiss, and automatic drawer close upon selecting any chapter link.
  * Verified in `DocsCenter.test.tsx` (lines 980-1010): opens drawer, asserts chapter links, selects a chapter link and verifies drawer closes, opens drawer and verifies dismiss via backdrop click, and verifies dismiss via Escape key.

### Finding 2: Offline Bundled Wiki Images & Safe Markdown Image Rendering (Critical Issue 2)
- Problem: `DocMarkdownViewer.tsx` lacked image syntax handling, causing embedded `![alt](src)` markdown images to render as literal `!Alt Text` strings; no wiki images were bundled into `kanban/web/public/`.
- Remediation:
  * In `scripts/sync_wiki_bundle.py`: Added `sync_wiki_images()` which copied all 65 PNG screenshots from `thumbs-up-kanban.wiki/images/` into `kanban/web/public/docs-images/`.
  * In `scripts/sync_wiki_bundle.py`: Updated `load_chapters_from_wiki()` to put `Home.md` (`Overview`) FIRST (`Chapter 1 of 27`!), resolving alphabetical sorting that previously pushed `Home` to Chapter 11.
  * In `DocMarkdownViewer.tsx` (lines 28-56): Added `resolveSafeDocImageUrl()` which strictly resolves relative `images/<file>`, `./images/<file>`, `/docs-images/<file>`, and `docs-images/<file>` paths to `/docs-images/<file>`, while rejecting all external or protocol URLs (`http:`, `https:`, `//`, `data:`, `javascript:`).
  * In `DocMarkdownViewer.tsx` (lines 381-403): Added standalone figure/img line parsing (`<figure className="kb-doc-figure">`, `<img loading="lazy" className="kb-doc-image" />`, `<figcaption>`).
  * In `DocMarkdownViewer.tsx` (lines 89-106): Updated `renderInlineMarkdown` regex to safely parse inline `![alt](src)` markdown tokens before hyperlink tokens.
  * In `DocMarkdownViewer.css`: Added responsive styles using design tokens (`max-width: 100%`, `border-radius: var(--radius-md)`, `border: 1px solid var(--border-subtle)`).
  * Verified in `DocsCenter.test.tsx` (lines 910-978): verifies block image rendering, inline image rendering, empty alt text fallback, and rejection of remote URLs.

### Finding 3: Mobile Header Layout & Search Placeholder Clipping (Medium Issue 1)
- Problem: At 390px, "Kanban Docs" and "Offline Center" wrapped onto 2 lines each, and the search placeholder clipped to "Search offline ".
- Remediation:
  * In `DocsCenterPage.tsx` (lines 135-154) and `DocsCenterPage.css` (lines 318-350): Introduced `kb-docs-header-row-1` containing brand title, `Offline Center` badge, and `Chapters` button with `white-space: nowrap` and `flex-wrap: nowrap`.
  * Moved the search input container to row 2 with `width: 100%`, ensuring the full placeholder `"Search offline docs..."` remains unclipped without horizontal overflow.

### Finding 4: HelpDrawer Modal Focus Trap, Prop Sync & TOC Labels (Medium Issue 2 & Polish)
- Problem: `HelpDrawer.tsx` lacked initial focus placement, `Tab` focus trap, trigger focus restoration on close, and prop resync when `arg` changed while mounted. Heading links also displayed raw markdown backticks.
- Remediation:
  * In `HelpDrawer.tsx` (lines 64-75): Saved `document.activeElement` on mount into `previousActiveElementRef` and restored focus to the invoking trigger element on unmount.
  * In `HelpDrawer.tsx` (lines 77-90): Initial focus automatically moves to `closeButtonRef` upon opening the drawer.
  * In `HelpDrawer.tsx` (lines 136-156): Implemented accessible keyboard focus trap: `Shift+Tab` on first focusable element wraps to last focusable element; `Tab` on last focusable element wraps to first focusable element.
  * In `HelpDrawer.tsx` (lines 53-62): Implemented render-time prop resynchronization: when `arg` (`resolvedSlug` or `resolvedAnchor`) changes while mounted, state updates cleanly without cascading effect renders.
  * In `HelpDrawer.tsx` (lines 173-176) and `DocsCenterPage.tsx` (line 309): Stripped raw backticks from TOC section titles (`sec.title.replace(/`/g, '')`).
  * Verified in `DocsCenter.test.tsx` (lines 1011-1097, 1099-1137).

### Finding 5: Sticky Sidebar Scroll & Text Clipping (Polish)
- Problem: In `live-docs-desktop-dark.png`, scrolling clipped sidebar items mid-line and left a void underneath.
- Remediation:
  * In `DocsCenterPage.css` (lines 103-113, 226-236): Updated `.kb-docs-sidebar` and `.kb-docs-toc-rail` to:
    `position: sticky; top: 0; max-height: 100vh; overflow-y: auto; padding-bottom: var(--space-6);`
  * Elements now scroll smoothly within their visible containers without slicing text or leaving bottom voids.

### Finding 6: Dead Shadowed Routes Cleanup (Polish)
- Problem: `kanban/web/src/app/routes.tsx` had duplicate shadowed child routes for `/docs` and `/help` inside `RootShellLayout`.
- Remediation:
  * In `routes.tsx`, deleted dead lines ~2037-2051 inside `RootShellLayout`, leaving the top-level public bypass routes (lines 1994-2008) as the single authoritative route handlers.

### Finding 7: Act(...) and Controlled-Input Test Warnings Eliminated (QA Inaccuracy 3)
- Problem: `StandaloneStatusPanel.test.tsx` emitted multiple `act(...)` and uncontrolled-input warnings in `unit-test-results.txt`.
- Remediation:
  * In `StandaloneStatusPanel.tsx`: Gated `<ComposeExportTab />` to mount only when `activeTab === 'compose'` (`{activeTab === 'compose' && <ComposeExportTab />}`), preventing unmocked background fetch requests from resolving outside test boundaries.
  * In `StandaloneStatusPanel.tsx` (lines 834, 851, 871): Maintained controlled input state with valid boolean and number defaults.
  * In `StandaloneStatusPanel.test.tsx`: Wrapped all tab switches, button clicks, and synthetic keyboard events in `act(...)`.
  * Result: `unit-test-results.txt` has ZERO `act(...)` warnings and ZERO controlled-input warnings across ALL 14 test files!

### Finding 8: 100% Verbatim Accuracy in Proof Packet (QA Inaccuracies 1, 2, 4)
- Verified all counts, durations, and outputs across proof files:
  * `unit-test-results.txt`:
    - `DocsCenter.test.tsx`: 35/35 passed (duration 2.55s).
    - Full suite: 14 test files passed (14), 350 tests passed (350), duration 8.23s (tests 50%, environment 33%, import 11%, transform 6%, worker 1%).
    - Code coverage across all touched docs-center files: 99.5% Statements, 97.06% Branch, 100% Functions, 100% Lines (all exceeding the 95% threshold).
    - `cssTokensAudit.test.ts`: 4/4 passed (0 inline JSX `style={...}` attributes, 100% token usage).
  * `build-or-typecheck.txt`:
    - `tsc -b --noEmit`: 0 errors.
    - `eslint . --max-warnings 0`: 0 problems.
    - `vite build`: built in 1.28s, 720 modules transformed.
    - `ruff check scripts/sync_wiki_bundle.py`: All checks passed!
    - `ruff format --check scripts/sync_wiki_bundle.py`: 1 file already formatted.
    - `mypy scripts/sync_wiki_bundle.py`: Success: no issues found in 1 source file.
    - `python3 -m scripts.check_no_dashes`: 0 em/en-dashes found.

## 2. Evidence Files Index

- `docs/qa/KAN-16/unit-test-results.txt`: Verbatim Vitest coverage table and 14-file test execution output.
- `docs/qa/KAN-16/build-or-typecheck.txt`: Verbatim static gate logs (tsc, eslint, vite build, ruff, mypy, check_no_dashes).
- `docs/qa/KAN-16/changed-files-manifest.txt`: Complete manifest of changed files.
- `docs/qa/KAN-16/git-diff.patch`: Patch of all implementation and script changes.
- `docs/qa/KAN-16/screenshots/`: 11 Playwright screenshots documenting desktop, tablet, and mobile views.

Working directory and git status verified clean with unstaged local backup files preserved.
Ready for reality-checker QA gate certification.
