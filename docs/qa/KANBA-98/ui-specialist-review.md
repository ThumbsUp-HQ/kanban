# UI Specialist Gate Review: KANBA-98 (KB-P2-08)

- **Auditor**: `@ui-specialist` (Swarm UI & UX Architecture Specialist Gate)
- **Worktree**: `/tmp/kb-wt-KANBA-98`
- **Branch**: `feat/KANBA-98`
- **Ticket**: `KANBA-98` (`KB-P2-08`: `[Phase 2 / Auth] Identity linking without email auto-merge: (auth_card_id, immutable_subject_id), explicit AAL2 link flow & pre-hijack defense`)

---

### 1. Executive Summary & Verification Matrix

A forensic UI/UX consumer contract audit was performed for `KANBA-98` in `/tmp/kb-wt-KANBA-98`. `KB-P2-08` provides the backend identity linking and pre-hijack defense endpoints consumed by the user account settings, login error handling modals, and identity linking flows. The API response envelopes, error titles, guidance messages, and AAL2 step-up prompts were evaluated against Spec Sections 4.2, 4.3, and 5.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Pre-Hijack Error Guidance** | Informative RFC 7807 for `IDENTITY_LINK_REQUIRED` | Returns 409 with clear instructions to sign in with primary method and link provider | PASS |
| **AAL2 Freshness Enforcement** | Prompt for step-up auth on stale session | Returns 403 `AAL2_REQUIRED` / `AAL2_STALE` instructing client to prompt for re-authentication | PASS |
| **Identity Listing UX** | Safe metadata presentation in account settings | `GET /api/v1/auth/identities` returns card slug, display name, provider kind, email, timestamps | PASS |
| **Sole Auth Method Protection** | Prevent accidental account lockout | `DELETE /identities/{id}` returns 409 `LAST_AUTH_METHOD` with clear explanation | PASS |
| **OIDC / OAuth2 Linking Flow** | Redirect URL delivery with CSRF state | Returns `{mode: "redirect", authorize_url: "..."}` with `__Host-kb_oidc` cookie | PASS |
| **LDAP Linking Flow** | Inline credential prompt contract | Returns `{mode: "ldap_credentials", link_intent_id: "..."}` for modal form submission | PASS |
| **Screenshots Compliance** | N/A - Non-UI Ticket | Confirmed non-UI ticket (API & database layer); verified in `contract-sample.json` | PASS |
| **Typography Compliance** | Plain ASCII hyphens `-` only | Strictly plain ASCII hyphens used throughout code, comments, and reviews | PASS |

---

### 2. Frontend Consumer & Account Linking UX Analysis

1. **Pre-Hijack User Guidance (`IDENTITY_LINK_REQUIRED`):**
   - When an unlinked provider attempts to sign in with an email matching an existing account, the frontend login screen receives:
     ```json
     {
       "type": "https://errors.kanban.local/identity/link-required",
       "title": "Identity Link Required",
       "status": 409,
       "detail": "An account with this email address already exists. Please sign in using your existing authentication method, elevate your session, and link this provider in your account settings.",
       "code": "IDENTITY_LINK_REQUIRED"
     }
     ```
   - This clear guidance empowers the user to complete a safe authentication flow rather than failing silently or presenting confusing generic error messages.

2. **Step-Up Authentication Guidance (`AAL2_REQUIRED` / `AAL2_STALE`):**
   - Attempting to link an identity with AAL1 returns:
     ```json
     {
       "type": "https://errors.kanban.local/auth/aal2-required",
       "title": "AAL2 Required",
       "status": 403,
       "detail": "Account linking requires step-up authentication (AAL2).",
       "code": "AAL2_REQUIRED"
     }
     ```
   - The client UI can intercept this standard code and trigger an inline WebAuthn or TOTP verification modal without disrupting the user's workflow.

3. **Account Settings Connected Identities (`GET /api/v1/auth/identities`):**
   - Returns a structured list of linked providers formatted for rendering in the User Settings > Security > Connected Accounts tab:
     ```json
     {
       "identities": [
         {
           "id": "019323f4-0000-7000-8000-000000000001",
           "card_id": "019323f0-0000-7000-8000-000000000001",
           "card_slug": "corporate-google-oidc",
           "card_display_name": "Corporate Google Workspace",
           "provider_kind": "OIDC",
           "subject_email_at_link": "maya@corp.example",
           "created_at": "2026-11-13T12:00:00Z",
           "last_login_at": "2026-11-13T14:30:00Z"
         }
       ]
     }
     ```
   - No sensitive provider secrets or client secrets are exposed.

4. **Last Auth Method Deletion Protection (`LAST_AUTH_METHOD`):**
   - When a user attempts to remove their sole remaining authentication identity without having configured local admin credentials:
     ```json
     {
       "type": "https://errors.kanban.local/auth/last-auth-method",
       "title": "Last Authentication Method",
       "status": 409,
       "detail": "Cannot remove the sole remaining authentication method for this account without an active local password.",
       "code": "LAST_AUTH_METHOD"
     }
     ```
   - The UI presents a warning modal explaining why the identity cannot be unlinked, preserving account accessibility.

---

### 3. Screenshots Verification
- Status: N/A - Non-UI Ticket (verified per Ticket Spec line 92: `Screenshots: N/A - Non-UI Ticket`).
- Verified wire exchanges in `contract-sample.json`:
  * `409_IDENTITY_LINK_REQUIRED`
  * `403_AAL2_REQUIRED`
  * `200_POST_identities_link_start`
  * `200_GET_api_v1_auth_identities`
  * `409_LAST_AUTH_METHOD`

---

### 4. Gate Sign-Off
I have completed the UI Specialist Gate review for `KANBA-98`. The error codes, problem details payloads, step-up requirements, and identity listing structures conform with the user experience standards and security guidelines of the Kanban platform.

**VERDICT: APPROVED**
