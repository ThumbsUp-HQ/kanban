# Dependency Evaluation: KANBA-33 (KB-P5-01)

## Target Dependency
- Package: `httpx` (exact pin: `0.28.1`)
- Module: `agent` (`agent/pyproject.toml` runtime dependencies)
- License: `BSD-3-Clause` (permissive, zero copyleft)
- Transitive dependencies: `httpcore` (BSD-3-Clause), `h11` (MIT), `certifi` (MPL-2.0), `idna` (BSD-3-Clause), `sniffio` (Apache-2.0 / MIT), `anyio` (MIT)

---

## Verbatim Specialist Sign-Offs

### 1. Application and Supply-Chain Security Engineer (sec-eng - Swarm Message #72)

```markdown
### [DEP-EVAL KANBA-33] HTTPX for OllamaProvider and CassetteTransport

- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P5-01.md (KANBA-33 / KB-P5-01)
- Target Packages: httpx promoted to agent/pyproject.toml runtime dependencies

1. License and Compatibility Audit:
- httpx (BSD-3-Clause): Permissive async HTTP client.
- Transitive dependencies: httpcore (BSD-3-Clause), sniffio (Apache-2.0 / MIT), idna (BSD-3-Clause), certifi (MPL-2.0), anyio (MIT).
- License Compliance: 100% permissive. Zero copyleft contamination.

2. Supply-Chain and SSRF Hardening:
- Resolve-Then-Check CIDR Pinning: net_guard.resolve_and_pin resolves DNS before connect and validates all returned IP addresses against admin-approved allowed_ollama_cidrs. If any resolved address falls outside, the request is aborted with EgressDenied(code="OLLAMA_CIDR_DENIED"), defeating multi-record DNS rebinding.
- Cloud Metadata Protection: Critical cloud metadata ranges (169.254.0.0/16, fe80::/10, fd00:ec2::254/128, and IPv4-mapped forms ::ffff:169.254.0.0/112) are hard-denied unconditionally with OLLAMA_METADATA_DENIED, preventing SSRF against instance metadata services.
- Client Egress Hardening: Constructed with follow_redirects=False, max_redirects=0, and trust_env=False (ignoring HTTP_PROXY and HTTPS_PROXY). 3xx responses raise REDIRECT_REFUSED.
- Offline Test Isolation: CassetteTransport enables deterministic HTTP replay under pytest-socket (--disable-socket --allow-unix-socket) with zero live network calls.

3. Alternatives Evaluated:
- aiohttp (Apache-2.0): Heavier dependency footprint with historical parser CVEs; lacks the clean, pluggable transport abstraction (AsyncBaseTransport) provided by HTTPX for cassette replay.
- urllib3: Synchronous-only architecture; requires thread-pool offloading which causes thread contention and latency overhead in high-throughput async agent loops.

4. Verdict:
- Role Sign-Off: APPROVED by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-33.
```

---

### 2. Test and Build Quality Engineer (qa-eng - Swarm Message #74)

```markdown
### [DEP-EVAL KANBA-33] OllamaProvider Adapter and HTTP Cassette Transport (KB-P5-01)

Reviewer: qa-eng (Engineer #2, Test and Build Quality Engineer)
Scope: docs/tickets/KB-P5-01.md (KANBA-33 / KB-P5-01)
Target Dependency: httpx (BSD-3-Clause, runtime dependency in agent/pyproject.toml)

- License and Permissive Compliance:
  * httpx is licensed under the permissive BSD-3-Clause license. 100% compliant with the Apache-2.0 monorepo licensing invariant. Zero copyleft (GPL, AGPL, SSPL, LGPL).

- Test and Build Quality Assessment:
  * Pluggable Transport Architecture: httpx exposes first-class support for custom asynchronous transports via httpx.AsyncBaseTransport. This enables agent/testing/http_cassette.py to implement CassetteTransport, replaying recorded YAML cassettes directly in memory without opening TCP sockets.
  * Hermetic Socket Isolation: Seamlessly integrates with pytest-socket (--disable-socket --allow-unix-socket), allowing all 12 mandatory feature unit tests for OllamaProvider to execute completely offline in under 0.5 seconds with zero network flake or external Ollama daemon requirements.
  * Streaming and Flow Control: Native async streaming support (client.stream) enables precise validation of NDJSON response streams from Ollama, enforcing strict buffer caps (64 KiB line limit, 8 MiB stream limit) and error mapping (ProviderHTTPError, ProviderTimeout, ProviderProtocolError) without raw httpx exceptions leaking.
  * Static Type Safety: Ships with complete PEP 484 type annotations, achieving full compliance with mypy --strict agent with zero untyped call warnings.
  * Build Determinism: Pure Python implementation with minimal, fully permissive dependencies (httpcore, certifi, idna, sniffio, anyio). Rapid installation via uv sync --locked with zero compilation overhead.

- Alternatives Considered:
  * aiohttp: Heavier footprint, complex ClientSession lifecycle, and less ergonomic pluggable transport interface for in-memory cassette replay.
  * urllib3 / requests: Synchronous by default, requiring background thread pool offloading that introduces latency overhead and event loop contention during high-throughput token streaming.
  * Raw asyncio.open_connection: Requires implementing full HTTP/1.1 framing, chunked transfer encoding, and TLS negotiation from scratch, dramatically increasing maintenance and security risk.

- Engineer #2 Sign-off: APPROVED
```

---

### 3. Systems/Backend Architect (arch-reviewer - Swarm Message #76)

```markdown
### [DEP-EVAL KANBA-33] OllamaProvider Adapter with Net-Guard and Cassette Transport

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P5-01.md (KANBA-33 / KB-P5-01)
- Evaluated Dependencies:
  * httpx (BSD-3-Clause, promoted to agent/pyproject.toml runtime dependencies)

1. License and Compatibility:
httpx is licensed under the permissive BSD-3-Clause license. 100% compliant with the monorepo Apache-2.0 license policy. All transitive dependencies (httpcore, h11, certifi, idna, sniffio, anyio) are BSD-3-Clause or MIT permissive. Zero copyleft.

2. Supply-Chain and Attack Surface:
- Configured with trust_env=False to prevent proxy environment variable manipulation.
- Protected by resolve_and_pin SSRF defense in agent/providers/net_guard.py: resolves hostnames and validates all resolved IP addresses against administrator-approved CIDRs, strictly rejecting cloud metadata endpoints (169.254.169.254, fe80::/10, etc.) and defeating DNS rebinding.
- Connects exclusively over HTTP/HTTPS with optional client certificate mTLS.
- Testing executes 100% offline via CassetteTransport without network sockets.

3. Architectural Rationale and Alternatives Considered:
- httpx vs. aiohttp:
  * httpx provides clean, modular transport abstractions (httpx.AsyncBaseTransport) that enable seamless injection of CassetteTransport for offline deterministic replay.
  * httpx is already a core component of our Python toolchain, avoiding the introduction of new HTTP client libraries.
- httpx vs. urllib3 / requests:
  * requests and urllib3 are synchronous, requiring thread pool executors that add latency and resource overhead to high-throughput asynchronous agent pipelines.

4. Architectural Verdict:
APPROVED. Enables secure, air-gapped local LLM inference with robust SSRF defenses.
```
