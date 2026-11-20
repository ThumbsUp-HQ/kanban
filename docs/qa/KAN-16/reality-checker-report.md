# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Passive Clean-Room R1 audit only (0 shell commands executed, 0 URLs visited, 0 files modified; inspected exclusively via `read_file` per passive forensic rules).
**Evidence Captured**:
- QA Packet in `docs/qa/KAN-16/`: `message-to-reality-checker.md`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `live-fullstack-proof.txt`, `ui-specialist-review.md`
- 11 live Playwright PNG screenshots in `docs/qa/KAN-16/screenshots/`
- Direct source verification across `scripts/sync_wiki_bundle.py`, `kanban/web/src/features/docs-center/*`, `kanban/web/src/components/help/*`, `kanban/web/src/app/{routes.tsx,AppShell.tsx,shellPanels.tsx,Sidebar.tsx,Topbar.tsx}`, `kanban/web/src/features/auth/useSessionGuard.ts` (note: located under `features/auth/`, not `src/auth/`), and studio pages (`ProjectSettingsPage.tsx`, `WorkspaceSettingsPage.tsx`, `WorkflowStudioPage.tsx`, `AuthStudioPage.tsx`, `McpAccessStudio.tsx`, `AiStudioPage.tsx`, `StandaloneStatusPanel.tsx`)

**QA Cross-Validation**:
- **Confirmed**:
  - Offline `/docs` and `/help/:slug` routes are publicly accessible pre-bootstrap (`PUBLIC_PATH_PREFIXES` includes `'/docs'` and `'/help'` in `useSessionGuard.ts`, and top-level routes in `routes.tsx` lines 1994-2008 bypass `AppShell`).
  - `scripts/sync_wiki_bundle.py` compiles cleanly (`ruff` and `mypy` 0 issues) and bundles 27 chapters into `wikiManifest.ts`.
  - `DocsCenter.test.tsx` passes 29/29 tests with 99.39% statements, 97.59% branches, 100% functions, 100% lines coverage; `tsc -b --noEmit` and `eslint . --max-warnings 0` exit 0; `check_no_dashes.py` exits 0; `cssTokensAudit.test.ts` passes 4/4.
  - Live Playwright unmocked container (`kanban-liveqa-3`) verified 0 external egress, 0 console errors, 0 page errors, 0 HTTP 5xx responses, live Mermaid SVG rendering, and `HelpDrawer` preserving `"UNSAVED-DRAFT-42"` on `/projects/KAN/settings`.
- **Challenged / Discrepancies Found**:
  1. `ui-specialist-review.md` (line 84) claims `DocsCenter.test.tsx` passed `29/29 tests in 1.23s`, whereas verbatim `unit-test-results.txt` (line 15) shows `Duration  3.23s`.
  2. `ui-specialist-review.md` (line 91) claims `344/344 tests passed across all 11 touched studios`, whereas `unit-test-results.txt` shows 29 tests in `DocsCenter.test.tsx` plus 315 tests across 13 files (which include `cssTokensAudit.test.ts` [4] and `FieldHelpHint.test.tsx` [23]), meaning 288 tests across the 11 studio test files (344 total across all 14 test files).
  3. `message-to-reality-checker.md` (line 76) claims `Stderr act(...) warnings: 0`, which holds for `DocsCenter.test.tsx` and `RunnerStudioPage.test.tsx`, but `unit-test-results.txt` (lines 43-209) contains multiple `act(...)` and controlled-input warnings from `StandaloneStatusPanel.test.tsx`.
  4. `message-to-reality-checker.md` (line 96) reports Vite build time as `1.48s`, whereas `build-or-typecheck.txt` (line 33) shows `built in 1.62s` alongside chunk-size warnings (`mermaid.worker` 1,530.54 kB and `index` 2,369.70 kB > 500 kB).
  5. `ui-specialist-review.md` claims clean responsive adaptation across Tablet and Mobile, which is contradicted by visual inspection of `live-docs-tablet-light.png` and `live-docs-mobile-light.png` (no mobile/tablet chapter navigation UI exists when `.kb-docs-sidebar` is hidden).

## 📸 Complete System Evidence
**Visual Documentation**:
- Full system screenshots inspected (all 11 PNGs):
  - `docs/qa/KAN-16/screenshots/live-docs-desktop-light.png` (1440x900 Light)
  - `docs/qa/KAN-16/screenshots/live-docs-desktop-dark.png` (1440x900 Dark)
  - `docs/qa/KAN-16/screenshots/live-docs-tablet-light.png` (768x1024 Light)
  - `docs/qa/KAN-16/screenshots/live-docs-mobile-light.png` (390x844 Light)
  - `docs/qa/KAN-16/screenshots/live-help-guide-custom-fields-light.png` (1440x900 Light, `/help/Guide-Custom-Fields`)
  - `docs/qa/KAN-16/screenshots/live-docs-search-listbox-light.png` (1440x900 Light, search `"Mermaid"`)
  - `docs/qa/KAN-16/screenshots/live-project-settings-field-help-popover-light.png` (1440x900 Light, `(?)` popover + `"UNSAVED-DRAFT-42"`)
  - `docs/qa/KAN-16/screenshots/live-project-settings-help-drawer-light.png` (1440x900 Light, `HelpDrawer` open over blurred form)
  - `docs/qa/KAN-16/screenshots/live-project-settings-help-drawer-dark.png` (1440x900 Dark, `HelpDrawer` open)
  - `docs/qa/KAN-16/screenshots/live-help-drawer-mobile-light.png` (390x844 Light, `HelpDrawer` 100vw)
  - `docs/qa/KAN-16/screenshots/live-admin-ai-help-drawer-light.png` (1440x900 Light, `/admin/ai` `StudioDocLink`)
- User journey evidence:
  - `/docs` landing -> `/help/Guide-Custom-Fields` deep link -> `"Mermaid"` instant search listbox -> `/projects/KAN/settings` `(?)` popover -> `More info ->` slide-over `HelpDrawer` preserving `"UNSAVED-DRAFT-42"` -> `/admin/ai` `StudioDocLink` -> `HelpDrawer`
- Cross-browser comparison: Only Chromium Playwright screenshots provided; no Firefox/WebKit screenshots present.

**What System Actually Delivers**:
- **Desktop Light (`live-docs-desktop-light.png`, `live-help-guide-custom-fields-light.png`, `live-docs-search-listbox-light.png`)**: Clean 3-column layout (categories rail, prose content, right `ON THIS PAGE` TOC rail), `Chapter 11 of 27` (`Home` / `Overview`), rendered Mermaid diagram (`Alt: Mermaid diagram` tooltip visible), and responsive instant search listbox showing 8 matching results with category and snippet. However, `System Architecture` appears first in the left rail and `Home` is `Chapter 11 of 27` due to alphabetical `.md` sorting in `sync_wiki_bundle.py`.
- **Desktop Dark (`live-docs-desktop-dark.png`, `live-project-settings-help-drawer-dark.png`)**: Dark tokens render cleanly in the main pane and `HelpDrawer`, but `live-docs-desktop-dark.png` is captured mid-scroll where the sticky `.kb-docs-sidebar` (`height: calc(100vh - var(--topbar-h))`) slices `"Three-Surface Model Context..."` horizontally at the bottom edge of the rail and leaves a dark void underneath it.
- **Tablet & Mobile (`live-docs-tablet-light.png`, `live-docs-mobile-light.png`)**: Both the right TOC rail (`<= 1024px`) and left chapters sidebar (`<= 768px`) are set to `display: none` in `DocsCenterPage.css`, leaving zero chapter-switcher or drawer menu on 768px tablet or 390px mobile. On 390px mobile, `"Kanban Docs"` and `"Offline Center"` wrap onto 2 lines each and the search input placeholder clips to `"Search offline "`.
- **Contextual `(?)` Popover & `HelpDrawer` (`live-project-settings-field-help-popover-light.png`, `live-project-settings-help-drawer-light.png`, `live-help-drawer-mobile-light.png`, `live-admin-ai-help-drawer-light.png`)**: `FieldHelpHint` opens cleanly over `/projects/KAN/settings`, and clicking `More info ->` opens the 480px `HelpDrawer` (390px / 100vw on mobile) while keeping `/projects/KAN/settings` mounted and `"UNSAVED-DRAFT-42"` intact. Drawer header titles truncate (`"Ticket Screen, Peek Drawer, a..."`) and `SECTIONS` TOC links show raw markdown backticks (e.g., `` (`C`) ``, `` (`/admin/ai`) ``).

## 🧪 Integration Testing Results
- **End-to-End User Journeys**: **PARTIAL PASS**
  - Desktop `/docs` landing, `/help/:slug` alias, instant search, Mermaid rendering, and `/projects/KAN/settings` + `/admin/ai` `FieldHelpHint`/`StudioDocLink` -> `HelpDrawer` preserving `"UNSAVED-DRAFT-42"` PASS based on screenshots and `live-fullstack-proof.txt`.
  - Mobile and 768px Tablet chapter-browsing journey FAILS (`live-docs-tablet-light.png` and `live-docs-mobile-light.png` show no sidebar, no TOC, and no mobile chapter menu trigger).
  - Markdown chapters containing embedded `![alt](images/...)` screenshots FAIL image rendering in `DocMarkdownViewer.tsx` (verified by code inspection against `wikiManifest.ts` line 87).
- **Cross-Device Consistency**: **FAIL (Mobile/Tablet navigation & header wrapping)**
  - `horizontal overflow = false` holds across Desktop (1440x900), Tablet (768x1024), and Mobile (390x844), and Mobile `HelpDrawer` fits 390px (`live-help-drawer-mobile-light.png`). However, hiding `.kb-docs-sidebar` at `<= 768px` without a mobile/tablet navigation toggle breaks chapter discovery, and the 390px header wraps/clips (`live-docs-mobile-light.png`).
- **Performance Validation**: **PASS**
  - `/docs`: 1023 ms; `/help/Guide-Custom-Fields`: 605 ms; `/projects/KAN/settings`: 1111 ms (all under 3s threshold, 0 external requests, 0 console/page errors, 0 HTTP 5xx).
- **Specification Compliance**: **PARTIAL PASS**
  - Offline wiki bundling (27 chapters), pre-bootstrap public `/docs` & `/help` access, `Sidebar.tsx` + `Topbar.tsx` entry points, form-preserving `HelpDrawer`, `(?)` popovers, `StudioDocLink` across 11 studios, and zero inline JSX `style={...}` props are implemented.
  - Gaps: no mobile/tablet chapter navigation fallback, no markdown image (`![alt](src)`) support in `DocMarkdownViewer.tsx`, and missing `Tab` focus-trap/restoration in `HelpDrawer.tsx`.

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
- `StandaloneStatusPanel.test.tsx` in `unit-test-results.txt` (lines 43-209) still emits `act(...)` and controlled/uncontrolled input warnings (masked by `message-to-reality-checker.md` claiming `Stderr act(...) warnings: 0`).
- Vite production build (`build-or-typecheck.txt` lines 28-32) still emits >500 kB chunk warnings (`mermaid.worker` 1,530.54 kB, `index` 2,369.70 kB).

**New Issues Discovered**:
1. **No Mobile/Tablet Chapter Navigation (`DocsCenterPage.tsx`, `DocsCenterPage.css`, `live-docs-tablet-light.png`, `live-docs-mobile-light.png`)**: At `<= 768px` (which includes 768px tablet and 390px mobile), `.kb-docs-sidebar { display: none; }` removes the 27-chapter navigation rail with no hamburger drawer or chapter `<select>` fallback.
2. **Markdown Image Syntax Broken (`DocMarkdownViewer.tsx` vs `wikiManifest.ts`)**: `renderInlineMarkdown` (`DocMarkdownViewer.tsx` lines 35-36) lacks `![alt](src)` matching, and `isSafeUrl` rejects relative `images/...` paths. Embedded images in bundled wiki chapters (e.g., `admin-custom-scripted-fields-and-sandbox`) degrade to literal `!Alt Text` strings, and no wiki `images/*.png` assets are bundled in `changed-files-manifest.txt`.
3. **Mobile Header Wrapping & Placeholder Truncation (`live-docs-mobile-light.png`, `DocsCenterPage.css` lines 318-331)**: At 390px, `"Kanban Docs"` and `"Offline Center"` wrap onto 2 lines and the search placeholder clips to `"Search offline "`.
4. **`HelpDrawer` Modal Focus & Prop Sync Gaps (`HelpDrawer.tsx`)**: Despite `role="dialog"` and `aria-modal="true"`, `HelpDrawer.tsx` neither moves initial focus into the dialog, traps `Tab` focus inside the drawer, nor restores focus to the invoking `(?)` / `StudioDocLink` trigger on close. Also `activeAnchor` `useState(initialAnchor)` (line 49) would not resync if `arg` changes while already mounted.
5. **Unverified 9 of 11 Studios in Live Stack (`live-fullstack-proof.txt`)**: Only `/projects/KAN/settings` and `/admin/ai` have live Playwright proof; the other 9 studios rely on Vitest unit tests only.
6. **Minor Polish / Organization Issues**:
   - `sync_wiki_bundle.py` (line 256) sorts files alphabetically, placing `System Architecture` first and `Home` (`Overview`) at `Chapter 11 of 27`.
   - `HelpDrawer.tsx` and `DocsCenterPage.tsx` TOC rails render raw markdown backticks inside section titles (visible in `live-project-settings-help-drawer-light.png` and `live-admin-ai-help-drawer-light.png`).
   - `routes.tsx` duplicates `/docs`, `/docs/:slug`, `/help`, `/help/:slug` at lines 1994-2008 and lines 2037-2051 (inner routes are shadowed/dead).
   - `live-docs-desktop-dark.png` shows the sticky sidebar clipping `"Three-Surface Model Context..."` mid-line when scrolled.

**Critical Issues**:
1. Mobile (`390x844`) and Tablet (`768x1024`) users have no chapter navigation menu when `.kb-docs-sidebar` is hidden (`live-docs-tablet-light.png`, `live-docs-mobile-light.png`).
2. `DocMarkdownViewer.tsx` fails to render `![alt](src)` markdown images present in `wikiManifest.ts` (`admin-custom-scripted-fields-and-sandbox`), outputting stray `!Alt Text` prose instead.

**Medium Issues**:
1. Mobile header wrapping and truncated search placeholder at 390px (`live-docs-mobile-light.png`).
2. `HelpDrawer.tsx` lacks modal `Tab` focus trapping, initial focus placement, and focus restoration on close.
3. QA report inaccuracies in `ui-specialist-review.md` (`1.23s` vs `3.23s`, `344` studio tests vs `344` total across 14 files) and `message-to-reality-checker.md` (`0` stderr warnings vs `StandaloneStatusPanel.test.tsx` warnings; `1.48s` vs `1.62s`), plus live Playwright coverage missing for 9 of 11 wired studios.
4. Sticky sidebar mid-line text clipping in scrolled `live-docs-desktop-dark.png`, alphabetical chapter ordering putting `Home` at `Chapter 11 of 27`, raw backticks in TOC headings, and shadowed duplicate `/docs` routes in `routes.tsx`.

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: **B-**
**Design Implementation Level**: **Good**
**System Completeness**: **82%**
**Production Readiness**: **NEEDS WORK**

## 🔄 Deployment Readiness Assessment
**Status**: **NEEDS WORK**

**Required Fixes Before Production**:
1. Add a responsive chapter navigation drawer or selector button in `DocsCenterPage.tsx` / `DocsCenterPage.css` when `.kb-docs-sidebar` collapses at `<= 768px`, and fix the 390px header layout so `"Kanban Docs"`, `"Offline Center"`, and the search input do not wrap/clip (`live-docs-tablet-light.png`, `live-docs-mobile-light.png`).
2. Implement safe markdown image rendering (`![alt](src)`) in `DocMarkdownViewer.tsx` and bundle or resolve relative `images/*.png` wiki assets (or strip/map them cleanly with tests) so chapters like `admin-custom-scripted-fields-and-sandbox` do not emit raw `!Alt Text` strings.
3. Add accessible `Tab` focus trapping, initial focus placement, and trigger focus restoration to `HelpDrawer.tsx` (`role="dialog"`, `aria-modal="true"`), and strip inline backticks from TOC link labels.
4. Correct the inaccurate timing/count/warning claims in `ui-specialist-review.md` and `message-to-reality-checker.md`, and remove the dead duplicate `/docs` and `/help` child routes in `routes.tsx` (lines 2037-2051).

**Timeline for Production Readiness**: 1 revision cycle (estimated 0.5-1 day of focused frontend + QA evidence cleanup).
**Revision Cycle Required**: **YES**

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Full mobile/tablet chapter navigation parity without hiding all 27 chapters at `<= 768px`.
- Complete markdown image rendering or bundled wiki asset handling in `DocMarkdownViewer.tsx`.
- Full WAI-ARIA modal dialog focus management in `HelpDrawer.tsx`.
- Exact 1:1 accuracy between QA summary markdowns and raw tool logs.

**Quality Targets**:
- `>= 95%` Vitest coverage maintained on `docs-center` and `components/help` with 0 `act(...)` warnings.
- 0 broken/unparsed markdown image syntax across all 27 bundled `WIKI_CHAPTERS`.
- Clean 390px mobile and 768px tablet header + chapter-drawer screenshots with 0 text clipping or 2-line badge wrapping.

**Evidence Requirements**:
- Updated Playwright screenshots showing mobile (`390x844`) and tablet (`768x1024`) chapter menu open/usable and crisp single-row header layout.
- Live Playwright screenshot of a chapter containing an embedded image (e.g., `admin-custom-scripted-fields-and-sandbox`) verifying rendered media instead of `!Alt Text`.
- Updated `docs/qa/KAN-16/` logs with accurate durations/counts and verified keyboard focus-trap tests for `HelpDrawer`.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-16/ and docs/qa/KAN-16/screenshots/
**Re-assessment Required**: After fixes implemented
