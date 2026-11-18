# Verification Proof & Reality-Checker Submission: KANBA-230

## Metadata
- **Ticket ID:** `KANBA-230`
- **Ticket Title:** Post-Upgrade Local Admin Sign-In Failures: Stale Session / CSRF Wedge Elimination, Compose Automated Migrations, Origin Normalization, and Error Copy
- **Assignee:** `w2-auth`
- **Worktree Branch:** `feat/w2-auth`
- **Submission Date:** 2026-11-18

---

## 1. Scope & Verification Packet Inventory
The forensic QA proof packet is organized inside `docs/qa/KANBA-230/`:
- `git-diff.patch`: Clean unified diff for all KANBA-230 changes against main.
- `changed-files-manifest.txt`: Paths for all files modified in KANBA-230.
- `unit-test-results.txt`: Raw test execution output.
- `build-or-typecheck.txt`: Raw build, typecheck, lint, and license outputs (0 errors, 0 warnings).
- `screenshots/`: 8 Playwright screenshots covering Light, Dark, Desktop, Tablet, and Mobile viewports plus correlation error displays.
- `verification-proof.md`: Complete verification proof with artifact links.

---

## 2. Core Root Causes Addressed
1. **Stale Cookie Wedge:**
   - Dead or unresolvable session/CSRF cookies previously caused requests to fall back to `PRE_SESSION_ID` without clearing the browser's stale cookies, resulting in persistent `403 CSRF_REJECTED` wedges on `/login`.
   - Fixed by bootstrapping session on `/login` mount, prioritizing `cachedCsrfToken` in `client.ts`, clearing stale session cookies with `Max-Age=0`, reissuing valid pre-session CSRF cookies on dead sessions, and retrying failed unsafe login/claim calls once after refreshing CSRF.
2. **Automated Compose Migrations & Startup Schema Verification:**
   - Added hardened `kanban-migrate` service (`alembic upgrade head`, user `65532:65532`, cap_drop `ALL`, `data_net`) with `condition: service_completed_successfully` dependencies.
   - Added startup verification in `kanban/app.py` logging a clear diagnostic if the database Alembic head is behind code head.
3. **Public Origin Normalization:**
   - Subpath URLs (e.g. `https://example.com/kanban`) in `KANBAN_PUBLIC_ORIGIN` / `KB_PUBLIC_ORIGIN` previously failed `Origin` header matching because the port/path was not stripped to `scheme://netloc`.
   - Fixed via `urllib.parse.urlsplit` normalization in `CsrfMiddleware._validate_metadata`.
4. **Actionable Non-Enumerating Error Copy:**
   - Updated `formatAuthError` in `authApi.ts` to map unrecovered `CSRF_REJECTED` to `"Your browser session token is out of date - reload the page and try again."` and map 5xx / `INTERNAL_ERROR` to server/correlation messages with `request_id`, while preserving strict anti-enumeration on 401 `INVALID_CREDENTIALS`.

---

## 3. Visual Screenshot Evidence
- [Desktop Dark Login](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-dark-desktop.png)
- [Desktop Light Login](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-light-desktop.png)
- [Tablet Dark Login](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-dark-tablet.png)
- [Tablet Light Login](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-light-tablet.png)
- [Mobile Dark Login](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-dark-mobile.png)
- [Mobile Light Login](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-light-mobile.png)
- [Correlation Error Dark](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-error-correlation-dark-desktop.png)
- [Correlation Error Light](file:///home/adamoutler/kanban/docs/qa/KANBA-230/screenshots/kanba-230-login-error-correlation-light-desktop.png)

---

## 4. Automated Test Evidence
- Local unit tests passed (39 pytest, 48 vitest).
- Network isolation verified with `make compose-check`.
- Code Quality: `make check` passed with zero errors.
- Style Rules: `python3 scripts/check_no_dashes.py` passed with 0 em/en-dashes.
