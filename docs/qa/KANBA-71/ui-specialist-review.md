# UI Specialist Gate Final Audit: APPROVED for KANBA-71 (KB-P5-16)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-71`
- Branch: `feat/KANBA-71`
- Ticket: `KANBA-71` (`KB-P5-16`: `[Phase 5 / Database + API] agent_definitions registry, CLI binary allowlist & banned-flag validation (save + runtime)`)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend contract, API error ergonomics, and UX readiness audit was conducted for `KANBA-71` in `/tmp/kb-wt-KANBA-71`. While `KB-P5-16` is a backend database and REST API ticket without direct frontend screenshots (Screenshots: N/A - Non-UI Ticket per KB-P5-16 proof criteria), it establishes the core data contracts and error boundaries for the upcoming Agent Studio UI (`KB-P5-24`). All request/response schemas, discrete RFC 7807 problem details, CLI policy error payloads, timing equalization, and canonical Markdown normalization were forensically evaluated against S14.2, S14.3, and Section 5.4 architecture specifications.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **API Error Ergonomics** | Discrete RFC 7807 problem details for UI form binding | Discretely typed problem codes (`BANNED_CLI_FLAG`, `CODEX_SANDBOX_OVERRIDE`, `CLI_BINARY_NOT_ALLOWLISTED`, `CLI_ARGS_INVALID`, `HARNESS_FIELDS_INVALID`, `AGENT_IN_USE`) | PASS |
| **Form Stepper Contracts** | Strict harness field mutual exclusion | `in_app_sdk`, `cli_pipe`, and `remote_runner` mutual exclusion enforced cleanly via Pydantic validators | PASS |
| **CLI Argument Tokenization** | Index-annotated argument validation | Argument index and offending token reported in `detail`, enabling per-pill field errors in UI tag inputs | PASS |
| **Canonical Markdown Safety** | Safe system instructions handling | `system_instructions_md` normalized via `normalize_to_markdown()` with 64 KiB ceiling and surrogate safety | PASS |
| **Timing Equalization** | Anti-enumeration timing floor | 25.0ms `timing_floor` on GET/PATCH/DELETE endpoints defeats side-channels within 100ms UX budget | PASS |
| **Deletion Dependency Guard** | 409 Conflict on transition hook reference | `AGENT_IN_USE` problem returned when agent is bound to active hooks, preventing dangling references | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 53/53 passed in 3.93s; `kanban.agents` achieved 97.76% coverage (exceeds >=95.00% requirement) | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (582 files), Mypy strict clean (212 files), Lint-imports clean (2 kept, 0 broken) | PASS |

---

### 2. Frontend Contract & UX Ergonomics Audit for Agent Studio (`KB-P5-24`)

1. **Discrete RFC 7807 Problem Codes for UI Form Binding:**
   - In modern single-page applications, generic 422 `VALIDATION_ERROR` payloads force UIs into brittle string parsing to display inline field errors.
   - `KANBA-71` provides high-precision, machine-readable problem codes matching `urn:kanban:problem:<CODE>`:
     * `BANNED_CLI_FLAG`: Emitted when an argument matches banned flags (e.g., `--yolo`, `--full-auto`, `--dangerously*`). The `detail` field identifies the exact index and argument (e.g., `"Argument at index 1 ('--yolo') violates banned CLI flag policy"`), allowing Agent Studio to render an inline error pill directly underneath the offending token.
     * `CODEX_SANDBOX_OVERRIDE`: Emitted when `codex` is missing the mandatory `['-p', '-s', 'read-only']` prefix or attempts sandbox bypass (`-s`, `--sandbox`, `-c`, `--config`). Enables the UI to offer an automated "Fix Prefix" action button.
     * `CLI_BINARY_NOT_ALLOWLISTED`: Emitted when an unsupported executable is provided, allowing the UI dropdown to highlight available options (`agy`, `codex`, `gemini-cli`, `claude-code`).
     * `CLI_ARGS_INVALID`: Emitted when argument count exceeds 32, byte length is outside 1..256 bytes, or control characters (NUL, CR, LF) are detected.
     * `HARNESS_FIELDS_INVALID`: Emitted when required fields for the chosen harness kind are missing or mutually exclusive fields are populated. This supports dynamic form field visibility in the Agent Studio harness selector.
     * `AGENT_IN_USE`: Emitted on `DELETE` when active transition interceptor hooks bind the agent, enabling a clear confirmation/warning modal listing active usages.

2. **System Instructions Markdown Normalization & Bounds:**
   - System prompts are stored as canonical Markdown in `system_instructions_md`.
   - Length is enforced with a strict 64 KiB ceiling (`MAX_INSTRUCTIONS_BYTES = 65536`).
   - Normalization via `normalize_to_markdown()` strips invisible Unicode directional and tag characters, disarms dangerous script/URI links, and formats content canonically.
   - Malformed Unicode (such as lone surrogates) is caught at validation time and returned as an RFC 7807 problem rather than throwing an unhandled 500 server crash, preserving a smooth authoring experience in ProseMirror or Monaco editor components.

3. **Anti-Enumeration Timing Equalization (25.0ms):**
   - The endpoints `GET /api/v1/agent-definitions/{agent}`, `PATCH /api/v1/agent-definitions/{agent}`, and `DELETE /api/v1/agent-definitions/{agent}` wrap their execution in `async with timing_floor(floor_ms=25.0)`.
   - This prevents malicious actors from probing workspace agent existence via response latency discrepancies between existing and non-existing records.
   - From a UI perspective, 25.0ms is well below the standard 100ms human perception threshold, ensuring that Agent Studio navigation, detail drawers, and update operations feel instantaneous.

4. **Security & Data Sanitization Invariants:**
   - All response payloads use `AgentDefinitionResponse` with `extra="forbid"`, preventing accidental field leakage.
   - Principal IDs and workspace relationships are strictly bound under PostgreSQL `FORCE ROW LEVEL SECURITY`.
   - The double-gated execution invariant (`validate_cli_args` at save time + `assert_runtime_argv` at invocation time) ensures complete defense-in-depth against direct database manipulation.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-71/docs/qa/KANBA-71/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-71`.

Verdict: APPROVED