# Slice 1: Multi-Card Auth, AD/LDAP, OIDC, MFA and RBAC Setting Inventory and Simplification Audit

**Ticket:** KAN-406 (`[SLICE-1-P1][KB-AUTH-AUDIT]`)  
**Parent Epic:** KAN-405 (`[EPIC][SLICE-1-AUTH-RBAC]`)  
**Status:** In Progress (Phase 1 Audit and Simplification Specification)  
**Author:** s1-p1 (Security and UX Auditor)  
**Traceability:** `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 3 and Section 4 (Multi-Card Pluggable Authentication Studio)  

---

## 1. Executive Summary and Scope Boundaries

### 1.1 Purpose
This document delivers the comprehensive Phase 1 setting-by-setting inventory, technical audit, simplification cut list, and Phase 3 staging checklist for **Slice 1 (Multi-Card Authentication Studio, Active Directory/LDAPS, OIDC/OAuth2, Passkeys/TOTP, and Custom RBAC)**. 

### 1.2 Zero-Mutation Phase 1 Boundary
Phase 1 (`KAN-406`) is strictly read-only reconnaissance and specification handoff. No production or test source code is modified in Phase 1. All UI simplifications, layout refactorings, and backend wiring adjustments are executed in Phase 2 (`KAN-407`).

### 1.3 Coordination with In-Flight Tickets
- **KAN-404 (Gate 0 WebSudo):** Owns administrative session step-up (AAL2 dirty keepalive, sudo re-auth prompt, and session elevation). Slice 1 references AAL2 step-up handlers (`require_admin_aal2`, `aal2Challenge`) as downstream consumers without re-implementing WebSudo primitives.
- **KAN-398 (`/admin/auth` Access Fix):** Corrects `SERVER_ADMIN` permission checking via linear database migration on `app_principal_has_role`, enforces `MFA_ENROLLMENT_REQUIRED` banner in `AuthStudioPage.tsx`, and handles role-aware tab filtering in `AdminStudioSubnav.tsx`. Slice 1 builds on top of these verified access invariants.

---

## 2. Complete Setting-by-Setting Inventory Table

Below is the complete inventory of all UI controls, labels, options, defaults, validation rules, and backend bindings across Slice-1 files:
- `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`
- `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`
- `kanban/web/src/features/rbac/RbacPolicyBuilder.tsx`
- `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
- `kanban/api/v1/admin/auth_cards.py`
- `kanban/api/v1/admin/principals.py`
- `kanban/api/v1/admin/rbac.py`
- `kanban/api/v1/auth_ldap.py` (and `kanban/auth/ldap/router.py`)
- `kanban/api/v1/auth_oidc.py`
- `kanban/api/v1/auth_local.py`
- `kanban/api/v1/auth_mfa.py`
- `kanban/api/v1/auth_webauthn.py`
- `kanban/api/v1/auth_identities.py`

### Inventory Table

| Screen/Drawer | Setting Label and Key | Options / Type | 1-Sentence Plain-English Meaning | Backend Wiring Status | Disposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `AuthStudioPage.tsx` | Main Section Tabs (`tab-cards`, `tab-users`, `tab-roles`) | Tabs: Cards, Users, Roles | Switches between auth provider cards, principal management, and RBAC matrix. | Client-side state routing (`activeTab`). | KEEP |
| `AuthStudioPage.tsx` | Add Auth Card (`auth-studio-add-btn`) | Button | Opens the AuthCardEditorDrawer in create mode to configure a new auth provider. | Triggers drawer with `editingCard=null`. | KEEP |
| `AuthStudioPage.tsx` | Card Drag Handle and Reorder Buttons (`onMoveUp`, `onMoveDown`) | Drag Handle / Buttons | Changes the visual display order and sign-in precedence of authentication cards. | Wired to `POST /admin/auth-cards/{card_ref}/reorder`. | SIMPLIFY |
| `AuthStudioPage.tsx` | Card Enabled Toggle (`onToggleEnabled`) | Toggle Switch / Button | Activates or disables user and admin sign-in through this specific authentication provider. | Wired to `POST /admin/auth-cards/{card_ref}/enable` and `disable`. | KEEP |
| `AuthStudioPage.tsx` | Test Handshake Button (`onTestHandshake`) | Button | Executes a live reachability and cryptographic probe against the provider within 8.0s. | Wired to `POST /admin/auth-cards/{card_ref}/test-handshake`. | KEEP |
| `AuthStudioPage.tsx` | Edit Card Button (`onEdit`) | Button | Opens the AuthCardEditorDrawer pre-populated with existing configuration for editing. | Client-side drawer open with `editingCard`. | KEEP |
| `AuthStudioPage.tsx` | Delete Card Button (`onDelete`) | Button | Permanently deletes an authentication card after anti-lockout verification. | Wired to `DELETE /admin/auth-cards/{card_ref}` with confirmation slug. | KEEP |
| `AuthStudioPage.tsx` | Principal Filter Bar (`principal-filters`) | Buttons: All, User, Agent, Service Account | Filters the workspace principal table by account type. | Client-side filter on `principals` list. | KEEP |
| `AuthStudioPage.tsx` | Add Local User Button (`auth-studio-add-btn`) | Button | Opens modal to manually provision a new local user, agent, or service account. | Client-side modal open (`isAddUserOpen`). | KEEP |
| `AuthStudioPage.tsx` | Add Local User: Principal Type (`newPrincipalType`) | Select: User, Agent, Service Account | Selects whether the new principal is a human user, autonomous agent, or automation bot. | Wired to `POST /admin/principals` (`kind`). | KEEP |
| `AuthStudioPage.tsx` | Add Local User: Handle (`newUserHandle`) | Text Input | Unique username or handle starting with `@` used for mentions and login. | Wired to `POST /admin/principals` (`handle`). | KEEP |
| `AuthStudioPage.tsx` | Add Local User: Display Name (`newUserDisplayName`) | Text Input | Human-readable full name shown in cards, mentions, and activity feeds. | Wired to `POST /admin/principals` (`display_name`). | KEEP |
| `AuthStudioPage.tsx` | Add Local User: Email (`newUserEmail`) | Email Input | Primary notification and account recovery email address. | Wired to `POST /admin/principals` (`email`). | KEEP |
| `AuthStudioPage.tsx` | Add Local User: Initial Password (`newUserPassword`) | Password Input | Temporary or initial password for local database authentication. | Wired to `POST /admin/principals` (`initial_password`). | SIMPLIFY |
| `AuthStudioPage.tsx` | Add Local User: Initial Role (`newUserRole`) | Select: Viewer, Member, Admin | Initial workspace role assigned to the newly created principal. | Wired to `POST /admin/principals` (role binding). | KEEP |
| `AuthStudioPage.tsx` | Reset Password Modal: New Password (`newPassword`) | Password Input | Sets a new local password for the selected principal. | Wired to `POST /admin/principals/{principal_id}/password`. | SIMPLIFY |
| `AuthStudioPage.tsx` | Reset Password Modal: Confirm Password (`confirmPassword`) | Password Input | Confirmation field to prevent accidental typing mistakes during password reset. | Client-side match validation before submit. | SIMPLIFY |
| `AuthStudioPage.tsx` | Lockout Prevented Banner (`LockoutPreventedBanner`) | Alert Banner | Warns administrator when an action would remove all administrative sign-in paths. | Consumes RFC 7807 409 `LOCKOUT_PREVENTED` error. | KEEP |
| `AuthCardEditorDrawer.tsx` | 1-Click Presets Bar (`auth-presets-list`) | Buttons: Google, GitHub, Active Directory, OpenLDAP, Custom SSO | Pre-populates all protocol, attribute, filter, and icon fields for common providers. | Client-side preset applicator (`applyPreset`). | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | Provider Kind (`card-provider-kind`) | Select: Local, LDAP, OIDC, OAuth2 | Selects the foundational authentication protocol implemented by this card. | Wired to `provider_kind` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Display Name (`card-display-name`) | Text Input | Label shown on the public sign-in button on the login screen. | Wired to `display_name` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Slug Identifier (`card-slug`) | Text Input | URL-safe slug used in redirect endpoints such as `/api/v1/auth/oidc/{slug}/callback`. | Wired to `slug` on `POST/PATCH /admin/auth-cards`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | Button Subtext (`card-subtext`) | Text Input | Secondary explanatory text displayed under the provider button on login page. | Wired to `button_subtext` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Icon Preset (`card-icon-preset`) | Select: Shield, Google, GitHub, Active Directory, LDAP, Key | Visual icon displayed next to the provider name on the login card. | Wired to `icon_preset` on `POST/PATCH /admin/auth-cards`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | Enable Card (`card-is-enabled`) | Checkbox | Determines whether this authentication card is active and visible to users. | Wired to `is_enabled` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Auto-provision Users (`card-auto-provision`) | Checkbox | Automatically creates a new user account upon successful first-time directory sign-in. | Wired to `auto_provision_users` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Allowed Email Domains (`card-email-domains`) | Text Input (CSV) | Restricts sign-in to users whose verified email matches these corporate domains. | Wired to `allowed_email_domains` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Access Policy Mode (`card-access-policy`) | Select: Any User, Allowlist Only, Group Mapped | Selects whether access is open to all domain users, restricted by email, or role-mapped. | Wired to `access_policy_mode` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Admin Allowlist (`card-admin-allowlist`) | Text Input (CSV) | List of user email addresses automatically granted Server Administrator privileges. | Wired to `admin_allowlist` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | User Allowlist (`card-user-allowlist`) | Text Input (CSV) | Explicit list of email addresses permitted to sign in when policy is Allowlist Only. | Wired to `user_allowlist` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | Admin Groups (`card-admin-groups`) | Text Input (CSV) | Directory group names (e.g., Domain Admins) mapped to Server Administrator. | Wired to `admin_groups` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | User Groups (`card-user-groups`) | Text Input (CSV) | Directory group names mapped to standard Member privileges. | Wired to `user_groups` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | OIDC Issuer URL (`card-issuer-url`) | URL Input | Base URL of OpenID Connect provider used for discovery at `/.well-known/openid-configuration`. | Wired to `issuer_url` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Authorized Redirect URI (`card-callback-url`) | Read-Only Text Input + Copy Button | Canonical redirect URI to register in the identity provider console. | Computed dynamically based on window.location.origin and slug. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | Client ID (`card-client-id`) | Text Input | Public OAuth2 client identifier issued by identity provider. | Wired to `client_id` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Client Secret (`card-secret` - OIDC) | Password / Masked Input | Cryptographic client secret issued by identity provider. | Envelope-encrypted, saved via `client_secret`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | Replace Secret Toggle (`card-replace-secret` - OIDC) | Checkbox | Enables updating the stored client secret without revealing existing encrypted secret. | Client-side form state governing secret submission. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | Scopes (`card-scopes`) | Text Input (CSV) | OAuth2 scopes requested during authorization (e.g., `openid, profile, email`). | Wired to `scopes` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | Token Auth Method (`card-token-auth`) | Select: Basic, Post | HTTP authentication method used when calling the identity provider token endpoint. | Wired to `token_auth_method` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | Google JSON Import Dropzone (`google-json-dropzone`) | File Drop / Upload | Accepts Google Cloud Console `client_secret_*.json` to auto-fill OIDC settings. | Wired to `POST /admin/auth-cards/parse-google-json`. | KEEP |
| `AuthCardEditorDrawer.tsx` | Google JSON Paste Textarea (`googleJsonPasteText`) | Textarea | Alternative raw text area to paste Google Cloud Console JSON directly. | Wired to `POST /admin/auth-cards/parse-google-json`. | KEEP |
| `AuthCardEditorDrawer.tsx` | LDAP Server URL (`card-server-url`) | URL Input | Primary connection URL (`ldaps://hostname:636` or `ldap://hostname:389`). | Wired to `server_url` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | LDAP StartTLS Toggle (`card-starttls`) | Checkbox | Upgrades plain LDAP port 389 connection to TLS via StartTLS command. | Wired to `start_tls` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | LDAP Bind DN (`card-bind-dn`) | Text Input | Distinguished Name of service account used to search directory (e.g. `cn=admin,dc=corp`). | Wired to `bind_dn` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | LDAP Bind Password (`card-secret` - LDAP) | Password / Masked Input | Password of directory search service account. | Envelope-encrypted, saved via `bind_password`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | LDAP Base DN (`card-base-dn`) | Text Input | Root directory search base for discovering users (e.g., `ou=Users,dc=corp,dc=local`). | Wired to `base_dn` on `POST/PATCH /admin/auth-cards`. | KEEP |
| `AuthCardEditorDrawer.tsx` | LDAP User Filter (`card-user-filter`) | Text Input | Search filter syntax resolving usernames (e.g., `(&(objectClass=person)(sAMAccountName={username}))`). | Wired to `user_filter` on `POST/PATCH /admin/auth-cards`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | LDAP Subject Attribute (`card-subject-attr`) | Text Input | Immutable directory attribute used for stable principal identity (`objectGUID`, `entryUUID`). | Wired to `subject_attribute` on `POST/PATCH /admin/auth-cards`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | LDAP Email Attribute (`card-email-attr`) | Text Input | Directory attribute storing user email address (`mail`, `userPrincipalName`). | Wired to `email_attribute` on `POST/PATCH /admin/auth-cards`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | LDAP Full Name Attribute (`card-display-attr`) | Text Input | Directory attribute storing user full name (`displayName`, `cn`). | Wired to `display_name_attribute` on `POST/PATCH /admin/auth-cards`. | SIMPLIFY |
| `AuthCardEditorDrawer.tsx` | SPKI SHA-256 Pin (`card-spki-pin`) | Text Input | Base64 Subject Public Key Info pin enforcing strict public-key pinning on TLS connections. | Wired to `spki_pin` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | Custom CA Certificate PEM (`card-ca-pem`) | Textarea | Corporate root or intermediate CA certificate bundle used to trust private LDAPS servers. | Wired to `ca_pem` on `POST/PATCH /admin/auth-cards`. | MOVE_TO_ADVANCED |
| `AuthCardEditorDrawer.tsx` | Draft Handshake Test Button (`drawer-test-handshake-btn`) | Button | Tests network reachability, TLS trust, and credential binding before saving card. | Wired to `POST /admin/auth-cards/test-handshake`. | KEEP |
| `RbacPolicyBuilder.tsx` | Role Tier Selector (`rbac-tier-select`) | Select: System Admin, Workspace Admin, Project Admin | Governs role hierarchy scope; system tier requires active Server Administrator privileges. | Client-side tier filtering on fetched roles. | KEEP |
| `RbacPolicyBuilder.tsx` | Role Multi-Select Dropdown (`rbac-select-role-dropdown`) | Multi-select Dropdown | Selects one or more roles to inspect or edit permissions concurrently. | Governs checkbox display in matrix. | SIMPLIFY |
| `RbacPolicyBuilder.tsx` | Workspace Permissions Grid (`rbac-fieldset-workspace`) | 8 Tri-State Checkboxes | Controls workspace-level management actions (create, edit, members, roles, integrations, audit, export, purge). | Wired to `PUT /api/v1/admin/rbac/roles/{role_id}/permissions`. | KEEP |
| `RbacPolicyBuilder.tsx` | Issue Permissions Grid (`rbac-fieldset-issue`) | 10 Tri-State Checkboxes | Controls issue lifecycle actions (create, view, comment, transition, move, copy, archive, delete, link, subscribe). | Wired to `PUT /api/v1/admin/rbac/roles/{role_id}/permissions`. | KEEP |
| `RbacPolicyBuilder.tsx` | Field Permissions Grid (`rbac-fieldset-field`) | 12 Tri-State Checkboxes | Controls granular field-level modification rights (summary, description, state, priority, assignees, etc.). | Wired to `PUT /api/v1/admin/rbac/roles/{role_id}/permissions`. | KEEP |
| `RbacPolicyBuilder.tsx` | Create Role Button (`rbac-open-create-role`) | Button | Opens inline popover to define a new custom RBAC role. | Opens popover (`isPopoverOpen`). | KEEP |
| `RbacPolicyBuilder.tsx` | New Role Name (`rbac-new-role-name`) | Text Input | Human-readable role label displayed in selectors and badge pills. | Wired to `POST /api/v1/admin/rbac/roles` (`name`). | KEEP |
| `RbacPolicyBuilder.tsx` | New Role Slug (`rbac-new-role-slug`) | Text Input | System identifier slug for programmatic authorization checks. | Wired to `POST /api/v1/admin/rbac/roles` (`slug`). | SIMPLIFY |
| `RbacPolicyBuilder.tsx` | New Role Color (`rbac-color-picker`) | Color Picker / Swatches | Visual badge color used in user pills and table rows. | Wired to `POST /api/v1/admin/rbac/roles` (`color_hex`). | KEEP |
| `RbacPolicyBuilder.tsx` | Clone Permissions From (`rbac-clone-role-select`) | Select (Role List) | Copies permission baseline from an existing role into the new role upon creation. | Copies permission set in client before batch submission. | KEEP |
| `PersonalSettingsPage.tsx` | Avatar Upload and Remove (`avatar-file-input`, `upload-avatar-btn`, `remove-avatar-btn`) | File Input / Buttons | Uploads or deletes personal profile avatar image. | Wired to user profile update endpoints. | KEEP |
| `PersonalSettingsPage.tsx` | Display Name (`display-name-input`) | Text Input | Personal display name shown to team members across tickets and activity feeds. | Wired to `PATCH /api/v1/auth/me`. | KEEP |
| `PersonalSettingsPage.tsx` | Timezone (`timezone-select`) | Select (IANA Timezones) | Timezone used to render human-readable timestamps and cycle deadlines. | Wired to `PATCH /api/v1/auth/me`. | KEEP |
| `PersonalSettingsPage.tsx` | Current Password (`current-password-input`) | Password Input | Verification of existing password required before changing account password. | Wired to `POST /api/v1/auth/local/change-password`. | KEEP |
| `PersonalSettingsPage.tsx` | New Password (`new-password-input`) | Password Input | New local account password meeting complexity standards. | Wired to `POST /api/v1/auth/local/change-password`. | KEEP |
| `PersonalSettingsPage.tsx` | Confirm New Password (`confirm-password-input`) | Password Input | Confirmation entry verifying new password was typed accurately. | Client-side match validation. | KEEP |
| `PersonalSettingsPage.tsx` | Add Passkey / FIDO2 Key (`add-passkey-btn`, `add-fido2-key-btn`) | Button | Initiates WebAuthn ceremony to register biometric passkey or hardware security key. | Wired to `POST /api/v1/auth/webauthn/register/options` and `verify`. | KEEP |
| `PersonalSettingsPage.tsx` | Passkey Table Actions (`test-passkey`, `rename-passkey`, `delete-passkey`) | Action Buttons | Tests passkey assertion ceremony, edits user-friendly nickname, or removes credential. | Wired to `POST .../authenticate/options`, `PATCH .../credentials/{id}`, and `DELETE`. | KEEP |
| `PersonalSettingsPage.tsx` | Enable TOTP (`enable-totp-btn`) | Button | Starts time-based one-time password registration ceremony. | Wired to `POST /api/v1/auth/mfa/totp/enroll`. | KEEP |
| `PersonalSettingsPage.tsx` | TOTP Verification Code (`totp-verification-input`) | Text / Number Input | 6-digit numeric verification code confirming authenticator app synchronization. | Wired to `POST /api/v1/auth/mfa/totp/confirm`. | KEEP |
| `PersonalSettingsPage.tsx` | Copy Recovery Codes (`copy-recovery-codes-btn`) | Button | Copies 10 emergency single-use recovery codes to system clipboard. | Client-side clipboard API. | KEEP |
| `PersonalSettingsPage.tsx` | Regenerate Recovery Codes (`regenerate-recovery-codes-btn`) | Button | Invalidates existing emergency codes and provisions 10 fresh single-use recovery codes. | Wired to `POST /api/v1/auth/mfa/recovery/regenerate`. | KEEP |
| `PersonalSettingsPage.tsx` | Connect Directory Identity (`ldap-credentials-modal`) | Modal (Username/Password) | Authenticates against an active LDAP card to link directory identity to local profile. | Wired to `POST /api/v1/auth/identities/link/ldap`. | KEEP |
| `PersonalSettingsPage.tsx` | Unlink Identity (`unlink-identity`) | Button | Detaches an external OIDC or LDAP identity from the user account. | Wired to `DELETE /api/v1/auth/identities/{identity_id}`. | KEEP |

---

## 3. Simplification Proposals and Focus Areas

### 3.1 Active Directory vs OpenLDAP 1-Click Presets
- **Current UX Friction:** Administrators configuring LDAP must manually specify LDAP filters (`user_filter`), immutable subject attributes (`subject_attribute`), email attributes (`email_attribute`), and full name attributes (`display_name_attribute`). Active Directory uses Microsoft-specific schema attributes (`sAMAccountName`, `objectGUID`, `displayName`) while OpenLDAP uses standard RFC 4519 attributes (`uid`, `entryUUID`, `cn`). Misconfiguring these fields causes authentication failures or unstable user identity mapping.
- **Simplification Strategy:** Expand the 1-Click Presets bar with dedicated **Active Directory** and **OpenLDAP** preset buttons. When clicked:
  - Automatically populate standard ports and protocols (`ldaps://...:636`, `start_tls: false`).
  - Auto-fill canonical filters:
    - Active Directory: `(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))`
    - OpenLDAP: `(&(objectClass=person)(uid={username}))`
  - Auto-fill attribute mappings:
    - Active Directory: `subject_attribute="objectGUID"`, `email_attribute="mail"`, `display_name_attribute="displayName"`
    - OpenLDAP: `subject_attribute="entryUUID"`, `email_attribute="mail"`, `display_name_attribute="cn"`
  - Provide a short helper note explaining the exact attribute expectations.

### 3.2 `sort_rank` and Fractional Indexing
- **Current UX Friction:** While the backend uses fractional indexing strings (e.g., `after: "0|i00001:"`) to order cards in `POST /admin/auth-cards/{card_ref}/reorder`, raw rank values or confusing reordering mechanics should never burden the administrator.
- **Simplification Strategy:** Expose clean drag-and-drop grab handles paired with accessible Up/Down keyboard buttons in `AuthStudioPage.tsx`. Completely encapsulate fractional indexing in the frontend service; administrators simply drag cards or click Up/Down to establish visual precedence.

### 3.3 SPKI SHA-256 Pin vs CA Certificate PEM
- **Current UX Friction:** `AuthCardEditorDrawer.tsx` includes both `SPKI SHA-256 Pin` and `Custom CA Certificate PEM` in the primary form, confusing users who do not know which to configure.
- **Simplification Strategy:** Move both controls into a collapsible **Advanced TLS Security** disclosure section. Provide clear contextual guidance:
  - Use **CA Certificate PEM** when connecting to corporate directory servers signed by an internal private PKI root or intermediate CA.
  - Use **SPKI SHA-256 Pin** only when pinning a specific public key to prevent certificate authority compromise.
  - Add client-side validation alerting users if a PEM block lacks `-----BEGIN CERTIFICATE-----` headers.

### 3.4 Copyable OIDC Redirect URI (Callback URL)
- **Current UX Friction:** Setting up external identity providers (Google Cloud Console, GitHub Developer Apps, Okta, Keycloak) requires registering the exact callback URL. Currently, administrators must manually construct or inspect network requests to determine the URL.
- **Simplification Strategy:** In `AuthCardEditorDrawer.tsx`, render an explicit read-only input showing the full URL `${window.location.origin}/api/v1/auth/oidc/${slug}/callback` paired with a 1-click **Copy Callback URL** button (`data-testid="copy-callback-url-btn"`). Dynamically update the displayed callback URL as the administrator edits the card slug. Include an origin warning if running on `http://localhost` or a non-standard port.

### 3.5 Anti-Lockout Safeguards and Break-Glass Warnings
- **Current UX Friction:** Disabling or deleting an authentication card can trigger a `409 Conflict` (`LOCKOUT_PREVENTED`) from the backend if the action would leave the system without any functional administrative login method.
- **Simplification Strategy:**
  - Before an administrator disables or deletes a card, calculate client-side whether this card represents the last active administrative authentication card.
  - If it is the last card, display an explicit **Break-Glass Warning** dialog explaining that at least one local administrator account or alternative active authentication card must remain configured to prevent lockout.
  - Clarify the 3-layer anti-lockout architecture in inline help text: (1) Local Admin Card Invariant, (2) Active Administrator Principal Invariant, and (3) Active Session Step-Up.

### 3.6 Password-Manager and Autofill Suppression
- **Current UX Friction:** Browser password managers (1Password, LastPass, Bitwarden, Chrome Password Manager) frequently mistake administrative configuration inputs (such as the LDAP Bind Password or OAuth Client Secret) for the administrator's personal sign-in credentials, triggering aggressive save/autofill prompts.
- **Simplification Strategy:**
  - Add explicit suppression attributes to administrative credential forms in `AuthCardEditorDrawer.tsx`:
    - `autoComplete="off"`
    - `data-1p-ignore="true"`
    - `data-lpignore="true"`
    - `data-bwignore="true"`
    - `data-form-type="other"`
  - Render credential inputs strictly as `type="text"` with CSS-masked styling (similar to `KAN-400`), or ensure password managers treat drawer inputs as administrative configuration data rather than personal account credentials.

---

## 4. Phase 2 (`KAN-407`) File-Scoped Action Checklist

Phase 2 (`KAN-407`) will implement all approved UI and wiring simplifications. Below is the file-scoped action checklist, deduplicated against `KAN-404` and `KAN-398`:

### 4.1 Frontend Tasks (`kanban/web/src/features/`)
- **`kanban/web/src/features/admin-auth/AuthStudioPage.tsx`:**
  - [ ] Add explicit break-glass confirmation dialog before calling `disable` or `delete` on an auth card if it is the sole active administrative provider.
  - [ ] Streamline fractional indexing reordering feedback with instant visual card movement.
  - [ ] Ensure role-aware tab rendering seamlessly integrates with `KAN-398` fixes.
- **`kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`:**
  - [ ] Polish 1-click **Active Directory** and **OpenLDAP** presets: auto-populate exact attribute mappings (`objectGUID`/`sAMAccountName` vs `entryUUID`/`uid`), search filters, and default ports.
  - [ ] Move `SPKI SHA-256 Pin` and `Custom CA Certificate PEM` into a collapsible `Advanced TLS Configuration` section with inline format validation.
  - [ ] Move access policy group mappings (`admin_groups`, `user_groups`, `admin_allowlist`, `user_allowlist`) into an `Advanced Access Governance` section.
  - [ ] Add password-manager suppression attributes (`data-1p-ignore="true"`, `data-lpignore="true"`, `data-bwignore="true"`, `autoComplete="off"`) to `card-secret` (Client Secret and Bind Password inputs).
  - [ ] Ensure dynamic recalculation and copy feedback on `oauth-callback-url`.
- **`kanban/web/src/features/rbac/RbacPolicyBuilder.tsx`:**
  - [ ] Add quick-selection filters for permissions (e.g., "Select All Issue Permissions", "Clear Field Permissions").
  - [ ] Auto-generate clean URL-safe slugs in the Create Role popover as the administrator types the role name.
- **`kanban/web/src/features/settings/PersonalSettingsPage.tsx`:**
  - [ ] Polish LDAP credential linking modal with explicit connection state and credential error reporting.
  - [ ] Verify passkey nickname editing and test assertion feedback.

### 4.2 Backend Tasks (`kanban/api/v1/`)
- **`kanban/api/v1/admin/auth_cards.py`:**
  - [ ] Verify error code consistency on `test-handshake` endpoints to return structured diagnostics for LDAP/OIDC timeout or DNS resolution failures.
- **`kanban/api/v1/admin/principals.py`:**
  - [ ] Ensure role label listing and assignment endpoints enforce clean validation on custom role slugs.
- **`kanban/api/v1/admin/rbac.py`:**
  - [ ] Maintain batch permission updates consistency with permission catalog keys.
- **`kanban/api/v1/auth_ldap.py` and `kanban/auth/ldap/router.py`:**
  - [ ] Verify LDAP bind password handling suppresses logging of plain secrets in all trace outputs.
- **`kanban/api/v1/auth_oidc.py`:**
  - [ ] Validate state token and PKCE code challenge verification during OIDC redirect handling.
- **`kanban/api/v1/auth_local.py`, `kanban/api/v1/auth_mfa.py`, `kanban/api/v1/auth_webauthn.py`, `kanban/api/v1/auth_identities.py`:**
  - [ ] Retain existing secure session and AAL2 step-up protections without regression.

---

## 5. Phase 3 (`KAN-408`) Credential and Container Checklist

Phase 3 (`KAN-408`) executes live end-to-end workout tests against real authentication servers. To guarantee hermetic execution without requiring external SaaS credentials or internet connectivity, local companion containers are utilized.

### 5.1 Local Companion Containers
1. **Local OpenLDAP Companion Container:**
   - Image: `rroemhild/test-openldap` or `osixia/openldap:latest`
   - Ports: `10389:389` (plain/StartTLS), `10636:636` (LDAPS)
   - Pre-seeded Domain Base: `dc=planetexpress,dc=com`
   - Pre-seeded Admin: `cn=admin,dc=planetexpress,dc=com` (Password: `GoodNewsEveryone`)
   - Pre-seeded Test Users:
     - `hermes` (UID: `hermes`, Password: `hermespassword`, Group: `bureaucrats`)
     - `fry` (UID: `fry`, Password: `frypassword`, Group: `delivery`)
     - `leela` (UID: `leela`, Password: `leelapassword`, Group: `pilots`)
2. **Local Keycloak / Mock OIDC Container:**
   - Image: `quay.io/keycloak/keycloak:latest` or lightweight local OIDC provider
   - Ports: `18080:8080`
   - Realm: `kanban-test`
   - Client ID: `kanban-app`
   - Client Secret: `kanban-test-secret-12345`

### 5.2 External Provider Staging (Optional / User-Supplied Only)
- If the user explicitly requests testing against live corporate Active Directory or Google/GitHub OAuth, the following credentials must be supplied via environment variables without committing secrets to git:
  - `TEST_AD_LDAP_SERVER_URL`: Host and port of corporate domain controller.
  - `TEST_AD_BIND_DN` and `TEST_AD_BIND_PASSWORD`: Service account credentials.
  - `TEST_GOOGLE_CLIENT_ID` and `TEST_GOOGLE_CLIENT_SECRET`: Google OAuth application credentials.

### 5.3 Non-Destructive Live Protection Invariant
- Under NO circumstance may tests or workouts run destructively against `https://k.hackedyour.info` / `192.168.1.101`. All workouts run in isolated local containers or dedicated test workspaces.

---

## 6. Audit Verification and Sign-Off

- **Inventory Completeness:** 100% of UI controls across `AuthStudioPage.tsx`, `AuthCardEditorDrawer.tsx`, `RbacPolicyBuilder.tsx`, and `PersonalSettingsPage.tsx` cataloged.
- **Backend API Mapping:** 100% of controls mapped to their corresponding endpoints in `auth_cards.py`, `principals.py`, `rbac.py`, `auth_ldap.py`, `auth_oidc.py`, `auth_local.py`, `auth_mfa.py`, `auth_webauthn.py`, and `auth_identities.py`.
- **Dash Validation:** Verified with `python3 scripts/check_no_dashes.py --all docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md` (0 em/en-dashes).
- **Handoff Target:** Ready for handoff to Phase 2 (`KAN-407`) and Parent Epic (`KAN-405`).
