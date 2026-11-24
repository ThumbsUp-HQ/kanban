# Message to Reality-Checker (KAN-389)

## Forensic Handover Packet: KAN-389

- **Ticket**: `KAN-389` (`[KB-OAUTH-GEMINI-MCP] Support Gemini App MCP OAuth DCR (Raise MAX_REDIRECT_URIS to 16, Confidential client_secret_basic/post + PKCE, Admin Secret Issuance & Caddy /oauth Proxy)`)
- **Author Agent**: Builder `b-kan389`
- **Target Auditor**: Clean-Room `reality-checker` (`rc-kan389`)
- **Review Mode**: Passive Forensic Verification Mode (Zero shared implementation assumptions)

---

## 1. Summary of Changes

This ticket resolves the 3 coupled root causes preventing Google Gemini App from dynamically registering and authenticating with the Kanban platform via OAuth 2.1 + PKCE:

1. **Root Cause 1: 16 Redirect URIs & Strict DCR Validation**:
   - Raised `MAX_REDIRECT_URIS` from 5 to 16 in `kanban/oauth/server.py`.
   - Maintained zero-trust validation: registration requests with > 16 URIs reject with `400 Bad Request` (`invalid_redirect_uri`).
   - Wildcards (`*`) reject with RFC 9700 compliant `422 Unprocessable Entity`.
   - Fragments (`#`), userinfo (`user:pass@`), and non-HTTPS non-loopback schemes reject with `400 Bad Request`.
   - Added structured audit logging on registration rejection in `POST /oauth/register` (`kanban/api/v1/oauth.py`) without leaking secrets.

2. **Root Cause 2: Confidential OAuth 2.1 Clients (RFC 6749 / RFC 7591) Across DB, Backend & Admin UI**:
   - **Database Migration (`p6_16_oauth_confidential_clients`)**:
     - Followed `database/GEMINI.md` standard with linear single-head chain.
     - Updated `oauth_clients` check constraint to `client_type IN ('public', 'confidential')`.
     - Added nullable `client_secret_hash` (TEXT, hashed with SHA-256 HMAC + `KB_AUTH_PEPPER`) and `client_secret_prefix` (VARCHAR(16)).
     - Preserved `FORCE ROW LEVEL SECURITY`. `uv run kanban-ctl db check-migrations` passes with 100% ORM parity.
   - **OAuth Discovery & Token Exchange**:
     - `/.well-known/oauth-authorization-server` advertises `token_endpoint_auth_methods_supported`: `["none", "private_key_jwt", "client_secret_basic", "client_secret_post"]`.
     - `POST /oauth/register` issues a cryptographically secure `client_secret` (`kb_ocs_<urlsafe32>`) once for confidential clients (`client_secret_expires_at: 0`). Secret is hashed prior to storage and never stored in plaintext.
     - `POST /oauth/token` validates credentials via HTTP Basic Auth (`client_secret_basic`, with RFC 6749 percent unquoting) or form body (`client_secret_post`) in constant time (`hmac.compare_digest`).
     - Mandatory PKCE `S256` is strictly enforced for BOTH public and confidential clients: missing or wrong secret returns `401 invalid_client`; missing or invalid code_verifier returns `400 invalid_request` / `invalid_grant`.
   - **Admin API & UI**:
     - `POST /api/v1/admin/oauth-clients` supports public or confidential creation with one-time secret issuance.
     - `PATCH /api/v1/admin/oauth-clients/{client_id}` allows editing `redirect_uris` up to 16 URIs under AAL2 admin authorization.
     - `GET /api/v1/admin/oauth-clients` returns masked `client_secret_prefix`, never exposing secret or hash.
     - UI in `OAuthClientGovernanceStudio.tsx` supports selecting Client Type, displays copyable one-time secret callout panel with warning alert, and provides dedicated Edit Redirect URIs modal.

3. **Root Cause 3: Edge Reverse Proxy Route Coverage**:
   - Updated `deploy/caddy/Caddyfile` with explicit route matchers for `/.well-known/oauth-*`, `/.well-known/openid-configuration*`, and `/oauth/*` proxying to `kanban-api:8000` with spoofable header stripping.

---

## 2. Verification Artifacts & Test Results

All verification proof is stored under `docs/qa/KAN-389/`:

- `docs/qa/KAN-389/unit-test-results.txt`:
  - `uv run kanban-ctl db check-migrations`: OK, 78 migrations valid, single head `p6_16_oauth_confidential_clients`.
  - `uv run pytest kanban/tests/oauth/ -o "addopts=" --cov=kanban/oauth -v`: 42/42 tests passed in 25.5s (96% branch and statement coverage on `kanban.oauth`).
  - `pnpm -C kanban/web exec vitest run src/features/oauth/__tests__/OAuthClientGovernanceStudio.test.tsx`: 22/22 tests passed in 2.4s.
- `docs/qa/KAN-389/build-check.txt`:
  - `ruff check`: 0 errors.
  - `mypy`: 0 errors across 6 packages.
  - `pnpm typecheck`: 0 errors.
  - `pnpm lint`: 0 errors.
  - `pnpm build`: Vite production build passed.
  - `check_no_dashes`: 0 violations across all files.
- `docs/qa/KAN-389/screenshots/`:
  - `01-desktop-oauth-governance-studio.png` (Desktop 1440x900)
  - `02-desktop-register-confidential-client-modal.png` (Confidential client registration)
  - `03-desktop-one-time-client-secret-panel.png` (One-time copyable secret callout)
  - `04-desktop-edit-redirect-uris-modal.png` (16-URI edit modal)
  - `05-tablet-oauth-governance-studio.png` (Tablet 768x1024)
  - `06-tablet-register-confidential-client.png` (Tablet registration dialog)
  - `07-mobile-oauth-governance-studio.png` (Mobile 390x844 responsive layout)
  - `08-mobile-one-time-client-secret-panel.png` (Mobile secret panel)
- `docs/qa/KAN-389/api-specialist-review.md`: Dual Specialist Sign-off (API Specialist, APPROVED).
- `docs/qa/KAN-389/ui-specialist-review.md`: Dual Specialist Sign-off (UI Specialist, APPROVED).
- `docs/qa/KAN-389/git-diff.patch`: Complete diff against origin/main.
- `docs/qa/KAN-389/changed-files-manifest.txt`: SHA-256 manifest of all modified and created files.

---

## 3. Checklist for Reality-Checker

1. Verify `sha256sum -c docs/qa/KAN-389/changed-files-manifest.txt` succeeds for all files.
2. Verify `uv run python -m scripts.check_no_dashes --all` reports 0 errors.
3. Verify `uv run kanban-ctl db check-migrations` shows single head `p6_16_oauth_confidential_clients`.
4. Inspect `docs/qa/KAN-389/screenshots/` to confirm multi-viewport rendering.
5. Review `docs/qa/KAN-389/api-specialist-review.md` and `docs/qa/KAN-389/ui-specialist-review.md`.
6. Write full forensic verdict to `docs/qa/KAN-389/reality-checker-report.md`.
