# Forensic Verification Hand-off: KAN-313

- **Ticket:** KAN-313 ([KB-TAB-TITLE]) - Fix Double-Thumbs-Up (👍 👍kanban) Browser Tab Title Across SPA, Swagger/ReDoc & Dynamic Route Navigation (4 Problems)
- **Assignee:** Swarm Worker `b-kan313`
- **Branch:** `feat/KAN-313`
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan313-70598e1c`
- **Quality Gate:** Ready for Passive Forensic Audit (`reality-checker`)

---

## 1. Scope & Implementation Summary

This ticket resolves the double thumbs-up (`👍 👍kanban`) browser tab title across the SPA, Swagger/ReDoc documentation, and dynamic route navigation.

1. **Problem 1 (SPA Root `<title>`):**
   - Updated `kanban/web/index.html:8` from `<title>👍kanban</title>` to `<title>kanban</title>`.
   - Combined with `/favicon.ico` (`👍`), the browser tab chrome displays a clean single icon plus text (`👍 kanban`).
   - In-page headings, sidebar branding, `AboutPage.tsx`, OpenAPI `info.title == "👍kanban API"`, and WebAuthn Relying Party name `rp.name == "👍kanban"` strictly retain `👍kanban`.

2. **Problem 2 (Swagger UI & ReDoc Titles):**
   - Updated `kanban/api_docs.py:708` (`render_swagger_ui_html`) to use `<title>{html.escape(display_title)} - Swagger UI</title>`, generating `<title>kanban API - Swagger UI</title>`.
   - Updated `kanban/api_docs.py:834` (`render_redoc_html`) to use `<title>{html.escape(display_title)} - ReDoc</title>`, generating `<title>kanban API - ReDoc</title>`.
   - In-page hero title `<h1>👍kanban API</h1>` preserved for canvas branding.
   - Updated assertions in `kanban/tests/test_api_docs.py` (lines 106, 141).

3. **Problem 3 (Dynamic Title Hook & Route Synchronization):**
   - Created `kanban/web/src/app/documentTitle.ts` exporting `BRAND_TITLE = 'kanban'`, `stripLeadingThumb()`, `formatDocumentTitle()`, and `useDocumentTitle()`.
   - Added unmount cleanup and `stripLeadingThumb` in `FullScreenIssueRoute` (`routes.tsx:1783-1793`).
   - Wired route-aware title synchronization into `AppShell.tsx` and standalone routes (`DocsCenterPage.tsx`, `LoginPage.tsx`, `SetupClaimPage.tsx`, `DeviceActivatePage.tsx`, and `NotFoundView`).

4. **Problem 4 (Unit & E2E Verification):**
   - Added unit test suite `kanban/web/src/app/__tests__/documentTitle.test.ts` achieving 96.55% statement and 95.65% branch coverage.
   - Added route transition and unmount restoration tests to `kanban/web/src/app/routes.test.tsx`.
   - Updated `kanban/web/e2e/sample/harness.spec.ts` title assertion to `'kanban'`.
   - Created E2E test `kanban/web/e2e/qa/kan-313-tab-title-screenshots.spec.ts` capturing 5 responsive screenshots across viewports and color schemes.

---

## 2. Forensic Artifact Inventory

The following verification artifacts have been generated in `docs/qa/KAN-313/`:

1. `git-diff.patch`: Unified diff of all modified and newly created files against main.
2. `unit-test-results.txt`: Raw test execution output showing:
   - 23 passed pytest tests in `test_api_docs.py` and `test_export_openapi.py`.
   - 128 passed Vitest tests across `documentTitle.test.ts`, `routes.test.tsx`, `routesDeepCoverage.test.tsx`, and `wave4BranchBooster.test.tsx`.
3. `build-check.txt`: Raw validation output from `make check`, `pnpm typecheck`, `pnpm lint` (0 warnings), and `pnpm build`.
4. `screenshots/`: 5 responsive Playwright screenshots:
   - `01-desktop-board-title-light.png` (Desktop 1440x900 Light - Board view title verification)
   - `02-desktop-board-title-dark.png` (Desktop 1440x900 Dark - Board view title verification)
   - `03-tablet-fullscreen-issue-title.png` (Tablet 1024x768 - Full-Screen ticket title verification)
   - `04-mobile-portrait-docs-center-title.png` (Mobile 390x844 Portrait - Docs Center title verification)
   - `05-mobile-landscape-api-docs-title.png` (Mobile 844x390 Landscape - Swagger UI API docs title verification)
5. `api-specialist-review.md`: Complete audit by API Specialist approving contract, CSP, and title generation.
6. `ui-specialist-review.md`: Complete audit by UI/UX Specialist approving visual proofs, responsive layouts, and hook lifecycles.
7. `changed-files-manifest.txt`: SHA-256 checksum manifest of all modified, added, and QA packet files.

---

## 3. Passive Verification Command for Reality-Checker

```bash
sha256sum -c docs/qa/KAN-313/changed-files-manifest.txt
uv run python -m scripts.check_no_dashes docs/qa/KAN-313/message-to-reality-checker.md
```
