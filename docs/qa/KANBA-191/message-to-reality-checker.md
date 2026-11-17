# KANBA-191 Verification Note for Reality-Checker

## Ticket Metadata
- **Ticket ID:** KANBA-191
- **Title:** [KB-LOG-STD] Standardized Semantic Emoji Logging System (👍 / ⛔ / ❌) with Log-Injection Sanitization and Credential Scrubbing
- **Module:** `kanban-core` (`kanban.logging`)
- **Scope:** Pure backend, standalone runtime, MCP server, agent CLI, and database outbox/migration logging infrastructure.

## UI / Screenshot Audit
- **Visual Browser Screenshots:** **N/A - Non-UI Ticket**.
- This ticket modifies zero frontend React/TypeScript UI code, styles, templates, or HTML presentation. All changes standardize runtime server, CLI, and container stdout/stderr log formatting.

## Forensic Proof Inventory
The following raw proof artifacts have been populated in `docs/qa/KANBA-191/`:
1. `git-diff.patch` - Unified git diff containing all codebase additions and modifications for KANBA-191.
2. `changed-files-manifest.txt` - File inventory with SHA-256 digests and line counts.
3. `unit-test-results.txt` - Verbatim console output and exit code (0) of running `uv run pytest kanban/tests/test_logging_standard.py kanban/tests/api/test_request_id.py tests/deploy/test_standalone_entrypoint.py -q` (35 tests passing).
4. `build-check.txt` - Verbatim console output and exit code (0) of running `make check` (`ruff check`, `ruff format --check`, `mypy` on 1018 files, `lint-imports` contract validation, `check_no_dashes`).
5. `sample-logs.txt` - Captured raw log emissions demonstrating:
   - `👍` (INFO/DEBUG) records with request ID correlation.
   - `⛔` (WARNING) records on policy blocks, 4xx responses, and rate limits.
   - `❌` (ERROR/CRITICAL) records on 5xx failures and exceptions with single-line escaped tracebacks.
   - Neutralization of CRLF line-forging, ANSI escape sequences, BiDi overrides, and UTF-16 lone surrogates.
   - Complete credential scrubbing (`Bearer`, `kb_pat_*`, `kb_runner_*`, `kb_setup_*`, `__Host-kb_session`, `kb_session`, database DSN passwords, and key-value secrets).

## Traceability to Requirements
- `kanban/__init__.py`: PEP 562 lazy `create_app` export ensuring `import kanban.logging` is fast and side-effect-free.
- `kanban/logging.py`: Canonical `KanbanLogFormatter`, `KanbanLogFilter`, `sanitize_log_text`, `scrub_log_secrets`, `status_symbol_for_level`, `log_ok`, `log_blocked`, `log_error`, and `configure_logging()`.
- `kanban/security/scrubber.py`: Extended `_RE_KANBAN_KEY` to cover `kb_pat_*` and `kb_runner_*`.
- `kanban/app.py`: Integrated `configure_logging()`.
- `kanban/api/problems.py`: Added `⛔` (WARNING) logging for 4xx and `❌` (ERROR) logging for 5xx with request ID correlation.
- `kanban/cli/ctl.py`, `mcp/app.py`, `agent/cli.py`, `agent/remote_runner/cli.py`: Wired `configure_logging()` into entry points.
- `database/outbox/relay.py`, `database/migrations/env.py`: Integrated `👍` / `⛔` / `❌` semantic emoji formatting using stdlib logging only, strictly preserving `database` zero upward imports.
- `deploy/standalone/entrypoint.py`: Forwarded `KB_LOG_LEVEL` in `build_child_env()` and formatted `log_phase()` and fatal stderr outputs with `👍` / `⛔` / `❌`.
- `kanban/GEMINI.md`: Documented `kanban.logging` module contract and semantic logging standard.
