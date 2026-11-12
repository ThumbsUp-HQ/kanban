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

