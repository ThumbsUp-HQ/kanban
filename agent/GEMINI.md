# Agent Runtime Module Manifest (`kanban-agent`)

## Responsibility
Multi-provider LLM and autonomous agent runtime supporting OpenAI, Ollama, and Gemini providers, as well as zero-shell CLI pipe harnesses (agy -p, codex -p) and outbound mTLS remote repository runners. Powers ScriptRunner-style workflow transition interceptors, permission-filtered inline cursor completions, sticky-to-doc synthesis, and semantic search.

## Depends On
- `mcp` (`kanban-mcp` package for invoking platform MCP tools and resources).

## Depended On By
Top-level platform orchestration and workflow triggers (highest layer in workspace hierarchy).

## Inbound Contracts
- Workflow transition events, inline completion requests, and autonomous agent task triggers.
- Pluggable deterministic AI Response Fixtures (FixtureLLMProvider, FixtureCLIRunner) for fast offline test isolation.

## Outbound Contracts
- Structured prompts and tool calls dispatched to configured LLM backends and CLI harnesses.
- Model Context Protocol tool execution requests dispatched to kanban-mcp using on-behalf-of (OBO) user context.

## Performance Budgets
- Inline cursor Sparkle completion FIM latency < 150ms.
- Offline fixture-based agent test execution < 10ms per scenario.
- CLI runner subprocess execution timeout default 30 seconds.

## Failure Modes
- Upstream provider rate limiting (HTTP 429) triggering exponential backoff retry.
- Provider authentication failure halting transition pipeline.
- CLI runner subprocess failure or timeout marking transition gate failed.
- Model output schema validation error failing closed.

## CLI Framework Contract (`kanban-agent`)

The `kanban-agent` command-line interface provides a typed, zero-shell manual validation workbench for local agent evaluation and testing:

- Entry Point: `kanban-agent` (`agent.cli:main`), registered via `pyproject.toml`.
- Subcommand Registry: `register_subcommand(SubcommandSpec(...))` provides extensibility for future interceptor and agent validation tools (`validate-transition`, `validate-sparkle`, `validate-sticky-promo`, `validate-qa-packet`).
- Standard Flags: `--provider` (e.g. `fixture`), `--model` (e.g. `fixture-echo-v1`), `--cassette` (YAML path), `--verbose-tools` (full tool args and results), `--report` (`text` or `json`).
- Context Scrubbing: Pluggable `ContextScrubber` callable hook sanitizing secret tokens before terminal rendering or log storage.

### Standard 4-Section Validation Report Schema

Every `validate-*` command emits a structured `ValidationReport` containing four sections:
1. `=== 1. RENDERED CONTEXT ===`: Exact rendered prompt or context after passing through the context scrubber.
2. `=== 2. TOOL TRACE ===`: Summary count and tool names by default, or full JSON arguments and return payloads when `--verbose-tools` is specified.
3. `=== 3. LATENCY & TOKENS ===`: TTFT latency, total execution duration, prompt and completion token counts, and routing trace.
4. `=== 4. SCHEMA & POLICY STATUS ===`: Boolean validity flag (`valid: true` or `valid: false`), outcome status string, error code, and failure detail.

### Deterministic Exit Codes

The CLI strictly produces three deterministic integer exit codes:
- `0` (`ExitCode.OK`): Execution succeeded and schema/policy constraints were fully satisfied.
- `1` (`ExitCode.RUNTIME_ERROR`): Infrastructure runtime errors, upstream HTTP 4xx/5xx faults, missing cassette files, or uncaught exceptions.
- `2` (`ExitCode.SCHEMA_OR_POLICY_VIOLATION`): CLI argument errors, cassette mismatch/validation failures, model schema validation failures, safety blocks, policy refusals, or TTFT SLA breaches.

## Ollama Provider Adapter (`OllamaProvider`)

The `OllamaProvider` adapter implements the `@runtime_checkable LLMProvider` protocol for local and self-hosted Ollama daemons, supporting Fill-In-the-Middle (FIM) streaming, structured JSON schema output, and batch vector embeddings.

### Network Contract & SSRF Defenses

1. `resolve_and_pin(url, allowed_cidrs)`:
   - Synchronously or asynchronously resolves the host to all IPv4 and IPv6 addresses via `getaddrinfo`.
   - Validates that every resolved address belongs to the configured CIDR allowlist (defaults to `127.0.0.0/8`, `::1/128`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`).
   - Strictly enforces hard-denied metadata and link-local networks (`169.254.0.0/16`, `fe80::/10`, `fd00:ec2::254/128`, `0.0.0.0/8`, `::/128`, `224.0.0.0/4`, `ff00::/8`, and IPv4-mapped IPv6 `::ffff:169.254.0.0/112`).
   - If ANY resolved address is hard-denied or falls outside the allowed CIDRs, the request fails immediately to prevent DNS rebinding attacks.
   - Rewrites outbound request target to the pinned IP with SNI / Host header preserved.
2. Optional mTLS Transport:
   - Configurable via `ca_cert_path`, `client_cert_path`, and `client_key_path` in `OllamaSettings`.
3. Strict Streaming and Size Limits:
   - Per-line stream size capped at 64 KiB (`LINE_TOO_LARGE` / `ProviderProtocolError` on overflow).
   - Maximum response payload capped at 16 MiB.
   - Batch embeddings capped at 512 texts per request.
   - HTTP redirects (3xx) are strictly refused (`REDIRECT_REFUSED` / `ProviderProtocolError`).

### Specific Error Codes

- `OLLAMA_METADATA_DENIED`: Target host resolves to hard-denied cloud metadata or link-local network.
- `OLLAMA_CIDR_DENIED`: Target host resolves to an IP outside the configured CIDR allowlist.
- `MODEL_NOT_ALLOWED`: Requested model name is not in the configured `allowed_models` list.
- `REDIRECT_REFUSED`: Ollama daemon responded with an HTTP redirect (3xx), which is prohibited.
- `LINE_TOO_LARGE`: SSE/JSON stream line exceeded the 64 KiB safety threshold.
- `BATCH_TOO_LARGE`: Batch embedding request exceeded 512 input texts.


## Gemini Provider Adapter (`GeminiProvider`)

The `GeminiProvider` adapter implements the `@runtime_checkable LLMProvider` protocol over the official `google-genai` SDK, supporting Vertex AI and paid Google AI Studio endpoints with strict data residency pinning, explicit safety settings, and zero prompt retention.

### Architecture and Data Residency

1. Pinned Data Residency & Zero Prompt Retention:
   - Supports two mutually exclusive execution modes: `vertex` and `ai_studio_paid`.
   - The free AI Studio tier (`ai_studio`) is strictly prohibited and unrepresentable, ensuring enterprise-grade zero prompt retention.
   - For `vertex` mode, requires explicit regional pinning (`vertex_location` within `allowed_vertex_regions`). The `"global"` region is strictly rejected.
   - Residency tier identifier exposed as `f"gemini-vertex:{vertex_location}"` or `"gemini-ai-studio-paid"`.
2. Credential Isolation & Secret Redaction:
   - In `vertex` mode, API keys are forbidden (`api_key=None`). Authentication relies on Google Cloud credentials.
   - In `ai_studio_paid` mode, API key is required and wrapped in `SecretStr`.
   - API keys are strictly redacted from `repr`, `str`, log statements, and exception messages (`_redact` helper).
3. Native Structured Output & Local Schema Defense:
   - Configures `response_mime_type="application/json"` and `response_schema` on outbound requests.
   - Model outputs are re-validated locally against the requested Pydantic model (`ProviderSchemaError` on mismatch), enforcing defense-in-depth against malformed JSON or unvalidated fields.
4. Content Safety Filters:
   - Default safety thresholds set `HARM_CATEGORY_HARASSMENT`, `HARM_CATEGORY_HATE_SPEECH`, `HARM_CATEGORY_SEXUALLY_EXPLICIT`, and `HARM_CATEGORY_DANGEROUS_CONTENT` to `BLOCK_MEDIUM_AND_ABOVE`.
   - Chunks or responses with `finish_reason == "SAFETY"` or prompt feedback blocks raise typed `ProviderSafetyBlock`.
5. Size Limits & Batch Bounds:
   - Batch vector embeddings capped at 64 inputs per request (`BATCH_TOO_LARGE` on overflow).
   - Per-input character count capped at 8,192 characters (`INPUT_TOO_LARGE` on overflow).

### Specific Error Codes

- `MODEL_NOT_ALLOWED`: Requested model name is outside the configured `model_allowlist`.
- `BATCH_TOO_LARGE`: Embedding batch contains more than 64 input strings.
- `INPUT_TOO_LARGE`: Embedding input text exceeds 8,192 characters.
- `SAFETY_BLOCK`: Generation or prompt was blocked by content safety filters.
- `SCHEMA_ERROR`: Model output failed local Pydantic schema validation.
- `HTTP_ERROR`: Upstream Gemini or Vertex API returned an HTTP 4xx or 5xx status code.
- `TIMEOUT`: Request exceeded the configured timeout deadline.

## OpenAI Provider Adapter (`OpenAIProvider`)

The `OpenAIProvider` adapter implements the `@runtime_checkable LLMProvider` protocol over `AsyncOpenAI`, supporting streaming completions, strict structured outputs, and batch vector embeddings for OpenAI and OpenAI-compatible inference servers (vLLM, Azure OpenAI, LiteLLM).

### Privacy, Residency & Security Guarantees

1. Zero Data Retention Mandate (`store=False`):
   - Every outbound chat completion request strictly enforces `"store": false` via the private `_chat_kwargs()` builder, ensuring prompts and completions are never logged or stored for training by OpenAI.
2. Endpoint URL & SSRF Validation:
   - Base URLs must use `https://` unless targeting local loopback addresses (`127.0.0.1`, `::1`, `localhost`) for self-hosted inference servers.
   - Userinfo (`user:pass@host`), query parameters, and fragments are strictly rejected.
3. Deterministic Retries & Client Isolation:
   - Initialized with `max_retries=0`, delegating all failover and retry decisions to the platform router.
   - Configured with `trust_env=False` and `follow_redirects=False` to prevent ambient proxy interception and redirect abuse.
   - HTTP redirects (3xx) raise `ProviderProtocolError` with code `REDIRECT_REFUSED`.
4. Strict Structured Outputs:
   - Uses `response_format` with `type: "json_schema"` and `strict: True`.
   - Recursively enforces `additionalProperties: False` and ensures all properties are marked required across all object schemas.
   - Local validation via Pydantic model ensures schema compliance; refusals raise `ProviderRefusal`.
5. Secret Protection:
   - `api_key` is encapsulated in Pydantic `SecretStr` and excluded from `repr()`, logs, and exception strings.
