# API Specialist Review: KAN-27 (KB-P3-AUDIT-21)

- Ticket: KAN-27
- Title: [KB-P3-AUDIT-21] Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan27-47504391`
- Branch: `feat/KAN-27`
- Commit: `4fd4c2039b6e1514c0f6914d5c6cc1ca4e64959d`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-27 on branch `feat/KAN-27` (commit `4fd4c203`). The ticket fixes backend external identity link initiation and browser-binding cookie forwarding in `IdentityLinkService.start_link` and `link_ldap`, eliminates unauthenticated link initiation query parameters from public auth routes, enforces conditional AAL2 step-up verification on `POST /api/v1/auth/identities/link/start`, ensures caller session preservation without unearned AAL2 privilege elevation in the OIDC callback, and wires provider connection controls in `PersonalSettingsPage`.

All API contracts, security invariants, session preservation behaviors, and test coverage requirements are verified and approved:
1. Exact route and schema alignment across `auth_identities.py`, `auth_oidc.py`, `auth_cards_public.py`, and `identity_service.py`.
2. Removal of unauthenticated `link_intent_id` query parameters across public endpoints (`GET /api/v1/auth/cards/{slug}/start`, `GET /api/v1/auth/oidc/{slug}/start`, and callback routes). Link initiation is strictly restricted to authenticated, CSRF-protected `POST /api/v1/auth/identities/link/start`.
3. In `oidc/flow.py`: `resolved_link_intent_id` is derived strictly from the cryptographically bound `auth_requests` row in PostgreSQL rather than user-supplied query parameters, preventing Login-CSRF and cross-session linking attacks.
4. Conditional AAL2 dependency `require_link_aal2`: Enforces fresh AAL2 (age <= 900s) when the user has enrolled MFA (`totp` or `webauthn`) or holds an administrative role, while cleanly allowing zero-factor standard AAL1 users to link identities on active sessions.
5. In `oidc/flow.py` callback: Preserves the existing caller session upon successful identity resolution without invoking `create_after_login(..., aal_level=2)`, preventing unearned privilege elevation. On error or conflict (e.g. `409 IDENTITY_ALREADY_LINKED`), redirects cleanly to `/settings/profile?link_error=<code>` and clears ephemeral browser-binding cookies.
6. `start_link` calls `get_oidc_flow(request)`, sets `return_to="/settings/profile"`, parses `authorize_url` from `headers["Location"]` (on `OidcStartResponse` `RedirectResponse`), and forwards all browser-binding `Set-Cookie` headers (`headers.getlist("set-cookie")` / fallback) onto the JSON response `raw_headers` returning `{ mode: "redirect", authorize_url }`.
7. High test coverage: 43 Pytest tests passing in 4.25s (`auth_identities.py` achieves 95% coverage), and 66 Vitest tests passing in `PersonalSettingsPage.test.tsx` (98.39% Stmts, 95.43% Branch, 99.00% Funcs, 100% Lines).
8. Static analysis: Clean across `ruff check`, `mypy` (1091 files), `lint-imports` (2 kept, 0 broken), `tsc -b`, `eslint`, and `check_no_dashes` (0 em/en-dashes).

---

## 2. Detailed Contract & Security Verification

### 2.1 Backend Link Initiation & Cookie Forwarding (`IdentityLinkService.start_link`)
- Backend Source: `kanban/auth/identity_service.py`
- In `start_link`:
  - Resolves OIDC flow via `get_oidc_flow(request)`.
  - Configures `return_to="/settings/profile"` so successful IdP redirection returns to the user profile settings page.
  - Correctly inspects `start_resp.headers["Location"]` (since `OidcStartResponse` is a `RedirectResponse` subclass) rather than expecting a non-existent `authorize_url` attribute.
  - Extracts all browser-binding `Set-Cookie` headers via `headers.getlist("set-cookie")` and returns them in `cookie_headers`.
- In `start_identity_link` (`kanban/api/v1/auth_identities.py`):
  - Appends each cookie header to `response.raw_headers` as `(b"set-cookie", ch.encode("latin-1"))`, ensuring the client browser receives necessary PKCE and state cookies.
  - Returns JSON payload `{ "mode": "redirect", "authorize_url": "..." }`.

### 2.2 Attack Surface Reduction & CSRF Binding
- Public Endpoints Hardened:
  - `GET /api/v1/auth/cards/{slug}/start`: `link_intent_id` parameter removed; passes `link_intent_id=None`.
  - `GET /api/v1/auth/oidc/{slug}/start`: `link_intent_id` parameter removed; passes `link_intent_id=None`.
  - `GET /api/v1/auth/oidc/{slug}/callback`: `link_intent_id` query parameter removed; passes `link_intent_id=None`.
- In `oidc/flow.py`:
  - `resolved_link_intent_id: uuid.UUID | None = row["link_intent_id"]`
  - Explicitly discards any runtime query parameter `link_intent_id` and binds resolution strictly to the sealed database record created by `IdentityLinkService.start_link`.
  - Prevents Login-CSRF injection attacks where an attacker tricks an authenticated user into linking the attacker's IdP account.

### 2.3 Conditional AAL2 Step-Up Policy (`require_link_aal2`)
- Dependency Source: `kanban/api/v1/auth_identities.py`
- Evaluation Logic:
  - Validates active session (`principal.session_id is not None`).
  - Evaluates user MFA enrollment status via `kb_auth.mfa_status` and role bindings for administrative privileges (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `PROJECT_ADMIN`).
  - If user has enrolled MFA (TOTP or WebAuthn) OR is an admin:
    * Enforces `principal.aal_level >= 2` (`ApiProblem(403, code="AAL2_REQUIRED")`).
    * Enforces freshness `age <= 900s` (`ApiProblem(403, code="AAL2_STALE")`).
  - If user is a standard zero-factor user:
    * Allows link initiation directly on the authenticated AAL1 session without deadlock.

### 2.4 Callback Session Preservation & Clean Redirection (`OidcFlow.callback`)
- Flow Source: `kanban/auth/oidc/flow.py`
- Resolution Logic:
  - When `resolved_link_intent_id is not None`:
    * Resolves identity via `self._identity_resolver.resolve(assertion, dummy_req, resolved_link_intent_id)`.
    * On successful resolution: Redirects to `/settings/profile?linked={slug}` with HTTP 302, clears browser-binding cookies, and preserves caller session cookies.
    * On `ProblemException` (e.g. duplicate identity conflict `409 IDENTITY_ALREADY_LINKED`): Redirects to `/settings/profile?link_error={err_code}` with HTTP 302, clears browser-binding cookies, and preserves session.
    * Guarantees zero unearned privilege escalation: Session AAL level is not updated or overwritten by the OIDC login flow.

### 2.5 LDAP Identity Linking (`IdentityLinkService.link_ldap`)
- Flow Source: `kanban/auth/identity_service.py`
- Resolves LDAP authentication service via `get_ldap_service(request)`.
- Invokes `ldap_auth_service.authenticate` with session, card, username, password, request, and `link_intent_id`.
- Returns `{ "status": "ok", "message": "Identity linked successfully", "linked": true }`.

---

## 3. Dependency, Layering & Static Quality Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy`: 0 errors across 1091 source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
  - `python3 -m scripts.check_no_dashes --all`: 0 errors (strict 0 em-dashes and en-dashes).
- Clean Patch Artifact: `docs/qa/KAN-27/git-diff.patch` verified to contain zero `docs/qa/*` files.

---

## 4. Test Coverage Audit

- Pytest Suite:
  - 43 passed in 4.25s across `kanban/tests/auth/`.
  - `kanban/api/v1/auth_identities.py`: 95% coverage (satisfies >= 95% mandate).
  - All modified logic in `identity_service.py` (`start_link`, `link_ldap`) and `oidc/flow.py` verified with targeted tests covering OIDC link start, cookie forwarding, callback session preservation, cross-account conflict 409, and unauthenticated start rejection.
- Vitest Suite:
  - 66 passed in `PersonalSettingsPage.test.tsx`.
  - Statement coverage: 98.39%, Branch coverage: 95.43%, Function coverage: 99.00%, Line coverage: 100%.
  - `cssTokensAudit.test.ts`: Passed 4/4 (100% canonical tokens).
- Verbatim raw test output is preserved in `docs/qa/KAN-27/unit-test-results.txt`.

---

## 5. Verification Verdict

All API contracts, authentication boundaries, CSRF mitigations, conditional AAL2 step-up protections, and session preservation behaviors are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
