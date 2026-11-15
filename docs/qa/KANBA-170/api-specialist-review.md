# API & Architecture Specialist Review - KANBA-170 (`KB-QA-02`)

- **Ticket:** `KANBA-170` (`KB-QA-02`: Root Landing `/`, Initialization/Auth Session Guard & Unified `/projects/:projectKey/issues` inside `AppShell`)
- **Specialist Reviewer:** `arch-reviewer` (Swarm API & Architecture Specialist Gate Auditor)
- **Date:** 2026-11-15
- **Status:** **APPROVED (Grade A)**

---

## 1. Scope Audited

- `kanban/web/src/features/auth/useSessionGuard.ts`
- `kanban/web/src/App.tsx`
- `kanban/web/src/app/routes.tsx`
- `kanban/web/src/app/AppShell.tsx`
- `kanban/web/src/app/routes.test.tsx`
- `kanban/web/src/features/projects/CreateProjectModal.test.tsx`

---

## 2. API Wire Contracts & Security Invariant Verification

1. **Initialization & Session Guard Wire Contract (`useSessionGuard.ts`):**
   - `useSessionGuard` queries `GET /api/v1/setup/status` (`credentials: 'same-origin'`, `Accept: 'application/json'`) with `AbortController` cleanup on unmount.
   - When `initialized === false`, it transitions state to `redirecting` and navigates via `replace: true` to `/setup`, preventing uninitialized workspace shell exposure on `/`.
   - Next, `useSessionGuard` queries `GET /api/v1/auth/session` (`credentials: 'same-origin'`).
   - When `authenticated === false`, it caches the pre-session `csrf_token` in `document.cookie` (`kb_csrf`, `SameSite=Lax`, `path=/`) and redirects (`replace: true`) to `/login`.
   - When `authenticated === true` and `mfa_pending === true` (AAL1 partial session during first-boot or mandatory MFA enrollment), it redirects (`replace: true`) to `/setup` so step-up MFA enrollment is completed before workspace access.
   - Public routes (`/login`, `/setup`, `/activate`, `/__dev`) bypass the redirect loop cleanly.

2. **Pre-Request Regex Validation & Uniform Anti-Enumeration (`routes.tsx`):**
   - `ProjectRouteContainer` validates `PROJECT_KEY_REGEX = /^[A-Z][A-Z0-9]{1,9}$/` and `ISSUE_KEY_REGEX = /^[A-Z][A-Z0-9]{1,9}-[0-9]{1,9}$/` before enabling `useQuery` against `GET /api/v1/projects/{projectKey}`.
   - Malformed keys immediately render the uniform S3.4 `<NotFoundView />` (`"Not found or no access"`) with zero outbound network requests (`expect(fetchSpy).not.toHaveBeenCalled()`).
   - Invalid `?layout=` search parameters (such as `?layout=<script>alert(1)</script>`) are sanitized against `VALID_LAYOUTS` (`list`, `board`, `table`, `calendar`, `timeline`) and normalized to `?layout=list` via `navigate(..., { replace: true })`.

3. **Unified Shell & Zero-Remount Drawer Background (`App.tsx`, `routes.tsx`, `AppShell.tsx`):**
   - `/projects/:projectKey/issues` now routes through `ProjectRouteContainer` -> `AppShell` -> `ProjectIssuesRoute` -> `IssuesWorkspaceRoute`.
   - Opening the peek drawer (`?peek=KAN-101`) renders `<IssueSurface />` inside `#kb-issue-surface-host` while keeping `IssuesWorkspaceRoute` mounted in `<main id="main">`, eliminating the background board unmount regression reported in Human Browser QA Suite 4.1 and Suite 5.1.

4. **Workspace Root Home View (`WorkspaceHomeView` on `/`):**
   - Replaces the bare `<RoutePlaceholder route="/" />` with `WorkspaceHomeView`, which invokes `useSessionGuard()`, fetches `GET /api/v1/projects` (`credentials: 'same-origin'`), and renders project cards with direct navigation to Work Items, Board, Stickies, Docs, and Custom Fields.

---

## 3. Verification Proof Summary

- **Unit & Integration Tests:** `13 passed` test files (`102 passed` tests) in `docs/qa/KANBA-170/unit-test-results.txt`.
- **Typecheck & Production Build:** `tsc -b --noEmit` and `vite build` exit `0` in `docs/qa/KANBA-170/build-check.txt`.
- **Verdict:** **APPROVED** for merge and `reality-checker` audit.
