# API Specialist Review: KAN-25 (KB-P3-AUDIT-19)

- Ticket: KAN-25
- Title: Add Self-Service Passkey & FIDO2 Security Key Registration, Key Testing, and AAL2 Step-Up Handling on Profile Settings
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Workspace: `/home/adamoutler/kanban`
- Branch: `main`
- Commit: `53f7b6e` (merging `fix/KAN-25-rc2` at `d7e206c`)
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-25 on `main` at commit `53f7b6e`. The ticket implements self-service passkey and FIDO2 hardware security key enrollment, credential testing via WebAuthn authentication assertion, device badge classification, clone detection warnings, complete AAL2 step-up interception on Profile Settings, credential scoping during key testing, accessible modal focus trapping, backend credential ID exposure in `list_credentials`, and mobile CSS specificity separation for stacked cards.

All API contracts, security boundaries, unit test coverage mandates, and unmocked live full-stack validation checks are verified and approved:
1. Exact route path alignment between the frontend client (`personalSettingsApi.ts`, `PasskeyEnrollModal.tsx`, `PersonalSettingsPage.tsx`) and the live FastAPI backend router in `kanban/api/v1/auth_webauthn.py`.
2. Binary base64url challenge and credential serialization/deserialization contracts in `webauthn.ts`.
3. Cryptographic and authentication security invariants, including secure context enforcement, RP ID scoping (`rp.name = "👍kanban"`, `rp.id = "localhost"`), credential-specific challenge filtering, and anti-replay safeguards.
4. Exposing raw WebAuthn base64url `credential_id` via `bytes_to_base64url(bytes(r.credential_id))` in `list_credentials` (`kanban/api/v1/auth_webauthn.py:579`), ensuring exact matching against `optionsJson.allowCredentials[].id` during `[Test Key]`.
5. Mobile CSS card layout specificity fix (`.kb-personal-settings-table td.kb-personal-settings-td`) preserving flex space-between alignment and clean label-value separation (56.8px gap on 390x844 viewport).
6. Robust RFC 9457 ApiProblem error handling and step-up orchestration across both `AAL2_REQUIRED` and `AAL2_STALE` challenges with seamless automatic request retry.
7. High unit test coverage: 23 passing Pytest tests with 98% coverage on `kanban/api/v1/auth_webauthn.py`, and 105 passing Vitest tests with >= 95% statement and branch coverage across all touched frontend API and component files.
8. Unmocked live full-stack proof in `docs/qa/KAN-25/live-fullstack-proof.txt` confirming all 7 live system checks pass against container `kanban-liveqa-1` with zero uncaught app errors.

---

## 2. Detailed Contract & Security Verification

### 2.1 WebAuthn Route Alignment & Schemas
- Backend Source: `kanban/api/v1/auth_webauthn.py`
- Frontend Source: `kanban/web/src/features/settings/personalSettingsApi.ts`
- Routes Audited:
  - Registration Options:
    - Frontend URL: `POST /api/v1/auth/webauthn/register/options`
    - Body: `{ authenticator_attachment?: "platform" | "cross-platform" }`
    - Response: `PublicKeyCredentialCreationOptionsJSON` (challenge, user, rp, pubKeyCredParams, timeout)
    - Verification: Matches backend `WebauthnRegisterOptionsRequest` and `auth_service.create_webauthn_registration_options`.
  - Registration Verification:
    - Frontend URL: `POST /api/v1/auth/webauthn/register/verify`
    - Body: `{ nickname?: string, credential: SerializedRegistrationCredential }`
    - Response: `{ verified: true, credential_id: string, nickname: string }`
    - Verification: Matches backend `WebauthnRegisterVerifyRequest`.
  - Authentication Options (Key Testing):
    - Frontend URL: `POST /api/v1/auth/webauthn/authenticate/options`
    - Body: `{}` (empty JSON object)
    - Response: `PublicKeyCredentialRequestOptionsJSON` (challenge, timeout, rpId, allowCredentials)
    - Verification: Matches backend `create_webauthn_authentication_options`.
  - Authentication Verification (Key Testing):
    - Frontend URL: `POST /api/v1/auth/webauthn/authenticate/verify`
    - Body: `{ credential: SerializedAssertionCredential }`
    - Response: `{ verified: true, credential_id: string, aal_level: number }`
    - Verification: Matches backend `WebauthnAuthenticateVerifyRequest`.
  - Credentials List:
    - Frontend URL: `GET /api/v1/auth/webauthn/credentials`
    - Schema items: `{ id, credential_id, nickname, sign_count, aaguid, transports, suspect_clone_at, created_at, last_used_at }`
    - Verification: `WebauthnCredentialItem` in `personalSettingsApi.ts` extended with `credential_id`, `transports`, `sign_count`, `aaguid`, and `suspect_clone_at`.
    - Backend Alignment: `kanban/api/v1/auth_webauthn.py:579` populates `"credential_id": bytes_to_base64url(bytes(r.credential_id))`, matching the base64url encoding used in `allowCredentials[].id`.

### 2.2 Binary Encoding & Serialization Contracts (`webauthn.ts`)
- The WebAuthn API requires binary ArrayBuffers for `challenge`, `user.id`, and `rawId`, whereas JSON transports base64url strings.
- In `kanban/web/src/features/auth/webauthn.ts`:
  - `prepareCreationOptions()`: Safely converts string `challenge` and `user.id` to ArrayBuffer using `base64urlToBuffer()`.
  - `prepareRequestOptions()`: Safely converts string `challenge` and allowed credential IDs to ArrayBuffer.
  - `serializeRegistrationCredential()`: Converts binary credential responses (`rawId`, `clientDataJSON`, `attestationObject`, `transports`) into JSON-safe base64url strings.
  - `serializeAssertionCredential()`: Converts binary assertion responses (`rawId`, `clientDataJSON`, `authenticatorData`, `signature`, `userHandle`) into JSON-safe base64url strings.
- All binary converters handle empty arrays, null values, and padding variants cleanly without throwing uncaught exceptions.

### 2.3 Targeted Credential Scoping (`PersonalSettingsPage.tsx`)
- In `handleTestKey(cred)`:
  - Scopes `optionsJson.allowCredentials` to the targeted credential ID (`cred.credential_id ?? cred.id`) so the browser authenticator prompts for that exact key.
  - Post-verification assertion confirms `verifyRes.credential_id` matches the tested credential (`cred.id` or `cred.credential_id`), preventing false passes if an authenticator returns an unassociated credential.
  - Displays section-scoped verified banner in `[data-testid="passkey-verified-banner"]` directly above the passkeys table in Section 3, alongside the updated last used timestamp.

### 2.4 Modal Accessibility & Focus Trapping (`PasskeyEnrollModal.tsx`)
- Header `✕` button (`aria-label="Close"`, min 44x44px tap target).
- `Escape` keydown listener cleanly dismisses modal when not submitting.
- Bidirectional Tab and Shift+Tab focus trapping keeps keyboard navigation safely bounded inside the dialog.

### 2.5 AAL2 Step-Up Orchestration (`AAL2_REQUIRED` & `AAL2_STALE`)
- Sensitive profile operations (registering passkeys, deleting passkeys, changing passwords) require Authenticator Assurance Level 2 (AAL2).
- When the backend challenges an operation with `ApiProblem(403, code="AAL2_REQUIRED")` or `ApiProblem(403, code="AAL2_STALE")`, `handleInterceptAal2()`:
  - Detects the step-up challenge code.
  - Preserves the pending operation in memory.
  - Prompts the user with `Aal2StepUpDialog` specifying available methods.
  - Upon successful verification, automatically resumes and retries the pending action without data loss.

---

## 3. Live Full-Stack Proof Audit (`live-fullstack-proof.txt`)

The unmocked live full-stack proof in `docs/qa/KAN-25/live-fullstack-proof.txt` was inspected across all 7 verification checks executed against container `kanban-liveqa-1` at `http://localhost:18951` (commit `53f7b6e`):

- **Check 1 (/setup Claim + Initial Passkey Enrollment):**
  - Read setup token from `/run/kanban/setup_token` and attached CDP CTAP2 internal virtual authenticator.
  - Initial enrollment established AAL2 session, returned 10 recovery codes, and confirmed `GET /api/v1/auth/me` with `is_server_admin: true` and `aal_level: 2`.
- **Check 2 (PasskeyEnrollModal UX + Dual Authenticator Enrollment):**
  - Confirmed modal close button count = 1 and `Escape` dismissed modal cleanly.
  - Enrolled platform authenticator "MacBook Touch ID" (HTTP 200).
  - Attached second CDP CTAP2 USB authenticator and enrolled "YubiKey 5C NFC" (HTTP 200).
  - Verified `GET /api/v1/auth/webauthn/credentials` returns valid base64url `credential_id` matching CTAP2 credentials.
- **Check 3 (Scoped [Test Key] on YubiKey 5C NFC + Section-3 Banner):**
  - Generated authentication assertion options scoped to YubiKey 5C NFC.
  - Completed assertion verification (HTTP 200).
  - Verified banner text: `👍 Key verified (YubiKey 5C NFC)`.
  - Confirmed `last_used_at` updated specifically for YubiKey while Touch ID `last_used_at` remained null (`sign_count` 2 vs 1).
- **Check 4 (Mobile 390x844 CSS Specificity Fix):**
  - Verified `.kb-personal-settings-table td.kb-personal-settings-td` applies specificity `(0, 2, 1)`.
  - Layout metrics confirmed `display: flex; justify-content: space-between; align-items: center; gap: 8px` with 56.8px gap between label and value, preventing any text concatenation.
- **Check 5 (Live suspect_clone_at Warning Badge):**
  - Simulated PostgreSQL `UPDATE suspect_clone_at` and verified live badge renders `⚠️ Suspected Clone` with danger styling.
- **Check 6 (Real !window.isSecureContext Notice):**
  - Tested over plain HTTP container IP `http://172.17.0.4:8080`.
  - Notice rendered at Y=452..500 and disabled buttons at Y=414..452 within 1440x900 viewport.
  - 0 uncaught application console errors or page errors.
- **Check 7 / Problem 3 (Live AAL2_REQUIRED & AAL2_STALE Step-Up Interception + Automatic Retry):**
  - **Sub-test 3A (AAL2_REQUIRED on Remove + Auto-Retry):** Forced AAL1 in PostgreSQL. `DELETE /api/v1/auth/webauthn/credentials/...` returned HTTP 403 `AAL2_REQUIRED`. `[data-testid="aal2-stepup-dialog"]` intercepted the challenge. User verified WebAuthn assertion (HTTP 200, `aal_level: 2`). The client automatically retried the DELETE operation which succeeded with HTTP 200 (`deleted: true`) without requiring a second click. Success alert "Passkey removed." displayed cleanly.
  - **Sub-test 3B (AAL2_STALE on + Add FIDO2 Security Key + Auto-Retry):** Forced stale AAL2 in PostgreSQL (`NOW() - INTERVAL '30 minutes'`). Clicking Add FIDO2 Security Key issued `POST /api/v1/auth/webauthn/register/options` returning HTTP 403 `AAL2_STALE`. Interceptor opened step-up dialog over enrollment modal. Upon assertion verification, registration options automatically retried (HTTP 200), registration completed (HTTP 200), and "Step-Up Retried Key" appeared in the passkeys table without clicking Continue again.
  - Zero uncaught application console errors and zero page errors recorded.

Overall Live Stack Verdict: PASS.

---

## 4. Dependency, Layering & Code Cleanliness Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy`: 0 errors across 1096 source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
  - `python3 -m scripts.check_no_dashes --all`: 0 errors (strict 0 em-dashes and en-dashes).
- Clean Patch Artifact: `docs/qa/KAN-25/git-diff.patch` verified to contain zero `docs/qa/*` files.

---

## 5. Test Coverage Audit

- Pytest Suite:
  - 23 passed in 9.97s across `kanban/tests/auth/`.
  - `kanban/api/v1/auth_webauthn.py`: 98% coverage (exceeds >= 95% mandate).
- Vitest Suite:
  - 105 passed across 5 test suites.
  - Every touched file meets the `>= 95%` coverage mandate:
    - `webauthn.ts`: 100% Stmts / 97.56% Branch
    - `PasskeyEnrollModal.tsx`: 98.92% Stmts / 98.59% Branch
    - `PersonalSettingsPage.tsx`: 99.32% Stmts / 95.39% Branch
    - `personalSettingsApi.ts`: 100% Stmts / 100% Branch
    - Total touched files: 99.32% Stmts / 96.35% Branch.
  - `cssTokensAudit.test.ts`: Passed 4/4 (100% canonical tokens).
- Verbatim raw test output is preserved in `docs/qa/KAN-25/unit-test-results.txt`.

---

## 6. Verification Verdict

All API contracts, WebAuthn schemas, credential scoping, accessibility invariants, and live full-stack step-up interception behaviors are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
