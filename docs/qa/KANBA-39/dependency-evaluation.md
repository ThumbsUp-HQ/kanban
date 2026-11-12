# Dependency Evaluation: google-genai (KANBA-39 / KB-P5-02)

## 1. Package Identification and Cryptographic Lockfile Pinning

- Package Name: `google-genai`
- Ecosystem: Python
- Module Scope: `agent/` (`kanban-agent` runtime dependencies in `agent/pyproject.toml`)
- Exact Pinned Version: `3.2.0`
- Wheel File: `google_genai-3.2.0-py3-none-any.whl`
- Wheel SHA-256 Digest: `4d7289b050ae2fec5cf1e2b4775f59de1730a9bacd714b4b33a11075f929f0da`
- Source Tarball: `google_genai-3.2.0.tar.gz`
- Source SHA-256 Digest: `b848937937b7b72594e75c57f01618ca201275afaedbfd717c004434ebf592f5`
- Upstream Registry: `https://pypi.org/project/google-genai/3.2.0/`
- License: `Apache-2.0` (Permissive; strictly compatible with monorepo license policy)

## 2. Transitive Dependency License Audit

All transitive dependencies introduced by `google-genai` are strictly permissive:

| Package | Version | License | License Category | Status |
| :--- | :--- | :--- | :--- | :--- |
| `anyio` | 4.16.0 | MIT | Permissive | APPROVED |
| `cffi` | 2.1.1 | MIT | Permissive | APPROVED |
| `charset-normalizer` | 3.5.2 | MIT | Permissive | APPROVED |
| `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Permissive | APPROVED |
| `distro` | 1.9.0 | Apache-2.0 | Permissive | APPROVED |
| `google-auth` | 2.62.2 | Apache-2.0 | Permissive | APPROVED |
| `httpcore2` | 2.16.0 | BSD-3-Clause | Permissive | APPROVED |
| `httpx2` | 2.16.0 | BSD-3-Clause | Permissive | APPROVED |
| `pyasn1` | 0.6.5 | BSD-2-Clause | Permissive | APPROVED |
| `pyasn1-modules` | 0.4.2 | BSD-2-Clause | Permissive | APPROVED |
| `pycparser` | 3.12 | BSD-3-Clause | Permissive | APPROVED |
| `pydantic` | 2.14.3 | MIT | Permissive | APPROVED |
| `requests` | 2.34.2 | Apache-2.0 | Permissive | APPROVED |
| `sniffio` | 1.3.1 | Apache-2.0 OR MIT | Permissive | APPROVED |
| `tenacity` | 9.1.4 | Apache-2.0 | Permissive | APPROVED |
| `truststore` | 0.10.5 | MIT | Permissive | APPROVED |
| `typing-extensions` | 4.16.0 | PSF-2.0 | Permissive | APPROVED |
| `urllib3` | 2.8.0 | MIT | Permissive | APPROVED |
| `websockets` | 17.4 | BSD-3-Clause | Permissive | APPROVED |

Automated license check verification: `uv run python -m scripts.license_gate` reports `SUMMARY python=90 node=1 violations=0`. Zero copyleft (GPL, AGPL, SSPL, LGPL) dependencies detected.

## 3. Supply-Chain Hardening and Security Controls

1. Zero Data Retention Mandate:
   - `GeminiSettings` strictly prohibits the free Google AI Studio tier (`mode="ai_studio"` is rejected by Pydantic model validation).
   - Only enterprise `vertex` and paid `ai_studio_paid` modes are supported, guaranteeing that inputs and prompts are never retained for model training.
2. Strict Vertex Regional Pinning:
   - For `vertex` mode, `vertex_location` must match an administrator-approved regional identifier in `allowed_vertex_regions`.
   - Wildcard `"global"` routing is programmatically rejected with an explicit validation error, preventing unexpected data egress across geopolitical boundaries.
3. Credential Hygiene & Secret Redaction:
   - API keys are held strictly as `pydantic.SecretStr` in memory and are excluded from `repr`, `str`, logging, and exception messages via the `_redact` method.
   - In `vertex` mode, API keys are rejected; authentication relies on Google Cloud Service Account credentials or ADC.
4. Defense-in-Depth Schema Validation:
   - In structured output generation, server-side `responseSchema` is supplemented by local re-validation using `req.response_model.model_validate_json(raw_json)`. If the upstream provider produces invalid or truncated fields, `ProviderSchemaError` is raised immediately.
5. Hermetic Offline Testing:
   - The provider accepts custom `AsyncBaseTransport` injected via `types.HttpOptions(async_client_args={"transport": transport, "trust_env": False})`.
   - Enables complete test isolation with `CassetteTransport` under `pytest-socket` (`--disable-socket --allow-unix-socket`).

## 4. Architectural Alternatives Evaluated

1. Deprecated `google-generativeai` SDK:
   - Rejected. Legacy SDK with divergent APIs, lack of native support for Gemini 2.x models, and announced upstream deprecation timeline.
2. Raw REST implementation via `httpx`:
   - Rejected. Reimplementing Google Cloud Vertex AI streaming protocols, OAuth token refresh flows, and protobuf-to-JSON type mappings from scratch introduces substantial maintenance complexity, bug surface, and security drift compared to the official Apache-2.0 `google-genai` SDK.

## 5. Specialist Evaluations & Verbatim Sign-Offs

### 5.1 Security Engineer Sign-off (sec-eng, Board Seq #72)

```
### [DEP-EVAL KANBA-39] GeminiProvider Adapter (google-genai)

- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P5-02.md (KANBA-39 / KB-P5-02)
- Target Packages: google-genai (pinned in agent/pyproject.toml and uv.lock)

1. License and Compatibility Audit:
- google-genai (Apache-2.0): Permissive SDK developed by Google.
- License Compliance: 100% Apache-2.0 compliant. Zero copyleft contamination.

2. Supply-Chain and Data Privacy Hardening:
- Zero Data Retention Mandate: GeminiSettings strictly prohibits the free AI Studio tier (mode="ai_studio" is rejected). Only vertex or ai_studio_paid are permitted, ensuring enterprise-grade zero prompt retention.
- Strict Region Pinning: vertex_location must belong to allowed_vertex_regions; wildcard "global" is rejected, preventing unexpected data egress across geopolitical jurisdictions.
- Credential Protection: API keys are held as Pydantic SecretStr and strictly redacted from logs, repr(), and exception strings.
- Local Schema Defense-in-Depth: Structured JSON outputs are re-validated locally against Pydantic models (raising ProviderSchemaError on mismatch), ensuring the server-side output cannot inject unvalidated fields into downstream agent workflows.
- Offline Test Capability: Configured with trust_env=False and supports injecting CassetteTransport for offline verification under pytest-socket.

3. Alternatives Evaluated:
- Deprecated google-generativeai: Legacy SDK with divergent APIs and planned deprecation. google-genai is the current, unified, and supported SDK for AI Studio and Vertex AI.
- Raw REST via httpx: Avoids SDK dependencies, but requires hand-crafting complex streaming SSE parsers and protobuf schemas. google-genai is Apache-2.0, officially maintained, and provides typed client configurations.

4. Verdict:
- Role Sign-Off: APPROVED by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-39.
```

### 5.2 Systems/Backend Architect Sign-off (arch-reviewer, Board Seq #76)

```
### [DEP-EVAL KANBA-39] GeminiProvider Adapter (google-genai)

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P5-02.md (KANBA-39 / KB-P5-02)
- Evaluated Dependencies:
  * google-genai (Apache-2.0, exact pin in agent/pyproject.toml)

1. License and Compatibility:
google-genai is licensed under the permissive Apache-2.0 license. Perfectly aligned with the monorepo Apache-2.0 license policy. Zero copyleft.

2. Supply-Chain and Attack Surface:
- Scoped to agent/ module for Google Cloud Vertex AI and paid Google AI Studio integrations.
- Enforces zero data retention: the free tier is programmatically forbidden; only enterprise Vertex AI and paid AI Studio modes are permitted.
- Enforces explicit Vertex region pinning (e.g. europe-west4, us-central1), rejecting unpinned global routing to satisfy strict data residency requirements.
- Uses httpx under the hood, enabling seamless integration of CassetteTransport for offline unit testing.
- Secrets are wrapped in Pydantic SecretStr and strictly excluded from logs, error messages, and object representations.

3. Architectural Rationale and Alternatives Considered:
- google-genai vs. deprecated google-generativeai:
  * google-generativeai is the legacy SDK and lacks first-class support for Gemini 2.x models, unified Vertex/AI Studio switching, and structured Pydantic response schemas.
  * google-genai is the current, official Google SDK designed for modern agentic workflows.
- google-genai vs. custom raw REST implementation:
  * Writing custom REST clients for Vertex AI and AI Studio requires reimplementing streaming protocols, token refresh logic, and safety rating parsing, increasing ongoing maintenance overhead.

4. Architectural Verdict:
APPROVED. Standardizes enterprise-grade Gemini integration with verifiable data residency controls.
```

### 5.3 Test and Build Quality Engineer Sign-off (qa-eng, Board Seq #74 Batch Context)

```
Evaluator: Test and Build Quality Engineer (qa-eng)
Scope: docs/tickets/KB-P5-02.md (KANBA-39 / KB-P5-02)
Target Package: google-genai==3.2.0 (Apache-2.0)

- License and Build Determinism:
  * Pure Python wheel with complete type annotations, cleanly installing via uv sync --locked in <100ms.
  * Validated under Apache-2.0 monorepo license gate with zero violations.
- Test Ergonomics and Offline Replay:
  * Direct injection of CassetteTransport into types.HttpOptions(async_client_args={"transport": transport}) allows 100% offline unit testing under pytest-socket (--disable-socket --allow-unix-socket).
  * Fast test execution: 26 unit tests execute in under 3.0s, achieving 97.30% statement and branch coverage on agent/providers/gemini.py.
  * Flawless static analysis: mypy --strict agent passes with zero errors; ruff check and ruff format clean.

Verdict: APPROVED
```
