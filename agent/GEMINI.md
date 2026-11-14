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

## Provider Router & Resilience (`ProviderRouter`, `CircuitBreaker`, `AirGapGuard`)

The `ProviderRouter` wraps multi-candidate provider pools with 3-state per-(workspace, provider) circuit breakers, data-residency locking, and fail-closed air-gap enforcement.

### Circuit Breaker Invariants (`CircuitBreaker`)

- State Key: `(workspace_id: UUID, provider_config_id: UUID)` stored in an in-process dictionary (per-replica state).
- Three-State Machine:
  * `CLOSED`: Normal operation. Availability failures increment consecutive failure counter.
  * `OPEN`: Reached failure threshold (`DEFAULT_FAILURE_THRESHOLD = 5`). Outbound requests skip this candidate without network I/O.
  * `HALF_OPEN`: Cooldown period (`DEFAULT_OPEN_COOLDOWN_S = 30.0s`) has elapsed. Admits exactly 1 probe call. Probe success resets failure count to 0 and transitions to `CLOSED`. Probe failure restarts cooldown and transitions back to `OPEN`.
- Trip Conditions:
  * `ProviderHTTPError` with status `429` or `>= 500`.
  * `ProviderTimeout` (including TTFT SLA breach).
  * `ProviderUnavailable`.
- Content/Policy Exemptions: `ProviderSchemaError`, `ProviderSafetyBlock`, `ProviderRefusal`, `ProviderPolicyError` do NOT trip the breaker (they represent content or policy decisions, not provider availability).
- Retry-After Backoff: An HTTP 429 response carrying a `Retry-After` header extends cooldown to `max(open_cooldown_s, retry_after_s)` capped at `MAX_COOLDOWN_S = 300.0s`.

### Air-Gap Enforcement (`AirGapGuard`)

- Fail-Closed Policy: If `air_gap_mode` is `True` or unspecified (`None`), external cloud egress is forbidden.
- Allowed Providers Under Air-Gap: Strictly `ollama` (local loopback/CIDR pinned) and `fixture` (offline testing).
- Rejection Barrier: Calls to `gemini` or `openai` raise `EgressDenied(code="AIR_GAP_EGRESS_DENIED")` BEFORE provider construction, DNS resolution, or socket allocation.

### Routing & Failover Invariants (`ProviderRouter`)

- Residency Locking: Candidates are prioritized by `priority` ascending. The first healthy candidate selected fixes the request's `residency_tier`. Any subsequent failovers MUST stay within that exact same residency tier (cloud never fails over to a different vendor tier; air-gapped workloads never fail over to cloud).
- Max Attempts: Capped at `min(len(eligible), 3)` attempts per request.
- Streaming Failover Barrier: Failover is permitted strictly before the first stream chunk is yielded. Once token streaming begins, upstream faults propagate immediately to prevent mixed-model corrupted generation.
- TTFT SLA Enforcement: When `ttft_deadline_ms` is configured, waiting for the first chunk is bounded by `asyncio.timeout`. Expiry invokes `aclose()` on the upstream stream and trips the candidate's circuit breaker with `ProviderTimeout`.

## Local Passive Forensic QA Audit (`kanban-agent validate-qa-packet`, `agent.qa_validator`)

The `validate-qa-packet` subcommand performs deterministic passive proof-bundle checks and a structured reality-checker forensic audit over `docs/qa/<ID>/` proof directories and ticket YAML/Markdown files without executing shell commands, visiting external URLs, or decoding untrusted image payloads.

### Deterministic Proof Bundle Inspector (`agent.qa_validator.bundle_inspector`)

- Pure Passive Containment: Resolves proof directory strictly, rejecting any symlink escaping the proof directory (`PROOF_SYMLINK_ESCAPE`), rejecting FIFOs/devices/sockets (`PROOF_INVALID_ENTRY`), and enforcing a 2 MiB per-file and 16 MiB per-bundle limit (`PROOF_BUNDLE_TOO_LARGE`).
- Passive PNG Inspection: Validates standard PNG header (`89 50 4E 47 0D 0A 1A 0A`) and extracts width and height from the IHDR chunk via `struct.unpack` without running subprocesses or decoding untrusted raster payloads.
- Dual Ticket Parsing: Parses both YAML ticket specifications (`examples/tickets/*.yaml`) and Markdown ticket specifications with YAML frontmatter (`docs/tickets/KB-*.md`).
- Seven Non-Bypassable Deterministic Checks:
  1. `CORE_ARTIFACTS_PRESENT`: Verifies `git-diff.patch`, `unit-test-results.txt`, and `build-check.txt` (or `build-or-typecheck.txt`) exist and are > 0 bytes.
  2. `UNIT_TESTS_EXIT_ZERO`: Verifies `unit-test-results.txt` contains a positive passing summary marker and zero failure or non-zero exit markers.
  3. `BUILD_CHECK_CLEAN`: Verifies `build-check.txt` contains zero unhandled error exit markers or exceptions.
  4. `UI_SPECIALIST_GATE`: If `ui-specialist` is in gates or `[UI]` tag appears, verifies `ui-specialist-review.md` exists with an explicit `APPROVED` verdict, and that `screenshots/` contains >= 3 valid PNG files covering desktop, tablet, and mobile viewports (or explicitly declared `N/A - Non-UI Ticket`).
  5. `API_SPECIALIST_GATE`: If `api-specialist` is in gates or `[API]` tag appears, verifies both `api-specialist-review.md` and `ui-specialist-review.md` exist and contain explicit `APPROVED` verdicts.
  6. `DEPENDENCY_EVALUATION_GATE`: If `new_dependencies` is non-empty or `[DEP]` tag appears, verifies `dependency-evaluation.md` exists and references permissive license, SHA-256 hash, and specialist sign-offs.
  7. `NO_RAW_SECRETS_IN_PROOF`: Scans all text artifacts in the proof directory with `outbound_secret_scrubber`, failing if unredacted live secrets (`sk-*`, `ghp_*`, `AKIA*`, PEM keys, `kb_*`) are present, and redacting them before LLM spotlighting.

### Reality-Checker Forensic Auditor & Anti-Fantasy Gate (`agent.qa_validator.auditor`)

- Passive Forensic Prompt: Ingests `.agents/agents/reality-checker.md` and appends the mandatory passive forensic mode override forbidding subprocess/URL execution.
- Spotlight Isolation: Isolates scrubbed ticket specification and proof artifacts within randomized `<<<UNTRUSTED_QA_EVIDENCE_<hex> >>>` delimiters.
- Hard Anti-Fantasy Invariant: Enforced in code (never trusted to model alone): if any deterministic check failed, OR `verdict.grade != "A"`, OR `len(verdict.critical_issues) > 0`, OR any `dod_verdicts` item has `passed == False`, any claimed `readiness == "READY"` is overridden to `readiness = "NEEDS_WORK"` with `policy_override = "FANTASY_APPROVAL_BLOCKED"`.

## Sparkle FIM Completion Engine (`agent.sparkle`, `agent.asgi`)

The Sparkle (`✨`) FIM engine delivers low-latency, permission-isolated inline completions for Markdown surfaces (Summary, Description, Comment, Sticky, Doc) across the web interface.

### Performance Budgets

- End-to-End Ghost Text Latency: p95 < 150ms over 200 iterations.
- Context Retrieval Database Ceiling: Hard <= 18ms statement_timeout executed under least-privilege `app_rls_reader` and `SET LOCAL TRANSACTION READ ONLY`.
- Provider Streaming TTFT SLA: 115ms time-to-first-token deadline.
- Overall Pipeline Execution Timeout: Hard 130ms overall timeout (`asyncio.timeout(0.130)`).
- Input Payload Bound: Maximum 16 KiB HTTP request body (larger payloads rejected with RFC 7807 413).
- Token Budget: 1-48 tokens generated at temperature = 0.15, capped at 400 characters.

### Defense-in-Depth Pipeline Order

1. Truncate Input: Keeps the last 1,500 characters of prefix and first 500 characters of suffix.
2. Scrub-First Mandate: Evaluates prefix and suffix with `outbound_secret_scrubber` before any network or database I/O. Detection of any secret or API key halts execution immediately, returning `status="secret_scrubbed"` with zero embedder, DB, or provider invocations.
3. Local Vector Embedding: Generates a 384-dimensional dense vector over the last 512 characters of scrubbed prefix using the in-process Int8 ONNX embedder (`bge-small-en-v1.5`).
4. RLS-Pinned Context Retrieval: Executes a dedicated session as role `app_rls_reader` under `READ ONLY` and `statement_timeout = '18ms'`. Session context (`principal_id`, `workspace_id`, `token_scopes`, `aal_level`) is bound strictly from the authenticated `PrincipalContext`. Retrieves up to 4 nearest chunks from `object_embeddings` in the same project and resolves chunk markdown through RLS-protected base tables (`issues`, `docs`, `stickies`, `pages`). Snippets are capped at 400 characters, re-scrubbed, and isolated within per-request random delimiters `<<<UNTRUSTED_CONTEXT_<16 hex>>>>`.
5. Streaming FIM Completion: Streams completion tokens from the configured `ProviderRouter` candidate within residency tier rules.
6. Output Filtering & Defense: Buffers completion tokens before emission. Strips all HTML tags and entity-decoded markup (`<...>`), removes invisible zero-width and unicode tag plane characters (`U+200B..U+200F`, `U+E0000..U+E007F`), rejects prompt-override patterns (e.g. `ignore previous instructions`, `system:`, `[INST]`), and runs `outbound_secret_scrubber` on output (dropping completion if any secret was echoed). Empty outputs return `status="empty"`.
7. SSE Streaming Endpoint: Emits exactly one `event: completion` (when `ok`) and one `event: done` carrying status, TTFT, and total latency. Cache-Control is pinned to `no-store` and `X-Accel-Buffering: no`. Client disconnect cleanly cancels the in-flight pipeline task and provider stream.

### Failure Modes and Fallback Semantics

- Secret Scrubbed: Inbound secret detected in prefix/suffix -> returns `event: done` with `status="secret_scrubbed"` (editor remains IDLE).
- Context Retrieval Timeout: Database statement exceeds 18ms -> `QueryCanceled` caught gracefully, continuing with zero context snippets and `retrieval_status="timeout"`.
- Provider Timeout / SLA Breach: Upstream LLM exceeds 115ms TTFT or 130ms overall timeout -> provider stream closed via `aclose()`, returning `event: done` with `status="timeout"`.
- Provider Unavailable / 429 / 5xx: Upstream provider rate limits or server errors -> trips circuit breaker and returns `event: done` with `status="unavailable"` (HTTP 200, never 5xx).
- Output Filter Rejection: Output contained HTML tags, prompt injection, echoed secret, or empty content -> returns `event: done` with `status="empty"`.
- CSRF Protection: Missing or mismatched `X-CSRF-Token` against cookie `__Host-kb_csrf` -> RFC 7807 403 Forbidden.
- Permission Check: Caller lacks EDIT on `object_id` (when provided) or VIEW on `project_id` -> timing-equalized RFC 7807 404 Not Found.
- Body Size Overflow: Request body exceeds 16 KiB -> RFC 7807 413 Payload Too Large.


## Sparkle Manual CLI Validation (`kanban-agent validate-sparkle`)

The `validate-sparkle` CLI tool exercises the exact production `run_sparkle_pipeline()` from the terminal for a given Markdown string with a `|` cursor marker, executing strictly within a specified user's RLS scope against live or fixture providers.

### Usage and Flags

```bash
uv run kanban-agent validate-sparkle \
  --provider {ollama,gemini,openai,fixture} \
  --input-markdown "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind." \
  --project KAN \
  --as-user "@adam" \
  [--model MODEL] \
  [--cassette PATH] \
  [--http-cassette PATH] \
  [--iterations N] \
  [--surface {summary,description,comment,sticky,doc}] \
  [--report {text,json}] \
  [--database-url URL] \
  [--verbose-tools]
```

### Key Technical Contracts

1. Cursor Marker Parsing:
   - Exactly one unescaped `|` pipe character is required.
   - Escaped `\|` sequences are preserved as literal pipe characters.
   - Zero or multiple unescaped markers reject with exit code 2 and status `CURSOR_MARKER_INVALID`.
2. Strict RLS Scope & Non-Bypass Enforcement:
   - Evaluates caller role via `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user`.
   - If connected role has `rolsuper = true` or `rolbypassrls = true`, execution halts immediately with exit code 2 and status `RLS_BYPASS_ROLE_REFUSED`.
   - Resolves `--as-user @handle` and `--project KEY` within the tenant workspace. Unknown users or projects trigger exit code 2 with `PRINCIPAL_NOT_FOUND` or `PROJECT_NOT_FOUND`.
   - Binds `PrincipalContext(principal_id, workspace_id)` and retrieves nearest embeddings strictly through `RLSSessionFactory`, preventing cross-tenant or unauthorized canary leakage.
3. Secret Scrub-First Mandate:
   - Inbound text is scrubbed before pipeline execution. If an API token or credential is detected, execution halts with exit code 2 and status `secret_scrubbed` with zero provider calls.
   - Raw secrets are never printed to terminal stdout or serialized JSON reports.
4. Structured 4-Section Output & JSON Schema:
   - Text report renders Section 1 (Rendered Context), Section 2 (Tool Trace), Section 3 (Latency & Tokens), Section 4 (Schema & Policy Status), and Section 5 (Route Trace).
   - Multi-iteration runs (`--iterations N`, 1..500) print percentile statistics (`p50`, `p90`, `p95`, `p99`). If `p95 > 150.0ms`, the command fails with exit code 2 and status `LATENCY_SLA_BREACH`.
   - JSON report (`--report json`) validates strictly against schema `kb-sparkle-report/v1` with `additionalProperties: false`.
5. Deterministic Exit Codes:
   - `0`: Valid completion accepted (`status == "ok"`).
   - `1`: Infrastructure runtime error (`DATABASE_UNREACHABLE`, `PROVIDER_UNAVAILABLE`).
   - `2`: Schema/policy refusal (`CURSOR_MARKER_INVALID`, `RLS_BYPASS_ROLE_REFUSED`, `PRINCIPAL_NOT_FOUND`, `PROJECT_NOT_FOUND`, `SECRET_SCRUBBED`, `TTFT_TIMEOUT`, `LATENCY_SLA_BREACH`, output filter drops).

## Token Budget Enforcer (`agent.budget`, KB-P5-05a, S10.2)

The `BudgetEnforcer` provides atomic LLM token allocation and settlement protocols across daily and monthly period caps stored in `ai_token_ledgers`:

- Atomic Reserve/Settle Protocol:
  - `reserve(workspace_id, project_id, provider_config_id, estimate_tokens)` executes atomic single-statement updates against active period windows (`daily` and `monthly`). If any active cap is exhausted, the reservation rolls back immediately and raises `BudgetExceeded(code="AI_BUDGET_EXCEEDED", period="daily"|"monthly")`.
  - Missing ledger rows for a period explicitly indicate unconstrained budget for that period.
  - `settle(reservation, actual_tokens)` moves `min(actual, estimate)` tokens from reserved to used and clears remaining reservations. Post-hoc overages (`actual > estimate`) record full token usage without blocking and log `AI_BUDGET_OVERAGE`.
  - `release(reservation)` restores all reserved tokens to zero on upstream provider failures or timeouts.
- Concurrency Invariant:
  - Atomic single-statement updates serialized at the PostgreSQL row level guarantee that under high concurrent contention (e.g. 50 parallel requests), no burst of agent calls can exceed a configured cap.
- Time Boundaries:
  - Period starts are computed strictly in UTC (`daily` at `YYYY-MM-DD`, `monthly` at `YYYY-MM-01`).




