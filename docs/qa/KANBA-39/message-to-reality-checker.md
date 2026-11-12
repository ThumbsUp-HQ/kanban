# Verification Handover Note: KANBA-39 (KB-P5-02)

## Overview

Ticket: KANBA-39 (Specification: KB-P5-02)
Title: [Phase 5 / Agent] GeminiProvider adapter (google-genai) with response_schema, safety settings & Vertex region pin
Author: builder-19 (Implementation Author)

All literal Definition of Done criteria specified in `docs/tickets/KB-P5-02.md` have been fully implemented, validated locally under strict offline test isolation, and packaged into the passive audit bundle under `docs/qa/KANBA-39/`.

## Summary of Changes

1. **Dependency Addition & Supply Chain Evaluation (`google-genai==3.2.0`):**
   - Added `google-genai==3.2.0` (Apache-2.0, permissive monorepo compliant) to `agent/pyproject.toml` runtime dependencies.
   - Synchronized `uv.lock` and locked workspace dependencies.
   - Captured wheel hash (`sha256:4d7289b050ae2fec5cf1e2b4775f59de1730a9bacd714b4b33a11075f929f0da`) and transitive dependency audit in `docs/qa/KANBA-39/dependency-evaluation.md`.
   - Collected specialist evaluations and approvals from Security Engineer (`sec-eng`, board seq #72), Architecture Reviewer (`arch-reviewer`, board seq #76), and QA Engineer (`qa-eng`).
   - Verified clean license audit via `make license` (`violations=0`).

2. **Gemini Settings (`GeminiSettings` in `agent/providers/gemini.py`):**
   - Frozen Pydantic model (`extra="forbid"`) enforcing strict isolation between Vertex AI and AI Studio:
     - `mode: Literal["vertex", "ai_studio_paid"]`: Free tier `ai_studio` cannot be represented, ensuring enterprise-grade zero prompt retention.
     - `api_key: SecretStr | None`: Required when `mode == "ai_studio_paid"`, strictly forbidden when `mode == "vertex"`.
     - `vertex_project: str | None` and `vertex_location: str | None`: Required when `mode == "vertex"`, strictly forbidden when `mode == "ai_studio_paid"`.
     - Regional Pinning: `vertex_location` must be present in `allowed_vertex_regions`. Wildcard `"global"` routing is strictly rejected.
     - Content Safety: Default safety thresholds set `HARM_CATEGORY_HARASSMENT`, `HARM_CATEGORY_HATE_SPEECH`, `HARM_CATEGORY_SEXUALLY_EXPLICIT`, and `HARM_CATEGORY_DANGEROUS_CONTENT` to `BLOCK_MEDIUM_AND_ABOVE`.
     - Timeout: `timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)`.

3. **Gemini Provider Adapter (`GeminiProvider` in `agent/providers/gemini.py`):**
   - Implements `@runtime_checkable LLMProvider` protocol wrapping official `google-genai` SDK:
     - `stream_complete`: Token streaming via `client.aio.models.generate_content_stream(...)` with temperature, max_output_tokens, and safety settings. Yields typed `StreamChunk` with delta, index, and finish_reason. Chunks or prompt feedback with `finish_reason == "SAFETY"` immediately raise `ProviderSafetyBlock`.
     - `generate_structured`: Structured output generation via `client.aio.models.generate_content(...)` with `response_mime_type="application/json"` and `response_schema`. Re-validated locally against the requested Pydantic model (`ProviderSchemaError` on schema mismatch or truncation).
     - `embed_batch`: Batch vector embedding via `client.aio.models.embed_content(...)` with 64-input batch cap (`BATCH_TOO_LARGE`) and 8,192 character per-input cap (`INPUT_TOO_LARGE`).
     - `health_probe`: Non-raising availability probe via `models.get(model)` returning `HealthStatus`.
     - Data Residency: Exposes `residency_tier` as `f"gemini-vertex:{vertex_location}"` or `"gemini-ai-studio-paid"`.
     - Secret Hygiene: API keys wrapped in `SecretStr`, omitted from `__repr__` and `__str__`, and redacted from all exception strings via `_redact`.
     - Offline Replay: Configured with `trust_env=False` and injects `CassetteTransport` into `types.HttpOptions(async_client_args={"transport": transport})`.

4. **Provider Factory Registration (`agent/providers/registry.py`):**
   - Registered `gemini` in `build_provider(kind, settings, *, transport)` supporting `GeminiSettings` or raw dictionary.

5. **CLI Harness Integration (`agent/cli.py` & `agent/cli_commands/validate_echo.py`):**
   - Added `"gemini"` to available CLI `--provider` choices.
   - Wired `validate-echo` to instantiate and execute `GeminiProvider` with `--http-cassette`.

6. **Documentation (`agent/GEMINI.md`):**
   - Documented `GeminiProvider`, architecture, data residency rules, content safety filters, and error codes (`MODEL_NOT_ALLOWED`, `BATCH_TOO_LARGE`, `INPUT_TOO_LARGE`, `SAFETY_BLOCK`, `SCHEMA_ERROR`, `HTTP_ERROR`, `TIMEOUT`).

7. **Test Fixtures & Cassettes (`tests/fixtures/ai/`):**
   - Created all 8 required cassette files conforming to `agent/testing/cassette.schema.json`:
     - `gemini_stream_ok.yaml`
     - `gemini_structured_ok.yaml`
     - `gemini_structured_schema_mismatch.yaml`
     - `gemini_safety_block.yaml`
     - `gemini_embed_ok.yaml`
     - `gemini_fault_429.yaml`
     - `gemini_fault_503.yaml`
     - `gemini_fault_timeout.yaml`

8. **Automated Unit Test Suite (`agent/tests/providers/test_gemini.py`):**
   - 26 unit tests covering all 9 mandatory feature test cases.
   - 97.30% statement and branch coverage on `agent/providers/gemini.py` (threshold >= 95% met).
   - Hermetic test isolation: 100% offline execution under `pytest-socket` (`--disable-socket --allow-unix-socket`) in < 3.0s.

## Verification Proof Artifacts

All verification artifacts are located in `docs/qa/KANBA-39/`:
- `git-diff.patch`: Complete unified git diff against main commit `26ae9f0`.
- `unit-test-results.txt`: Raw output and exit code of DoD pytest command showing 26 passed tests and 97.30% coverage.
- `build-check.txt`: Raw output showing mypy strict, ruff check, ruff format, lint-imports, and make check passing clean.
- `license-gate.txt`: Raw output of license gate check showing 0 violations across 90 Python packages and 1 Node package.
- `dependency-evaluation.md`: Supply chain audit, cryptographic wheel SHA-256, alternatives, and specialist sign-offs for `google-genai==3.2.0`.
- `cli-run.txt`: Verbatim CLI traces showing command (a) exiting 0 and command (b) exiting 1 with `ProviderHTTPError(429)`.
- `message-to-reality-checker.md`: This handover document.
- Screenshots: N/A - Non-UI Ticket.

## Definition of Done Verification Checklist

- [x] File existence and implementation: `agent/providers/gemini.py` implements `GeminiSettings` and `GeminiProvider`; `agent/providers/registry.py` registers `gemini`.
- [x] Dependency pinned: `agent/pyproject.toml` pins `google-genai==3.2.0`; `uv.lock` contains exact version and hashes; `make license` exits 0 with 0 violations.
- [x] Cassettes present: all 8 cassette files exist under `tests/fixtures/ai/` and pass schema validation.
- [x] Unit tests passing with >=95% coverage: 26 tests pass with 97.30% coverage under `--disable-socket --allow-unix-socket` in 2.67s. All 9 required test cases implemented.
- [x] Build, lint, and type checking: `mypy --strict agent`, `ruff check agent`, `ruff format --check agent`, and `lint-imports` pass with 0 errors.
- [x] CLI validation: `validate-echo` positive run exits 0; fault 429 run exits 1 with `ProviderHTTPError(429)`.
- [x] Documentation: `agent/GEMINI.md` updated with provider contract and error codes.
- [x] Forensic proof packet: all required files populated in `docs/qa/KANBA-39/`.
- [x] Character standard: zero non-ASCII dashes (hyphens only) across all modified and generated files.
