# Verification Proof Packet: KANBA-168 (KB-QA-07)

## Summary of Changes

1. **CSP `img-src` Syntax Fix (`kanban/security/headers.py` & `kanban/tests/test_security_headers.py`):**
   - Replaced invalid `data:image/png data:image/webp` MIME-subtype syntax in `CSP_POLICY` with `img-src 'self' blob: data:;` so Chromium accepts `data:` image URIs without console CSP syntax rejections.
   - Updated `test_security_headers_present_on_all_responses` to assert `img-src 'self' blob: data:;` and reject `data:image/` subtypes.

2. **Workspace Stickies Creation & CSRF Bootstrap (`WorkspaceStickiesView.tsx`, `stickiesApi.ts`, `StickiesViews.test.tsx`):**
   - Wired `createMutation` and `onCreateSticky` into `<StickiesGrid>` inside `WorkspaceStickiesView.tsx` so `/stickies` renders `+ New Sticky` in the header and `+ Create your first sticky` in the empty state.
   - Added `getStickiesCsrfToken()`, `resetStickiesCsrfCache()`, and `mutateWithCsrf()` in `stickiesApi.ts` to bootstrap `/api/v1/auth/session` when no CSRF cookie is present and attach `X-CSRF-Token` on `POST`/`PATCH`/`DELETE` mutations, with fallback project resolution (`GET /api/v1/projects`) when default project `KAN` returns 404.

3. **Docs Tree Duplicate 404 Elimination & CSRF Bootstrap (`DocsWorkspaceView.tsx`, `docsApi.ts`, `DocsWorkspaceView.test.tsx`, `routes/projects/settings/custom-fields.tsx`):**
   - Updated `fetchDocsTree` in `docsApi.ts` so `ApiProblem` HTTP errors from `GET /api/v1/projects/{projectKey}/docs/tree` rethrow immediately without firing a duplicate 404 request to `GET /api/v1/docs/{projectKey}/tree`.
   - Added `ensureDocsCsrfToken()` in `docsApi.ts` (invoked on mount in `DocsWorkspaceView.tsx` and before unsafe requests in `typedFetch`) and 404 project-doc resolution in `createPage`.
   - Added `getCustomFieldsCsrfToken()` and `ensureCustomFieldsCsrfToken()` in `kanban/web/src/routes/projects/settings/custom-fields.tsx` to bootstrap `/api/v1/auth/session` and attach `X-CSRF-Token` on `POST /api/v1/projects/:projectKey/custom-fields`.

## Evidence Inventory (`docs/qa/KANBA-168/`)

- `docs/qa/KANBA-168/git-diff.patch`
- `docs/qa/KANBA-168/unit-test-results.txt` (6/6 Pytest security header tests + 21/21 Vitest test files, 233/233 tests passing, 100% statements/lines/functions, 95.86% branch coverage)
- `docs/qa/KANBA-168/build-check.txt` (`ruff`, `mypy`, `eslint --max-warnings 0`, `pnpm run build` all exit 0)
- `docs/qa/KANBA-168/api-specialist-review.md` (`@arch-reviewer` APPROVED)
- `docs/qa/KANBA-168/ui-specialist-review.md` (`@ui-specialist` APPROVED)
- `docs/qa/KANBA-168/screenshots/`:
  - `workspace-stickies-desktop.png`, `workspace-stickies-tablet.png`, `workspace-stickies-mobile.png`
  - `project-docs-desktop.png`, `project-docs-tablet.png`, `project-docs-mobile.png`
