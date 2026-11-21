# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Passive forensic mode enforced (`read_file` only; zero shell commands, zero URLs visited, zero files modified). Audited `.agents/agents/reality-checker.md`, all 9 documentation/proof files in `docs/qa/KAN-61/`, all 13 PNG screenshots in `docs/qa/KAN-61/screenshots/`, and all 15 source/test files on disk listed in the review scope.
**Evidence Captured**:
- `docs/qa/KAN-61/changed-files-manifest.txt` (36 files with SHA256 hashes)
- `docs/qa/KAN-61/git-diff.patch` (1802 lines; note stale embedded manifest and pre-fix diffs)
- `docs/qa/KAN-61/unit-test-results.txt` (`255 passed, 1 warning in 7.75s`, `95%` aggregate coverage across 9 listed files)
- `docs/qa/KAN-61/build-or-typecheck.txt` (`ruff check` on modified files, `check_no_dashes`, `lint-imports` 2 kept / 0 broken; zero mypy/pyright/frontend build logs)
- `docs/qa/KAN-61/live-fullstack-proof.txt` (zero-mock live telemetry on `http://127.0.0.1:18962` at commit `9d5577ad9b50`)
- `docs/qa/KAN-61/api-specialist-review.md` (`STATUS: APPROVED`) & `docs/qa/KAN-61/ui-specialist-review.md` (`STATUS: APPROVED`)
- 13 PNG screenshots in `docs/qa/KAN-61/screenshots/`

**QA Cross-Validation**: **CHALLENGED**. Previous QA and specialist signoffs (`message-to-reality-checker.md`, `api-specialist-review.md`, `ui-specialist-review.md`, `verification-summary.md`) contain factual inaccuracies and omit real defects directly visible in disk code, test output, and screenshots:
1. `message-to-reality-checker.md` (lines 19-25) and `api-specialist-review.md` (lines 25-31) claim `StrictVerdictSchema` defines `decision`, `verdict`, `findings`, `definition_of_done_evaluation`, `risk_assessment`, and `confidence_score`. On disk (`agent/harnesses/in_app_sdk.py:76-85`), `StrictVerdictSchema` actually defines `decision`, `reason_markdown`, `add_labels`, and `cited_files`.
2. `message-to-reality-checker.md`, `api-specialist-review.md`, and `verification-summary.md` cite `255/255 passed in 9.28s` from an older test run (preserved inside `git-diff.patch:1539`), whereas current `docs/qa/KAN-61/unit-test-results.txt:52` shows `255 passed, 1 warning in 7.75s` with an active `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` at `agent/tests/gates/test_gate_runner.py:317`.
3. `api-specialist-review.md:73` claims `0 type errors`, yet `docs/qa/KAN-61/build-or-typecheck.txt` contains zero typecheck (mypy/pyright/tsc) or build execution output.
4. `git-diff.patch` does not match current disk files (`changed-files-manifest.txt` hashes differ from `git-diff.patch:1472-1489`), and `live-fullstack-proof.txt:6-7` cites production fixes in `kanban/app.py` and `compute_issue_etag()` that are absent from `changed-files-manifest.txt` and `git-diff.patch`.
5. `ui-specialist-review.md` claims clean UI rendering and `Zero inline JSX style={...} attributes`, yet no frontend files are included in the diff/manifest and multiple UI/telemetry defects are directly visible in the screenshots.

## 📸 Complete System Evidence
**Visual Documentation**:
- Admin / Config screens: `62-ai-provider-gemini-top-key-probe.png`, `63-ai-provider-ollama-probed-models.png`, `64-agent-qa-done-definition.png`, `65-workflow-attach-qa-done-gate.png` (byte-identical to `live-workflow-attach-qa-done-gate-desktop.png`)
- Positive outcome (`KAN-1` -> `Done`): `66-qa-gate-positive-approved-done.png` (byte-identical to `live-qa-gate-positive-approved-done-desktop.png`), `live-qa-gate-positive-tablet.png`, `live-qa-gate-positive-mobile.png`
- Negative outcome (`KAN-2` retained in `In Progress`): `67-qa-gate-negative-saturn-ice-cream-vetoed.png` (byte-identical to `live-qa-gate-negative-saturn-ice-cream-vetoed-desktop.png`), `live-qa-gate-negative-tablet.png`, `live-qa-gate-negative-mobile.png`

**What System Actually Delivers**:
- **Schema Utilities & Providers**: `agent/providers/schema_utils.py` (`dereference_json_schema`, `clean_gemini_schema`, `make_strict_json_schema`, `strip_think_tags`) is cleanly implemented and wired into `OllamaProvider`, `GeminiProvider`, and `OpenAIProvider`. `InAppSdkHarness` uses `StrictVerdictSchema` and seals `nonce = ctx.verdict_nonce` into `kb-transition-verdict/v1`.
- **Gate Worker & Timeout**: `GateWorker.handle_dispatch` (`agent/gates/worker.py:230-236`) catches `(TimeoutError, ProviderTimeout)` and records `GATE_TIMEOUT`. `GateWorkerRunner._load_entities` (`agent/gates/runner.py:334-439`) resolves `AIProviderConfig`, computes `cutoff_ms = min(int(prov_timeout), int(agent_timeout))`, unwraps API keys safely via `dek_kid` / `__dict__` check, and instantiates live providers.
- **Secret Redaction**: `agent/providers/errors.py:30-49` and `kanban/security/scrubber.py:35,220-224` redact `AQ.[A-Za-z0-9_-]{20,}` keys.
- **Actual UI Reality in Screenshots**:
  - `62-ai-provider-gemini-top-key-probe.png` shows masked Gemini API key, `https://generativelanguage.googleapis.com`, `20000` ms cutoff, and probed model chips (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-preview-tts`).
  - `63-ai-provider-ollama-probed-models.png` shows Ollama `http://192.168.1.115:11434` with probed model chips.
  - `64-agent-qa-done-definition.png` shows `QA Done Gate` (`in_app_sdk`, `ollama`, `gemma3:4b`, `20000` ms), scrolled past the modal header.
  - `65-workflow-attach-qa-done-gate.png` shows `require-ai-qa-on-done` attached to `In Progress` -> `Done` (`Fail-Closed`), with `Allowed Mutable Fields` clipped at the bottom border above the footer buttons.
  - `66-qa-gate-positive-approved-done.png` (and tablet/mobile variants) shows `KAN-1` in `Done` state, two prior `Gate timed out after 20000 ms` comments, and an approval comment with raw unrendered markdown hashes (`## ✅🤖 Workflow Transition Gate Approved`, `### Reality Check / Gate Rationale`).
  - `67-qa-gate-negative-saturn-ice-cream-vetoed.png` (and tablet/mobile variants) shows `KAN-2` retained in `In Progress`, but displays `require-ai-qa-on-done evaluating gate via cli: agy -p (:ro)` for an `in_app_sdk` / `ollama` agent, shows `Comments (0)` despite a visible veto comment, and truncates `In Progress` to `In Progres` in the desktop right-hand `State` select control.

## 🧪 Integration Testing Results
**End-to-End User Journeys**: **PARTIAL / NEEDS WORK**
- **Provider Config -> Agent Def -> Attach Hook**: Evidenced across `62`, `63`, `64`, `65` (with modal footer clipping in `65`). No UI screenshot provided for OpenAI provider setup.
- **In-Transition Gate Execution (Ollama Positive & Negative)**: Evidenced in `66` (`KAN-1` moved to `Done` after prior `20000 ms` timeouts) and `67` (`KAN-2` vetoed in `In Progress`), but `KAN-2` activity telemetry misreports `cli: agy -p (:ro)`, `Comments (0)` miscounts comments, and `KAN-1` comment headings render raw `##`/`###`.
- **Gemini / OpenAI / Dedicated Timeout E2E UI**: Only logged as text lines in `live-fullstack-proof.txt` (lines 17-30); no UI screenshots exist for Gemini or OpenAI gate verdicts or a standalone `GATE_TIMEOUT` view.

**Cross-Device Consistency**: **PARTIAL PASS**
- Tablet (`live-qa-gate-positive-tablet.png`, `live-qa-gate-negative-tablet.png`) and mobile (`live-qa-gate-positive-mobile.png`, `live-qa-gate-negative-mobile.png`) wrap without horizontal page overflow, though raw `##`/`###` markdown and `Comments (0)` / `cli: agy -p (:ro)` defects persist across viewports, and desktop `67` truncates `In Progres` in the right sidebar `State` dropdown.

**Performance Validation**: **PASS (WITH CAVEATS)**
- `unit-test-results.txt`: 255 tests executed in `7.75s`.
- `live-fullstack-proof.txt`: Gemini `1594ms-3215ms`, OpenAI `2224ms-3846ms`, Ollama `5213ms-31940ms`, and `nemotron-3-super` 5s strict cutoff enforced `GATE_TIMEOUT` at `6023ms`. Page load timing metrics were not captured in JSON telemetry.

**Specification Compliance**: **FAIL (GAPS IDENTIFIED)**
- **Claimed**: `"Zero warnings"` / `"255/255 passed in 9.28s"` / `"0 type errors"` / `">=95% coverage"` -> **Reality**: `unit-test-results.txt` has `1 warning` (`RuntimeWarning` at `test_gate_runner.py:317`), `agent/gates/runner.py` is `88%` and `agent/gates/worker.py` is `93%` (and `kanban/ai_config/service.py` is missing from coverage report), and no typechecker (`mypy`/`pyright`/`tsc`) ran in `build-or-typecheck.txt`.
- **Claimed**: `"AQ.* keys ... via ai_studio_paid mode with api_version='v1beta'"` (`message-to-reality-checker.md:41`) vs `"mode='vertex_express' ... target aiplatform.googleapis.com"` (`test_gemini.py:1032`) -> **Reality**: On disk, `agent/gates/runner.py:390-397` only selects `vertex_express` if `base_url` contains `aiplatform.googleapis.com`; if `base_url` is `None` (as in `test_gate_runner.py:452`) and the key starts with `AQ.`, `runner.py` sets `mode="ai_studio_paid"`, which causes `GeminiProvider.__init__` (`agent/providers/gemini.py:197-218`) to set `is_ai_studio_url=False`, `is_vertex_express=False`, and `api_version=None` (neither Vertex Express nor `v1beta`).

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
1. `agent/tests/gates/test_gate_runner.py:317` emits `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` because `mock_session = AsyncMock()` does not configure `mock_session.execute.return_value` as a sync `MagicMock` (`runner.py:325` calls `prov_res.scalar_one_or_none()`).
2. `git-diff.patch` and its embedded manifest are stale relative to the current files on disk, and `kanban/app.py` / ETag changes referenced in `live-fullstack-proof.txt` are missing from the patch and manifest.

**New Issues Discovered**:
1. **SSRF Pinning Bypass & Query-String Secret Leak in `kanban/ai_config/service.py:848-865,985`**: When `active_key.startswith("AQ.")` falls back to `https://aiplatform.googleapis.com/...:countTokens`, `probe_provider` calls `client.post(vertex_url, ..., params={"key": active_key})` directly instead of using `resolve_and_pin` / pinned IP + `sni_hostname`. Passing `active_key` in the URL query parameter (`?key=AQ....`) also risks leaking the key in `httpx` exception strings, because `probe_provider` line 985 returns `"message": str(exc)` without calling `redact_secrets()` or `scrub_text()`.
2. **Misrouted `AQ.` Key with `base_url=None` and Misreported `residency_tier`**:
   - In `agent/gates/runner.py:389-397`, an `AQ.` key with `provider_row.base_url = None` falls into `mode="ai_studio_paid"` without `generativelanguage.googleapis.com` in `base_url`, so `GeminiProvider.__init__` (`agent/providers/gemini.py:197-218`) initializes neither `vertexai=True` nor `api_version="v1beta"`.
   - Conversely, `GeminiProvider.residency_tier` (`agent/providers/gemini.py:247-251`) reports `gemini-vertex-express:<loc>` for any `AQ.` key even when `is_ai_studio_url` is True and `_client` was constructed in AI Studio mode (`vertexai=False`).
3. **Timeout Enforcement Asymmetry**:
   - `GeminiProvider.generate_structured` (`agent/providers/gemini.py:384-412`) and `OpenAIProvider.generate_structured` (`agent/providers/openai_provider.py:287-306`) do not enforce `req.ttft_deadline_ms` (relying on `GateWorker`'s outer `asyncio.timeout`), and `GateWorkerRunner.poll_once` (`agent/gates/runner.py:491-492`) computes sweep `deadline_at` solely from `agent_def.timeout_ms` rather than `min(prov_timeout, agent_timeout)`.
4. **Inaccurate Specialist Documentation**: `message-to-reality-checker.md` and `api-specialist-review.md` describe nonexistent fields on `StrictVerdictSchema` (`verdict`, `findings`, `definition_of_done_evaluation`, `risk_assessment`, `confidence_score`) instead of the actual fields (`decision`, `reason_markdown`, `add_labels`, `cited_files`).
5. **UI / Activity Telemetry Bugs Visible in Screenshots**:
   - `67-qa-gate-negative-saturn-ice-cream-vetoed.png`: Activity entry shows `evaluating gate via cli: agy -p (:ro)` for an `in_app_sdk` (`ollama`) gate; `Comments (0)` tab count disagrees with rendered veto comment; `In Progress` truncates to `In Progres` in the right sidebar State select box.
   - `66-qa-gate-positive-approved-done.png`: Gate approval comment displays raw `##` and `###` markdown heading tokens instead of rendered headings.
   - `65-workflow-attach-qa-done-gate.png`: `Allowed Mutable Fields` label is clipped at the bottom of the modal scroll area.

**Critical Issues** (Must-fix before production consideration):
1. Fix `kanban/ai_config/service.py:848-865,985` so the Vertex Express probe uses `resolve_and_pin` (no SSRF pinning bypass), removes `params={"key": active_key}` from the URL query string (use `x-goog-api-key` header only), and scrubs/redacts any exception message returned by `probe_provider`.
2. Fix `AQ.` key routing consistency between `agent/gates/runner.py:389-397` and `agent/providers/gemini.py:197-251` (default `AQ.` with `base_url=None` to `vertex_express` or explicit `generativelanguage.googleapis.com` `v1beta`, and align `residency_tier` with actual client target).
3. Eliminate the `RuntimeWarning` in `agent/tests/gates/test_gate_runner.py:317` and bring `agent/gates/runner.py` (88%), `agent/gates/worker.py` (93%), and `kanban/ai_config/service.py` to `>=95%` coverage.
4. Execute and archive actual typecheck (`mypy`/`pyright`) and frontend build verification in `build-or-typecheck.txt`, regenerate `git-diff.patch` / `changed-files-manifest.txt` against HEAD (including all touched files), and correct the hallucinated `StrictVerdictSchema` fields in `message-to-reality-checker.md` and `api-specialist-review.md`.

**Medium Issues** (Should-fix for better quality):
1. Fix `KAN-2` activity log text showing `evaluating gate via cli: agy -p (:ro)` for `in_app_sdk` runs, fix `Comments (0)` counter mismatch, and widen the right-hand `State` select box so `In Progress` does not clip.
2. Fix Markdown heading rendering (`##`, `###`) in `Workflow Transition Gate Approved` comments (`66-qa-gate-positive-approved-done.png`) and modal padding/scroll clipping on `Allowed Mutable Fields` (`65-workflow-attach-qa-done-gate.png`).
3. Honor `min(prov_timeout, agent_timeout)` in `GateWorkerRunner.poll_once` sweep deadline calculation (`agent/gates/runner.py:491-492`) and add unit tests for `InAppSdkHarness` `StrictVerdictSchema` field mapping.

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: B-
**Design Implementation Level**: Good (core backend schema dereferencing, `StrictVerdictSchema` nonce sealing, and multi-provider routing work in principle, but verification artifacts are out of sync and UI/security edge cases remain)
**System Completeness**: 80% (core backend harness implemented; typecheck proof, accurate QA docs, Vertex probe SSRF/key hygiene, and UI rendering/telemetry polish incomplete)
**Production Readiness**: NEEDS WORK

## 🔄 Deployment Readiness Assessment
**Status**: NEEDS WORK

**Required Fixes Before Production**:
1. Patch `kanban/ai_config/service.py:848-865,985` to route the Vertex Express `AQ.` fallback through `resolve_and_pin`, remove the `?key=` URL query parameter, and redact `probe_provider` error messages.
2. Align `agent/gates/runner.py:389-397` and `agent/providers/gemini.py:197-251` for `AQ.` keys when `base_url` is `None` vs `generativelanguage.googleapis.com`, and align `residency_tier` with actual mode.
3. Fix the unawaited `AsyncMock` `RuntimeWarning` in `agent/tests/gates/test_gate_runner.py:317` and raise `agent/gates/runner.py` (currently 88%), `agent/gates/worker.py` (currently 93%), and `kanban/ai_config/service.py` coverage to `>=95%` with `InAppSdkHarness` `StrictVerdictSchema` mapping tests.
4. Run and capture `mypy`/`pyright` + frontend build outputs in `docs/qa/KAN-61/build-or-typecheck.txt`, regenerate `git-diff.patch` and `changed-files-manifest.txt` from the exact commit under review, and fix the inaccurate `StrictVerdictSchema` documentation in `api-specialist-review.md` and `message-to-reality-checker.md`.
5. Fix the UI/telemetry defects observed in screenshots `65`, `66`, and `67` (`cli: agy -p (:ro)` misattribution on `in_app_sdk` gates, `Comments (0)` count mismatch, `In Progres` truncation, raw `##`/`###` headings in approval comment, and `Allowed Mutable Fields` modal clipping), and capture live screenshots of Gemini, OpenAI, and dedicated `GATE_TIMEOUT` UI states.

**Timeline for Production Readiness**: 1 revision cycle (1-2 days)
**Revision Cycle Required**: YES

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Exact synchronization between code on disk, `git-diff.patch`, `changed-files-manifest.txt`, and specialist review claims.
- Zero pytest warnings (`0 warnings`), full typecheck proof, and `>=95%` coverage per modified module.
- Clean SSRF pinning and zero query-string secret exposure in `probe_provider` Vertex Express fallback.
- Accurate UI activity telemetry (`in_app_sdk` vs `cli`), comment counts, markdown heading rendering, and select/modal layout sizing.

**Quality Targets**:
- `255+` unit tests passing with `0` warnings and `>=95%` coverage on every touched module (`runner.py`, `worker.py`, `in_app_sdk.py`, `service.py`, `gemini.py`, `ollama.py`, `openai_provider.py`, `schema_utils.py`, `scrubber.py`).
- `0` ruff errors, `0` mypy/pyright errors, `0` broken import-linter contracts, `0` non-ASCII dashes.
- `0` factual discrepancies in specialist reviews and verification packet.

**Evidence Requirements**:
- Updated `docs/qa/KAN-61/unit-test-results.txt` showing `0 warnings` and `>=95%` per-module coverage (including `kanban/ai_config/service.py`).
- Updated `docs/qa/KAN-61/build-or-typecheck.txt` including typecheck (`mypy`/`pyright`) and frontend build output.
- Synchronized `git-diff.patch` and `changed-files-manifest.txt` matching commit SHA256 hashes on disk.
- Updated Playwright screenshots showing fixed activity label (`in_app_sdk`), accurate comment counter, rendered markdown headings, unclipped modal/select controls, plus live Gemini/OpenAI/`GATE_TIMEOUT` UI captures.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-21
**Evidence Location**: docs/qa/KAN-61/
**Re-assessment Required**: After fixes implemented
