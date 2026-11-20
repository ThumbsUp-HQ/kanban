# API Specialist Security & Architecture Audit Review: KAN-25

## Audit Metadata
- Ticket ID: KAN-25 ([KB-P3-AUDIT-19])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan25-4e735c1c`
- Target Branch: feat/KAN-25
- Base Commit: 887e7e029127b77b5868a4d7c35dd2b818d3a4e5
- Head Commit: 2db09d6
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the implementation of ticket KAN-25 ([KB-P3-AUDIT-19]), providing self-service passkey and FIDO2 hardware security key enrollment, credential testing via WebAuthn authentication assertion, device badge classification, clone detection warnings, and complete AAL2 step-up interception on Profile Settings.

The audit verifies:
1. Exact route path alignment between the frontend client (`personalSettingsApi.ts`, `PasskeyEnrollModal.tsx`, `PersonalSettingsPage.tsx`) and the live FastAPI backend router in `kanban/api/v1/auth_webauthn.py`.
2. Binary base64url challenge and credential serialization/deserialization contracts.
3. Cryptographic and authentication security invariants, including secure context enforcement, RP ID scoping, and anti-replay safeguards.
4. Robust RFC 9457 ApiProblem error handling and step-up orchestration across both `AAL2_REQUIRED` and `AAL2_STALE` challenges.
5. High unit test coverage: 93 passing Vitest tests with >= 95% branch coverage across all touched frontend API and component files.

---

## Detailed Contract & Security Verification

### 1. WebAuthn Route Alignment & Schemas
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
    - Schema items: `{ id, nickname, sign_count, aaguid, transports, suspect_clone_at, created_at, last_used_at }`
    - Verification: `WebauthnCredentialItem` in `personalSettingsApi.ts` extended with `transports`, `sign_count`, `aaguid`, and `suspect_clone_at`.

### 2. Binary Encoding & Serialization Contracts (`webauthn.ts`)
- The WebAuthn API requires binary ArrayBuffers for `challenge`, `user.id`, and `rawId`, whereas JSON transports base64url strings.
- In `kanban/web/src/features/auth/webauthn.ts`:
  - `prepareCreationOptions()`: Safely converts string `challenge` and `user.id` to ArrayBuffer using `base64UrlToArrayBuffer()`.
  - `prepareRequestOptions()`: Safely converts string `challenge` to ArrayBuffer.
  - `serializeRegistrationCredential()`: Converts binary credential responses (`rawId`, `clientDataJSON`, `attestationObject`, `transports`) into JSON-safe base64url strings.
  - `serializeAssertionCredential()`: Converts binary assertion responses (`rawId`, `clientDataJSON`, `authenticatorData`, `signature`, `userHandle`) into JSON-safe base64url strings.
- All binary converters handle empty arrays, null values, and padding variants cleanly without throwing uncaught exceptions.

### 3. Cryptographic & Context Security Invariants
- Secure Context Invariant:
  - `isWebAuthnSupported()` strictly checks `window.isSecureContext === true`, `typeof window.PublicKeyCredential !== 'undefined'`, and `typeof navigator.credentials?.create === 'function' && typeof navigator.credentials?.get === 'function'`.
  - When `!window.isSecureContext`, `PersonalSettingsPage.tsx` displays a visible warning banner (`webauthn-insecure-context-notice`) informing the operator that WebAuthn requires HTTPS or localhost, and disables enrollment action buttons.
- Hostile Input Defense:
  - Nickname inputs are validated locally (required, trimmed, max 64 characters) and sanitized server-side.
  - Authenticator attachment choice is constrained strictly to `"platform"` | `"cross-platform"` | `undefined`.

### 4. AAL2 Step-Up Orchestration (`AAL2_REQUIRED` & `AAL2_STALE`)
- Sensitive profile operations (registering passkeys, deleting passkeys, changing passwords) require Authenticator Assurance Level 2 (AAL2).
- When the backend challenges an operation with `ApiProblem(403, code="AAL2_REQUIRED")` or `ApiProblem(403, code="AAL2_STALE")`, `handleInterceptAal2()`:
  - Detects the step-up challenge code.
  - Preserves the pending operation in memory.
  - Prompts the user with `Aal2StepUpDialog` specifying available methods (`methods: problem.problem.methods`).
  - Upon successful verification, automatically resumes and retries the pending action without data loss.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `package.json` or `pyproject.toml`.
2. [x] Admin Route Security: `/api/v1/admin/*` endpoints remain protected with `Depends(require_admin_aal2)`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken.
4. [x] Test Coverage: All touched files achieve >= 95% statement and branch coverage (`webauthn.ts` 100%/97.56%, `personalSettingsApi.ts` 100%/100%, `PasskeyEnrollModal.tsx` 96.77%/97.61%, `PersonalSettingsPage.tsx` 99.29%/96.31%).
5. [x] Static Analysis: `uv run ruff check .`, `uv run mypy`, `npm run typecheck`, and `npm run lint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, and `message-to-reality-checker.md` verified in `docs/qa/KAN-25/`.

---

## Verdict & Handoff
STATUS: APPROVED

All API contracts, endpoint URLs, WebAuthn schemas, cryptographic encodings, error flows, and AAL2 step-up behaviors have been audited, tested, and verified clean.
