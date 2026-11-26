# Message to Reality-Checker: KAN-435

## Ticket Scope & Deliverable Summary
- **Ticket ID:** `KAN-435` (`[BUG][AGENT-OLLAMA] Increase StructuredRequest max_output_tokens / Ollama num_predict From 1024 to 4096 to Prevent Reasoning-Model JSON Truncation`)
- **Branch:** `fix/KAN-435-ollama-structured-max-output-tokens`
- **Base:** `ef35fd3f`
- **Visual Proof:** `N/A - Non-UI Ticket (pure Python agent/provider runtime change with zero frontend/UI diff)`

## Root Cause & Architecture Fix Summary
1. **`StructuredRequest` Default Token Budget Raised (`agent/providers/base.py`):**
   - **Root Cause:** `StructuredRequest.max_output_tokens` was defaulted to `1024`, causing reasoning models (such as `deepseek-r1` or `qwen2.5-coder` with long chain-of-thought traces or complex schema payloads) to exceed the generation limit before producing the complete JSON closing brackets.
   - **Resolution:** Increased `StructuredRequest.max_output_tokens` default from `1024` to `4096` (`Field(default=4096, ge=1, le=32768)`). Preserved `CompletionRequest.max_output_tokens` at `default=256` (Sparkle FIM inline completion).

2. **In-App SDK Harness Token Alignment (`agent/harnesses/in_app_sdk.py`):**
   - **Root Cause:** `InAppSdkHarness.run()` did not explicitly pass `max_output_tokens` to `StructuredRequest`, relying on implicit defaults. Furthermore, token reservation estimation must remain conservative.
   - **Resolution:** Added `DEFAULT_STRUCTURED_MAX_OUTPUT_TOKENS: Final[int] = 4096` and passed it explicitly in `StructuredRequest(..., max_output_tokens=DEFAULT_STRUCTURED_MAX_OUTPUT_TOKENS, ...)`. Left `DEFAULT_ESTIMATE_TOKENS: Final[int] = 1024` intact so `BudgetEnforcer.reserve()` does not over-reserve token budgets on small workspaces.

3. **Ollama Truncation Diagnostic on `done_reason="length"` (`agent/providers/ollama.py`):**
   - **Root Cause:** When Ollama hit `num_predict`, it returned `done_reason: "length"` with partial JSON. The provider simply raised a generic `ProviderSchemaError("Ollama message content is not valid JSON")` without indicating truncation or the configured limit.
   - **Resolution:** Captured `done_reason = data.get("done_reason")`. When `json.loads` fails and `done_reason == "length"`, raises `ProviderSchemaError` with explicit diagnostic `done_reason=length (truncated at num_predict={req.max_output_tokens})` and the preview content. Otherwise preserved existing `ProviderSchemaError` contract.

## Verification Evidence & Quality Metrics
1. **Unit & Regression Test Coverage:**
   - Command: `uv run pytest agent/tests/ --cov=agent.harnesses.in_app_sdk --cov=agent.providers.base --cov=agent.providers.ollama --cov-branch --cov-report=term-missing -q`
   - Pass Rate: 631 of 631 tests passed (0 failures, 4 benign third-party warnings).
   - Coverage:
     * `agent/harnesses/in_app_sdk.py`: 99% (185 stmts, 44 branches)
     * `agent/providers/base.py`: 99% (119 stmts, 14 branches)
     * `agent/providers/ollama.py`: 96% (309 stmts, 80 branches)
     * Overall across touched files: 97% (exceeds >=95% requirement)
   - Verbatim Log: Recorded in `docs/qa/KAN-435/unit-test-results.txt`.

2. **Mandatory Test Cases Implemented:**
   - `agent/tests/harnesses/test_in_app_sdk.py`:
     * `test_in_app_sdk_passes_default_structured_max_output_tokens`: Asserts `InAppSdkHarness.run()` passes `max_output_tokens == 4096` (`>= 4096`) on `StructuredRequest`.
   - `agent/tests/providers/test_ollama.py`:
     * `test_ollama_generate_structured_sends_default_num_predict`: Asserts `generate_structured()` sends `options["num_predict"] == 4096` by default.
     * `test_ollama_generate_structured_done_reason_length_diagnostic`: Asserts when Ollama returns `done_reason: "length"`, `ProviderSchemaError` contains `done_reason=length` and `num_predict=4096`.
   - `agent/tests/providers/test_base_protocol.py`:
     * `test_structured_request_token_bounds_and_defaults`: Asserts `StructuredRequest` defaults `max_output_tokens` to `4096` and enforces `[1, 32768]` bounds (rejecting `0` and `32769`), while `CompletionRequest` defaults to `256`.

3. **Static Analysis & Build Hygiene:**
   - Ruff Check: All checks passed.
   - Ruff Format: 2885 files formatted cleanly.
   - Mypy Strict: Success: no issues found in 1370 source files.
   - Dash Audit: `python3 scripts/check_no_dashes.py --all` passed with 0 violations (zero em-dash or en-dash characters).
   - Verbatim Log: Recorded in `docs/qa/KAN-435/build-check.txt`.
