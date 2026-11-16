# Message to Reality-Checker: Forensic QA Audit for KANBA-161

**Ticket ID:** `KANBA-161` (`docs/tickets/KB-P5-23.md`)  
**Title:** `[Phase 5 / Agent CLI] kanban-agent validate-transition workbench across in_app_sdk, cli_pipe & remote_runner harnesses`  
**Implementing Agent:** `@p5-156`  
**Date:** 2026-11-15  
**Audit Mode:** Pure passive forensic verification (`docs/qa/KANBA-161/`)

---

## 1. Executive Summary & Verification Evidence

All Technical Actions, Definition of Done criteria, and Forensic Verification Proof requirements specified in `docs/tickets/KB-P5-23.md` have been fully implemented, rigorously validated locally, and assembled into static unedited artifacts in `docs/qa/KANBA-161/`.

| Verification Proof File | Description | Status |
| :--- | :--- | :--- |
| `docs/qa/KANBA-161/unit-test-results.txt` | Raw pytest execution output with coverage metrics (`>= 95%`) | **PASS (96.40% coverage, 9 passed in 8.88s, exit=0)** |
| `docs/qa/KANBA-161/build-check.txt` | Raw static analysis: Ruff linter, Mypy strict, and layer import contracts | **PASS (0 errors, 114 source files clean, exit=0)** |
| `docs/qa/KANBA-161/cli-run.txt` | Raw terminal outputs and exit codes for all 4 required invocations (a)-(d) | **PASS ((a) exit 0, (b) exit 0, (c) exit 0, (d) exit 2)** |
| `docs/qa/KANBA-161/report-sample.json` | Sample JSON report from invocation (b) validated against JSON Schema | **PASS (jsonschema validation clean, additionalProperties: false)** |
| `docs/qa/KANBA-161/git-diff.patch` | Complete unified diff from `origin/main` | **PASS (199 KB unified patch)** |
| Screenshots | N/A - Non-UI ticket | **N/A** |

---

## 2. Deliverables & Technical Actions Audit

### 2.1 CLI Workbench Implementation (`agent/cli_commands/validate_transition.py`)
- **Subcommand Registration:** Registered `validate-transition` in `agent/cli.py` subcommand registry.
- **Harness Support:**
  - `in_app_sdk`: Invokes `InAppSdkHarness` with `ExplicitFixtureLLMProvider` and `_build_mcp_fixture_transport` for canned MCP responses.
  - `cli_pipe`: Invokes `CliPipeHarness` with `ExplicitFixtureCLIRunner` and working-tree read-only snapshot.
  - `remote_runner`: Invokes `RemoteRunnerHarness`. When `--remote-loopback` is supplied, spins up an in-process TLS 1.3 mTLS server (`websockets.serve`) with ephemeral X.509 EC certificates and launches a local `RunnerDaemon` with `LoopbackJobExecutor`.
- **Security & Pipeline Execution:**
  - Runtime CLI argument validation via `assert_runtime_argv` (`KB-P5-16`) fails closed on banned flags (`--yolo`, `CODEX_SANDBOX_OVERRIDE`) with exit code `2`.
  - Context rendering via `build_transition_context()` with dynamic security nonces and random delimiters. Secret redactions strictly applied.
  - Verdict parsing via `parse_verdict_output()` conforming to `kb-transition-verdict/v1`.
  - Working tree immutability: Git object database inspected read-only without modifying `.git` or working-tree files.

### 2.2 Schema & Reporting Aligned (`agent/cli_report.py` & JSON Schema)
- `agent/cli_report.py`: `ValidationReport.schema_version` includes `"kb-validate-transition-report/v1"` and exposes optional `transition_details: dict[str, Any] | None`.
- `agent/schemas/kb-validate-transition-report-v1.json`: Configured with `additionalProperties: false`, strictly validating rendered context, tool traces, metrics, schema status, and transition details.

### 2.3 Sample Configs & Fixtures
- `examples/agents/agy-gate.yaml`: Sample `cli_pipe` configuration using `/usr/local/bin/agy -p`.
- `examples/agents/codex-gate.yaml`: Sample `cli_pipe` configuration using `/usr/local/bin/codex -p -s read-only`.
- `examples/agents/ollama-gate.yaml`: Sample `in_app_sdk` configuration using `qwen2.5-coder:7b` with `bare_git_tools` and MCP read tools.
- `examples/agents/remote-gate.yaml`: Sample `remote_runner` configuration bound to pool `default`.
- `examples/tickets/kan-142.yaml`: Sample ticket specification with user story, technical actions, and definition of done.
- `tests/fixtures/ai/mcp_kan_100_fixture.yaml`: Canned read-only MCP responses for ticket `KAN-100`.

### 2.4 Feature Unit Tests (`agent/tests/cli/test_validate_transition.py`)
All 7 required DoD test cases + branch coverage tests implemented:
1. `test_cli_pipe_s15_3_example_1`: Positive `cli_pipe` running exact flag set from S15.3 example 1 -> exit 0.
2. `test_in_app_sdk_positive_and_require_approve`: Positive `in_app_sdk` with `--provider fixture`, `--cassette`, and `--mcp-fixture` -> exit 0; `--require-approve` -> exit 2.
3. `test_remote_runner_loopback`: Positive `remote_runner` with `--remote-loopback` exercising TLS 1.3 mTLS WSS frames -> exit 0.
4. `test_security_banned_flags_and_secret_redaction`: Banned flags exit 2; GitHub PATs redacted in context and JSON report.
5. `test_security_repo_immutability`: Working tree status and file mtimes unchanged across all 3 harnesses.
6. `test_negative_schema_and_policy_violations`: Malformed verdict stdout exits 2, missing ticket file exits 1.
7. `test_json_schema_compliance`: `--report json` strictly validates against `kb-validate-transition-report/v1` schema.
8. `test_additional_cli_flags_and_errors`: Edge cases and error branch coverage.
9. `test_direct_handler_and_helpers`: Direct namespace dispatch, helper fallbacks, and provider edge cases.

---

## 3. Definition of Done Checklist

- [x] **File Existence & Implementation:** `agent/cli_commands/validate_transition.py`, `examples/agents/{agy-gate,codex-gate,ollama-gate,remote-gate}.yaml`, and `examples/tickets/kan-142.yaml` exist; `validate-transition` registered in `agent/cli.py`.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest agent/tests/cli/test_validate_transition.py -q -p no:cacheprovider --cov=agent.cli_commands.validate_transition --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with 96.40% coverage.
- [x] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict agent && uv run lint-imports` all exit `0`.
- [x] **CLI Manual Validation (`cli-run.txt`):** Contains unedited stdout/stderr and exit codes for (a) exit 0, (b) exit 0, (c) exit 0, and (d) exit 2.
- [x] **Forensic Proof Packet Complete:** All required files exist in `docs/qa/KANBA-161/` and are synced to `/home/adamoutler/kanban/docs/qa/KANBA-161/`.

---

## 4. Certification Request

`KANBA-161` is complete, fully tested, and ready for forensic audit by `@reality-checker`.
