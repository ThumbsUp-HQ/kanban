# API Specialist Review - KAN-435

**Ticket:** KAN-435 (`[BUG][AGENT-OLLAMA] Increase StructuredRequest max_output_tokens / Ollama num_predict From 1024 to 4096 to Prevent Reasoning-Model JSON Truncation`)
**Branch / Base:** `fix/KAN-435-ollama-structured-max-output-tokens` (base `ef35fd3f`)
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan435-69f3b094`
**Reviewer Role:** Backend/API Specialist (`backend-architect`)

---

## 1. Scope & Files Inspected

Verified directly against the worktree files and QA artifacts:

- `docs/qa/KAN-435/git-diff.patch` (272 lines across 6 files)
- `agent/providers/base.py`
- `agent/harnesses/in_app_sdk.py`
- `agent/providers/ollama.py`
- `agent/tests/harnesses/test_in_app_sdk.py`
- `agent/tests/providers/test_base_protocol.py`
- `agent/tests/providers/test_ollama.py`
- `docs/qa/KAN-435/unit-test-results.txt`
- `docs/qa/KAN-435/build-check.txt`

---

## 2. API & Contract Verification

### 2.1 Provider DTOs (`agent/providers/base.py`)
- **`StructuredRequest.max_output_tokens` (line 141):** Verified `Field(default=4096, ge=1, le=32768)`. Default raised from `1024` to `4096` while preserving strict lower/upper bounds (`1 <= max_output_tokens <= 32768`).
- **`CompletionRequest.max_output_tokens` (lines 93-98):** Verified unchanged at `default=256, ge=1, le=32768` with `AliasChoices("max_output_tokens", "max_tokens")`, keeping streaming autocomplete latency budgets isolated from structured reasoning requests.
- **Backward Compatibility & Bounds:** Frozen Pydantic DTOs (`ConfigDict(frozen=True, extra="forbid", ...)`) remain intact; callers supplying explicit `max_output_tokens` continue to work unchanged.

### 2.2 In-App SDK Harness (`agent/harnesses/in_app_sdk.py`)
- **`DEFAULT_ESTIMATE_TOKENS` (line 45):** Verified unchanged at `1024` for pre-execution budget reservation (`budget_enforcer.reserve(...)`, line 276), with post-call reconciliation via `budget_enforcer.settle(reservation, actual_tokens, ...)` (lines 369-372).
- **`DEFAULT_STRUCTURED_MAX_OUTPUT_TOKENS` (lines 32, 46):** Verified defined as `Final[int] = 4096` and exported in `__all__`.
- **`InAppSdkHarness.run()` (lines 358-366):** Verified `StructuredRequest(...)` explicitly passes `max_output_tokens=DEFAULT_STRUCTURED_MAX_OUTPUT_TOKENS` (`4096`, satisfying `>= 4096`).

### 2.3 Ollama Provider (`agent/providers/ollama.py`)
- **`num_predict` Forwarding (lines 371-381):** `generate_structured()` forwards `"num_predict": req.max_output_tokens` inside `payload["options"]` to Ollama `/api/chat`, yielding `num_predict=4096` by default for `StructuredRequest` and `InAppSdkHarness.run()`.
- **Truncation Diagnostic on JSON Failure (lines 405-417):** Reads `done_reason = data.get("done_reason")` before `json.loads(cleaned_content)`. On `json.JSONDecodeError`, when `done_reason == "length"`, raises `ProviderSchemaError` with the explicit diagnostic message:
  `Ollama structured output truncated: done_reason=length (truncated at num_predict={req.max_output_tokens}): {content_str!r}`.
  Non-length JSON failures retain the existing `Ollama message content is not valid JSON: {content_str!r}` `ProviderSchemaError`.
- **Security & Reliability:** SSRF/CIDR pinning (`resolve_and_pin`), `model_allowlist` enforcement, `strip_think_tags()` handling for reasoning models, and strict Pydantic schema validation (`req.response_model.model_validate`) remain intact. No new external dependencies were introduced.

---

## 3. Test Coverage, Static Analysis & Formatting

### 3.1 Unit Tests (`docs/qa/KAN-435/unit-test-results.txt` & Test Files)
- **New/Updated Tests Verified:**
  - `agent/tests/providers/test_base_protocol.py` (`test_structured_request_token_bounds_and_defaults`, lines 404-446): asserts `StructuredRequest.max_output_tokens == 4096` default, valid boundary values `1` and `32768`, `ValidationError` on `0` and `32769`, and `CompletionRequest.max_output_tokens == 256`.
  - `agent/tests/harnesses/test_in_app_sdk.py` (`test_in_app_sdk_generic_provider_and_arg_redaction` lines 389-393; `test_in_app_sdk_passes_default_structured_max_output_tokens` lines 399-440): asserts `InAppSdkHarness.run()` sends `max_output_tokens == DEFAULT_STRUCTURED_MAX_OUTPUT_TOKENS == 4096` (`>= 4096`).
  - `agent/tests/providers/test_ollama.py` (`test_ollama_generate_structured_sends_default_num_predict` lines 909-941; `test_ollama_generate_structured_done_reason_length_diagnostic` lines 944-976): asserts `options.num_predict == 4096` in outgoing `/api/chat` payload and verifies `ProviderSchemaError` includes `done_reason=length`, `num_predict=4096`, and the truncated payload when `done_reason == "length"`.
- **Recorded Test Run (`unit-test-results.txt`):**
  - `631 passed` in `38.38s`
  - Coverage on touched source files (`>=95%` requirement met):
    - `agent/harnesses/in_app_sdk.py`: `99%` (185 stmts, 0 miss, 44 branches, 3 partial)
    - `agent/providers/base.py`: `99%` (119 stmts, 1 miss, 14 branches, 0 partial)
    - `agent/providers/ollama.py`: `96%` (309 stmts, 10 miss, 80 branches, 5 partial)
    - Total across touched files: `97%`

### 3.2 Lint, Format, Type-Check & Character Hygiene (`docs/qa/KAN-435/build-check.txt`)
- `ruff check`: `All checks passed!`
- `ruff format --check`: `2885 files already formatted`
- `mypy`: `Success: no issues found in 1370 source files`
- **Dash Hygiene:** Verified zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) in `git-diff.patch` and all modified sections.

---

Verdict: APPROVED
