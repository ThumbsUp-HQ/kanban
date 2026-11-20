# API Specialist Review: KAN-25 (KB-P3-AUDIT-19)

- Ticket: KAN-25
- Title: Add Self-Service Passkey & FIDO2 Security Key Registration, Key Testing, and AAL2 Step-Up Handling on Profile Settings
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan25-rc1-ad1c82a2`
- Branch: `fix/KAN-25-rc1`
- Commit: `6dad2ff`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API and Architecture audit inspects ticket KAN-25 on remediation branch `fix/KAN-25-rc1` (commit `6dad2ff`). The ticket implements self-service passkey and FIDO2 hardware security key enrollment, credential testing via WebAuthn authentication assertion, device badge classification, clone detection warnings, complete AAL2 step-up interception on Profile Settings, credential scoping during key testing, and accessible modal focus trapping.

All API contracts, security boundaries, and coverage requirements are verified and approved:
1. Exact route path alignment between the frontend client (`personalSettingsApi.ts`, `PasskeyEnrollModal.tsx`, `PersonalSettingsPage.tsx`) and the live FastAPI backend router in `kanban/api/v1/auth_webauthn.py`.
2. Binary base64url challenge and credential serialization/deserialization contracts.
3. Cryptographic and authentication security invariants, including secure context enforcement, RP ID scoping, credential-specific challenge filtering, and anti-replay safeguards.
4. Robust RFC 9457 ApiProblem error handling and step-up orchestration across both `AAL2_REQUIRED` and `AAL2_STALE` challenges.
5. High unit test coverage: 105 passing Vitest tests with >= 95% statement and branch coverage across all touched frontend API and component files.

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

## 3. Dependency, Layering & Code Cleanliness Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy`: 0 errors across 1095 source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
  - `python3 -m scripts.check_no_dashes --all`: 0 errors.
- Clean Patch Artifact: `docs/qa/KAN-25/git-diff.patch` verified to contain zero `docs/qa/*` files.

---

## 4. Test Coverage Audit

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

## 5. Verification Verdict

All API contracts, WebAuthn schemas, credential scoping, and accessibility invariants are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
