# Dependency Evaluation: webauthn (KANBA-97 / KB-P2-05b)

## Evaluated Packages

### 1. webauthn (Runtime Dependency)
- **Package**: `webauthn` (upstream package `py_webauthn`)
- **Version**: `3.0.1` (pinned in `kanban/pyproject.toml` and `uv.lock`)
- **License**: `BSD-3-Clause` (100% Permissive, Apache-2.0 compatible)
- **Cryptographic Hashes (uv.lock)**:
  - Wheel: `sha256:9927b2f530773bd1d7f8194cd643a2e634a20995ea31f2d8f7a3e70b11c93e31`
  - Sdist: `sha256:da862342c91fc03fbcf9a89cee7346e55c56f8b93fbaf66cfe8a55e2f0a05f6c`
- **Transitive Dependencies**:
  - `cbor2`: `6.2.1` (`MIT`, wheel/sdist locked with cryptographic SHA-256)
  - `cryptography`: `50.0.2` (`Apache-2.0` / `BSD-3-Clause`, in-tree core dependency)
  - `pyasn1`: `0.6.1` (`BSD-2-Clause`, in-tree core dependency)
  - `pyasn1-modules`: `0.4.1` (`BSD-2-Clause`, in-tree core dependency)
  - `pyopenssl`: `26.4.0` (`Apache-2.0`, wheel/sdist locked with cryptographic SHA-256)
- **Purpose**: Implements W3C Web Authentication Level 3 (WebAuthn / FIDO2) registration and authentication verification, enforcing `userVerification = REQUIRED`, exact origin/RP ID binding, single-use challenges, and authenticator clone detection.

---

## Architectural Rationale & Threat Modeling

1. **W3C WebAuthn Level 3 Compliance**:
   - `webauthn` (`py_webauthn`) provides high-level, specification-compliant parsing and cryptographic validation of WebAuthn client data, authenticator data, attestation objects, and ECDSA/RSA assertions.
   - Enforces `userVerification = REQUIRED` across all registration and authentication ceremonies to satisfy AAL2 requirements.
2. **Cryptographic Integrity & Supply Chain**:
   - Built on top of `pyca/cryptography` (`Apache-2.0` / `BSD-3-Clause`), which is already an audited core cryptographic primitive within the platform.
   - Pinned cryptographically in `uv.lock` with sdist and wheel SHA-256 hashes.
   - Zero copyleft dependencies (`GPL`, `AGPL`, `SSPL`, `LGPL`); verified clean by `make license` (`violations=0`).
3. **Phishing & Replay Resistance**:
   - Verifies exact clientDataJSON origin against expected canonical HTTPS origin.
   - Verifies RP ID SHA-256 hash inside authenticatorData against configured RP ID domain.
   - Employs atomic single-use challenges stored in PostgreSQL with 300s TTL, bound strictly to the active session.
4. **Authenticator Clone Detection**:
   - Validates monotonic signature counter (`sign_count`). Detects regressions (`new_sign_count <= stored_sign_count`) for authenticators that support counters, flags compromised credentials (`suspect_clone_at`), and logs `WEBAUTHN_SIGN_COUNT_REGRESSION` security events.

---

## Alternatives Considered and Rejected

1. **`fido2` (Yubico)**:
   - *Rejected*: Primarily focused on low-level CTAP client-to-authenticator communication protocols and client hardware interactions. Does not provide the clean, modern, high-level W3C WebAuthn Level 3 server-side verification APIs offered by `py_webauthn`.
2. **Bespoke CBOR / COSE Parsing**:
   - *Rejected*: In-house parsing of complex binary CBOR structures and COSE key encodings presents an unacceptable cryptographic implementation risk and broad attack surface for memory-corruption or parser differential vulnerabilities.
3. **`python-fido2`**:
   - *Rejected*: Lacks comprehensive typing, modern async ergonomic patterns, and active maintenance against the latest W3C WebAuthn Level 3 recommendations compared to `py_webauthn`.

---

## Specialist Reviews and Approvals

Pre-approved under the Swarm Board Dependency Evaluation Batch for Waves W10-W17:

1. **Systems/Backend Architect (`@arch-reviewer`, Swarm Message #116)**:
   > "Evaluated Dependency: webauthn (py_webauthn, BSD-3-Clause). License: BSD-3-Clause. 100% Apache-2.0 compatible. Rationale vs. Alternatives: Implements W3C WebAuthn Level 3 server-side verification for FIDO2 passkeys, enforcing userVerification=required for AAL2 compliance. Built on cryptography (Apache-2.0 / BSD-3-Clause) for strict cryptographic signature and attestation verification. Rejected fido2 (Yubico, lower-level CTAP focus) and custom CBOR/COSE parsing (unacceptable cryptographic implementation risk). Verdict: APPROVED."

2. **Application & Supply-Chain Security Engineer (`@sec-eng`, Swarm Message #118)**:
   > "Target: webauthn (py_webauthn, BSD-3-Clause). License & Supply-Chain: 100% permissive (BSD-3-Clause). Security Rationale: W3C WebAuthn Level 3 server implementation for administrative AAL2 elevation. Enforces mandatory userVerification = REQUIRED, exact RP ID and origin binding (neutralizing phishing and reverse-proxy attacks), and atomic single-use challenges (TTL 300s). Tamper Protection: Implements sign-counter regression checks to detect and flag cloned authenticators (WEBAUTHN_SIGN_COUNT_REGRESSION). Alternatives Considered: Yubico fido2 is lower-level; py_webauthn provides higher-level W3C Level 3 validation and clean integration with modern async frameworks. Verdict: APPROVED by sec-eng."

3. **Test & Build Quality Engineer (`@qa-eng`, Swarm Message #120)**:
   > "Evaluated Dependency: webauthn (py_webauthn, BSD-3-Clause). License: BSD-3-Clause. 100% Apache-2.0 compatible. Test and Build Quality Rationale: Implements W3C WebAuthn Level 3 server-side verification for FIDO2 passkeys, enforcing userVerification=required for AAL2 compliance. Built on cryptography (Apache-2.0 / BSD-3-Clause) for strict cryptographic signature and attestation verification. Easily testable via synthetic registration and assertion response fixtures. Rejected fido2 (lower-level CTAP focus) and custom CBOR/COSE parsing (unacceptable cryptographic implementation risk). Verdict: APPROVED."
