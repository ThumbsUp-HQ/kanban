# Dependency Evaluation: KANBA-19 (KB-P0-12)

## 1. Evaluated Dependencies and Cryptographic Hashes

| Package | Version | License | Target Scope | First SHA-256 (from `uv.lock`) |
| :--- | :--- | :--- | :--- | :--- |
| `pydantic` | `2.14.3` | `MIT` | Runtime (`agent/pyproject.toml`) | `1054f237f4d4733e5a30e1e2333bd33a2004ab9ab1510bd053a9a31bb48e232d` |
| `pyyaml` | `6.0.3` | `MIT` | Runtime (`agent/pyproject.toml`) | `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` |
| `jsonschema` | `4.26.0` | `MIT` | Runtime (`agent/pyproject.toml`) | `0c26707e2efad8aa1bfc5b7ce170f3fccc2e4918ff85989ba9ffa9facb2be326` |
| `types-PyYAML` | `6.0.12.20261111` | `Apache-2.0` | Dev Toolchain (`pyproject.toml`) | `c511f563eaf820b948c4ff6f43fe0b9d48b227be442a69058d9f68f139cae1fb` |
| `types-jsonschema` | `4.26.0.20261006` | `Apache-2.0` | Dev Toolchain (`pyproject.toml`) | `3eb7db61b6819d40addfdaac7173e749071a7d4a9a4394f0c844598ec84b2500` |

All dependencies are 100% permissively licensed (`MIT` and `Apache-2.0`). Zero copyleft (`GPL`, `AGPL`, `LGPL`, `SSPL`) dependencies introduced.

---

## 2. Alternatives Considered

- **`ruamel.yaml` vs. `pyyaml`:**
  - `ruamel.yaml` is designed for preserving comments and file structure in round-trip editing workflows at the expense of a larger C-extension footprint and complex parsing surface.
  - `pyyaml` with `yaml.safe_load` provides lightweight, fast, safe parsing of read-only YAML test cassettes while strictly forbidding arbitrary object constructor tags.
- **`msgspec` vs. `pydantic`:**
  - While `msgspec` provides fast pure serialization, `pydantic` v2 provides first-class JSON Schema (Draft 2020-12) generation required for structured LLM provider outputs, field validation hooks, and immutable models (`ConfigDict(frozen=True, extra="forbid")`).
- **Custom cassette validation vs. `jsonschema`:**
  - `jsonschema` provides Draft 2020-12 standard schema enforcement with precise path reporting, eliminating ad-hoc procedural validation logic.

---

## 3. Specialist Evaluations and Sign-offs

### Systems/Backend Architect Evaluation (`arch-reviewer`)
```markdown
[DEP-EVAL KANBA-19] LLMProvider Protocol, Typed Errors, FixtureLLMProvider & FixtureCLIRunner

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P0-12.md (KANBA-19 / KB-P0-12)
- Evaluated Dependencies:
  * pydantic (MIT)
  * pyyaml (MIT)
  * jsonschema (MIT)
  * types-PyYAML (Apache-2.0, dev typing stub if required)
  * types-jsonschema (Apache-2.0, dev typing stub if required)

1. License and Compatibility:
All components and type stubs are licensed under MIT or Apache-2.0. Completely permissive, zero copyleft (GPL, AGPL, SSPL, LGPL).

2. Supply-Chain and Attack Surface:
- Scoped to agent module runtime and test harness.
- pyyaml is restricted strictly to yaml.safe_load. Arbitrary Python object instantiation tags (such as !!python/object/apply) are strictly forbidden, mitigating YAML deserialization remote code execution vulnerabilities.
- File sizes for cassettes are bounded to a maximum of 1 MiB to prevent denial-of-service via memory exhaustion.

3. Architectural Rationale and Alternatives Considered:
- pyyaml vs. ruamel.yaml:
  * ruamel.yaml is optimized for preserving comments and formatting in round-trip config file editing, at the expense of complex C extensions and a larger parsing surface.
  * For immutable AI test cassettes, pyyaml using safe_load is lightweight, fast, robust, and minimizes parsing vulnerabilities.
- pydantic v2 vs. msgspec / dataclasses:
  * While dataclasses are built-in, they lack validation hooks, JSON schema generation, and strict coercion controls.
  * pydantic v2 (Rust core) provides high-performance validation, immutable models via ConfigDict(frozen=True, extra="forbid"), and first-class JSON Schema (Draft 2020-12) reflection required for structured LLM provider outputs.
- jsonschema vs. custom cassette validation:
  * jsonschema provides standard Draft 2020-12 validation against cassette.schema.json, ensuring that test cassettes adhere to strict contract specifications without requiring ad-hoc procedural validation logic.
- Offline Fixture Architecture:
  * FixtureLLMProvider and FixtureCLIRunner enable deterministic replay of streaming, structured responses, and CLI subprocess execution under pytest-socket isolation (--disable-socket). Tests execute offline in sub-second runtimes without external LLM API costs or flake.

4. Architectural Verdict:
APPROVED. Standardizes vendor-neutral AI abstractions with deterministic offline verification.
```

### Application and Supply-Chain Security Engineer Evaluation (`sec-eng`)
```markdown
[DEP-EVAL KANBA-19] LLMProvider Protocol and Fixtures

- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P0-12.md (KANBA-19 / KB-P0-12)
- Target Packages: pydantic, pyyaml, jsonschema, types-PyYAML, types-jsonschema

1. License and Compatibility Audit:
- pydantic (MIT): Permissive data validation and settings management.
- pyyaml (MIT): Permissive YAML parser and emitter.
- jsonschema (MIT): Permissive JSON Schema validation library.
- types-PyYAML (Apache-2.0), types-jsonschema (Apache-2.0): Permissive static typing stubs.
- License Compliance: 100% permissive. Zero GPL, AGPL, SSPL, or LGPL licenses.

2. Supply-Chain and Hostile Input Hardening:
- Safe Deserialization: Historical PyYAML vulnerabilities derive from yaml.load() and arbitrary Python object constructor tags (!!python/object/apply). System invariants strictly mandate yaml.safe_load() and prohibit unsafe tags; malicious serialization payloads are rejected by CassetteValidationError.
- Strict Schema Constraints: jsonschema (Draft 2020-12) strictly validates cassette structure against cassette.schema.json, enforcing 1 MiB file size limits, strict enum matching, and extra attribute prohibition, neutralizing prompt-injection tampering and payload manipulation.
- Runtime Immutability: Pydantic v2 models enforce ConfigDict(frozen=True, extra="forbid"), preventing runtime monkeypatching or attribute injection.
- Zero Network Dependency: FixtureLLMProvider and FixtureCLIRunner operate deterministically offline under --disable-socket with simulated latency and zero external network access.

3. Alternatives Evaluated:
- ruamel.yaml: Rejected. Complex and historically volatile API with slower parse speeds; primarily beneficial for round-trip YAML comment preservation which is unnecessary for read-only test fixture cassette replay.
- msgspec: Rejected. Highly performant but lacks native YAML parsing without external C libraries and lacks rich Draft 2020-12 JSON Schema validation integration. Pydantic v2 combined with jsonschema provides standard-compliant validation, deep ecosystem support, and strict typing guarantees.

4. Verdict:
- Role Sign-Off: APPROVED by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-19.
```

### Test and Build Quality Engineer Evaluation (`qa-eng`)
```markdown
[DEP-EVAL KANBA-19] AI Agent LLMProvider Protocol, Typed Errors, and Fixture Harness (KB-P0-12)

- Target Dependencies:
  * pydantic (MIT)
  * pyyaml (MIT)
  * jsonschema (MIT)
  * types-PyYAML (Apache-2.0), types-jsonschema (Apache-2.0, type stubs for mypy strict)

- Test and Build Quality Assessment:
  * pydantic (v2): High-speed data validation and modeling powered by pydantic-core in Rust. Enforces immutable protocol contracts (ConfigDict(frozen=True, extra="forbid")) for vendor-neutral DTOs (CompletionRequest, StructuredRequest, StructuredResponse, EmbedBatchRequest, HealthStatus). Performs boundary validation (temperature limits, token bounds, batch sizes 1..64) locally before network dispatch.
  * pyyaml: Robust YAML parsing using safe loading (yaml.safe_load). Used to load deterministic test cassettes while strictly disallowing arbitrary Python object deserialization (e.g. !!python/object).
  * jsonschema: Enforces schema compliance on test cassettes against agent/testing/cassette.schema.json using Draft202012Validator. Validates matcher rules, simulated TTFT delays, and fault injection payloads before fixture playback.
  * types-PyYAML and types-jsonschema: Required dev typing stubs ensuring zero untyped call warnings under mypy --strict.
  * Test Harness Alignment: Enables deterministic, offline AI test execution via FixtureLLMProvider and FixtureCLIRunner under pytest-socket (--disable-socket). Allows complete fault injection testing (HTTP 429, timeouts, schema errors, malformed outputs) without external API dependencies or financial costs.

- Alternatives Considered:
  * ruamel.yaml vs pyyaml: ruamel.yaml is focused on round-trip YAML comment and structure preservation, adding unneeded complexity and slower performance for read-only cassette fixtures. pyyaml with safe_load provides clean, fast, safe parsing.
  * msgspec vs pydantic: While msgspec is fast for pure serialization, pydantic v2 offers mature JSON Schema generation required for structured output contracts with LLMs, robust field validators, and rich typing ecosystem support.

- Engineer #2 Sign-off: APPROVED
```
