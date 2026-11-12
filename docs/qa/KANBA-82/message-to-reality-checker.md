# Reality-Checker Verification Packet: KANBA-82 (KB-P2-07)

## Ticket Overview
- **Ticket ID**: `KANBA-82`
- **Spec Section**: `KB-P2-07` (S4.2 item 2, S4.1, S3.1, S2.5, requirement #6)
- **Title**: `[Phase 2 / Auth] LDAPS / StartTLS card: TLS-hard before bind, CA PEM + SPKI SHA-256 pin, RFC 4515 escaping, ephemeral user bind & group DN sync`
- **Wave**: `W15`
- **Git Branch**: `feat/KANBA-82` in isolated worktree `/tmp/kb-wt-KANBA-82`

---

## Technical Actions & File Manifest

1. **Database Migration & Models**:
   - `database/migrations/versions/p2_07_ldap_group_mappings.py` (`down_revision = "p2_06_account_linking_recovery"`)
   - `database/migrations/sql/p2_07_ldap_group_mappings.up.sql`
   - `database/migrations/sql/p2_07_ldap_group_mappings.down.sql`
   - Table `ldap_group_mappings` created with `ENABLE` and `FORCE ROW LEVEL SECURITY` where `workspace_id = current_setting('app.workspace_id')::uuid` with index on `(card_id, normalized_dn)`.
   - ORM model `LdapGroupMapping` mapped in `database/models/auth.py` and exported in `database/models/__init__.py`. Table count in `database/tests/test_p1_17_models.py` updated to 43 tables (`len(orm_tables) == 43`). Migration test verified in `database/tests/migrations/test_p2_07_migration.py`.

2. **Core LDAP Implementation (`kanban/auth/ldap/`)**:
   - `config.py`: `LdapCardConfig` Pydantic model (`extra="forbid"`) enforcing `url` protocol validation, SSRF egress protection (`127.0.0.0/8`, `::1`, `169.254.0.0/16`, `fe80::/10` rejected unless private egress allowed), X.509 PEM bundle verification, and SPKI SHA-256 public key pin format validation.
   - `escape.py`: RFC 4515 filter escaping (`*`, `(`, `)`, `\`, `\x00` escaped to `\2a`, `\28`, `\29`, `\5c`, `\00`) and RFC 4514 DN parsing and normalization (`normalize_dn`, `escape_dn_value`, `unescape_dn_value`). Structural AST invariance check verifies that user filter substitution does not alter the operator count or tree depth.
   - `asn1_ber.py`: RFC 4511 BER streaming codec for LDAPv3 messages with strict streaming bounds (`MAX_BER_MESSAGE_SIZE = 262,144` bytes), rejection of indefinite length encodings, and support for `StartTLS` ExtendedRequest, `BindRequest`, `SearchRequest`, and `UnbindRequest`.
   - `client.py`: `LdapTlsHardClient` implementing the `TLS_HARD` invariant:
     * `ldaps`: Establishes TLS immediately on connect with TLS >= 1.2 and certificate verification.
     * `starttls`: Opens TCP, sends ONLY `ExtendedRequest(StartTLS)` as `messageID=1`, verifies `resultCode == 0`, upgrades transport via `loop.start_tls()` prior to constructing or dispatching any `BindRequest`.
     * SPKI Pinning: Extracts leaf certificate DER `SubjectPublicKeyInfo`, computes SHA-256 digest, and enforces match against configured `spki_sha256_pins` before bind.
   - `service.py`: `LdapAuthService.authenticate` executing service search, ephemeral user bind, mutable `bytearray` zeroization in `finally`, 120ms timing floor, uniform 401 `INVALID_CREDENTIALS` error mapping, and handoff to `IdentityResolver`.
   - `sync.py`: `sync_ldap_groups` reconciling directory group DNs into workspace groups (`principals(type='GROUP')` and `principal_group_edges`), automatically provisioning new edges, revoking removed card-managed group edges, and leaving local non-LDAP group memberships untouched.
   - `protocol.py` and `group_sync.py`: Interface re-exports.
   - `router.py` & `kanban/api/v1/auth_ldap.py`: HTTP routes `POST /api/v1/auth/ldap/{slug}/login` and alias `POST /api/v1/auth/cards/{slug}/ldap-login` with CSRF validation, rate limiting (`AUTH_LOGIN_IP`, `AUTH_LOGIN_ACCOUNT`), timing floor, and admin test endpoint `POST /api/v1/admin/auth-cards/{card_id}/ldap-test`.
   - `kanban/tests/fixtures/fake_ldap.py`: In-memory mock LDAPv3 server supporting LDAPS and StartTLS over Unix domain sockets.

3. **Mandatory Test Suite & Verification Proof**:
   - `kanban/tests/auth/test_ldap_escape.py`: 14/14 tests passing.
   - `kanban/tests/auth/test_ldap_tls_and_bind.py`: 19/19 tests passing (covers all 12 mandatory test cases from ticket spec).
   - `kanban/tests/auth/test_ldap_group_sync.py`: 4/4 tests passing.
   - `database/tests/migrations/test_p2_07_migration.py`: 1/1 migration test passing.
   - Total coverage: **96.03%** branch+line coverage across target modules (exceeds 95.0% threshold).

4. **Forensic Proof Manifest (`docs/qa/KANBA-82/`)**:
   - `git-diff.patch`: Complete git diff against base.
   - `unit-test-results.txt`: Full pytest execution log showing 38 passed in 7.65s with 96.03% coverage.
   - `build-check.txt`: Static analysis verification showing ruff clean, ruff format clean, mypy strict clean (280 source files), lint-imports clean (2 kept, 0 broken), license gate clean (`violations=0`), check_no_dashes clean, and zero hits for banned library `ldap3`.
   - `wire-tls-proof.txt`: Captured socket byte traces from test cases 2, 3, and 5 showing zero `0x60` BindRequest tags on unencrypted wire, zero cleartext passwords, and verified SPKI SHA-256 digest validation.
   - `contract-sample.json`: Wire exchanges for successful login (200), invalid credentials (401), rate limited (429), admin card test (200), and resolver assertion handoff.
   - `dependency-evaluation.md`: Pinned `pyasn1` evaluation (`BSD-2-Clause`), sha256 lockfile hashes, and justification for rejecting `ldap3` (`LGPL-3.0`) and `python-ldap` (native C).
   - `message-to-reality-checker.md`: This forensic manifest.
