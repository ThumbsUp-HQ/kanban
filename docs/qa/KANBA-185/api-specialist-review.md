# API Specialist Forensic QA Review: KANBA-185

## Metadata
- **Ticket ID:** KANBA-185
- **Title:** [KB-AUTH-JSON] Google OAuth Client JSON Importer with Endpoint Pinning, SSRF Protection, and Zero Secret Echo
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `1003e0d` (merged into `main`)
- **Review Date:** 2026-11-17
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 JSON Parser Specification & Endpoint Pinning (`kanban/auth/oidc/google_json.py`)
- **Strict Size Ceiling:** Payload length is checked against `MAX_GOOGLE_JSON_BYTES = 32768` bytes prior to JSON parsing, raising `GOOGLE_JSON_TOO_LARGE` (422/413) if exceeded.
- **Lone Surrogate Rejection:** Rejects UTF-16 lone surrogates (`0xD800 <= ord(c) <= 0xDFFF`) with `INVALID_UTF8_SURROGATE` before encoding/decoding, preventing encoding corruption and parser bypasses.
- **Client Type Enforcement:** Enforces presence of top-level `web` configuration object. Explicitly rejects `installed` (desktop) client JSON with informative diagnostic error `INVALID_GOOGLE_CLIENT_TYPE`.
- **Cryptographic Endpoint Pinning:**
  - `auth_uri` is strictly pinned to `https://accounts.google.com/o/oauth2/auth` and `https://accounts.google.com/o/oauth2/v2/auth`.
  - `token_uri` is strictly pinned to `https://oauth2.googleapis.com/token`, `https://accounts.google.com/o/oauth2/token`, and `https://www.googleapis.com/oauth2/v4/token`.
  - `auth_provider_x509_cert_url` must match allowed prefixes (`https://www.googleapis.com/oauth2/` or `https://accounts.google.com/`).
- **SSRF Hardening:** Untrusted, custom, loopback, private RFC 1918, or cloud metadata endpoints are rejected with `UNTRUSTED_GOOGLE_ENDPOINT`.

### 1.2 Zero Secret Echo & Envelope Encryption (`KB-P3-36` Invariants)
- **Preview Endpoint (`POST /api/v1/admin/auth-cards/parse-google-json`):**
  - Parses Google JSON to return metadata (`client_id`, `project_id`, `issuer`, `redirect_uris`, `javascript_origins`, `callback_uri_matched`).
  - **Zero Secret Echo:** Returns `has_client_secret: bool` and never returns `client_secret` or private keys in the response payload.
  - Protected with `require_admin_aal2` dependency.
- **Card Upsertion (`POST` / `PUT` `/api/v1/admin/auth-cards`):**
  - Extracts `client_secret` from `google_oauth_json`.
  - Strips forbidden secrets from `public_config` (`OidcCardConfig.reject_secrets_and_normalize` raises `SECRET_IN_PUBLIC_CONFIG` 422 if credentials appear in `public_config`).
  - Converts secrets into volatile `bytearray`, seals them into `envelope_encrypted_secret` using an ephemeral DEK via `StaticKekProvider`, and zeros the mutable memory buffer in a `finally` block (`secret_buf[i] = 0`).

---

## 2. Test Suite & Proof Verification

### 2.1 Backend Unit & Integration Tests
- Executed `kanban/tests/auth/test_google_oauth_json.py` and `kanban/tests/auth/test_auth_cards_admin_api.py`:
  - 18 passed in 4.25s, 0 failures, 0 warnings.
  - Tested: valid Google web JSON, oversized payload rejection (>32KB), lone-surrogate rejection, installed desktop JSON rejection, untrusted auth/token URI rejection, redirect URI validation, preview endpoint with zero secret echo, and card creation with envelope encryption.

### 2.2 Proof Artifacts Audit (`docs/qa/KANBA-185/`)
- `git-diff.patch`: Verified clean diff against KANBA-190 base.
- `changed-files-manifest.txt`: All files verified with SHA-256 digests and line counts.
- `unit-test-results.txt`: Confirms 18 passing backend pytest tests + 25 passing frontend Vitest tests.
- `build-check.txt`: Clean `ruff`, `mypy --strict kanban` (499 files clean), `pnpm run typecheck`, `pnpm run lint`, and `check_no_dashes`.
- `contract-sample.json`: Valid JSON schema compliant sample demonstrating `parse-google-json` preview and card creation response with secret redaction and envelope encryption.
- `message-to-reality-checker.md`: Comprehensive traceability mapping across requirements and proof artifacts.

---

## 3. Specialist Verdict

The implementation in commit `1003e0d` satisfies all backend API security boundaries, endpoint pinning guarantees, volatile memory sanitization, and AAL2 access controls specified in KANBA-185.

**Verdict: APPROVED**
