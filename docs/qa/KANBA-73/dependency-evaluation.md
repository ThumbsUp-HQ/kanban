# Dependency Evaluation: `joserfc` and `httpx` (Wave W14, KB-P2-06)

- Date: 2026-11-12
- Ticket: KANBA-73 (KB-P2-06: `[Phase 2 / Auth] OIDC / OAuth2 card: Auth Code + PKCE S256, single-use state/nonce, iss/aud/azp pinning, JWKS caching & private_key_jwt`)
- Evaluator: `sec-eng` (Application & Supply-Chain Security Engineer)

---

## 1. Package: `joserfc==1.8.0`

### Cryptographic Lockfile Pinning
- Pinned Version: `1.8.0`
- License: `BSD-3-Clause` (permissive, fully compatible with Apache-2.0)
- Repository: `https://github.com/lepture/joserfc`
- PyPI URL: `https://pypi.org/project/joserfc/1.8.0/`
- Wheel SHA-256: `176b836ac7ed9a46a88629e24076314b475f33a75d0bad7f26146e572eed7c79`
- sdist SHA-256: `cbf03cb2c6db8cc5289f1ef8718842e53dba244b4c0de5fefa0c0eaee4bde8db`

### Transitive Closure Analysis
`joserfc==1.8.0` declares exactly one dependency:
- `cryptography>=42.0.0` (locked in workspace at `cryptography==50.0.2`, Apache-2.0 / BSD-3-Clause)
Zero additional transitive runtime packages are introduced into the environment.

### Security Invariants & Behavioral Verification
- Telemetry & Network Egress: Verified zero network calls, analytics, or phone-home telemetry.
- Alg Confusion Immunity: Rejects `alg=none` and symmetric HMAC algs (`HS256`, `HS384`, `HS512`) during asymmetric key verification.
- Header Reference Defense: External header references (`jku`, `x5u`, `jwk`) are strictly ignored and never resolved via remote HTTP requests.
- Private Key Member Filtering: JWKS import enforces absence of private RSA/EC exponents (`d`, `p`, `q`, `dp`, `dq`, `qi`).

### Alternatives Considered
- `python-jose`: Strictly banned by Section 2.5 of the architecture specification and repository rules due to unmaintained upstream, security CVE history, and lack of modern JOSE specification support.
- `Authlib`: Authored by the same maintainer (Hsiaoming Yang), but includes a massive monolithic OAuth 1.0/2.0 server framework that introduces substantial unnecessary attack surface.
- `PyJWT`: Widely used, but lacks native RFC 7517 KeySet serialization and fine-grained RFC 7523 asymmetric client assertion generation.

---

## 2. Package: `httpx==0.28.1`

### Cryptographic Lockfile Pinning
- Pinned Version: `0.28.1`
- License: `BSD-3-Clause` (permissive, fully compatible with Apache-2.0)
- Repository: `https://github.com/encode/httpx`
- PyPI URL: `https://pypi.org/project/httpx/0.28.1/`
- sdist SHA-256: `75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc`

### Transitive Closure Analysis
- `anyio` (MIT)
- `certifi` (MPL-2.0)
- `httpcore` (BSD-3-Clause)
- `idna` (BSD-3-Clause)
All four dependencies are already locked and utilized across the workspace.

### Security Invariants & Behavioral Verification
- Egress Control: `httpx.AsyncClient` instances in `kanban.auth.oidc` enforce `follow_redirects=False`, strict timeouts (5.0s default), and maximum response payload bounds (256 KiB discovery, 64 KiB token exchange).
- SSRF Defense: Destination URLs are validated prior to connection against loopback (`127.0.0.0/8`, `::1`), link-local / cloud metadata (`169.254.0.0/16`, `fe80::/10`), and non-HTTPS schemes.

### Alternatives Considered
- `urllib.request`: Lacks native async I/O and modern connection pooling.
- `aiohttp`: Larger dependency footprint with complex C extensions and divergent API semantics compared to standard workspace tooling.

---

## 3. Engineering & Security Verdict
- Both dependencies comply with Apache-2.0 license compatibility mandates.
- License gate (`scripts/license_gate.py`) reports `violations=0`.
- All lockfile entries are pinned cryptographically with SHA-256 digests in `uv.lock`.
- Signed off by Application & Supply-Chain Security Engineer (`sec-eng`).
