# Forensic QA Verification Packet: KAN-7 ([KB-P3-AUDIT-01])

## 1. Executive Summary & Verification Context
- **Ticket ID:** KAN-7 ([KB-P3-AUDIT-01])
- **Repository Root:** `/home/adamoutler/kanban`
- **Status:** READY FOR CLEAN-ROOM AUDIT

This packet provides indisputable zero-mock forensic proof for all 4 scoped KAN-7 defects plus clean-room fail-closed auth and shell polish:
1. `POST /api/v1/setup/claim` RLS Context Binding (`bind_rls_context`) under PostgreSQL `FORCE ROW LEVEL SECURITY` (`kanban/auth/setup.py`).
2. Headless setup token permissions (`UID 65532` `/run/kanban` mode `0600`), `KB_SETUP_TOKEN_FILE` passthrough (`deploy/standalone/entrypoint.py`), and `_persist_token` fallback persistence (`kanban/auth/setup.py`).
3. Recovery Code HTML5 `pattern="[A-Za-z0-9\-]{8,32}"` UnicodeSets (`/v` flag) `SyntaxError` fix (`kanban/web/src/features/auth/SecondFactorStep.tsx`).
4. `SecondFactorStep` root `data-testid="second-factor-step"`, single-card layout (zero nested `.auth-panel` borders), `0` inline `style={{...}}` props, and fail-closed `AppShell` + `RealtimeProvider` auth gate (`0` `401` API requests and `0` WS/SSE connections when unauthenticated, pre-claim, or `mfa_pending: true`).

## 2. Unit Test & Static Quality Proof
- **Backend Unit Tests (`docs/qa/KAN-7/unit-test-results.txt`):** `46 passed` across `kanban/tests/auth/test_setup.py` and `tests/deploy/test_standalone_entrypoint.py` (`100%` statement and branch coverage on `kanban/auth/setup.py`, `99%` coverage on `deploy/standalone/entrypoint.py`, `0` missed statements, `99%` combined coverage).
- **Frontend Unit Tests (`docs/qa/KAN-7/unit-test-results.txt`):** `134 passed` across touched suites (`99.29%` Stmts, `96.30%` Branch, `100%` Funcs, `99.71%` Lines; `AppShell.tsx` `97.67%` branch, `useSessionGuard.ts` `95.31%` branch, `SecondFactorStep.tsx` `96.42%` branch, including `src/styles/__tests__/cssTokensAudit.test.ts`).
- **Static Checks (`docs/qa/KAN-7/build-or-typecheck.txt`):** `uv run mypy` (Success: no issues found in 1094 source files), `uv run ruff check .` (All checks passed!), `uv run ruff format --check .` (1858 files already formatted), `uv run lint-imports` (Contracts: 2 kept, 0 broken), `tsc -b --noEmit` (0 errors), `eslint --max-warnings 0` (0 errors, 0 warnings), `vite build` (clean production build), and `check_no_dashes` all exit `0`.

## 3. Zero-Mock Live Full-Stack Proof (`docs/qa/KAN-7/live-fullstack-proof.txt`)
Verified against live standalone container `kanban-liveqa-1` (`thumbs-up-kanban:local-qa` on `http://localhost:18951`, embedded PostgreSQL 16 + Uvicorn UID `65532`, **zero** `mockApi` / `page.route` stubs):
- `/run/kanban/setup_token` verified at `Uid=65532, Gid=65532, mode=0600`.
- Pre-claim `GET /` mounts `app-shell-auth-loading` and redirects to `/setup` with `0` `401`s, `0` WS/SSE attempts, `0` `console.error`, `0` `pageerror`.
- `/setup?token=...` scrubs URL query, `POST /api/v1/setup/claim` returns `200`, CTAP2 WebAuthn passkey registration (`POST /api/v1/auth/webauthn/registration/verify`) returns `200` (`aal_level: 2`), recovery codes generated (`200`), workspace renders cleanly.
- Logout -> unauthenticated `GET /` redirects to `/login` (`0` `401`s, `0` errors) -> password login (`mfa_pending: true`) -> direct `GET /` redirects back to `/login` (`0` `401`s, `0` WS/SSE, `0` errors) -> Recovery Code login (`POST /api/v1/auth/recovery/verify` -> `200`) -> `GET /api/v1/auth/session` returns `authenticated: true, mfa_pending: false, aal_level: 2`.
- Container logs (`101` lines): `0` occurrences of `401`, `403`, `404`, or `500`.

## 4. Live Zero-Mock Screenshots (`docs/qa/KAN-7/screenshots/`)
- `live-01-setup-claim-light-desktop.png`
- `live-01b-setup-passkey-enrolled-light.png`
- `live-02-setup-recovery-codes-light.png`
- `live-03-workspace-light-desktop.png`
- `live-04-workspace-dark-desktop.png`
- `live-05-workspace-light-mobile.png`
- `live-06-login-light-desktop.png`
- `live-06b-login-light-mobile.png`
- `live-07-second-factor-initial-light.png`
- `live-08-second-factor-totp-tab-dark.png`
- `live-09-second-factor-recovery-tab-light.png`
- `live-10-second-factor-mobile-dark.png`
