# Message to Reality-Checker for KANBA-185

## Overview & Scope Summary
Ticket: `KANBA-185` ([KB-AUTH-JSON])
Focus: Google OAuth Client JSON (`client_secret_*.json`) upload, dropzone, and paste importer with endpoint pinning, SSRF protection, envelope-encrypted secret handling, and redirect URI callback validation.

Branch: `feat/kanba-190-185`
Commit Base: `445ad1b3a2912becf7828e693fca7766cd374fa9` (commit of KANBA-190)

## Scoped Requirements Matrix & Forensic Proofs

1. **Google OAuth Client JSON Parser & Endpoint Pinning (`kanban/auth/oidc/google_json.py`):**
   - Implements `parse_google_oauth_client_json` enforcing Google Cloud Console Web client JSON schema.
   - Enforces strict size ceiling of `<= 32,768` bytes (rejects larger with `413 Payload Too Large`).
   - Rejects UTF-16 lone surrogates (`0xD800 <= ord(c) <= 0xDFFF`).
   - Explicitly rejects `installed` desktop client configurations with informative error messages.
   - Pins `auth_uri` to `https://accounts.google.com/o/oauth2/auth` and `https://accounts.google.com/o/oauth2/v2/auth`.
   - Pins `token_uri` to `https://oauth2.googleapis.com/token`, `https://accounts.google.com/o/oauth2/token`, and `https://www.googleapis.com/oauth2/v4/token`.
   - Pins `auth_provider_x509_cert_url` to `https://www.googleapis.com/oauth2/v1/certs`.
   - SSRF Protection: Rejects any URL pointing to private RFC 1918 IPs, loopback (`127.0.0.1`), link-local (`169.254.169.254`), IPv6 local, or non-Google domains.
   - Proof: `kanban/tests/auth/test_google_oauth_json.py` (10 passed tests, verified in `docs/qa/KANBA-185/unit-test-results.txt`).

2. **Security & Zero Secret Leakage (`KB-P3-36` & `KB-AUTH-JSON` Invariants):**
   - The preview endpoint `POST /api/v1/admin/auth-cards/parse-google-json` parses client JSON and audits redirect URIs without EVER echoing back the raw `client_secret`. It returns `has_client_secret: true` and masks secret content.
   - Card creation and update via `POST/PUT /api/v1/admin/auth-cards` accepts `google_oauth_json`, extracts and seals the `client_secret` into `envelope_encrypted_secret` using an ephemeral DEK, and strips all secrets from `public_config`.
   - Both preview and creation endpoints are protected by `require_admin_aal2` dependency.
   - Proof: `docs/qa/KANBA-185/contract-sample.json` and `test_case_9_google_oauth_json_preview_and_card_creation` in `kanban/tests/auth/test_auth_cards_admin_api.py`.

3. **Redirect URI Callback Auditing:**
   - Evaluates parsed `redirect_uris` against canonical callback URI:
     `{origin}/api/v1/auth/oidc/{slug}/callback`
   - Matching callback produces green `.auth-google-json-status--ok` badge (`✓ Authorized Redirect URI matched`).
   - Mismatched callback produces amber `.auth-google-json-status--warning` badge (`⚠️ Authorized Redirect URI mismatch`) with:
     - Expected callback URI display.
     - One-click copy button for the expected callback URL.
     - Collapsible list of actual redirect URIs present in the JSON.
   - Proof: `docs/qa/KANBA-185/screenshots/` and tests in `AuthCardEditorDrawer.test.tsx`.

4. **Web UI Importer Ergonomics & Accessibility (`AuthCardEditorDrawer.tsx` & `adminAuth.css`):**
   - Provides a drag-and-drop dropzone with `.auth-google-json-dropzone--active` visual state on dragover.
   - Provides an accessible hidden file input triggered by "Upload JSON File" button.
   - Provides an expandable "Paste JSON" disclosure with textarea and "Apply Google JSON" button.
   - Traps focus and handles Escape and Tab accessibility according to WAI-ARIA dialog practices.
   - WCAG AA compliant contrast for all badges and buttons across Dark and Light themes.
   - Proof: 10 annotated Playwright screenshots in `docs/qa/KANBA-185/screenshots/`.

5. **Automated Unit & Build Quality Gates:**
   - Backend Pytest: 18 / 18 tests passed (`kanban/tests/auth/test_google_oauth_json.py` + `kanban/tests/auth/test_auth_cards_admin_api.py`).
   - Frontend Vitest: 25 / 25 tests passed in `AuthCardEditorDrawer.test.tsx` (87 / 87 admin-auth tests overall).
   - Linters: `ruff check .` clean (0 warnings), `mypy --strict kanban` clean (0 issues in 499 source files).
   - Web Checks: `pnpm run typecheck` clean (0 errors), `pnpm run lint` clean (0 warnings), `pnpm run build` clean (production bundle built in 1.02s).
   - ASCII Hyphen Compliance: `scripts.check_no_dashes --all` passed cleanly (zero forbidden em-dashes/en-dashes).
   - Zero files modified outside ticket scope (`database/`, `mcp/`, `deploy/`, `StandaloneStatusPanel.*` untouched).

## Forensic Proof Index
- `docs/qa/KANBA-185/git-diff.patch` (complete per-ticket diff against KANBA-190)
- `docs/qa/KANBA-185/changed-files-manifest.txt`
- `docs/qa/KANBA-185/unit-test-results.txt`
- `docs/qa/KANBA-185/build-check.txt`
- `docs/qa/KANBA-185/contract-sample.json`
- `docs/qa/KANBA-185/screenshots/google-json-dropzone-initial-desktop-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-paste-open-desktop-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-matched-callback-desktop-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-matched-callback-desktop-light.png`
- `docs/qa/KANBA-185/screenshots/google-json-mismatched-warning-desktop-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-matched-tablet-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-warning-tablet-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-matched-mobile-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-warning-mobile-dark.png`
- `docs/qa/KANBA-185/screenshots/google-json-matched-mobile-light.png`
