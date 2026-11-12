# Reality-Checker Verification Packet: KANBA-82 (KB-P2-07)

## Ticket Overview
- **Ticket ID**: `KANBA-82`
- **Spec Section**: `KB-P2-07` (S4.2 item 2, S4.1, S3.1, S2.5, requirement #6)
- **Title**: `[Phase 2 / Auth] LDAPS / StartTLS card: TLS-hard before bind, CA PEM + SPKI SHA-256 pin, RFC 4515 escaping, ephemeral user bind & group DN sync`
- **Wave**: `W15`
- **Git Branch**: `feat/KANBA-82` in isolated worktree `/tmp/kb-wt-KANBA-82`

---

## Technical Actions & Specialist Review Resolution

### 1. Resolution of Specialist Review Feedback (B1 - B5)
- **B1 (CVE-2011-0411 Plaintext Injection & MessageID Validation)**:
  * Implemented pre- and post-upgrade buffer checks in `_connect_starttls` to reject injected frames before/after TLS upgrade with `LdapTlsError("STARTTLS_BUFFER_INJECTION")`.
  * Migrated transport upgrade to official Python 3.12 `await writer.start_tls(ssl_ctx, server_hostname=host)`.
  * Enforced strict response `messageID` validation across `StartTLS`, `bind()`, and `search()` operations, raising `LdapProtocolError` on mismatch.
  * Verified via dedicated test `test_b1_starttls_buffer_injection_and_msg_id`.
- **B2 (Hostile Wire Timeouts & Search Bounds)**:
  * Added `op_timeout` wrapping for `read_ber_packet`, `write/drain`, and TLS upgrade in `asyncio.timeout(DEFAULT_OP_TIMEOUT)`.
  * Added `DEFAULT_TOTAL_TIMEOUT` wrapping across the network phase of `LdapAuthService.authenticate()`, mapping timeouts uniformly to 401 `INVALID_CREDENTIALS`.
  * Enforced `size_limit` check during search streaming, raising `LdapSearchError("SIZE_LIMIT_EXCEEDED")` if the server returns more than requested entries.
  * Verified via dedicated test `test_b2_hostile_wire_timeouts_and_size_limit`.
- **B3 (Uniform 401 Failure & LdapProtocolError Hierarchy)**:
  * Made `LdapProtocolError` subclass `LdapError`.
  * Mapped all protocol errors, search failures, bind rejections, and timeouts in `service.authenticate()` to RFC 7807 401 `INVALID_CREDENTIALS` (`"Authentication Failed"` / `"Invalid credentials"`), preventing account enumeration or information leakage.
  * Verified via dedicated test `test_b3_uniform_failure_and_malformed_bind_response` and `test_ui_b2_byte_identical_401_responses`.
- **B4 (Admin Test Route Authorization & Error Sanitization)**:
  * Protected `POST /api/v1/admin/auth-cards/{card_id}/ldap-test` with `require_admin_aal2` dependency (verified with `assert_admin_routes_protected`).
  * Added 25ms timing floor `timing_floor(floor_ms=25.0)`.
  * Sanitized failure responses: returns allowlisted error codes (`TLS_HANDSHAKE_FAILED`, `SPKI_PIN_MISMATCH`, `BIND_FAILED`, `TIMEOUT`, `CONNECTION_FAILED`) without raw exception disclosure.
  * Implemented generic 404 `CARD_NOT_FOUND` with detail `"Authentication provider card not found"` without echoing `card_id` for missing and non-LDAP cards.
  * Verified via full authorization matrix test `test_admin_ldap_test_connection_endpoint` (401 anonymous, 403 member, 403 admin AAL1, 200 admin AAL2, 404 anti-enumeration).
- **B5 (Session Issuance & CSRF Protection)**:
  * Integrated with `SessionService.create_after_login()` to issue server-side session, returning `__Host-kb_session` and CSRF cookie headers on login success.
  * Added `retry_after_seconds` integer member and `Retry-After` HTTP header to 429 `RATE_LIMITED` responses in `kanban/api/problems.py`.
  * Enforced `extra="forbid"` on `LdapLoginRequest` and synchronized username trimming.
  * Verified via tests `test_b4_machine_readable_429`, `test_b5_session_issuance_and_csrf_cookie`, and `test_ui_b3_csrf_protection_with_csrf_middleware`.

---

## Mandatory Test Suite & Verification Proof

- `kanban/tests/auth/test_ldap_escape.py`: 14/14 tests passing.
- `kanban/tests/auth/test_ldap_tls_and_bind.py`: 26/26 tests passing.
- `kanban/tests/auth/test_ldap_group_sync.py`: 4/4 tests passing.
- `database/tests/migrations/test_p2_07_migration.py`: 1/1 migration test passing.
- Total suite: **45 passed in 9.84s** with **95.57%** branch+line coverage (exceeds 95.0% threshold). Zero warnings.

---

## Forensic Proof Manifest (`docs/qa/KANBA-82/`)

- `git-diff.patch`: Complete git diff against main.
- `unit-test-results.txt`: Full pytest execution log showing 45 passed with 95.57% coverage.
- `build-check.txt`: Static analysis verification showing ruff clean, ruff format clean, mypy strict clean (369 source files), lint-imports clean (2 kept, 0 broken), license gate clean (`violations=0`), and check_no_dashes clean.
- `wire-tls-proof.txt`: Captured socket byte traces from test cases showing zero `0x60` BindRequest tags on unencrypted wire, zero cleartext passwords, and verified SPKI SHA-256 digest validation.
- `contract-sample.json`: Faithful wire exchanges recorded from real test client runs for login success (200), invalid credentials (401), rate limited (429), admin test success (200), admin test not found (404), admin test connection failure (200), and CSRF validation failed (403).
- `dependency-evaluation.md`: Pinned `pyasn1` evaluation (`BSD-2-Clause`), sha256 lockfile hashes, and justification for rejecting `ldap3` (`LGPL-3.0`) and `python-ldap` (native C).
- `message-to-reality-checker.md`: This forensic manifest.
