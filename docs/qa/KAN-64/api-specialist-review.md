# API & Security Specialist Review: KAN-64 (`[KB-SEC-02]`)

- **Reviewer Persona:** `security-engineer` / `backend-architect` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-64` (`[KB-SEC-02] Enforce Cryptographic X.509 CA Chain + Challenge-Response PoP on Runner WebSocket, Block Slot Hijacking, & Fix Enrollment Config`)
- **Audited Commit (`HEAD`):** `9608688ec98aa2aa4a8f93a105ae330548d7c2a7` (`9608688e`)
- **Audited Branch:** `feat/KAN-64-runner-mtls-pop`
- **Reviewed Artifacts:**
  - `docs/qa/KAN-64/git-diff.patch`
  - `docs/qa/KAN-64/contract-sample.json`
  - `docs/qa/KAN-64/unit-test-results.txt`
  - `docs/qa/KAN-64/build-check.txt`
  - `docs/qa/KAN-64/message-to-reality-checker.md`
- **Reviewed Source & Test Files:**
  - `kanban/runners/pki.py`
  - `kanban/runners/hub.py`
  - `kanban/api/v1/remote_runners.py`
  - `agent/remote_runner/daemon.py`
  - `agent/remote_runner/cli.py`
  - `agent/remote_runner/config.py`
  - `kanban/tests/runners/test_remote_runners.py`
  - `kanban/tests/runners/test_pki_and_enrollment.py`
  - `kanban/tests/runners/test_wss_hub.py`
  - `agent/tests/remote_runner/test_config_and_enroll.py`
  - `agent/tests/remote_runner/test_daemon_e2e.py`
  - `agent/tests/test_remote_runner.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-64` delivers critical cryptographic hardening to the remote agent execution fleet, securing WebSocket control connections against rogue client certificates, man-in-the-middle impersonation, connection slot hijacking, and configuration tampering.

Key accomplishments:
1. **Cryptographic X.509 CA Chain & Constraint Validation:** `verify_runner_client_cert_chain` in `kanban/runners/pki.py` validates leaf certificate issuer signatures against the active or previous/grace Runner CA using `cryptography.x509`. It enforces strict leaf constraints: `BasicConstraints(ca=False)`, `ExtendedKeyUsage(CLIENT_AUTH)`, validity period bounds, Subject Common Name (`runner:<runner_id>` or `runner-<runner_id>`), and DER SHA-256 fingerprint verification.
2. **Pre-Registration Proof-of-Possession (PoP):** Prior to accepting WebSocket handshake registration, the server issues a `challenge_hello` containing a 32-byte random hex nonce. Within a strict 5.0s window, the runner must respond with a `challenge_response` containing a digital signature over `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_fingerprint_sha256}` produced by the leaf certificate's private key (supporting ECDSA, Ed25519, and RSA keys).
3. **Anti-Slot Hijacking Protection:** `RunnerHub.register_runner` verifies whether the runner ID already possesses an active connection with status `online`. Any subsequent connection attempt is rejected with `RunnerAlreadyConnectedError` and closed with WebSocket close code `4409` (`ALREADY_CONNECTED`), leaving the live active connection uninterrupted.
4. **Hardened Enrollment & TOML Configuration:** The runner enrollment CLI persists `ca.pem` with strict `0o600` file permissions and generates a standardized `runner.toml` (also `0o600`) containing `runner_id`, `server_url`, `cert_path`, `key_path`, `ca_cert_path`, and `allowed_repos`.
5. **Quality & Test Compliance:** 53 runner-specific unit/integration tests and 612 broader suite tests passed with zero failures. Static analysis (`make check`, `ruff`, `mypy`) and repository-wide dash checks passed with 0 errors.

---

## 2. Cryptographic & Protocol Architecture

### 2.1 X.509 Chain Verification (`kanban/runners/pki.py`)
`verify_runner_client_cert_chain` performs 6 distinct verification gates:
1. `leaf_cert.fingerprint(hashes.SHA256()) == expected_fingerprint_sha256` (rejects with `FINGERPRINT_MISMATCH`)
2. `Subject.CN in ("runner:<id>", "runner-<id>")` (rejects with `SUBJECT_MISMATCH`)
3. `BasicConstraints.ca is False` (rejects with `BASIC_CONSTRAINTS_INVALID` or `BASIC_CONSTRAINTS_MISSING`)
4. `ExtendedKeyUsage` contains `ExtendedKeyUsageOID.CLIENT_AUTH` (rejects with `EXTENDED_KEY_USAGE_INVALID` or `EXTENDED_KEY_USAGE_MISSING`)
5. Validity window `not_valid_before_utc <= now <= not_valid_after_utc` (rejects with `CERT_NOT_YET_VALID` or `CERT_EXPIRED`)
6. Issuer signature verification against active or previous CA public key via `leaf_cert.verify_directly_issued_by(ca_cert)` (rejects with `ISSUER_SIGNATURE_INVALID`)

### 2.2 Proof-of-Possession Challenge Flow (`kanban/api/v1/remote_runners.py`, `agent/remote_runner/daemon.py`)
- After certificate validation and WebSocket accept:
  - Server sends: `ChallengeHelloFrame(type="challenge_hello", nonce="<32-byte-hex>", runner_id="<uuid>")`
  - Strict 5.0s timeout enforced via `asyncio.timeout(5.0)`
  - Runner calculates expected canonical payload: `f"kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256.hex()}".encode("utf-8")`
  - Runner signs with private key; server verifies signature against `leaf_cert.public_key()` via `_verify_pop_signature`
  - Rejection produces immediate WebSocket closure with code `4401` (failed PoP) or `4408` (timeout)

### 2.3 Anti-Slot Hijacking (`kanban/runners/hub.py`)
- `RunnerHub.register_runner`:
  - Inspects `self._connections`
  - If `runner_id in self._connections` and `existing.status == "online"`: raises `RunnerAlreadyConnectedError("ALREADY_CONNECTED", ...)`
  - Endpoint catches exception and closes connection with code `4409` reason `"ALREADY_CONNECTED"`
  - Active runner session remains connected and serving jobs

### 2.4 Enrollment & Configuration (`agent/remote_runner/cli.py`, `agent/remote_runner/config.py`)
- `enroll_runner`:
  - Writes CA cert to `ca.pem` with `os.chmod(path, 0o600)`
  - Writes config to `runner.toml` with `os.chmod(path, 0o600)`
  - Retains backwards-compatible `ca.crt` (0o644) and `config.yaml`
  - `load_runner_config` parses `.toml` files natively using Python 3.11+ `tomllib`

---

## 3. Wire Contract & Exchange Verification

Audited `contract-sample.json` exchanges:
- `challenge_hello_frame`: Validated frame schema with 32-byte hex nonce and runner UUID.
- `challenge_response_frame`: Validated base64 signature response.
- `challenge_pop_payload_template`: Confirmed format `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_fingerprint_sha256}`.
- `anti_hijacking_rejection`: Verified close code `4409` (`ALREADY_CONNECTED`).
- `runner_toml_sample` & `file_permission_invariants`: Verified `0o600` file permission requirements.

---

## 4. Test Verification & Code Coverage

- **Pytest Results:**
  - `kanban/tests/runners/test_pki_and_enrollment.py`: 8 passed
  - `kanban/tests/runners/test_remote_runners.py`: 8 passed
  - `kanban/tests/runners/test_wss_hub.py`: 10 passed
  - `agent/tests/remote_runner/test_config_and_enroll.py`: 10 passed
  - `agent/tests/remote_runner/test_daemon_e2e.py`: 8 passed
  - `agent/tests/remote_runner/test_executor.py`: 5 passed
  - `agent/tests/test_remote_runner.py`: 4 passed
  - Total: 53 passed in 6.44s (full runner test suite)
- **Static Analysis & Dash Verification:**
  - `make check`: 0 errors
  - `ruff check`: 0 errors
  - `ruff format --check`: 0 errors
  - `mypy`: 0 errors
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (zero em/en-dashes)

---

## 5. Review Sign-Off

All cryptographic chain verification, challenge-response PoP, anti-hijacking, and enrollment invariants for `KAN-64` are approved.

**STATUS: APPROVED**
