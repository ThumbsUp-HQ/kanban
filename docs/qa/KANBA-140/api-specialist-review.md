# API Specialist Gate Review: KANBA-140 (KB-P4-16) - Headless CLI Device Approval (RFC 8628)

- Ticket: KANBA-140 (KB-P4-16)
- Title: Headless CLI Device Approval (RFC 8628) + Scopable MCP Keys & Connected Apps Studio UI
- Status: APPROVED
- Reviewer: arch-reviewer (Swarm Architectural & API Specialist Gate)

---

## 1. Architectural & Security Verification

1. **RFC 8628 Device Authorization Grant Lifecycle (Spec S11.1)**:
   - Validated `kanban.oauth.device.initiate_device_authorization()` and `kanban.api.v1.oauth.oauth_device_authorize()`.
   - The device authorization endpoint issues an ephemeral `device_code` (stored as SHA-256 hash only) and an 8-character `user_code` separated into two 4-character chunks (`XXXX-XXXX`).
   - Token polling endpoint `/oauth/token` conforms strictly to RFC 8628 Section 3.5:
     * Returns HTTP 400 `authorization_pending` while the request awaits user action.
     * Returns HTTP 400 `slow_down` when polling occurs faster than the negotiated `interval` (5s), automatically incrementing the required interval by 5 seconds.
     * Returns HTTP 400 `expired_token` when the 600-second TTL expires.
     * Returns HTTP 400 `access_denied` when the user rejects the device code.
     * Issues an ES256 JWT access token and refresh token once approved.

2. **Base-20 Consonant Alphabet & Anti-Phishing (Spec S11.1)**:
   - The `user_code` alphabet is strictly constrained to the 20 consonants `BCDFGHJKLMNPQRSTVWXZ` (excluding vowels `A, E, I, O, U` and ambiguous `Y` to eliminate offensive word generation and phonetic/visual confusion).
   - Normalization logic converts input to uppercase, strips whitespace and hyphens, and validates string length and character set bounds before querying storage.

3. **Brute-Force & Rate-Limiting Defenses (Spec S11.1, S6.1)**:
   - Evaluated sliding-window brute-force protections for `user_code` lookup and activation.
   - Verification attempts exceeding 5 invalid attempts within a 60-second window are blocked with HTTP 429 `rate_limit_exceeded`, neutralizing automated enumeration attacks against the 20^8 (25.6 billion) code space.

4. **Step-Up AAL2 Gate Enforcement for High-Privilege Scopes (Spec S11.1, S3.1)**:
   - When the requested `resource` matches administrative surfaces (`/mcp/admin`), activation requires the approving session to be authenticated at `AAL2` (WebAuthn/Passkey or TOTP).
   - AAL1 sessions are rejected with a structured step-up challenge requiring secondary factor verification before the grant can be confirmed.

5. **Storage, Schema & Row-Level Security (Spec S11.1, S1.1)**:
   - Schema `database/migrations/versions/p4_16_oauth_device_codes.py` creates table `oauth_device_codes` with indices on `device_code_sha256` and `user_code`.
   - Raw plaintext device codes are never stored in the database.
   - RLS policies ensure device records are managed exclusively through authenticated backend application roles with strict isolation.

---

## 2. Test Coverage & Quality Verification

- Unit & integration tests: 12/12 passing in 4.28s across `kanban/tests/oauth/test_device_flow.py`, `database/tests/migrations/test_p4_16_migration.py`, and `database/tests/test_p1_17_models.py`.
- Line and branch coverage: 95.0% coverage on `kanban.oauth.device` (meeting the >= 95% threshold).
- Static analysis: Ruff clean, Mypy strict clean (550 source files).
- Typography: Zero Unicode dashes (`check_no_dashes.py --all` clean).

---

## 3. Verdict

APPROVED. The backend implementation delivers complete RFC 8628 device flow compliance, robust cryptographic protection, strict rate limiting, and zero-leakage token handling.
