# Verification Handover Note: KANBA-33 (KB-P5-01)

## Overview

Ticket: KANBA-33 (Specification: KB-P5-01)
Title: [Phase 5 / Agent] OllamaProvider adapter with resolve-then-check CIDR pin, optional mTLS, streaming & embed
Author: builder-19 (Implementation Author)

All literal Definition of Done criteria specified in `docs/tickets/KB-P5-01.md` have been fully implemented, validated locally under strict offline test isolation, and packaged into the passive audit bundle under `docs/qa/KANBA-33/`.

## Summary of Changes

1. **Dependency Addition & Supply Chain Evaluation (`httpx==0.28.1`):**
   - Added `httpx==0.28.1` (BSD-3-Clause, Apache-2.0 compatible) to `agent/pyproject.toml` runtime dependencies.
   - Synchronized `uv.lock` and locked workspace dependencies.
   - Obtained three specialist sign-offs (Security Engineer, QA Engineer, Architecture Reviewer) recorded in `docs/qa/KANBA-33/dependency-evaluation.md`.
   - Verified clean license audit via `make license` (`violations=0`).

2. **Network Security Guard (`agent/providers/net_guard.py`):**
   - Implemented `resolve_and_pin(host, port, allowed_cidrs, *, resolver)`.
   - Hard-denied cloud metadata and link-local ranges: `169.254.0.0/16`, `fe80::/10`, `fd00:ec2::254/128`, `0.0.0.0/8`, `::/128`, `224.0.0.0/4`, `ff00::/8`, and IPv4-mapped IPv6 `::ffff:169.254.0.0/112`.
   - Enforced multi-record DNS rebinding defense: every returned IP must belong to the allowed CIDRs and not match any hard-denied network.
   - Raises `EgressDenied(code="OLLAMA_METADATA_DENIED")` or `EgressDenied(code="OLLAMA_CIDR_DENIED")`.

3. **Ollama Provider Adapter & Settings (`agent/providers/ollama.py`):**
   - `OllamaSettings`: Frozen Pydantic model with strict validation rejecting userinfo, query parameters, and fragments on `base_url`, requiring at least 1 CIDR and 1 model, and validating mutual presence of mTLS cert and key paths.
   - `OllamaProvider`: Implements `@runtime_checkable LLMProvider` protocol:
     - `stream_complete`: Fill-In-the-Middle (FIM) streaming via `/api/generate` with suffix, temperature, and token options. Per-line limit capped at 64 KiB (`LINE_TOO_LARGE`) and total stream limit capped at 16 MiB.
     - `generate_structured`: Structured chat completion via `/api/chat` with JSON schema enforcement and Pydantic response validation (`ProviderSchemaError` on schema mismatch or non-JSON content).
     - `embed_batch`: Batch vector embedding via `/api/embed` with batch size limit of 64 texts (`BATCH_TOO_LARGE` if > 512 requested) and 8,192 character per-text limit.
     - `health_probe`: Non-raising daemon health check via `/api/tags` returning `HealthStatus`.
     - Error mapping: 3xx redirects map to `REDIRECT_REFUSED`, 429 maps to `ProviderHTTPError` with `retry_after_s`, 500 maps to `ProviderHTTPError`, timeouts map to `ProviderTimeout`, and connection errors map to `ProviderUnavailable`.
     - Hardened client: `trust_env=False`, `follow_redirects=False`, and explicit SNI hostname extension.

4. **Provider Registry (`agent/providers/registry.py`):**
   - Implemented `build_provider(kind, settings, *, transport)` factory supporting both "ollama" and "fixture" providers.

5. **Deterministic Replay Transport (`agent/testing/http_cassette.py`):**
   - Implemented `CassetteTransport(httpx.AsyncBaseTransport)` for offline HTTP replay.
   - Supports method, path, and `json_contains` request matching, NDJSON/SSE streaming, and fault injection (`http_429`, `http_500`, `timeout`, `connect_error`, `malformed_body`, `oversize_line`).
   - Extended `agent/testing/cassette.schema.json` and `agent/testing/fixtures.py` with backward-compatible `http_exchanges`.

6. **CLI Extensions (`agent/cli.py` & `agent/cli_commands/validate_echo.py`):**
   - Added `--http-cassette` and `--base-url` CLI arguments.
   - Updated `validate-echo` to support `--provider ollama`.

7. **Documentation Manifest (`agent/GEMINI.md`):**
   - Documented `OllamaProvider`, network contract, SSRF defenses, and error codes with zero non-ASCII dashes.

8. **Test Fixtures & Cassettes (`tests/fixtures/ai/`):**
   - Created all 9 required cassette files:
     - `ollama_fim_stream_ok.yaml`
     - `ollama_chat_structured_ok.yaml`
     - `ollama_chat_structured_invalid_json.yaml`
     - `ollama_embed_ok.yaml`
     - `ollama_fault_429.yaml`
     - `ollama_fault_500.yaml`
     - `ollama_fault_timeout.yaml`
     - `ollama_fault_redirect_302.yaml`
     - `ollama_fault_oversize_line.yaml`

## Verification Proof Artifacts

All verification artifacts are located in `docs/qa/KANBA-33/`:
- `git-diff.patch`: Full git diff against main commit `67a77ea`.
- `unit-test-results.txt`: Verbatim output of the mandated pytest run showing 98 passed tests and 97.06% combined branch+line coverage across all target modules.
- `build-check.txt`: Clean output from `mypy --strict agent`, `ruff check agent`, `ruff format --check agent`, `lint-imports`, `make license`, and `make check`.
- `cli-run.txt`: Verbatim execution trace showing CLI run (a) exiting 0 and CLI run (b) exiting 2 with `OLLAMA_METADATA_DENIED`.
- `cassette-list.txt`: Directory listing of all 9 cassette files.
- `dependency-evaluation.md`: Dependency evaluation and sign-offs for `httpx==0.28.1`.
- `message-to-reality-checker.md`: This handover document.

## Definition of Done Verification Checklist

- [x] File existence and implementation: `agent/providers/ollama.py`, `agent/providers/net_guard.py`, `agent/providers/registry.py`, `agent/testing/http_cassette.py`.
- [x] Cassettes present: all 9 cassette files exist under `tests/fixtures/ai/` and pass schema validation.
- [x] Unit tests passing with >=95% coverage: 98 tests pass with 97.06% coverage under `--disable-socket --allow-unix-socket` in <1.0s. All 12 required test cases implemented.
- [x] Build, lint, and type checking: `mypy --strict agent`, `ruff check agent`, `ruff format --check agent`, and `lint-imports` pass with 0 errors.
- [x] CLI validation: `validate-echo` positive run exits 0; cloud metadata run exits 2 with `OLLAMA_METADATA_DENIED`.
- [x] Documentation: `agent/GEMINI.md` updated with provider contract and error codes.
- [x] Forensic proof packet: all 7 required files populated in `docs/qa/KANBA-33/`.
- [x] Character standard: zero non-ASCII dashes (hyphens only) across all modified files.
