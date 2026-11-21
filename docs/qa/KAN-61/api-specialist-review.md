# Clean-Room API Specialist Review: KAN-61

- **Ticket:** KAN-61 (`[KB-AI-HARNESS-01]`)
- **Title:** Multi-Provider In-Transition AI Agent Harness: Flat Verdict Schema, Strict Schema Dereferencing, Cutoff Timeouts, and Fail-Closed Workflow Gate UI
- **Reviewer:** `api-spec-2` (Clean-Room Backend / API / Security Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-61`
- **Branch:** `main` (commit `9d5577ad9b50`)
- **Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Verification Scope

A clean-room API, Security, Schema, and Contract audit was conducted for ticket **KAN-61** integrated into `main` at commit `9d5577ad9b50`. The review integrates empirical evidence from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-2` (`http://127.0.0.1:18962`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-61/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-61/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

KAN-61 provides the multi-provider transition harness that enables automated, secure, and fail-closed AI agent evaluations on issue transitions (specifically `In Progress -> Done`).

Key architectural and security invariants certified:

1. **Wire Verdict Schema & Dereferencing (`agent/providers/schema_utils.py`)**:
   - Implemented `dereference_json_schema()` to resolve internal `$defs` or `$ref` pointers into self-contained inlined JSON schemas for local edge models (Ollama grammar constraints) and cloud providers (OpenAI / Gemini structured outputs).
   - Enforces `StrictVerdictSchema` (`kb-transition-verdict/v1`):
     * `decision`: Literal["approve", "reject"]
     * `reason_markdown`: str
     * `add_labels`: list[str]
     * `cited_files`: list[str]
   - Disallows unparsed prose or unstructured outputs; parsing is strictly validated against the model schema.

2. **Live ProviderRouter Integration in GateWorkerRunner (`agent/gates/runner.py`)**:
   - `GateWorkerRunner` directly integrates `ProviderRouter` to instantiate live providers with cryptographic envelope decryption (`dek_kid`), timeout enforcement, and network guard bounds.
   - Nonce-sealed requests prevent replay attacks across transition events.
   - Deferred column handling: inspected `provider_row.dek_kid` and `provider_row.__dict__` to prevent `sqlalchemy.exc.MissingGreenlet` errors when loading `AIProviderConfig`.

3. **Strict Cutoff Enforcement & Fail-Closed Semantics**:
   - Enforces `timeout_ms = min(provider.timeout_ms, agent.timeout_ms)`.
   - If an evaluation exceeds `timeout_ms` or the provider fails, the gate fails closed:
     * Card is retained in `In Progress`.
     * State is recorded as `timed_out` or `vetoed`.
     * A persistent audit comment is posted to the ticket (`🛑🤖 Gate timed out after ... ms`).
     * Zero hung background worker threads or zombie tasks.

4. **Multi-Provider Protocol Adaptations**:
   - **Google Gemini (`agent/providers/gemini.py`)**: Supports `AQ.` keys configured against `https://generativelanguage.googleapis.com` via `ai_studio_paid` mode with `api_version="v1beta"`, utilizing `response_mime_type="application/json"` and `response_schema`.
   - **Ollama (`agent/providers/ollama.py`)**: Inlines JSON schema into the `format` parameter; cleans `<think>...</think>` tags via `strip_think_tags()` for deep reasoning models (e.g., Nemotron, DeepSeek).
   - **OpenAI (`agent/providers/openai_provider.py`)**: Leverages `response_format={"type": "json_schema", "json_schema": {"strict": True, ...}}`.

5. **Secret Sanitization & Zero Leaks (`kanban/security/scrubber.py`)**:
   - Zero API keys (`AQ.`, `sk-proj-`, bearer tokens) leak into container logs, task traces, or ticket activity comments.

---

## 2. Live Container Verification (`kanban-liveqa-2`, `:18962`, commit `9d5577ad9b50`)

Empirical testing on `kanban-liveqa-2` validated all 6 model configurations across positive (`KAN-1`) and negative (`KAN-2`) transition requests:
- **Fast GPU Ollama (`192.168.1.115:11434`) `gemma3:4b`**: Positive `approve` (`Done`, 31,431 ms); Negative `reject` (vetoed in `In Progress`, 16,630 ms).
- **Fast GPU Ollama (`192.168.1.115:11434`) `granite3.3:2b`**: Positive `timed_out` at 20,000 ms (fail-closed); Negative `reject` (vetoed in `In Progress`, 12,691 ms).
- **AI Supercomputer Ollama (`192.168.1.101:11434`) `gemma4:e2b`**: Positive `approve` (`Done`, 19,892 ms); Negative `reject` (vetoed in `In Progress`, 5,213 ms).
- **AI Supercomputer Ollama (`192.168.1.101:11434`) `nemotron-3-super:latest`**: 5s cutoff triggered `GATE_TIMEOUT` at 6,023 ms (fail-closed); 45s cutoff returned Positive `approve` (31,940 ms) and Negative `reject` (26,502 ms).
- **Google Gemini (`gemini-2.5-flash-lite`)**: Positive `approve` (`Done`, 3,215 ms); Negative `reject` (vetoed in `In Progress`, 1,594 ms).
- **OpenAI (`gpt-4o-mini`)**: Positive `approve` (`Done`, 3,846 ms); Negative `reject` (vetoed in `In Progress`, 2,224 ms).

---

## 3. Unit Test & Static Check Evidence

- **Pytest**: 255/255 passed in 9.28s.
- **Coverage**: 95% total module coverage across all touched backend packages.
- **Static Checks**: 0 lint errors, 0 type errors.
- **Dashes**: 0 unicode em/en-dashes.

---

## 4. Final Verdict

STATUS: APPROVED
The backend multi-provider AI agent harness satisfies all security, performance, and contract requirements.
