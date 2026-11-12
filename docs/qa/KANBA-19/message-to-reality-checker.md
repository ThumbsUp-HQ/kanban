# Forensic QA Handoff: KANBA-19 (KB-P0-12)

## 1. Ticket Overview
- **Ticket ID:** `KANBA-19`
- **Specification:** `docs/tickets/KB-P0-12.md`
- **Title:** `[Phase 0 / Agent] LLMProvider protocol, typed errors, FixtureLLMProvider & FixtureCLIRunner`
- **Epic:** `KB-E0`
- **Spec Sections:** S10.1 (LLMProvider protocol), S15.2 (Pluggable deterministic AI fixtures), S2.5 (Permissive supply chain)
- **Branch:** `feat/KANBA-19` (worktree `/tmp/kb-wt-KANBA-19`)

---

## 2. Summary of Implementation
- **Typed Error Hierarchy (`agent/providers/errors.py`):**
  - Implemented `ProviderError` with code validation (`^[A-Z][A-Z0-9_]{2,63}$`) and automatic secret redaction (sanitizing Bearer tokens, `sk-*`, `ghp_*`, `AKIA*`, `kb_*`, `AIza*`, JWT tokens, and `api_key`/`secret`/`token`/`password` parameters).
  - Implemented all 10 specialized subclasses: `ProviderHTTPError` (with `status` and `retry_after_s`), `ProviderTimeout`, `ProviderUnavailable`, `AllProvidersUnavailable`, `ProviderProtocolError`, `ProviderSchemaError`, `ProviderSafetyBlock`, `ProviderRefusal`, `ProviderPolicyError`, and `EgressDenied`.
- **Vendor-Neutral Protocol & DTOs (`agent/providers/base.py`):**
  - Implemented immutable Pydantic v2 models (`ConfigDict(frozen=True, extra="forbid")`): `CompletionRequest`, `StreamChunk`, `ToolCallStep`, `StructuredRequest[TModel]`, `StructuredResponse[TModel]`, `EmbedBatchRequest` (strictly enforcing batch bounds 1..64 and input length 1..8192 chars), `HealthStatus`, `CLIRunRequest` (rejecting empty argv, `/bin/sh`, `bash -c`, or any shell invocation with ValueError), and `CLIRunResult`.
  - Implemented `@runtime_checkable class LLMProvider(Protocol)` and `@runtime_checkable class CLIRunner(Protocol)`.
  - Re-exported all 11 error classes and DTOs in `agent/providers/__init__.py`.
- **Cassette Schema & Deterministic Fixtures (`agent/testing/cassette.schema.json`, `agent/testing/fixtures.py`):**
  - Draft 2020-12 JSON schema enforcing `cassette_version: 1`, `matcher`, `tool_script`, `simulated_ttft_ms`, `usage`, `stream_chunks`, `final_verdict`, `structured_output`, `embeddings`, `cli_result`, and `fault` specifications with `additionalProperties: false`.
  - `load_cassette()` rejecting files > 1 MiB (`MAX_CASSETTE_BYTES`), parsing via `yaml.safe_load`, and validating against schema via `Draft202012Validator`.
  - `FixtureLLMProvider` matching requests in order, recording telemetry in `call_log`, replaying SSE stream chunks, validating structured outputs into `response_model`, generating deterministic L2-normalized vectors from `{dimension, seed}`, and raising exact typed faults without real wall-clock sleep.
  - `FixtureCLIRunner` matching argv prefix and UTF-8 decoded stdin strings without spawning subprocesses, supporting timeout and malformed stdout fault injection.
- **Sample AI Fixtures (`tests/fixtures/ai/`):**
  - `echo_stream_ok.yaml`
  - `transition_rls_veto.yaml` (matching exact S15.2 specification fields)
  - `cli_agy_approve_ok.yaml`
  - `fault_429.yaml`
  - `fault_malformed_stdout.yaml`
- **Dependencies & Typing:**
  - Pinned `pydantic==2.14.3`, `pyyaml==6.0.3`, `jsonschema==4.26.0` in `agent/pyproject.toml`.
  - Pinned dev stubs `types-PyYAML==6.0.12.20261111` and `types-jsonschema==4.26.0.20261006` in root `pyproject.toml`.
  - Verified supply-chain sign-offs from `arch-reviewer`, `sec-eng`, and `qa-eng`.

---

## 3. Verification & Compliance Evidence
- **Branch Test Coverage:** `97.73%` total branch+line coverage across `agent/` (surpassing `>=95%` mandate).
- **Execution Performance:** Full pytest suite (29 tests) executes in `0.56s` (surpassing `< 10s` budget).
- **Zero Warnings / Strict Typing:**
  - `uv run ruff check agent`: 0 errors / clean.
  - `uv run ruff format --check agent`: 14 files clean.
  - `uv run mypy --strict agent`: 0 errors across 12 source files.
  - `uv run lint-imports`: 1 kept, 0 broken contracts.
  - `uv lock --locked`: clean lockfile resolution.
- **Encoding Compliance:** Zero `U+2014` or `U+2013` non-ASCII dashes present anywhere in added/modified files.
- **Visual Screenshots:** `N/A - Non-UI Ticket` (headless agent provider and fixture infrastructure).

---

## 4. Manifest of Forensic Artifacts in `docs/qa/KANBA-19/`
1. `dependency-evaluation.md`: Full dependency audit with pinned versions, SHA-256 hashes, alternatives considered, and signed evaluations from `arch-reviewer`, `sec-eng`, and `qa-eng`.
2. `cassette-validation.txt`: Automated output validating all 5 sample cassettes against Draft 2020-12 schema.
3. `unit-test-results.txt`: Full raw output and exit code 0 of coverage pytest command.
4. `build-check.txt`: Full raw output and exit codes of ruff, mypy, lint-imports, and uv lock.
5. `git-diff.patch`: Unified diff of all branch changes against the base commit.
