# KANBA-230: Post-Upgrade Local Admin Sign-In Failures

## Overview
This ticket resolves post-upgrade local admin sign-in failures and stale session/CSRF wedges across multi-container Docker Compose deployments and reverse proxy setups.

## Core Root Causes Addressed
1. **Stale Cookie Wedge:**
   - Dead or unresolvable `__Host-kb_session` / `kb_session` and `__Host-kb_csrf` / `kb_csrf` cookies previously caused requests to fall back to `PRE_SESSION_ID` without clearing the browser's stale cookies, resulting in persistent `403 CSRF_REJECTED` wedges on `/login`.
   - Fixed by bootstrapping session on `/login` mount, prioritizing `cachedCsrfToken` in `client.ts`, clearing stale session cookies with `Max-Age=0`, reissuing valid pre-session CSRF cookies on dead sessions, and retrying failed unsafe login/claim calls once after refreshing CSRF.
2. **Automated Compose Migrations & Startup Schema Verification:**
   - Multi-container Docker Compose previously lacked an automatic migration step prior to starting `kanban-api` and `outbox-relay`.
   - Added hardened `kanban-migrate` service (`alembic upgrade head`, user `65532:65532`, cap_drop `ALL`, `data_net`) with `condition: service_completed_successfully` dependencies.
   - Added startup verification in `kanban/app.py` logging a clear `❌` diagnostic if the database Alembic head is behind code head.
3. **Public Origin Normalization:**
   - Subpath URLs (e.g. `https://example.com/kanban`) in `KANBAN_PUBLIC_ORIGIN` / `KB_PUBLIC_ORIGIN` previously failed `Origin` header matching because the port/path was not stripped to `scheme://netloc`.
   - Fixed via `urllib.parse.urlsplit` normalization in `CsrfMiddleware._validate_metadata`.
4. **Actionable Non-Enumerating Error Copy:**
   - Updated `formatAuthError` in `authApi.ts` to map unrecovered `CSRF_REJECTED` to `"Your browser session token is out of date - reload the page and try again."` and map 5xx / `INTERNAL_ERROR` to server/correlation messages with `request_id`, while preserving strict anti-enumeration on 401 `INVALID_CREDENTIALS`.

## Verification
- Local unit tests passed (39 pytest, 48 vitest).
- Network isolation verified with `make compose-check`.
- Playwright screenshot tests generated desktop, tablet, and mobile artifacts in `docs/qa/KANBA-230/screenshots/`.
