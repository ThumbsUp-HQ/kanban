# Reality-Checker Verification Packet: KAN-61

**Ticket ID:** `KAN-61` (`[KB-AI-HARNESS-01]`)
**Title:** Multi-Provider In-Transition AI Agent Harness: Flat Verdict Schema, Strict Schema Dereferencing, Cutoff Timeouts, and Fail-Closed Workflow Gate UI
**Branch:** `main` (commit `9d5577ad9b50`)
**Container Environment:** `http://localhost:18962` (container: `kanban-liveqa-2`)
**Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`

---

## 1. Executive Summary & Verification Highlights

This packet provides forensic verification for ticket **KAN-61** integrated on `main` at commit `9d5577ad9b50`, incorporating empirical results from zero-mock Live Full-Stack QA against container `kanban-liveqa-2` (`http://localhost:18962`, embedded PostgreSQL 16 + FORCE RLS).

All core requirements and acceptance criteria have been implemented, verified, and certified:

1. **Flat Wire Verdict Schema & JSON Schema Dereferencing**:
   - `dereference_json_schema()` in `agent/providers/schema_utils.py` inlines all internal `$defs` or `$ref` schemas into self-contained schemas for local edge models (Ollama format constraint) and cloud structured outputs.
   - Enforces `StrictVerdictSchema` (`kb-transition-verdict/v1`):
     * `decision`: Literal["approve", "reject"]
     * `reason_markdown`: str
     * `add_labels`: list[str]
     * `cited_files`: list[str]

2. **Live ProviderRouter Integration in GateWorkerRunner**:
   - `GateWorkerRunner` in `agent/gates/runner.py` directly resolves live AI providers via `ProviderRouter` with encrypted DEK key unwrapping (`dek_kid`), timeout bounds, and network guards.
   - Resolved `MissingGreenlet` error during async execution by checking `dek_kid` and `__dict__` instead of deferred column access.
   - Nonce-sealed requests prevent replay attacks across transition events.

3. **Strict Cutoff Timeout Enforcement & Fail-Closed Retention**:
   - Enforces `timeout_ms = min(provider.timeout_ms, agent.timeout_ms)`.
   - On timeout or provider failure, the gate fails closed:
     * Card remains safely in `In Progress`.
     * Audit comment is posted (`🛑🤖 Gate timed out after ... ms`).
     * State is recorded as `timed_out` or `vetoed`.
     * Zero hung background worker threads.

4. **Multi-Provider Protocol Adaptations**:
   - **Google Gemini (`agent/providers/gemini.py`)**: Routes `AQ.` keys configured against `https://generativelanguage.googleapis.com` via `ai_studio_paid` mode with `api_version="v1beta"`, utilizing `response_mime_type="application/json"` and `response_schema`.
   - **Ollama (`agent/providers/ollama.py`)**: Passes dereferenced JSON schema via `format` parameter; strips `<think>` tags via `strip_think_tags()` for reasoning models.
   - **OpenAI (`agent/providers/openai_provider.py`)**: Leverages `response_format={"type": "json_schema", ...}`.

5. **Secret Sanitization & Zero Leaks**:
   - Raw API keys (`AQ.`, `sk-proj-`, bearer tokens) are scrubbed from container logs, task traces, and issue comments (`LOG_LEAK_COUNT: 0`).

---

## 2. Test Suite & Coverage Evidence

- **Unit Tests**: 255/255 passed in 9.28s.
- **Module Coverage**:
  * `agent/gates/runner.py`: 88%
  * `agent/gates/worker.py`: 93%
  * `agent/harnesses/in_app_sdk.py`: 95%
  * `agent/providers/errors.py`: 100%
  * `agent/providers/gemini.py`: 95%
  * `agent/providers/ollama.py`: 96%
  * `agent/providers/openai_provider.py`: 98%
  * `agent/providers/schema_utils.py`: 98%
  * `kanban/security/scrubber.py`: 100%
  * **Total Coverage**: 95% across touched backend packages (meets >=95% gate standard).

---

## 3. Artifact Index in `docs/qa/KAN-61/`

- `live-fullstack-proof.txt`: Zero-mock live execution telemetry against `kanban-liveqa-2` (`:18962`, commit `9d5577ad9b50`).
- `unit-test-results.txt`: Verbatim pytest execution outputs (255 passed, 95% coverage).
- `build-or-typecheck.txt`: Verbatim static checks and build outputs.
- `git-diff.patch`: Complete git diff patch.
- `api-specialist-review.md`: Dual-specialist API and architecture audit signoff (STATUS: APPROVED).
- `ui-specialist-review.md`: Dual-specialist UI and layout audit signoff (STATUS: APPROVED).
- `verification-summary.md`: Summary of implementation and validation criteria.
- `screenshots/62-ai-provider-gemini-top-key-probe.png`: Gemini provider registration with masked key and probed models.
- `screenshots/63-ai-provider-ollama-probed-models.png`: Fast GPU Ollama provider registration with probed models.
- `screenshots/64-agent-qa-done-definition.png`: Agent definition registration drawer for `@qa-done-gate`.
- `screenshots/65-workflow-attach-qa-done-gate.png`: AttachHookDialog configuring `@qa-done-gate` on `In Progress -> Done`.
- `screenshots/66-qa-gate-positive-approved-done.png`: Positive evaluation result (`KAN-1` transitioned to `Done`, `✅🤖 Approved`).
- `screenshots/67-qa-gate-negative-saturn-ice-cream-vetoed.png`: Negative evaluation result (`KAN-2` vetoed in `In Progress`, `🛑🤖 Rejected`).
- `screenshots/live-qa-gate-positive-approved-done-desktop.png`: Positive evaluation desktop screenshot.
- `screenshots/live-qa-gate-positive-tablet.png`: Positive evaluation tablet screenshot.
- `screenshots/live-qa-gate-positive-mobile.png`: Positive evaluation mobile screenshot.
- `screenshots/live-qa-gate-negative-saturn-ice-cream-vetoed-desktop.png`: Negative evaluation desktop screenshot.
- `screenshots/live-qa-gate-negative-tablet.png`: Negative evaluation tablet screenshot.
- `screenshots/live-qa-gate-negative-mobile.png`: Negative evaluation mobile screenshot.
- `screenshots/live-workflow-attach-qa-done-gate-desktop.png`: Workflow attachment desktop screenshot.
