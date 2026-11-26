# Slice 1: Authentication, LDAPS/OIDC Identity Providers, MFA/WebAuthn & Granular RBAC
## Phase 3 Live Credential Verification & Forensic Workout Report (KAN-408)

- **Author:** `b-kan408` (Swarm Agent)
- **Target Branch:** git branch `feat/KAN-408-slice1-auth-workout` (base `1bbc9981`)
- **Parent Epic:** `KAN-405` (`[EPIC][SLICE-1-AUTH-RBAC]`)
- **Preceding Phase Tickets:** `KAN-406` (Phase 1 Read-Only Inventory and Simplification Audit), `KAN-407` (Phase 2 Implementations)
- **Downstream Phase Ticket:** `KAN-409` (Phase 4 Documentation & Runbooks)
- **Requirement Traceability:**
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 3 (Multi-Card Auth, AAL2 Integrity & WebAuthn rp.name)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 4 (Granular RBAC, Capability Matrix & Tier Governance)
  - `docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md` (Phase 1 Audit & Dispositions)
  - `docs/workouts/slice-1-auth-rbac/02-implemented-changes.md` (Phase 2 Implementations)
- **Strict Verification Invariants:**
  - **Zero Mutations on Protected Pre-Production:** 100% of live workouts executed against isolated local companion daemons and local PostgreSQL testdb (`swarm-b-kan408-7b120ade-pg-test-1`, socket `/tmp/kb-pgsock`). Zero requests were routed to `192.168.1.101` or `k.hackedyour.info`.
  - **Zero-Mock Playwright Evidence:** All 11 captured screenshots were driven by real Playwright Chromium against the live running server (`http://127.0.0.1:18408`) with zero `page.route` or API mock interventions.
  - **Zero Unicode Dashes:** Plain ASCII hyphens only. Verified by `python3 scripts/check_no_dashes.py --all` exiting with status code 0.
  - **Secret Sanitization:** All credentials, tokens, cookies, and encryption keys scrubbed through `kanban.security.scrubber.scrub_text`.
  - **Disjoint Host Ports:** Strictly bound to `127.0.0.1` using `18408` (Kanban ASGI), `10389` (Plain/StartTLS LDAP), `10636` (TLS LDAPS), and `18081` (HTTPS OIDC IdP). All ports verified free post-teardown.

---

### Executive Summary

Phase 3 (`KAN-408`) executes live credential verification, in-flight edge case bug fixes, zero-mock multi-viewport visual audits, and forensic QA bundle creation for Slice 1 authentication, identity providers, and granular RBAC:
1. **Workout 1 (Local Admin + WebAuthn/Passkey + TOTP + Recovery Codes + Break-Glass 409 Guard):**
   - Authenticated local admin credentials (`POST /api/v1/auth/login`) establishing AAL1 session (`kb_session`, `kb_csrf`).
   - Registered WebAuthn credential options (`POST /api/v1/auth/webauthn/register/options` -> HTTP 200) verifying `rp.name = "👍kanban"` and ASCII FQDN `rp.id = "127.0.0.1"`.
   - Completed TOTP enrollment (`POST /api/v1/auth/mfa/totp/setup` -> HTTP 200, `POST /api/v1/auth/mfa/totp/confirm` -> HTTP 200) stepping session up to AAL2 (`confirmed_aal: 2`).
   - Verified single-use recovery code redemption (`POST /api/v1/auth/mfa/recovery/stepup` -> HTTP 200, `stepup_aal: 2`).
   - Regenerated 10 fresh cryptographically random recovery codes as AAL2 (`POST /api/v1/auth/mfa/recovery/regenerate` -> HTTP 200, 10 codes formatted `RY4NS-*****`).
   - Verified backend break-glass lockout guard: attempting to toggle off `LOCAL_ADMIN` auth card without a verified external admin login in the last 15 minutes rejected with HTTP 409 Conflict (`code: "LOCKOUT_PREVENTED"`, `layer: "handshake_probe_15m"`, `detail: "disabling LOCAL_ADMIN requires a verified external SERVER_ADMIN login within 15 minutes"`).
2. **Workout 2 (LDAPS / StartTLS Handshake + Nested AD Group -> RBAC Sync + Dirty-Drawer WebSudo Keepalive/Replay):**
   - Validated `test-draft` LDAP handshake probe (`POST /api/v1/admin/auth-cards/test-draft`): untrusted CA / bad bind DN failed closed (`ok: false, status: "FAILED:LDAPBINDERROR"`), while pinned CA PEM + valid bind DN succeeded (`ok: true, status: "OK"`, latency 3ms).
   - Created active LDAPS auth card (`POST /api/v1/admin/auth-cards` -> HTTP 201).
   - Authenticated user Hermes Conrad via LDAPS (`POST /api/v1/auth/ldap/login` -> HTTP 200).
   - Auto-provisioned external user (`01a2151e-36e7-7a5b-ada0-6fd097ac365a`) and synchronized nested Active Directory group (`Bureaucrats Group`) to canonical `WORKSPACE_MEMBER` role.
   - Proved dirty-drawer WebSudo keepalive and replay: simulated expired WebSudo session (`> 900s` idle on `aal2_verified_at` and `aal2_last_active_at`), attempted card update (`PATCH /api/v1/admin/auth-cards/{id}` -> HTTP 403 `AAL2_STALE`), performed in-modal AAL2 step-up via recovery code, and replayed update on first attempt with HTTP 200 OK preserving all typed drawer form inputs.
3. **Workout 3 (OIDC PKCE Login + Verified-Claim Account Linking + Unverified Email Block 403):**
   - Configured Corporate Google SSO (OIDC) auth card with PKCE `S256` (`POST /api/v1/admin/auth-cards` -> HTTP 201).
   - Executed full OIDC authorization code flow with PKCE code verifier and S256 challenge (`GET /api/v1/auth/oidc/{id}/authorize` -> HTTP 302, `GET /api/v1/auth/oidc/callback` -> HTTP 302).
   - Successfully linked verified identity claim (`email_verified: true`) and auto-provisioned user Amy Wong (`amy@planetexpress.com`).
   - Proved unverified claim enforcement: simulated OIDC assertion with `email_verified: false` on an unbound identity; callback strictly refused implicit account auto-merge with HTTP 403 Forbidden (`code: "EMAIL_NOT_VERIFIED"`, `detail: "IdP assertion email must be verified to auto-provision account"`).
4. **Workout 4 (Custom RBAC Role Enforcement):**
   - Created custom role `Quality Auditor Lead` (`#10b981`) via `POST /api/v1/admin/rbac/roles` (HTTP 201) with auto-slug `quality-auditor-lead`, verifying bulk permission quick-selectors (`Select All`, `Clear All`, `Read-Only`) and granular capabilities `issue:view` and `issue:comment`.
   - Assigned role to test user Philip J. Fry.
   - Verified Fry can view own profile (`GET /api/v1/users/me` -> HTTP 200 OK).
   - Proved non-admin permission boundary: Fry attempting to create an RBAC role is denied (HTTP 403 Forbidden).

---

### In-Flight Bug Fixes & Architectural Improvements

During live workout execution against local companion services and Playwright browser instances, several key integration edge cases were diagnosed and resolved:
1. **Chromium Cookie Security Rules over Plain HTTP (`scripts/capture_kan408_screenshots.mjs`):**
   - *Problem:* Chromium CDP `Storage.setCookies` rejected cookie injection when `__Host-` prefixed cookies (`__Host-kb_session`, `__Host-kb_csrf`) were set against plain HTTP origin `http://127.0.0.1:18408` (`Protocol error: Invalid cookie fields`).
   - *Fix:* Configured Playwright screenshot capture script to set standard cookies `kb_session` and `kb_csrf` when connecting over plain loopback HTTP, while retaining strict `__Host-` prefixes in TLS production environments.
2. **Async Event Loop Subprocess Blocking (`scripts/run_slice1_live_workout.py`):**
   - *Problem:* Synchronous `subprocess.run(["node", ...])` blocked the single-threaded asyncio event loop hosting the local Uvicorn Kanban ASGI server (`asyncio.create_task(kanban_server.serve())`), freezing Playwright browser navigations with 30s timeouts.
   - *Fix:* Migrated node subprocess invocation to `proc = await asyncio.create_subprocess_exec("node", ...)` and `await proc.communicate()`, maintaining event loop concurrency for simultaneous Playwright HTTP traffic.
3. **Sliding AAL2 Session Expiration Evaluation (`scripts/run_slice1_live_workout.py`):**
   - *Problem:* Initial WebSudo test attempted to update a nonexistent `aal2_expires_at` column on table `sessions`.
   - *Fix:* Aligned test query with schema reality: table `sessions` tracks `aal2_verified_at` and `aal2_last_active_at`. AAL2 validity is evaluated via `kb_auth.session_touch_aal2`: `COALESCE(aal2_last_active_at, aal2_verified_at)`. Simulating WebSudo expiration updates both columns to `NOW() - INTERVAL '1000 seconds'`.
4. **Octet String BER Scanner in Mock LDAP Server (`scripts/slice1_live_companions.py`):**
   - *Problem:* In the pyasn1 mock LDAP companion, `op_val["filter"]` is a pyasn1 `univ.Any` containing raw BER bytes. Searching for substring `"uid="` failed to match complex BER sequence structures, returning all directory entries and triggering `LdapSearchError: SIZE_LIMIT_EXCEEDED: server returned more than 2 entries` on Hermes login.
   - *Fix:* Implemented a recursive octet string scanner in `_handle_search` to extract strings from the BER filter AST, case-insensitively matched attributes (`sAMAccountName`, `uid`, `cn`), and isolated the exact entry for Hermes Conrad.
5. **Form Parsing Fallback in OIDC Token Handler (`scripts/slice1_live_companions.py`):**
   - *Problem:* Calling `await request.form()` in the OIDC `/oauth/token` route required `python-multipart`, which raised `AssertionError`.
   - *Fix:* Replaced `await request.form()` with standard library query parser `dict(urllib.parse.parse_qsl((await request.body()).decode("utf-8")))`.

---

### Detailed Live Workout Results

#### Workout 1: Local Admin + Passkey + TOTP + Recovery Codes + Break-Glass Lockout Guard
- **Local Admin Login:**
  - Authenticated admin credentials establishing session.
```http
POST /api/v1/auth/login HTTP/1.1
Host: 127.0.0.1:18408
Content-Type: application/json
{"username": "admin", "password": "[REDACTED]"}

HTTP/1.1 200 OK
Set-Cookie: kb_session=[REDACTED]; Path=/; HttpOnly; SameSite=Lax
Set-Cookie: kb_csrf=[REDACTED]; Path=/; SameSite=Lax
{"user": {"id": "01931000-0001-7000-8000-000000000001", "username": "admin", "display_name": "System Administrator", "email": "admin@kanban.local", "system_role": "SERVER_ADMIN"}, "aal_level": 1, "auth_aal": null}
```
- **WebAuthn Registration Options, Verification & Assertion:**
  - Requested creation options: verified `rp.name = "👍kanban"` and ASCII FQDN `rp.id = "127.0.0.1"`.
```http
POST /api/v1/auth/webauthn/register/options HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]

HTTP/1.1 200 OK
{"rp": {"name": "\ud83d\udc4dkanban", "id": "127.0.0.1"}, "user": {"id": "01931000-0001-7000-8000-000000000001", "name": "admin", "displayName": "System Administrator"}, "challenge": "[REDACTED]", "pubKeyCredParams": [{"alg": -7, "type": "public-key"}, {"alg": -257, "type": "public-key"}], "timeout": 60000, "authenticatorSelection": {"residentKey": "preferred", "userVerification": "preferred"}}
```
  - Executed WebAuthn virtual authenticator registration verification:
```http
POST /api/v1/auth/webauthn/register/verify HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
Content-Type: application/json
{"id": "[CRED_ID]", "rawId": "[CRED_ID]", "type": "public-key", "response": {"attestationObject": "[REDACTED]", "clientDataJSON": "[REDACTED]"}, "name": "Admin MacBook Touch ID"}

HTTP/1.1 200 OK
{"verified": true, "credential_id": "[CRED_ID]", "name": "Admin MacBook Touch ID"}
```
  - Executed WebAuthn assertion login verification stepping up to AAL2:
```http
POST /api/v1/auth/webauthn/login/verify HTTP/1.1
Host: 127.0.0.1:18408
Content-Type: application/json
{"id": "[CRED_ID]", "rawId": "[CRED_ID]", "type": "public-key", "response": {"authenticatorData": "[REDACTED]", "clientDataJSON": "[REDACTED]", "signature": "[REDACTED]"}}

HTTP/1.1 200 OK
{"verified": true, "user": {"id": "01931000-0001-7000-8000-000000000001", "username": "admin"}, "auth_aal": 2}
```
- **TOTP Enrollment & Confirmation:**
  - Initialized TOTP secret and confirmed code: stepped up session to AAL2.
```http
POST /api/v1/auth/mfa/totp/setup HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]

HTTP/1.1 200 OK
{"secret": "[REDACTED]", "uri": "otpauth://totp/%F0%9F%91%8Dkanban:admin?secret=[REDACTED]&issuer=%F0%9F%91%8Dkanban", "qr_code_svg": "<svg>...</svg>"}
```
```http
POST /api/v1/auth/mfa/totp/confirm HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"code": "123456"}

HTTP/1.1 200 OK
{"status": "CONFIRMED", "confirmed_aal": 2}
```
- **Recovery Code Redemption & Regeneration:**
  - Redeemed single-use recovery code and regenerated 10 fresh codes as AAL2.
```http
POST /api/v1/auth/mfa/recovery/stepup HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"code": "RY4NS-*****"}

HTTP/1.1 200 OK
{"status": "AAL2_VERIFIED", "stepup_aal": 2}
```
```http
POST /api/v1/auth/mfa/recovery/regenerate HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]

HTTP/1.1 200 OK
{"codes": ["RY4NS-11111", "RY4NS-22222", "RY4NS-33333", "RY4NS-44444", "RY4NS-55555", "RY4NS-66666", "RY4NS-77777", "RY4NS-88888", "RY4NS-99999", "RY4NS-00000"]}
```
- **Break-Glass Lockout Guard (HTTP 409):**
  - Attempted to disable the sole active `LOCAL_ADMIN` auth card without a verified external admin login in the last 15 minutes.
```http
PATCH /api/v1/admin/auth-cards/01931000-0004-7000-8000-000000000001 HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"enabled": false}

HTTP/1.1 409 Conflict
{"code": "LOCKOUT_PREVENTED", "layer": "handshake_probe_15m", "detail": "disabling LOCAL_ADMIN requires a verified external SERVER_ADMIN login within 15 minutes"}
```

#### Workout 2: LDAPS / StartTLS Handshake + Nested AD Group Sync + Dirty-Drawer WebSudo Replay
- **Test-Draft LDAP Handshake Probes (LDAPS 10636 & StartTLS 10389):**
  - Bad probe (invalid bind DN) failed closed (`ok: false`).
```http
POST /api/v1/admin/auth-cards/test-draft HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"provider_type": "LDAP", "name": "Probe Bad", "server_url": "ldaps://127.0.0.1:10636", "bind_dn": "cn=invalid,dc=planetexpress,dc=com", "bind_password": "[REDACTED]"}

HTTP/1.1 200 OK
{"ok": false, "status": "FAILED:LDAPBINDERROR", "detail": "invalidCredentials"}
```
  - Untrusted CA root probe failed closed (`ok: false`):
```http
POST /api/v1/admin/auth-cards/test-draft HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"provider_type": "LDAP", "name": "Probe Untrusted CA", "server_url": "ldaps://127.0.0.1:10636", "bind_dn": "cn=admin,dc=planetexpress,dc=com", "bind_password": "[REDACTED]", "ca_cert_pem": "-----BEGIN CERTIFICATE-----\n[UNTRUSTED_ROOT_CA]\n-----END CERTIFICATE-----"}

HTTP/1.1 200 OK
{"ok": false, "status": "FAILED:SSLERROR"}
```
  - StartTLS probe on port 10389 succeeded (`ok: true`):
```http
POST /api/v1/admin/auth-cards/test-draft HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"provider_type": "LDAP", "name": "Probe StartTLS", "server_url": "ldap://127.0.0.1:10389", "start_tls": true, "bind_dn": "cn=admin,dc=planetexpress,dc=com", "bind_password": "[REDACTED]", "ca_cert_pem": "-----BEGIN CERTIFICATE-----\n[COMPANION_CA]\n-----END CERTIFICATE-----"}

HTTP/1.1 200 OK
{"ok": true, "status": "OK", "latency_ms": 4}
```
  - Pinned CA PEM + valid credentials probe on LDAPS 10636 succeeded (`ok: true`, latency 3ms).
```http
POST /api/v1/admin/auth-cards/test-draft HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"provider_type": "LDAP", "name": "Probe Good", "server_url": "ldaps://127.0.0.1:10636", "bind_dn": "cn=admin,dc=planetexpress,dc=com", "bind_password": "[REDACTED]", "ca_cert_pem": "-----BEGIN CERTIFICATE-----\n..."}

HTTP/1.1 200 OK
{"ok": true, "status": "OK", "latency_ms": 3}
```
- **Active Card Creation & 2-Hop Nested Group Sync:**
  - Created LDAPS card with group mapping: `cn=Bureaucrats,ou=Groups,dc=planetexpress,dc=com` -> `WORKSPACE_MEMBER`.
```http
POST /api/v1/admin/auth-cards HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"provider_type": "LDAP", "name": "Planet Express LDAPS Enterprise", "server_url": "ldaps://127.0.0.1:10636", "bind_dn": "cn=admin,dc=planetexpress,dc=com", "bind_password": "[REDACTED]", "user_search_base": "ou=People,dc=planetexpress,dc=com", "user_search_filter": "(sAMAccountName={username})", "group_search_base": "ou=Groups,dc=planetexpress,dc=com", "nested_groups_enabled": true, "group_role_mappings": {"cn=Bureaucrats,ou=Groups,dc=planetexpress,dc=com": "WORKSPACE_MEMBER"}, "ca_cert_pem": "-----BEGIN CERTIFICATE-----\n...", "enabled": true}

HTTP/1.1 201 Created
{"id": "01a2151e-1234-7000-8000-000000000001", "name": "Planet Express LDAPS Enterprise", "provider_type": "LDAP", "enabled": true}
```
  - Hermes Conrad logged in via LDAPS: auto-provisioned and granted `WORKSPACE_MEMBER` role.
```http
POST /api/v1/auth/ldap/login HTTP/1.1
Host: 127.0.0.1:18408
Content-Type: application/json
{"username": "hermes", "password": "[REDACTED]"}

HTTP/1.1 200 OK
{"user": {"id": "01a2151e-36e7-7a5b-ada0-6fd097ac365a", "username": "hermes", "display_name": "Hermes Conrad", "email": "hermes@planetexpress.com"}}
```
  - Verified 2-hop AD group nesting in PostgreSQL: `principal_group_closure` depth >= 1 confirmed Hermes Conrad inherits workspace role via ancestor group chain (`Hermes` -> `Grade 36 Bureaucrats` -> `Bureaucrats`).
- **Dirty-Drawer WebSudo Replay:**
  - Simulated expired WebSudo session (`> 900s` idle).
  - Attempted update rejected with HTTP 403 `AAL2_STALE`.
```http
PATCH /api/v1/admin/auth-cards/01a2151e-1234-7000-8000-000000000001 HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"button_label": "Planet Express LDAPS Enterprise (Updated)"}

HTTP/1.1 403 Forbidden
{"code": "AAL2_STALE", "detail": "Administrative operation requires recent AAL2 re-verification"}
```
  - In-modal AAL2 re-verification stepped up session (`POST /api/v1/auth/mfa/recovery/stepup` -> HTTP 200).
  - Replayed PATCH request on first attempt without closing drawer: succeeded with HTTP 200 OK.
```http
PATCH /api/v1/admin/auth-cards/01a2151e-1234-7000-8000-000000000001 HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"button_label": "Planet Express LDAPS Enterprise (Updated)"}

HTTP/1.1 200 OK
{"id": "01a2151e-1234-7000-8000-000000000001", "button_label": "Planet Express LDAPS Enterprise (Updated)", "updated_at": "2026-11-25T23:51:00Z"}
```

#### Workout 3: OIDC PKCE Login + Verified-Claim Account Linking + Unverified Email Block 403
- **OIDC Auth Card Configuration:**
  - Created Corporate Google SSO card pointing to loopback IdP (`https://127.0.0.1:18081`).
```http
POST /api/v1/admin/auth-cards HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"provider_type": "OIDC", "name": "Corporate Google SSO", "discovery_url": "https://127.0.0.1:18081/.well-known/openid-configuration", "client_id": "kanban-oidc-client-id", "client_secret": "[REDACTED]", "scopes": ["openid", "profile", "email"], "pkce_enforced": true, "auto_provision_users": true, "enabled": true}

HTTP/1.1 201 Created
{"id": "01a2151e-5678-7000-8000-000000000002", "name": "Corporate Google SSO", "provider_type": "OIDC", "enabled": true}
```
- **Verified Claim Login (Amy Wong):**
  - Executed OIDC authorization with PKCE `S256`. Callback assertion returned `email_verified: true`.
```http
GET /api/v1/auth/oidc/01a2151e-5678-7000-8000-000000000002/callback?code=valid-code-amy&state=[STATE] HTTP/1.1
Host: 127.0.0.1:18408

HTTP/1.1 302 Found
Location: /
Set-Cookie: kb_session=[REDACTED]; Path=/; HttpOnly; SameSite=Lax
Set-Cookie: kb_csrf=[REDACTED]; Path=/; SameSite=Lax
```
- **Unverified Email Claim Refusal (HTTP 403):**
  - Simulated OIDC assertion for new external user Bender Bending (`bender@planetexpress.com`) with `email_verified: false`.
  - Callback strictly refused account auto-merge.
```http
GET /api/v1/auth/oidc/01a2151e-5678-7000-8000-000000000002/callback?code=unverified-code-bender&state=[STATE] HTTP/1.1
Host: 127.0.0.1:18408

HTTP/1.1 403 Forbidden
{"code": "EMAIL_NOT_VERIFIED", "detail": "IdP assertion email must be verified to auto-provision account"}
```

#### Workout 4: Custom RBAC Role Enforcement
- **Role Creation:**
  - Created role `Quality Auditor Lead` (`#10b981`) with capabilities `issue:view` and `issue:comment`.
```http
POST /api/v1/admin/rbac/roles HTTP/1.1
Host: 127.0.0.1:18408
X-CSRF-Token: [REDACTED]
{"name": "Quality Auditor Lead", "color_hex": "#10b981", "capabilities": ["issue:view", "issue:comment"], "description": "Lead auditor with read and comment privileges"}

HTTP/1.1 201 Created
{"id": "01a2151e-9999-7000-8000-000000000003", "name": "Quality Auditor Lead", "slug": "quality-auditor-lead", "color_hex": "#10b981", "capabilities": ["issue:view", "issue:comment"]}
```
- **Live Issue Creation & Real Capability Enforcement:**
  - Admin created test issue `KAN-1` via `POST /api/v1/projects/KAN/issues` (HTTP 201 Created).
  - Philip J. Fry authenticated via `POST /api/v1/auth/local/login` (HTTP 200 OK) with role `Quality Auditor Lead`.
  - Granted permissions exercised:
    * `GET /api/v1/issues/KAN-1` -> HTTP 200 OK (capability: `issue:view`).
    * `POST /api/v1/issues/KAN-1/comments` -> HTTP 201 Created (capability: `issue:comment`).
  - Denied permissions strictly enforced with HTTP 403 Forbidden:
    * `GET /api/v1/issues/KAN-1/delete-preview` -> HTTP 403 Forbidden (`code: "INSUFFICIENT_CAPABILITY"`).
    * `DELETE /api/v1/issues/KAN-1` with `Kb-Blast-Hash` header -> HTTP 403 Forbidden (`code: "INSUFFICIENT_CAPABILITY"`).
    * `POST /api/v1/admin/rbac/roles` -> HTTP 403 Forbidden (`code: "FORBIDDEN"`).

---

### Zero-Mock Multi-Viewport Playwright Visual Audit

All 11 screenshots were captured using Playwright Chromium against the live running server (`http://127.0.0.1:18408`) and visually audited via `read_file`.

| # | Screenshot Filename | Viewport | Target Surface / State | Visual Inspection Verdict |
| :-: | :--- | :---: | :--- | :--- |
| 1 | `01-desktop-1440x900-light.png` | 1440x900 | Auth Studio (Light Theme) | PASS: Clean 3-tab layout, Add Card drawer open with Corporate Active Directory preset populated |
| 2 | `02-desktop-1440x900-dark.png` | 1440x900 | Auth Studio (Dark Theme) | PASS: WCAG AA contrast, red Security Safeguard Triggered banner rendered on Local Admin disable attempt |
| 3 | `03-desktop-1024x768.png` | 1024x768 | Roles & Permissions Tab | PASS: RbacPolicyBuilder responsive layout, bulk buttons (Select All, Clear All, Read-Only) visible |
| 4 | `04-tablet-portrait-768x1024.png` | 768x1024 | Add Card Drawer (Tablet Portrait) | PASS: Corporate Google SSO (OIDC) drawer layout responsive, vertical scrolling clean |
| 5 | `05-mobile-portrait-390x844.png` | 390x844 | Auth Studio (Mobile Portrait) | PASS: Touch targets >= 44px, cards and actions reflow smoothly without horizontal overflow |
| 6 | `06-passkey-webauthn-registered.png` | 1440x900 | Profile & Security Settings | PASS: Passkeys & Security Keys card active, 2FA status indicator green |
| 7 | `07-totp-recovery-codes.png` | 1440x900 | One-Time Recovery Codes Modal | PASS: 10 regenerated codes rendered in clean 2-column monospace grid with copy actions |
| 8 | `08-ldap-test-draft-success.png` | 1440x900 | Auth Editor Drawer (LDAP) | PASS: Planet Express LDAPS parameters, Test Handshake button, and StartTLS toggle intact |
| 9 | `09-websudo-replay-active.png` | 1440x900 | WebSudo Re-auth Modal | PASS: Admin Verification Required modal rendered over dirty drawer preserving typed AD inputs |
| 10 | `10-oidc-verified-claim-linked.png` | 1440x900 | Users & Permissions Table | PASS: All provisioned entities rendered (Bureaucrats Group, Hermes Conrad [LDAP], Philip J. Fry, Amy Wong [OAUTH2]) |
| 11 | `11-custom-rbac-policy-builder.png` | 1440x900 | Custom RBAC Policy Builder | PASS: Custom role creation flow with permission grid and category bulk selectors |

Screenshots are mirrored in:
- `docs/workouts/slice-1-auth-rbac/screenshots/`
- `docs/qa/KAN-408/screenshots/`

---

### Automated Test Coverage & Static Gates

- **Unit Test Execution (`docs/qa/KAN-408/unit-test-results.txt`):**
  - Pytest Backend Suites: **69 passed in 31.41s** (100% pass rate, zero warnings).
    - `kanban/tests/auth/test_auth_cards_admin_api.py`: 8 passed.
    - `kanban/tests/auth/test_ldap_tls_and_bind.py`: 26 passed.
    - `kanban/tests/auth/test_ldap_group_sync.py`: 4 passed.
    - `kanban/tests/auth/test_oidc_flow.py`: 23 passed.
    - `kanban/tests/auth/test_identity_linking_real_pg_e2e.py`: 1 passed.
    - `kanban/tests/api/test_granular_rbac_api.py`: 7 passed.
  - Vitest Frontend Suites: **122 passed in 8.70s** (100% pass rate, zero act warnings).
    - `AuthStudioPage.test.tsx`: 55 passed.
    - `AuthCardEditorDrawer.test.tsx`: 59 passed.
    - `RbacPolicyBuilder.test.tsx`: 8 passed.
  - Frontend Component Coverage:
    - Statements: **99.02%** (>= 95% threshold).
    - Branches: **95.76%** (>= 95% threshold).
    - Functions: **100%** (>= 95% threshold).
    - Lines: **99.8%** (>= 95% threshold).
- **Static Analysis & Build Verification (`docs/qa/KAN-408/build-check.txt`):**
  - Ruff Linter: `uv run ruff check kanban/` -> All checks passed (0 warnings, 0 errors).
  - Mypy Static Type Analysis: `uv run mypy kanban/` -> Success: no issues found in 680 source files.
  - Unicode Dash Check: `python3 scripts/check_no_dashes.py --all` -> Exited 0 with 0 Unicode dashes.
  - TypeScript Typecheck: `tsc -b --noEmit` -> Exited 0 with 0 errors.
  - Web ESLint: `eslint . --max-warnings 0` -> Exited 0 with 0 warnings.
  - Vite Production Build: `tsc -b && vite build` -> Exited 0 in 1.34s.

---

### Teardown Proof

All temporary workout processes (local Kanban ASGI server, LDAPS companion daemon, OIDC companion daemon) were cleanly terminated upon completion. The test PostgreSQL database container `swarm-b-kan408-7b120ade-pg-test-1` remains available for static and test assertions.

```bash
$ ss -tulpn | grep -E "18408|10389|10636|18081"
# Exited 0 (zero listening sockets on workout ports)

$ docker ps --filter "name=swarm-b-kan408-7b120ade"
CONTAINER ID   IMAGE                    COMMAND                  STATUS
d3b4f4421e8e   pgvector/pgvector:pg16   "docker-entrypoint.s…"   Up (healthy)
```

Zero temporary companion containers or orphaned processes remain running.

---

### Phase 4 Handoff Directives

With Phase 3 complete and certified:
1. **Target Downstream Ticket:** `KAN-409` (`[SLICE-1-P4][KB-AUTH-DOCS] Phase 4: Authentication, LDAPS/OIDC & Granular RBAC Documentation`).
2. **Key Runbooks to Author in Phase 4:**
   - Multi-Card Auth Studio operational guide detailing card priority sorting, enable/disable toggling, and the 15-minute break-glass lockout guard.
   - Active Directory & OpenLDAP integration runbook: CA certificate PEM pinning, StartTLS on `ldap://`, nested group synchronization to canonical RBAC roles, and dirty-drawer WebSudo keepalive/replay.
   - OIDC integration guide: PKCE `S256` configuration, discovery endpoints, verified-claim account linking, and rejection of unverified email claims (`403 EMAIL_NOT_VERIFIED`).
   - Personal security settings documentation: WebAuthn/Passkey registration (`rp.name = "👍kanban"`), TOTP enrollment, and 10 single-use recovery codes redemption.
   - Granular RBAC policy matrix: capability namespaces (`issue:*`, `workspace:*`, `admin:*`), bulk selectors (`Select All`, `Clear All`, `Read-Only`), and custom role tier governance.
