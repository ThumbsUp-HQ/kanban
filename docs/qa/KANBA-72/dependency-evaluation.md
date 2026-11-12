# Dependency Evaluation: argon2-cffi (KANBA-72 / KB-P2-04)

## Evaluated Packages

### 1. argon2-cffi (Runtime Dependency)
- **Package**: `argon2-cffi`
- **Version**: `25.1.0` (pinned in `kanban/pyproject.toml` and `uv.lock`)
- **License**: `MIT` (100% Permissive, Apache-2.0 compatible)
- **Cryptographic Hashes (uv.lock)**:
  - Wheel: `sha256:fdc8b074db390fccb6eb4a3604ae7231f219aa669a2652e0f20e16ba513d5741`
  - Sdist: `sha256:694ae5cc8a42f4c4e2bf2ca0e64e51e23a040c6a517a85074683d3959e1346c1`
- **Transitive Dependencies**:
  - `argon2-cffi-bindings`: `26.1.0` (`MIT`, wheel/sdist locked with cryptographic SHA-256)
- **Purpose**: Implements RFC 9106 Argon2id password hashing with memory hardness (`m = 65536` KiB, `t = 3`, `p = 4`, `hash_len = 32`, `salt_len = 16`) for break-glass Local Admin accounts.

---

## Architectural Rationale & Threat Modeling

1. **Memory-Hard Defense-in-Depth**:
   - Argon2id is the winner of the Password Hashing Competition (PHC) and the modern industry standard for password storage.
   - Tuned with `m = 64 MiB`, `t = 3`, `p = 4` to impose overwhelming memory cost on ASIC and GPU offline cracking rigs if a database dump is exfiltrated.
2. **Pre-Hash HMAC-SHA256 Pepper**:
   - Passwords undergo NFKC normalization, length validation (8..1024 bytes), and HMAC-SHA256 pepper application (`KB_AUTH_PEPPER`) before Argon2id processing.
   - Stored hashes cannot be cracked offline even with full access to the database dump unless the separate root pepper secret is also compromised.
3. **Concurrency & Resource Bounding**:
   - Memory consumption is strictly bounded to `4 x 64 MiB = 256 MiB` maximum via `asyncio.Semaphore(default 4)` with a 2.0s acquire timeout.
   - Saturated worker capacity fails closed with RFC 7807 `503 AUTH_BUSY` (`Retry-After: 2`) preventing memory-exhaustion denial-of-service attacks.
4. **Parameter Migration & Rehash**:
   - Exposes `needs_rehash(stored_hash)` to detect legacy or lower-cost hashes (e.g. `t = 2`) and atomically upgrades them to `t = 3` upon successful authentication.

---

## Alternatives Considered and Rejected

1. **Standard Library `hashlib.scrypt`**:
   - *Rejected*: While memory-hard, scrypt lacks PHC string representation formatting, requires custom serialization wrappers, and does not provide built-in parameter rehash detection (`needs_rehash`). Argon2id is specifically designed to resist both side-channel and GPU cracking.
2. **`passlib`**:
   - *Rejected*: Abandoned and unmaintained upstream; suffers from unpatched vulnerabilities and deprecation incompatibilities with modern Python 3.12+ and bcrypt/argon2 runtimes.
3. **`bcrypt`**:
   - *Rejected*: Restricted to 72 bytes maximum input length (causing truncation bugs or requiring custom pre-hash workarounds), lacks memory-hardness parameter tuning, and is susceptible to high-throughput FPGA/ASIC acceleration compared to Argon2id.

---

## Specialist Reviews and Approvals

Pre-approved under the Swarm Board Dependency Evaluation Batch for Waves W10-W17:

1. **Systems/Backend Architect (`@arch-reviewer`, Swarm Message #116)**:
   > "Implements RFC 9106 Argon2id, the PHC winner and industry benchmark for password hashing. Provides tunable memory hardness (64 MiB RAM, 3 iterations, 4 parallelism) to defeat GPU/ASIC brute-force attacks. Operates with server-side HMAC-SHA256 pepper for defense-in-depth. Rejected bcrypt (legacy, restricted to 72 bytes, GPU vulnerable) and passlib (unmaintained, abandoned). Verdict: APPROVED."

2. **Application & Supply-Chain Security Engineer (`@sec-eng`, Swarm Message #118)**:
   > "Target: argon2-cffi (MIT). License: MIT (Permissive, 100% Apache-2.0 compliant). Security Analysis: Memory-hard Argon2id (m=64MB, t=3, p=4) defeats GPU/ASIC cracking arrays. Combined with HMAC-SHA256 pepper (KB_AUTH_PEPPER), an exfiltrated database dump cannot be cracked offline without the separate root pepper key. Bounded hashing concurrency (semaphore limit) prevents memory DoS attacks. Verdict: APPROVED."

3. **Test & Build Quality Engineer (`@qa-eng`, Swarm Message #120)**:
   > "Target: argon2-cffi (MIT). License: MIT Permissive. Fully compatible with Apache-2.0 distribution. Cryptographic hashes locked in uv.lock. Fully testable using deterministic unit tests and timing benchmarks. Verdict: APPROVED."
