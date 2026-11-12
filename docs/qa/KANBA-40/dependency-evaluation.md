# Dependency Evaluation: KANBA-40 (KB-P5-03)

## Target Dependency
- Package: `openai` (exact pin: `3.49.0`)
- Module: `agent` (`agent/pyproject.toml` runtime dependencies)
- License: `Apache-2.0` (permissive, zero copyleft)
- Cryptographic hashes (`uv.lock`):
  - Wheel: `sha256:3977754792115027ba80ae16996ba3366478b5b228e1ab58e2660bd7ac8c3d78`
  - Sdist: `sha256:44badf2bea9bcd643dafa0bc4d5a109a14395889219fd68b8560322288196e96`
- Transitive dependencies and licenses:
  - `anyio` (MIT)
  - `httpx2` (BSD-3-Clause)
  - `jiter` (MIT)
  - `pydantic` (MIT)
  - `sniffio` (Apache-2.0 / MIT)
  - `typing-extensions` (PSF-2.0)
- License Audit Result: 100% permissive. Zero copyleft contamination (`scripts/license_gate.py` passed with 0 violations).

---

## Architectural Rationale and Alternatives Considered

1. **Official `openai` SDK vs. Raw HTTPX REST Client:**
   - Feasible, but `openai` provides standard SSE streaming chunk parsers, structured output schemas, and tool-calling models natively under Apache-2.0 with minimal overhead.
   - Using the official SDK avoids bespoke SSE parsers while retaining full control over the underlying HTTP transport via `http_client=httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False, max_retries=0)`.

2. **Official `openai` SDK vs. LiteLLM Client:**
   - LiteLLM introduces heavy proxy dependencies, rapid release cycles with breaking changes, and redundant multi-provider translation layers.
   - Direct `AsyncOpenAI` provides cleaner security auditing, lower attack surface, and focused compatibility with standard OpenAI and OpenAI-compatible API servers (e.g. vLLM, Azure, LiteLLM).

---

## Verbatim Specialist Sign-Offs

### 1. Application and Supply-Chain Security Engineer (sec-eng - Swarm Message #72)

```markdown
### [DEP-EVAL KANBA-40] OpenAIProvider Adapter (openai)

- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P5-03.md (KANBA-40 / KB-P5-03)
- Target Packages: openai (pinned in agent/pyproject.toml and uv.lock)

1. License and Compatibility Audit:
- openai (Apache-2.0): Permissive official client library.
- License Compliance: 100% Apache-2.0 compliant. Zero copyleft contamination.

2. Supply-Chain and Data Privacy Hardening:
- Mandatory Zero Data Retention (store=False): All outbound chat completion requests enforce store=False via an unbypassable internal _chat_kwargs() builder, preventing server-side logging and training ingestion by OpenAI.
- Base URL Validation: Custom base URLs are validated to prevent SSRF: cleartext http:// is rejected unless targeting loopback addresses (127.0.0.1, ::1 for local vLLM instances), and userinfo (user:pass@host) is strictly rejected.
- Deterministic Failover: Client is initialized with max_retries=0, ensuring that timeout and retry behaviors are handled deterministically by the platform agent router rather than uncontrolled SDK retry loops.
- Credential Protection: API keys are encapsulated in SecretStr, preventing leakage into log streams or error traces.
- Offline Test Isolation: Accepts custom httpx.AsyncClient with CassetteTransport, enabling 100% offline unit testing with pytest-socket.

3. Alternatives Evaluated:
- Raw REST via httpx: Feasible, but openai provides standard SSE streaming chunk parsers, structured output schemas, and tool-calling models natively under Apache-2.0 with minimal overhead.
- LiteLLM client: Introduces heavy proxy dependencies, rapid release cycles with breaking changes, and redundant middleware layers. Direct AsyncOpenAI provides cleaner security auditing.

4. Verdict:
- Role Sign-Off: APPROVED by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-40.
```

---

### 2. Systems/Backend Architect (arch-reviewer - Swarm Message #76)

```markdown
### [DEP-EVAL KANBA-40] OpenAIProvider Adapter (openai)

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P5-03.md (KANBA-40 / KB-P5-03)
- Evaluated Dependencies:
  * openai (Apache-2.0, exact pin in agent/pyproject.toml)

1. License and Compatibility:
openai is licensed under the permissive Apache-2.0 license. 100% compliant with the monorepo Apache-2.0 license policy. Zero copyleft.

2. Supply-Chain and Attack Surface:
- Scoped to agent/ module for OpenAI and compatible inference endpoints (vLLM, LiteLLM, Azure OpenAI).
- Mandatory zero data retention: outbound request builder strictly injects "store": false on all chat completion requests.
- Endpoint validation: base URLs must use HTTPS, allowing HTTP only for local loopback addresses (127.0.0.1, ::1).
- Client is configured with trust_env=False and follow_redirects=False to prevent proxy interception and redirect abuse.
- Supports custom http_client injection with CassetteTransport for offline testing.

3. Architectural Rationale and Alternatives Considered:
- openai SDK vs. custom raw REST implementation:
  * The official openai SDK is Apache-2.0 licensed, built on httpx, and provides typed streaming event parsing and native Pydantic structured output mapping (response_format with strict schema validation).
  * Using the official SDK avoids bespoke SSE parsers while retaining full control over the underlying HTTP transport.
- openai SDK vs. LiteLLM client:
  * LiteLLM carries a large dependency footprint and dynamic translation layers. The official openai SDK is lightweight, focused, and directly compatible with standard OpenAI-compatible API servers.

4. Architectural Verdict:
APPROVED. High-precision LLM provider adapter with guaranteed zero data retention.
```

---

### 3. Test and Build Quality Engineer (qa-eng - Swarm Message #115)

```markdown
### [DEP-EVAL KANBA-40] OpenAIProvider Adapter with AsyncOpenAI SDK (KB-P5-03)

- Target Dependencies:
  * openai (Apache-2.0, runtime dependency in agent/pyproject.toml)

- Test and Build Quality Assessment:
  * Async Client and Pluggable Transport: Standard AsyncOpenAI client configured with custom http_client=httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False, max_retries=0). Seamlessly integrates with CassetteTransport for deterministic offline cassette replay under pytest-socket.
  * Zero Prompt Retention Guarantee: Outbound request builder strictly enforces "store": false on all chat completion requests, verified on the wire by automated unit tests.
  * Strict Structured Outputs: Enforces JSON Schema structured output contracts (response_format with strict: True and additionalProperties: false), paired with local Pydantic re-validation.
  * Endpoint Security: Rejects non-HTTPS remote base URLs; permits HTTP only for local loopback addresses (127.0.0.1, ::1) when targeting self-hosted inference servers (vLLM, LiteLLM). Rejects redirects (3xx) with ProviderProtocolError(REDIRECT_REFUSED).

- Alternatives Considered:
  * Raw HTTPX Client without SDK: Requires bespoke implementation of SSE streaming parsers, chunk formatting, and typed API exceptions. The official openai SDK is Apache-2.0 licensed, fast, and pure Python.
  * litellm: Heavy transitive dependency graph with dynamic multi-provider translation layers; unnecessary for direct OpenAI and OpenAI-compatible endpoint integration.

- Engineer #2 Sign-off: APPROVED
```
