# Forensic QA Reality-Checker Audit Report: KANBA-185

## Metadata
- **Ticket ID:** KANBA-185
- **Title:** [KB-AUTH-JSON] Google OAuth Client Secret JSON (`client_secret_*.json`) Importer with Endpoint Pinning, SSRF Protection, and Redirect URI Callback Auditing
- **Module:** `kanban.auth.oidc`, `kanban-web` (`AuthCardEditorDrawer.tsx`, `adminAuthApi.ts`, `adminAuth.css`)
- **Evaluated Commit:** `1003e0d` (merged into `main`)
- **Auditor:** reality-checker (Passive Forensic QA Gate)
- **Date:** 2026-11-17
- **Overall Grade:** A
- **Verdict:** READY

---

## 1. Reality Check & Scope Validation

### 1.1 UI & Visual Proof Audit
- **Classification:** Full Stack Feature (Backend Parser/Endpoints + Admin Web UI Dropzone/Modal Importer).
- **Screenshots Inspected:** Audited all 10 annotated Playwright screenshots in `docs/qa/KANBA-185/screenshots/`:
  - `google-json-dropzone-initial-desktop-dark.png`
  - `google-json-paste-open-desktop-dark.png`
  - `google-json-matched-callback-desktop-dark.png`
  - `google-json-matched-callback-desktop-light.png`
  - `google-json-mismatched-warning-desktop-dark.png`
  - `google-json-matched-tablet-dark.png`
  - `google-json-warning-tablet-dark.png`
  - `google-json-matched-mobile-dark.png`
  - `google-json-warning-mobile-dark.png`
  - `google-json-matched-mobile-light.png`
- **Visual Observations:**
  - Distinct dropzone within recessed canvas container with clean dashed border and focus ring highlight on drag-over.
  - Expandable paste disclosure with accessible monospace textarea and instant DOM/state clearing upon application.
  - Status banner (`.auth-google-json-status--ok`) renders with green checkmark when the callback URI matches (`https://kanban.example.com/api/v1/auth/oidc/google-oauth/callback`).
  - Warning banner (`.auth-google-json-status--warning`) renders with amber warning box, expected callback display, single-click copy button, and collapsible list of conflicting URIs when a mismatch occurs.
  - Zero label/input overlap; minimum 44px tap targets on mobile viewports; verified WCAG AA contrast across Dark and Light schemes.

### 1.2 Specialist Gates Cross-Validation
- **Dual Specialist Mandate:** Both API and UI specialists must review.
- **API Specialist Review:** `docs/qa/KANBA-185/api-specialist-review.md` present and audited.
  - Reviewer: `api-specialist` (Backend Architect & API Tester Persona).
  - Assessment: Verified <=32 KiB payload ceiling, lone-surrogate rejection, endpoint pinning, SSRF checks, zero secret echo in preview, volatile bytearray zeroing, and `require_admin_aal2` route protection.
  - Verdict: **APPROVED**.
- **UI Specialist Review:** `docs/qa/KANBA-185/ui-specialist-review.md` present and audited.
  - Reviewer: `ui-specialist` (ArchitectUX & UI Designer Persona).
  - Assessment: Audited dropzone ergonomics, paste disclosure sanitization, redirect URI mismatch warnings, touch targets, keyboard navigation, and theme contrast.
  - Verdict: **APPROVED**.

---

## 2. Forensic Proof Packet Inspection (`docs/qa/KANBA-185/`)

1. **`git-diff.patch`**:
   - Matches merged commit `1003e0d`.
   - Introduces `kanban/auth/oidc/google_json.py` implementing `parse_google_oauth_client_json`.
   - Updates `kanban/api/v1/admin_auth_cards.py` with preview endpoint `POST /api/v1/admin/auth-cards/parse-google-json` and card upsertion handling for `google_oauth_json`.
   - Extends `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`, `adminAuthApi.ts`, and `adminAuth.css` with dropzone, file upload, paste disclosure, and callback mismatch warnings.
   - Preserves strict secret hygiene: secrets are extracted into volatile memory, sealed into `envelope_encrypted_secret`, stripped from `public_config`, and zeroed in a `finally` block.

2. **`changed-files-manifest.txt`**:
   - Lists all modified files with SHA-256 digests and line counts.

3. **`unit-test-results.txt`**:
   - Backend Pytest: 18 passed in 4.33s (10 in `test_google_oauth_json.py`, 8 in `test_auth_cards_admin_api.py`), Exit Code: 0.
   - Frontend Vitest: 25 passed in 1.93s (`AuthCardEditorDrawer.test.tsx`), Exit Code: 0.

4. **`build-check.txt`**:
   - Backend Ruff: All checks passed.
   - Backend Mypy: Success (499 source files clean).
   - Frontend Typecheck: `tsc -b --noEmit` clean.
   - Frontend Lint: `eslint . --max-warnings 0` clean.
   - Frontend Vite Build: Production build successful.
   - Dash Check: `scripts.check_no_dashes --all` passed with 0 violations.

5. **`contract-sample.json`**:
   - Valid JSON sample verifying preview response (`has_client_secret: true`, no secret echo, redirect URI match status) and card creation response (`envelope_encrypted_secret` sealed, public config sanitized).

---

## 3. Definition of Done Compliance Matrix

| Requirement | Implementation Evidence | Status |
| :--- | :--- | :---: |
| Google OAuth Client JSON Parser | `kanban/auth/oidc/google_json.py:parse_google_oauth_client_json` | PASS |
| Size Ceiling (<= 32,768 bytes) | Enforced before parsing; raises `GOOGLE_JSON_TOO_LARGE` | PASS |
| UTF-16 Lone Surrogate Rejection | Validated before decode; raises `INVALID_UTF8_SURROGATE` | PASS |
| Reject Installed Desktop Clients | Explicitly checks for top-level `web`; rejects `installed` | PASS |
| Cryptographic Endpoint Pinning | `auth_uri` and `token_uri` pinned strictly to Google accounts endpoints | PASS |
| SSRF Prevention | Rejects RFC 1918, loopback, link-local, and non-Google domains | PASS |
| Zero Secret Echo in Preview | `POST /api/v1/admin/auth-cards/parse-google-json` returns metadata + `has_client_secret` only | PASS |
| Volatile Memory Sanitization | Secrets placed in `bytearray` and zeroed in `finally` block | PASS |
| Admin AAL2 Route Protection | Endpoints protected with `require_admin_aal2` dependency | PASS |
| Drag-and-Drop Dropzone & Paste UX | Accessible dropzone, file input, and paste disclosure in `AuthCardEditorDrawer.tsx` | PASS |
| Redirect URI Callback Auditing | Live check against `{origin}/api/v1/auth/oidc/{slug}/callback` with warning banner and copy button | PASS |
| Specialist Gate Reviews | Both API Specialist and UI Specialist approved | PASS |
| Automated Tests & Build Gates | 18 backend tests + 25 frontend tests passing; typecheck, lint, build, and dash check exit 0 | PASS |

---

## 4. Certification

The forensic proof submitted in `docs/qa/KANBA-185/` provides indisputable, comprehensive evidence of correctness, cryptographic endpoint pinning, volatile memory sanitization, and full UI/UX accessibility.

- **Grade:** A
- **Verdict:** READY
