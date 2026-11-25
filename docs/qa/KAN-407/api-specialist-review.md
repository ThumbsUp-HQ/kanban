# API Specialist Review: KAN-407 (Slice 1 Phase 2 Multi-Card Auth & RBAC Simplification)

**Ticket:** KAN-407 (`[SLICE-1-P2][KB-AUTH-RBAC-SIMPLIFY]`)  
**Parent Epic:** KAN-405 (`[EPIC][SLICE-1-AUTH-RBAC]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan407-1e894da6`  
**Target Commit:** `feat/KAN-407-slice1-auth-simplify`  

---

## 1. Executive Summary & Verdict

This API Specialist Review audits the API client integration, authentication state management, RBAC bulk endpoint interactions, and defensive admin safeguards in **KAN-407: Simplify Multi-Card Auth, LDAP Group Sync & RBAC Matrix UI**.

The implementation in `feat/KAN-407-slice1-auth-simplify` strictly preserves and reinforces security and architectural contracts:
1. **Zero Database Migrations & Full Schema Parity**:
   - Implements all Slice 1 Phase 2 requirements across `AuthStudioPage`, `AuthCardEditorDrawer`, `RbacPolicyBuilder`, and `adminAuthApi.ts` without altering database schema or introducing new migration files.
2. **Sole Active Admin Card Lockout Prevention**:
   - `isSoleActiveAdminCard` in `adminAuthApi.ts` provides client-side pre-flight lockout detection for both `LOCAL_ADMIN` and external identity providers (`OIDC`, `OAUTH2`, `LDAP`), disabling deletion or deactivation controls when disabling the card would leave the server without an administrator authentication path.
   - Preserves backend `LOCKOUT_PREVENTED` error handling over HTTP.
3. **Password Manager Autocomplete & Secret Leakage Hardening**:
   - Secret inputs (`#card-secret`) avoid `input[type="password"]` to eliminate browser autofill / password manager overwriting of administrative client secrets. Applies `.kb-masked-api-key` CSS masking along with `autoComplete="off"`, `data-1p-ignore="true"`, `data-lpignore="true"`, `data-bwignore="true"`, and `data-form-type="other"`.
   - Write-only secret fields render empty on edit and send `secret_input` only when replacement is explicitly checked.
4. **RBAC Category Bulk Permission API Integration**:
   - `RbacPolicyBuilder` cleanly interacts with `POST /api/v1/admin/rbac/roles/permissions:batch` for category-level quick selectors (`Select All`, `Clear All`, `Read-Only preset`).
   - Silently handles `Aal2StepUpCancelledError` on cancelled WebSudo / AAL2 step-up challenges without triggering spurious error banners.

**Verdict: APPROVED.** Zero security regressions, zero unhandled errors, flawless typing and linting, and full alignment with backend contracts.

---

## 2. API Contract & Security Invariant Audit

### 2.1 Multi-Card Auth Lifecycle & Admin Safeguards (`adminAuthApi.ts`)
- **Lockout Detection Invariant**:
  ```typescript
  export function isSoleActiveAdminCard(
    card: { id: string; is_enabled: boolean; provider_kind: ProviderKind; public_config?: Record<string, unknown> },
    allCards: { id: string; is_enabled: boolean; provider_kind: ProviderKind; public_config?: Record<string, unknown> }[],
  ): boolean
  ```
  Evaluates active cards and ensures that `LOCAL_ADMIN` cannot be disabled if no active external identity provider exists, preventing accidental administrative lockout before the request hits the server.
- **Server-Side Authorization & AAL2 Wall**:
  All underlying auth card administrative endpoints (`POST /api/v1/admin/auth/cards`, `PUT /api/v1/admin/auth/cards/{card_id}`, `DELETE /api/v1/admin/auth/cards/{card_id}`) strictly enforce `require_admin_aal2`.

### 2.2 RBAC Policy Batch Operations (`RbacPolicyBuilder.tsx`)
- **Route:** `POST /api/v1/admin/rbac/roles/permissions:batch`
- **Payload Contract:** Dispatches atomic batches of permission grants/revocations across permission categories (`issue`, `project`, `workspace`, `admin`, `custom_field`).
- **Resilience:** Gracefully captures `Aal2StepUpCancelledError` and retains UI state without crashing or clearing active selections.

---

## 3. Automated Test Verification & Quality Gates

1. **Backend Test Suite (Pytest)**:
   - 69 tests passed across `test_auth_cards_admin_api.py`, `test_ldap_tls_and_bind.py`, `test_ldap_group_sync.py`, and `test_oidc_flow.py`.
   - 0 failures, 0 errors, 31.65s runtime.

2. **Frontend Test Suite (Vitest)**:
   - 122 tests passed across `AuthStudioPage.test.tsx` (55 tests), `AuthCardEditorDrawer.test.tsx` (59 tests), and `RbacPolicyBuilder.test.tsx` (8 tests).
   - 0 `act(...)` stderr warnings.
   - Branch coverage: **95.76%** across touched files (`AuthCardEditorDrawer.tsx` 95.57%, `AuthStudioPage.tsx` 95.68%, `RbacPolicyBuilder.tsx` 97.59%).

3. **Build & Static Analysis Pipeline**:
   - `ruff check`: All checks passed.
   - `mypy`: 0 issues in 680 source files.
   - `tsc -b --noEmit`: 0 errors.
   - `eslint`: 0 warnings, 0 errors.
   - `vite build`: Succeeded in 1.24s.
   - `check_no_dashes.py`: 0 forbidden Unicode dashes found.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-407/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: All tools exit 0 cleanly.
  - `unit-test-results.txt`: Documents 69 backend and 122 frontend tests.
  - `git-diff.patch`: Clean diff with 0 tracking artifacts.
  - `screenshots/`: 5 multi-viewport unclipped PNG captures.
  - `changed-files-manifest.txt` and `SHA256SUMS.txt`: Verified with `sha256sum -c`.

The API interactions and security architecture for KAN-407 are robust, verified, and approved for integration.
