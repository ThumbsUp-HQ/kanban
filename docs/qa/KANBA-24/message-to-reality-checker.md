# Reality-Checker Verification Handoff: KANBA-24 (KB-P0-13)

- Ticket ID: `KANBA-24` (`KB-P0-13`)
- Epic: `KB-E0` (Phase 0 Foundations)
- Spec Sections: S15.3, S15.2
- Implementing Author: `builder-19`
- Branch: `feat/KANBA-24`
- Base Commit: `75eb4e4ebbec9e0ba33f0cd11575728acc4c2253`

---

## 1. Summary of Changes

This ticket delivers the core typed CLI framework skeleton for `kanban-agent`, establishing the uniform terminal execution harness, typed subcommand registry, shared provider/model/verbosity flags, the standardized 4-section validation report (`ValidationReport`), deterministic integer exit codes (`0`, `1`, `2`), and a working `validate-echo` demonstration subcommand backed by `FixtureLLMProvider`:

1. `agent/cli_report.py`:
   - `ExitCode(IntEnum)`: `OK = 0`, `RUNTIME_ERROR = 1`, `SCHEMA_OR_POLICY_VIOLATION = 2`.
   - `map_exception_to_exit_code()`: Maps typed exceptions from `agent.providers.errors` and `agent.testing.fixtures` to deterministic exit codes.
   - `ReportMetrics`, `SchemaStatus`, `ValidationReport`: Frozen Pydantic v2 data models conforming to `kb-cli-validation-report/v1`.
   - `render_report()`: Emits 4 literal headings (`=== 1. RENDERED CONTEXT ===`, `=== 2. TOOL TRACE ===`, `=== 3. LATENCY & TOKENS ===`, `=== 4. SCHEMA & POLICY STATUS ===`) for text output and valid JSON for json output.
   - `default_context_scrubber`: Identity context scrubber callable.

2. `agent/cli.py`:
   - `SubcommandSpec`: Specification dataclass for typed subcommand registration.
   - `register_subcommand()`, `get_registered_subcommands()`: Thread-safe in-memory subcommand registry rejecting duplicates with `ValueError`.
   - `add_common_agent_flags()`: Configures `--provider`, `--model`, `--cassette`, `--verbose-tools`, `--report`.
   - `_CustomArgumentParser`: Overrides `error()` to exit with code `2` (`SCHEMA_OR_POLICY_VIOLATION`) and emit structured error text without tracebacks.
   - `main()` and `_async_main()`: Asynchronous execution pipeline supporting custom `ContextScrubber` injection.
   - Built-in registration of `validate-echo`.

3. `agent/cli_commands/validate_echo.py`:
   - `EchoVerdict`: Schema model for structured echo responses.
   - `configure_validate_echo_parser()`: Configures `--prompt` (default `"Hello Sparkle"`), `--mode` (`stream` or `structured`), `--ttft-deadline-ms`.
   - `handle_validate_echo()`: Orchestrates execution against `FixtureLLMProvider`, measures wall-clock latency, handles streaming/structured replaying, and produces `ValidationReport`.

4. `agent/pyproject.toml`:
   - Added `[project.scripts] kanban-agent = "agent.cli:main"` entrypoint.

5. `agent/GEMINI.md`:
   - Added full documentation of CLI framework contract, subcommand registry, 4-section report schema, and deterministic exit codes.

6. `tests/fixtures/ai/`:
   - Updated `echo_stream_ok.yaml` and `fault_429.yaml` matchers to support flexible local manual CLI validation while preserving all existing fixture tests.

7. `agent/tests/cli/test_cli_skeleton.py`:
   - Comprehensive unit test suite covering all 5 mandatory test cases from KB-P0-13 with 99.28% branch and line coverage.

---

## 2. Traceability Matrix

| Requirement | Implementation Artifact | Verification Test / Evidence |
| :--- | :--- | :--- |
| Entrypoint registration | `agent/pyproject.toml` (`kanban-agent = "agent.cli:main"`) | `test_case_5_extensibility_and_boundaries` (subprocess smoke) |
| Subcommand registry | `agent/cli.py` (`SubcommandSpec`, `register_subcommand`) | `test_case_5_extensibility_and_boundaries` (duplicate rejection, lookup) |
| Standard agent flags | `agent/cli.py` (`add_common_agent_flags`) | `test_case_1_positive_text_report`, `test_case_2_positive_json_and_verbose_tools` |
| Deterministic exit codes | `agent/cli_report.py` (`ExitCode`: 0, 1, 2) | `test_cli_report_formatting_and_mapping`, `test_case_3`, `test_case_4` |
| 4-Section report text/JSON | `agent/cli_report.py` (`render_report`) | `test_case_1_positive_text_report`, `test_case_2_positive_json_and_verbose_tools` |
| Pluggable ContextScrubber | `agent/cli.py`, `agent/cli_report.py` (`ContextScrubber`) | `test_case_5_extensibility_and_boundaries` (redaction check) |
| validate-echo demo command | `agent/cli_commands/validate_echo.py` | `test_case_1`, `test_case_2`, `test_case_3`, `test_case_4` |
| Zero non-ASCII dashes | All modified files | ASCII validation script |
| Zero new dependencies | `agent/pyproject.toml` | Verified lockfile and dependency check |

---

## 3. Definition of Done Compliance

- [x] **File Existence & Implementation:** `agent/cli.py`, `agent/cli_report.py`, `agent/cli_commands/validate_echo.py` exist; `agent/pyproject.toml` defines `kanban-agent = "agent.cli:main"`; `ExitCode` defines `OK = 0`, `RUNTIME_ERROR = 1`, `SCHEMA_OR_POLICY_VIOLATION = 2`.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest agent/tests/cli/test_cli_skeleton.py -q --cov=agent.cli --cov=agent.cli_report --cov=agent.cli_commands --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with 0 failures (11 passed, 99.28% coverage).
- [x] **Build / Type / Lint Clean:** `uv run ruff check agent && uv run ruff format --check agent && uv run mypy --strict agent && uv run lint-imports` exits `0`.
- [x] **CLI Manual Validation Proof:** `cli-run.txt` captures `uv run kanban-agent validate-echo` exiting `0` (`text` and `json`), `fault_429.yaml` exiting `1`, and TTFT SLA breach exiting `2`.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-24/`.

---

## 4. Verification Proof Artifact Index

1. `docs/qa/KANBA-24/build-check.txt`: Clean outputs of `ruff check`, `ruff format --check`, `mypy --strict`, and `lint-imports`.
2. `docs/qa/KANBA-24/unit-test-results.txt`: Pytest execution log with coverage report (99.28% coverage, 0 failures).
3. `docs/qa/KANBA-24/cli-run.txt`: Unedited stdout/stderr and exit codes for invocations (a), (b), (c), and (d).
4. `docs/qa/KANBA-24/git-diff.patch`: Unified diff of all modifications.
5. Screenshots: N/A - Non-UI backend CLI ticket.
