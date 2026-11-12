# Reality-Checker Verification Packet: KANBA-64 (KB-P2-02)

## Ticket Metadata
- Ticket ID: `KANBA-64`
- Spec Key: `KB-P2-02`
- Title: `[Phase 2 / Auth] Server-side sessions, HMAC-signed __Host- cookies, rotation, timeouts & CSRF`
- Epic: `KB-E2` (Phase 2 Kanban API & Core Platform Services)
- Spec Sections: `4` (multi-card auth sessions, AAL levels used by S4.2 item 3), `3.3` (`app.aal_level` binding), Requirement `#6`
- Dependencies: `KB-P2-01` (`PrincipalResolver`, `derive_subkey`, problem model), `KB-P2-03` (`kb_auth` schema and `kb_auth_owner` role)
- Gates: `reality-checker` (Passive Forensic Mode), `api-specialist`, `ui-specialist`

---

## User Story
As a **security engineer**, I need **opaque server-side sessions referenced by HMAC-signed `__Host-` cookies, rotated on every login and AAL change, expired by idle and absolute timeouts, and protected by session-bound double-submit CSRF on every unsafe method** so that **session fixation, cookie forgery, cookie tossing from sibling subdomains, stolen-cookie longevity, and cross-site request forgery are each blocked at a single choke point**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `database/models/auth.py` (`UserSession`), `database/migrations/versions/p2_02_sessions.py`, `database/migrations/sql/p2_02_sessions.{up,down}.sql`, `kanban/auth/sessions/__init__.py`, `kanban/auth/sessions/service.py`, `kanban/auth/sessions/cookies.py`, `kanban/auth/sessions/csrf.py`, `kanban/auth/sessions/resolver.py`, `kanban/api/v1/auth_session.py` exist and define `UserSession`, `SessionPolicy`, `SessionService.create_after_login`, `SessionService.elevate_aal`, `SessionService.logout`, `SessionCookieResolver`, `CsrfMiddleware`, `CSRF_EXEMPT_PATHS`, `require_full_session`, and the five `kb_auth.session_*` functions.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/auth/test_sessions.py kanban/tests/auth/test_cookies.py kanban/tests/auth/test_csrf.py database/tests/test_sessions_boundary.py database/tests/migrations/test_p2_02_migration.py -q --cov=kanban.auth.sessions --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 12 cases (28 passed in 1.15s, 97.95% branch+line coverage).
- [x] **Migration Reversible:** `test_21_sessions_migration_lifecycle` executes upgrade to `p2_02_sessions`, downgrade to `p2_03_auth_provider_cards`, and re-upgrade to head verifying clean schema creation, teardown, and restoration.
- [x] **Build / Type / Lint Clean:** `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict kanban database && uv run lint-imports && python3 -m scripts.check_no_dashes --all` exits `0`.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-64/`.

---

## Mandatory Feature Unit Tests Matrix (12/12 Covered)

| Case | Category | Test Target | Verification Description |
| :--- | :--- | :--- | :--- |
| **Case 1** | Positive Login & Cookies | `kanban/tests/auth/test_sessions.py::test_case_1_positive_login_and_cookie_attributes` | `create_after_login` sets `__Host-kb_session` with exact attributes (`Path=/`, `HttpOnly`, `Secure`, `SameSite=Lax`, no `Domain`); `GET /api/v1/auth/session` returns principal ID, workspace ID, AAL, and CSRF token. |
| **Case 2** | Security (Fixation) | `kanban/tests/auth/test_sessions.py::test_case_2_session_fixation_defense` | Attacker pre-login cookie C0 presented during login is explicitly revoked in DB; fresh cookie C1 issued; subsequent requests with C0 yield 401 `AUTHENTICATION_REQUIRED`. |
| **Case 3** | Security (Forgery) | `kanban/tests/auth/test_cookies.py::test_case_3_security_cookie_forgery_denied` | Cookie with valid token but forged HMAC signature, truncated signature, or flipped bit yields 401; DB session repository is never invoked. |
| **Case 4** | Security (Cookie Tossing) | `kanban/tests/auth/test_cookies.py::test_case_4_cookie_tossing_and_name_confusion` | Requests carrying `kb_session=...` or `__Secure-kb_session=...` without `__Host-` prefix are unauthenticated; duplicate `__Host-kb_session` headers fail closed. |
| **Case 5** | Security (AAL Rotation) | `kanban/tests/auth/test_sessions.py::test_case_5_rotation_on_aal_elevation` | `elevate_aal` revokes old session, creates new session with `rotated_from_id` pointing to old session, preserves original `absolute_expires_at`, and sets `aal2_verified_at`. |
| **Case 6** | Boundary (Timeouts) | `kanban/tests/auth/test_sessions.py::test_case_6_idle_and_absolute_timeouts` | Advance fake clock: request at `idle - 1s` succeeds; request at `idle + 1s` returns 401. Request with continuous activity at `absolute + 1s` returns 401. |
| **Case 7** | Boundary (Throttling) | `database/tests/test_sessions_boundary.py::test_case_7_last_seen_at_throttling_single_update` | Rapid sequential `session_resolve` calls within 30s trigger exactly one DB update to `last_seen_at` via 60s throttle condition. |
| **Case 8** | Security (CSRF) | `kanban/tests/auth/test_csrf.py::test_case_8_security_csrf_protections` | POST with valid session but missing `X-CSRF-Token` -> 403 `CSRF_REJECTED`; token from session A with session B -> 403; cross-site `Sec-Fetch-Site` -> 403; invalid `Origin` -> 403; valid token + same origin -> 200. |
| **Case 9** | Security (Logout) | `kanban/tests/auth/test_sessions.py::test_case_9_security_logout` | After `POST /api/v1/auth/logout`, old cookie resolves to 401; response emits `Set-Cookie` clearing both `__Host-kb_session` and `__Host-kb_csrf` with `Max-Age=0`. |
| **Case 10** | Security (MFA Pending) | `kanban/tests/auth/test_sessions.py::test_case_10_mfa_pending_enforcement` | Session with `mfa_pending=True` yields 403 `MFA_REQUIRED` on protected routes; succeeds with 200 on routes marked `allow_mfa_pending=True`. |
| **Case 11** | DB Boundary & Oversize | `database/tests/test_sessions_boundary.py::test_case_11_db_boundary_privilege_denials_and_no_hash_exposure`, `kanban/tests/auth/test_cookies.py::test_case_11_oversize_cookie_rejected_before_db` | As `kanban_app`, `SELECT * FROM sessions` fails with `42501` (permission denied); zero `kb_auth` functions return `token_sha256`; cookies > 128 characters rejected before DB lookup. |
| **Case 12** | Config Validation | `kanban/tests/auth/test_sessions.py::test_case_12_config_timeout_bounds_validation` | `SessionPolicy` rejects idle/absolute/aal2 timeout configurations outside `[300, 2592000]` with `ValueError` on startup. |

---

## Technical Architecture & Security Invariants

### 1. Database Storage & Function Boundary (`kb_auth` Schema)
- Table `public.sessions` is owned by `kb_auth_owner`, has `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`, and permissions are revoked from `PUBLIC, kanban_app, app_rls_reader`.
- Five `SECURITY DEFINER` functions in `kb_auth` manage sessions:
  * `kb_auth.session_create`: Inserts session with `token_sha256`.
  * `kb_auth.session_resolve`: Resolves active session, throttles `last_seen_at` updates to once per 60s, checks idle and absolute expiration.
  * `kb_auth.session_revoke`: Revokes session by setting `revoked_at = clock_timestamp()`.
  * `kb_auth.session_rotate`: Atomically revokes old session, inserts new session with `rotated_from_id`, and retains `absolute_expires_at`.
  * `kb_auth.session_revoke_all_for_principal`: Mass revocation on credential change or security alert.
- Zero functions expose `token_sha256`. DB compromise leaks only SHA-256 hashes, not plaintext tokens or signed cookies.

### 2. Cookie Hardening & Cryptographic Signatures
- Cookie name `__Host-kb_session` enforces browser-level host prefix requirements:
  * Must be delivered with `Secure; Path=/; SameSite=Lax`.
  * Must NOT include a `Domain` attribute (defends against cookie tossing from sibling subdomains).
- Format: `base64url(token32) + "." + base64url(HMAC-SHA256(subkey, token32))`
- Subkey derived via `derive_subkey(session_hmac_key, "session/cookie")`.
- Verification order: Check length <= 128 chars -> verify HMAC signature with constant-time `hmac.compare_digest` -> hash token with SHA-256 -> call DB `session_resolve`. Invalid or forged cookies never reach the database.

### 3. Session-Bound Double-Submit CSRF
- Token format: `base64url(nonce16) + "." + base64url(HMAC-SHA256(subkey, session_id.bytes + nonce16))`
- Subkey derived via `derive_subkey(session_hmac_key, "session/csrf")`.
- Delivered via non-HttpOnly cookie `__Host-kb_csrf` (allowing SPA JavaScript to read and attach to requests) and in `GET /api/v1/auth/session` response body.
- Unsafe HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) on `/api/*` require header `X-CSRF-Token` matching the cookie and cryptographic validation against the active `session_id`.
- Pre-session CSRF token issuance uses `PRE_SESSION_ID = uuid.UUID(int=0)`.
- Defense-in-depth checks:
  * `Sec-Fetch-Site`: Rejects values not in `("same-origin", "none")`.
  * `Origin`: Verifies origin matches configured `KANBAN_PUBLIC_ORIGIN` or request host.
