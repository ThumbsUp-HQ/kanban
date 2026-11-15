# API & Architecture Specialist Review - KANBA-168 (`KB-QA-07`)

- **Ticket:** `KANBA-168` (`KB-QA-07`: CSP `img-src` Syntax Fix, Workspace Stickies Creation & CSRF Bootstrap, Docs Tree 404 Elimination & Custom Fields CSRF)
- **Specialist Reviewer:** `arch-reviewer` (Swarm API & Architecture Specialist Gate Auditor)
- **Date:** 2026-11-15
- **Status:** **APPROVED (Grade A)**

---

## 1. Scope Audited

- `kanban/security/headers.py` & `kanban/tests/test_security_headers.py`
- `kanban/web/src/features/stickies/WorkspaceStickiesView.tsx`, `kanban/web/src/features/stickies/stickiesApi.ts`, & `kanban/web/src/features/stickies/StickiesViews.test.tsx`
- `kanban/web/src/features/docs/DocsWorkspaceView.tsx`, `kanban/web/src/features/docs/docsApi.ts`, & `kanban/web/src/features/docs/DocsWorkspaceView.test.tsx`
- `kanban/web/src/routes/projects/settings/custom-fields.tsx`

---

## 2. API Wire Contracts & Security Invariant Verification

1. **Standards-Compliant Content-Security-Policy `img-src` (`kanban/security/headers.py`):**
   - Replaces the W3C CSP3-invalid MIME-qualified scheme tokens `data:image/png data:image/webp` in `CSP_POLICY` with `img-src 'self' blob: data:;`, eliminating the Chromium console errors on every page load while preserving `default-src 'none'`, `script-src 'self'`, `style-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, and `require-trusted-types-for 'script'`.
   - `test_security_headers.py` verifies `img-src 'self' blob: data:;` and explicitly asserts that invalid `data:image/` tokens do not appear in the emitted `Content-Security-Policy` header.

2. **Workspace Stickies Creation & CSRF Bootstrap (`WorkspaceStickiesView.tsx`, `stickiesApi.ts`):**
   - `WorkspaceStickiesView` wires `createMutation` -> `onCreateSticky` on `StickiesGrid`, enabling `+ New Sticky` in the header and `+ Create your first sticky` in the empty state on `/stickies`.
   - `mutateWithCsrf` in `stickiesApi.ts` reads `__Host-kb_csrf` / `kb_csrf` or bootstraps from `GET /api/v1/auth/session` (`credentials: 'same-origin'`) before every `POST`/`PATCH`/`DELETE` request and attaches `X-CSRF-Token`.
   - If `POST /api/v1/projects/{projectKey}/stickies` returns `404` when the default `KAN` project does not exist, `createSticky` resolves the first active workspace project from `GET /api/v1/projects` and retries against `/api/v1/projects/{fallbackKey}/stickies`.

3. **Docs Tree 404 Elimination & Page Creation Resolution (`docsApi.ts`):**
   - `fetchDocsTree` calls `GET /api/v1/projects/{projectKey}/docs/tree` and rethrows `ApiProblem` HTTP errors directly without firing a redundant `GET /api/v1/docs/{projectKey}/tree` 404 request in the browser.
   - `typedFetch` calls `ensureDocsCsrfToken()` before unsafe methods, and `createPage` resolves or provisions the backing project Doc (`GET /api/v1/projects/{projectKey}` -> `GET /api/v1/docs?project=...` / `POST /api/v1/docs` -> `POST /api/v1/docs/{doc_ref}/pages`) when `docRefOrProjectKey` is a project identifier rather than a Doc UUID.

4. **Custom Fields Settings CSRF Bootstrap (`routes/projects/settings/custom-fields.tsx`):**
   - `ensureCustomFieldsCsrfToken` bootstraps `kb_csrf` from `GET /api/v1/auth/session` and ensures unsafe `custom-fields` requests include `X-CSRF-Token` and `credentials: 'same-origin'`, while preserving the non-admin `404` anti-enumeration guard.

---

## 3. Verification Proof Summary

- **Backend Security Header Tests:** `6 passed` in `1.17s` (`97%` coverage on `kanban/security/headers.py`) in `docs/qa/KANBA-168/unit-test-results.txt`.
- **Frontend Unit & Coverage Tests:** `21 passed` test files (`233 passed` tests, `100%` line/statement/function coverage, `95.86%` branch coverage) in `docs/qa/KANBA-168/unit-test-results.txt`.
- **Static Analysis & Build:** `ruff`, `mypy`, `eslint --max-warnings 0`, and `vite build` exit `0` in `docs/qa/KANBA-168/build-check.txt`.
- **Verdict:** **APPROVED** for merge and `reality-checker` audit.
