# Reality Checker Verification Packet: KAN-64

## Ticket Summary
- **Ticket ID:** KAN-64
- **Title:** [KB-SEC-02] Enforce Cryptographic X.509 CA Chain + Challenge-Response PoP on Runner WebSocket, Block Slot Hijacking, & Fix Enrollment Config
- **Branch:** `main` (merged from `feat/KAN-64-runner-mtls-pop`)
- **Merged `main` Commit SHA:** `4780e67294defaa9e7e82087fb175defba650aab` (`4780e672`, merging `9608688ec98aa2aa4a8f93a105ae330548d7c2a7`)
- **Browser Screenshots:** `N/A - Non-UI Runner mTLS PKI & WebSocket PoP Security Ticket`
- **Component Scope:** `kanban/runners/pki.py`, `kanban/runners/hub.py`, `kanban/api/v1/remote_runners.py`, `agent/remote_runner/daemon.py`, `agent/remote_runner/cli.py`, `agent/remote_runner/config.py`
- **Test Scope:** `kanban/tests/runners/test_remote_runners.py`, `agent/tests/test_remote_runner.py`

---

## Action Implementations

### Action 1: Cryptographic X.509 CA Chain and Leaf Constraint Verification
- **Module:** `kanban/runners/pki.py`
- **Function:** `verify_runner_client_cert_chain(leaf_pem_or_der, *, active_ca_cert_pem, previous_ca_cert_pem=None, expected_runner_id, expected_fingerprint_sha256, now=None) -> x509.Certificate`
- **Verifications Enforced:**
  1. **SHA-256 Fingerprint Match:** Validates leaf certificate DER SHA-256 fingerprint against expected fingerprint (`FINGERPRINT_MISMATCH`).
  2. **Subject CN Matching:** Enforces Subject Common Name equals `runner:<runner_id>` or `runner-<runner_id>` (`SUBJECT_MISMATCH`).
  3. **BasicConstraints:** Enforces `ca=False` (`BASIC_CONSTRAINTS_INVALID` / `BASIC_CONSTRAINTS_MISSING`).
  4. **ExtendedKeyUsage:** Enforces `ExtendedKeyUsageOID.CLIENT_AUTH` (`EXTENDED_KEY_USAGE_INVALID` / `EXTENDED_KEY_USAGE_MISSING`).
  5. **Validity Window:** Enforces `not_valid_before_utc <= now <= not_valid_after_utc` (`CERT_NOT_YET_VALID` / `CERT_EXPIRED`).
  6. **Cryptographic Issuer Signature:** Verifies leaf signature against active CA or grace/previous CA public key (`verify_directly_issued_by`). Supports ECDSA, Ed25519, and RSA keys.

### Action 2: Challenge-Response Proof-of-Possession on WebSocket
- **Modules:** `kanban/runners/hub.py`, `kanban/api/v1/remote_runners.py`, `agent/remote_runner/daemon.py`
- **WebSocket Flow:**
  1. Server validates mTLS client certificate CA chain before WebSocket acceptance.
  2. Server sends `ChallengeHelloFrame(type="challenge_hello", nonce="<32-byte-hex>", runner_id="<uuid>")`.
  3. Server awaits `ChallengeResponseFrame(type="challenge_response", signature_b64="...")` with strict 5.0s timeout (`asyncio.timeout(5.0)`).
  4. Server verifies signature over payload `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_fingerprint_sha256}` using leaf public key.
  5. Daemon automatically signs PoP challenges using leaf private key (`_sign_challenge`) supporting ECDSA, Ed25519, and RSA keys.

### Action 3: Block Slot Hijacking
- **Modules:** `kanban/runners/hub.py`, `kanban/api/v1/remote_runners.py`
- **Mechanism:**
  1. `RunnerHub.register_runner()` inspects `self._connections`. If an active runner exists with status `online`, registration is rejected with `RunnerAlreadyConnectedError("ALREADY_CONNECTED", ...)`.
  2. WebSocket endpoint terminates duplicate incoming connection immediately with close code `4409` (`ALREADY_CONNECTED`).
  3. Live active connection remains uninterrupted.

### Action 4: Enrollment ca.pem Permissions and runner.toml Configuration
- **Modules:** `agent/remote_runner/cli.py`, `agent/remote_runner/config.py`
- **Mechanism:**
  1. `enroll_runner` writes `ca.pem` with strict `0o600` permissions.
  2. `enroll_runner` writes `runner.toml` with strict `0o600` permissions containing: `runner_id`, `server_url`, `cert_path`, `key_path`, `ca_cert_path`, and `allowed_repos`.
  3. Backwards compatibility maintained: writes `ca.crt` (0o644) and `config.yaml`.
  4. `load_runner_config` parses `.toml` files natively using Python's `tomllib`.
  5. `RunnerConfig` supports bidirectional field mapping between `cert_path` / `client_cert_path` and `key_path` / `client_key_path`.

---

## Verification Evidence
- **Unit & Integration Tests:** 53 passed in 6.44s (`docs/qa/KAN-64/unit-test-results.txt`)
- **Code Coverage:** 91% total across touched modules (cli: 96%, config: 96%, hub: 94%, pki: 89%, daemon: 86%)
- **Static Analysis & Linting:** 0 errors on `ruff check`, `ruff format --check`, and `mypy` (`docs/qa/KAN-64/build-check.txt`)
- **No-Dashes Invariant:** `python -m scripts.check_no_dashes --all` passed with 0 errors
- **Contract Sample:** Verified in `docs/qa/KAN-64/contract-sample.json`
