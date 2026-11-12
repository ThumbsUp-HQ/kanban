---
id: KB-P2-05b
title: "[Phase 2 / Auth] WebAuthn / Passkeys registration & assertion (userVerification=required) as AAL2 factor"
epic: KB-E2
depends_on: [KB-P2-05a]
spec_sections: ["4.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: ["webauthn (py_webauthn)"]
state: Backlog
---

> Split note: second half of manifest row `KB-P2-05`. See `KB-P2-05a`.

### User Story
As an **administrator**, I need **to register FIDO2 passkeys and use them to reach AAL2, with server-side single-use challenges, strict origin/RP ID binding, mandatory user verification, and sign-counter clone detection** so that **phishing proxies, replayed assertions, credentials registered to another account, and cloned authenticators cannot produce an AAL2 session**.

**Requirement Traceability:** `S4.2` item 3 (WebAuthn/Passkey `FIDO2`, `userVerification = "required"`), `S2.5` (`py_webauthn` `BSD-3`), requirement `#6` | **Dependencies:** `KB-P2-05a` (AAL2 elevation path, MFA verify rate limit, `require_aal2`)

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/<rev>_webauthn.py`, `database/models/auth.py` (add `WebauthnCredential`, `WebauthnChallenge`)
   - `kanban/auth/mfa/webauthn.py`
   - `kanban/api/v1/auth_webauthn.py`
   - `kanban/tests/helpers/soft_authenticator.py` (test-only ES256 software authenticator built with `cryptography`)
   - `pyproject.toml` of `kanban` (add pinned `webauthn`)
2. **DDL** (kb_auth boundary):
   - `webauthn_credentials(id UUID PK, principal_id UUID NOT NULL, credential_id BYTEA NOT NULL UNIQUE CHECK (octet_length(credential_id) BETWEEN 16 AND 1023), public_key BYTEA NOT NULL, sign_count BIGINT NOT NULL, aaguid UUID, transports TEXT[] NOT NULL DEFAULT '{}', nickname TEXT CHECK (char_length(nickname) <= 64), created_at, last_used_at)`; max `10` credentials per principal (enforced in function).
   - `webauthn_challenges(id UUID PK, session_id UUID NOT NULL, purpose TEXT CHECK (purpose IN ('register','authenticate')), challenge BYTEA NOT NULL CHECK (octet_length(challenge) = 32), expires_at TIMESTAMPTZ NOT NULL, consumed_at TIMESTAMPTZ)`.
3. **Configuration:** `KANBAN_WEBAUTHN_RP_ID` (registrable domain, required), `KANBAN_PUBLIC_ORIGIN` (exact `https://` origin; `http://localhost:8080` permitted only when `KANBAN_DEPLOYMENT_MODE=standalone`). Startup fails if RP ID is not a suffix of the origin host.
4. **Registration:** `POST /api/v1/auth/webauthn/register/options` (requires AAL2 session, or `mfa_pending` session of a principal with zero confirmed factors for first enrollment) -> `generate_registration_options(rp_id, rp_name="Kanban", user_id=principal_id.bytes, user_name, challenge=secrets.token_bytes(32), timeout=300000, attestation=NONE, authenticator_selection=AuthenticatorSelectionCriteria(user_verification=REQUIRED, resident_key=PREFERRED), exclude_credentials=<existing>, supported_pub_key_algs=[ES256, EdDSA, RS256])`. `POST .../register/verify` -> `verify_registration_response(expected_challenge, expected_origin, expected_rp_id, require_user_verification=True)`; challenge consumed atomically (single use, `TTL 300s`, bound to `session_id`).
5. **Assertion (AAL2 elevation):** `POST /api/v1/auth/webauthn/authenticate/options` (session `mfa_pending` or AAL1) -> `allow_credentials` restricted to the session principal's credentials, `user_verification=REQUIRED`. `POST .../authenticate/verify` -> `verify_authentication_response(..., require_user_verification=True, credential_current_sign_count=stored)`; the credential row must belong to the session principal; then `SessionService.elevate_aal(session, 2)`.
6. **Clone detection:** if `new_sign_count != 0 or stored != 0` and `new_sign_count <= stored` -> reject `401 MFA_INVALID`, mark credential `suspect_clone_at`, append activity `WEBAUTHN_SIGN_COUNT_REGRESSION`.
7. **Rate limit & errors:** both verify routes use `AUTH_MFA_VERIFY`; every verification failure -> `401 MFA_INVALID` (library exception text logged at `INFO` without client data, never returned).
8. **Deletion:** `DELETE /api/v1/auth/webauthn/credentials/{id}` requires `require_aal2(max_age_seconds=900)`; refuses to delete the principal's last AAL2 factor when the principal holds an admin role (`409 LAST_FACTOR`).
9. **Security invariants asserted:** (a) assertion valid only for exact origin + RP ID + fresh single-use challenge bound to the same session; (b) UV flag mandatory; (c) credential must belong to the authenticating principal; (d) sign-count regression blocks the credential.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/auth/test_webauthn.py`
- **Required Test Cases:**
  1. Positive: soft authenticator registers (ES256), then asserts -> `aal_level=2`, session id rotated.
  2. Security (phishing origin): clientDataJSON `origin=https://kanban.example.evil` -> `401 MFA_INVALID`.
  3. Security (RP ID hash): authenticatorData rpIdHash for `evil.example` -> `401`.
  4. Security (UV missing): flags with UP=1, UV=0 -> `401`.
  5. Security (challenge replay): verify same assertion twice -> second `401`; challenge older than 300s -> `401`; challenge issued to session A used in session B -> `401`.
  6. Security (credential substitution): principal B's valid credential used during principal A's assertion -> `401`.
  7. Security (clone): stored `sign_count=10`, assertion with `sign_count=10` and `9` -> `401`, credential flagged, activity row written; `0/0` authenticator accepted.
  8. Security (type confusion): clientDataJSON `type=webauthn.create` on authenticate -> `401`.
  9. Boundary: 11th credential registration -> `409 CREDENTIAL_LIMIT`; nickname 65 chars -> `422`.
  10. Deletion: last factor of admin -> `409 LAST_FACTOR`; with stale AAL2 (`901s`) -> `403 AAL2_STALE`.
  11. Config: RP ID `example.com` with origin `https://kanban.other.org` -> startup error; `http://` origin outside standalone -> startup error.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** files above exist and define `WebauthnCredential`, `WebauthnChallenge`, `WebauthnService.registration_options`, `WebauthnService.verify_registration`, `WebauthnService.authentication_options`, `WebauthnService.verify_authentication`, and the four `/api/v1/auth/webauthn/*` POST routes plus the DELETE route.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/auth/test_webauthn.py -q --cov=kanban/auth/mfa/webauthn.py --cov=kanban/api/v1/auth_webauthn.py --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 11 cases.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict kanban database && uv run lint-imports && uv run python scripts/license_gate.py` exits `0`.
- [ ] **Dependency pinned:** `uv.lock` contains `webauthn` with version and sha256 hashes.
- [ ] **Forensic Proof Packet Complete:** all files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/schema-dump.sql`
5. `docs/qa/<TICKET_ID>/contract-sample.json` - raw registration options (challenge visible), authentication options, verify success, `MFA_INVALID`.
6. `docs/qa/<TICKET_ID>/dependency-evaluation.md` - `webauthn` (`py_webauthn`, BSD-3): pinned version + hash, transitive deps (`cbor2`, `pyOpenSSL`/`cryptography`, `asn1crypto`) with licenses, alternatives considered (`fido2` from Yubico BSD-2), architect + engineer sign-off.
7. `docs/qa/<TICKET_ID>/api-specialist-review.md`
8. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - confirms options payload is consumable by `navigator.credentials.create/get` with base64url fields.
9. Screenshots: N/A - Non-UI Ticket.
