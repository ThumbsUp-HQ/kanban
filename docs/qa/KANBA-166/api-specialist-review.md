# API & Architecture Specialist Review - KANBA-166 (`KB-QA-05`)

- **Ticket:** `KANBA-166` (`KB-QA-05`: Project Creation Modal, Dynamic Sidebar Projects & Global `+ New work item`)
- **Specialist Reviewer:** `arch-reviewer` (Swarm API & Architecture Specialist Gate Auditor)
- **Date:** 2026-11-15
- **Status:** **APPROVED (Grade A)**

---

## 1. Scope Audited

- `kanban/web/src/features/projects/CreateProjectModal.tsx`
- `kanban/web/src/features/projects/CreateProjectModal.test.tsx`
- `kanban/web/src/features/auth/useSessionGuard.ts` (`ensureSessionCsrfToken`)
- `kanban/web/src/app/Sidebar.tsx` & `kanban/web/src/app/Sidebar.test.tsx`
- `kanban/web/src/app/CommandPalette.tsx` & `kanban/web/src/app/CommandPalette.test.tsx`
- `kanban/web/src/app/routes.tsx` (`WorkspaceHomeView`, `ProjectIssuesRoute`)

---

## 2. API Wire Contracts & Security Invariant Verification

1. **Project Creation Endpoint & CSRF Contract (`CreateProjectModal.tsx`):**
   - Validates `name` (required, trimmed, `maxLength={120}`) and `identifier` against `PROJECT_IDENTIFIER_PATTERN = /^[A-Z][A-Z0-9]{1,9}$/` on the client prior to network submission, matching the backend `ProjectCreateRequest` schema.
   - `suggestProjectIdentifier(name)` deterministically derives a 2-10 character uppercase ASCII identifier starting with `[A-Z]` and strips all non-alphanumeric characters.
   - Before issuing `POST /api/v1/projects`, `CreateProjectModal` calls `ensureSessionCsrfToken()`, which reads `__Host-kb_csrf` / `kb_csrf` from `document.cookie` or bootstraps a fresh token from `GET /api/v1/auth/session` (`credentials: 'same-origin'`), attaching it in `X-CSRF-Token`.
   - Sends `{ name, identifier, description_markdown, modules_enabled }` as JSON with `credentials: 'same-origin'`, handles RFC 9457 / FastAPI `detail` error payloads cleanly without leaking raw stack traces, dispatches `kb:project-created`, and navigates to `/projects/${created.identifier}/issues`.

2. **Dynamic Project Discovery in Sidebar & Home (`Sidebar.tsx`, `routes.tsx`):**
   - `Sidebar` and `WorkspaceHomeView` query `GET /api/v1/projects` (`credentials: 'same-origin'`, `Accept: 'application/json'`) and support both array and `{ items: [...] }` envelope shapes.
   - Subscribes to `kb:project-created` and `kb:open-create-project` window events so newly created projects appear immediately in the Sidebar `Projects` tree and on `/` without requiring a full page reload.
   - Preserves fallback to the prop-supplied `projectKey` / `projectName` when offline or unmocked in unit tests.

3. **Global `+ New work item` & Command Palette Integration (`Sidebar.tsx`, `CommandPalette.tsx`, `routes.tsx`):**
   - Clicking `.kb-new-item-btn` (`+ New work item`) in `Sidebar` or selecting `Create work item` in `CommandPalette` dispatches `kb:create-issue` and navigates to `/projects/${activeProjectKey}/issues?create=1` when outside the issues route.
   - `ProjectIssuesRoute` consumes `?create=1`, strips the one-shot query parameter via `navigate(..., { replace: true })`, and opens `QuickCreateIssueModal`.

---

## 3. Verification Proof Summary

- **Unit & Integration Tests:** `13 passed` test files (`102 passed` tests) in `docs/qa/KANBA-166/unit-test-results.txt`, including dedicated `CreateProjectModal.test.tsx` and `Sidebar.test.tsx` suites.
- **Typecheck & Production Build:** `tsc -b --noEmit` and `vite build` exit `0` in `docs/qa/KANBA-166/build-check.txt`.
- **Verdict:** **APPROVED** for merge and `reality-checker` audit.
