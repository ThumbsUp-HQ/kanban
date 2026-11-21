# KAN-61 Verification Summary: Native Structured Outputs & Live Provider Harness

## Overview
Ticket: KAN-61 (`[KB-AI-HARNESS-01] Native Structured Outputs, Live ProviderRouter Wiring in GateWorkerRunner, Gemini AQ. Key Support, & Strict Cutoff Failover`)
Branch: `feat/KAN-61-ai-harness`

## Key Implementations

1. **Harden Native JSON Schema Structured Outputs Across Ollama, Gemini, and OpenAI**:
   - Implemented `agent/providers/schema_utils.py` with `dereference_json_schema`, `clean_gemini_schema`, `make_strict_json_schema`, and `strip_think_tags`.
   - In `InAppSdkHarness` (`agent/harnesses/in_app_sdk.py`), introduced `StrictVerdictSchema` with flat, explicit properties (`decision: Literal["approve", "reject"]`, `reason_markdown: str`, `add_labels: list[str]`, `cited_files: list[str]`). Replaced untyped `field_updates: dict[str, Any]` and `add_links: list[dict[str, Any]]` on the LLM wire schema to prevent schema rejection in OpenAI `strict: true` and Gemini `response_schema`, and mapped responses back into the canonical `TransitionVerdictPayload` / `TransitionVerdict` (`kb-transition-verdict/v1`) with `nonce = ctx.verdict_nonce`.
   - In `OllamaProvider` (`agent/providers/ollama.py`): prepended non-empty `system_prompt` to `messages`, passed `options: {temperature, num_predict}`, passed dereferenced `$defs`-free schema in `format`, and stripped `<think>...</think>` tags from reasoning model responses (`deepseek-r1`, `nemotron-3-super`, `qwen3`).
   - In `GeminiProvider` (`agent/providers/gemini.py`): cleaned schemas via `clean_gemini_schema` (removing `$defs`, `$ref`, `title`, and `default`), and stripped `<think>...</think>` tags.
   - In `OpenAIProvider` (`agent/providers/openai_provider.py`): enforced strict schema with `$defs` dereferencing, and stripped `<think>...</think>` tags.

2. **Gemini AQ. Key Support & Secret Redaction**:
   - Added regex pattern `\bAQ\.[A-Za-z0-9_-]{20,}\b` to secret scrubbing in `agent/providers/errors.py` (`redact_secrets` -> `AQ.[REDACTED]`) and `kanban/security/scrubber.py` (`outbound_secret_scrubber` -> `SecretKind.API_KEY` / `[REDACTED:API_KEY]`).
   - In `agent/providers/gemini.py`, added mode `"vertex_express"` and automatic routing to `genai.Client(vertexai=True, api_key=...)` when key starts with `AQ.`.
   - In `kanban/ai_config/service.py` (`probe_provider`), added automatic fallback probe to Vertex AI Express (`aiplatform.googleapis.com/.../models/gemini-2.5-flash-lite:countTokens`) when an `AQ.` key receives 400/401/403 on Google AI Studio endpoint.

3. **Wire Live Workspace AIProviderConfig & Strict Cutoff Timeout into GateWorkerRunner**:
   - In `agent/gates/runner.py` (`_load_entities`): queried enabled `AIProviderConfig` for the agent's provider kind, unwrapped API key via `AIProviderConfigService.unwrap_api_key`, determined effective cutoff timeout `cutoff_ms = min(int(prov_timeout), int(agent_timeout))` (passing `cutoff_s` to provider and `req.ttft_deadline_ms = min(cutoff_ms, 60000)`), instantiated live provider, registered live `InAppSdkHarness(provider=live_provider)` on registry, and handled unwrap/instantiation errors gracefully without crashing.
   - In `agent/gates/worker.py`: handled `(TimeoutError, ProviderTimeout)` and recorded fail-closed failure code `"GATE_TIMEOUT"`.
   - In `kanban/ai_config/service.py` (`probe_provider`): respected `timeout_ms` / `settings_json.get("timeout_ms")` via `httpx.Timeout` and `asyncio.timeout`.

## Verification Results
- Unit Tests: 255/255 passed in 9.28s.
- Code Coverage: 95% total across modified modules.
- Linter: Ruff check passed with 0 errors.
- Architecture: Import Linter contracts (agent -> mcp -> kanban -> database) passed with 0 broken contracts.
- Typography: Zero unicode em/en-dashes verified via `python3 -m scripts.check_no_dashes --all`.
