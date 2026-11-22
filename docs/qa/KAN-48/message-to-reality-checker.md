# Forensic QA Handoff: KAN-48

## Overview & User Story
- **Ticket ID:** KAN-48 ([KB-MCP-CLI] Build Schema-Driven kanban-cli with 1:1 MCP Tool Parity, --filter Predicate DSL, & Deterministic --json/--jsonl Unix Output)
- **Branch:** `main` (merged from `feat/KAN-48-kanban-cli-parity`)
- **Merged Commit (`HEAD`):** `366ff092239c9cb20598003a5de47cd6e80a1db1` (`366ff092`)
- **Pre-Ticket Base Commit (`main`):** `e0c66d93172e1bcf1e707c4714ef5bfc76294603` (`e0c66d93`)
- **Visual Browser Screenshots:** `N/A - Non-UI Ticket`
- **User Story:** As an autonomous agent, developer, or CI automation pipeline, I require a lightweight, Unix-composable `kanban-cli` that provides 1:1 parity with all 24 MCP tools, supports headless authentication, integrates `--filter` predicate query parsing, and provides deterministic YAML, JSON, and JSONL streaming outputs with zero ANSI pollution when piped.

---

## Evidence Manifest

1. **Git Diff Patch:**
   - Path: [git-diff.patch](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan48-fb1ff863/docs/qa/KAN-48/git-diff.patch)
   - Scope: Strictly confined to assigned slice (`mcp/cli/*`, `mcp/pyproject.toml`, `mcp/internal_client.py`, `mcp/protocol.py`, `kanban/auth/sessions/csrf.py`, `kanban/tests/auth/test_csrf_bearer_exemption.py`, `mcp/tests/cli/*`, `docs/qa/KAN-48/*`).
   - Line Count: 132 KiB unified diff.

2. **Unit Test Execution & Coverage Report:**
   - Path: [unit-test-results.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan48-fb1ff863/docs/qa/KAN-48/unit-test-results.txt)
   - Results: 52 passed, 0 failed across test suites.
   - Code Coverage: 95% total coverage on `mcp/cli/` (`mcp/cli/__init__.py`: 100%, `mcp/cli/auth.py`: 96%, `mcp/cli/main.py`: 100%, `mcp/cli/schema_cli.py`: 94%).
   - CSRF Exemption Test: 100% pass on stateless bearer bypass and cookie precedence.

3. **Build & Static Validation Suite:**
   - Path: [build-or-typecheck.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan48-fb1ff863/docs/qa/KAN-48/build-or-typecheck.txt)
   - Gate Checks:
     - `ruff check .`: 0 errors.
     - `ruff format --check .`: 2193 files already formatted.
     - `mypy`: 0 errors across 1214 source files.
     - `lint-imports`: 2 kept contracts (Layer order kept, MCP forbidden from importing database kept).
     - `check_no_dashes --all`: 0 em-dash or en-dash violations.
     - `check-migrations --static-only`: 66 valid migrations, single head.
     - `license_gate`: 0 copyleft/non-permissive violations.

4. **CLI Verification Trace:**
   - Path: [cli-verification-trace.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan48-fb1ff863/docs/qa/KAN-48/cli-verification-trace.txt)
   - Traced Commands:
     - `kanban-cli --help`: Top-level help, 24 tools, subsurfaces, global flags.
     - `kanban-cli create-ticket --help`: JIT help with schema properties and prose file aliases.
     - `kanban-cli read-ticket --help`: Parameter help and LOD options.
     - `kanban-cli search-tickets --help`: Parameter help, predicate filter options.
     - `kanban-cli transition-ticket --help`: Transition help, verification proof flags.
     - `kanban-cli docs --help`: Docs surface commands (search, create, update).
     - `kanban-cli admin --help`: Admin surface commands (12 tools).
     - `kanban-cli auth status`: Configuration status, endpoint, auth token resolution.
     - `kanban-cli completions bash`: Generated bash completion script.

---

## Detailed Requirement & Verification Matrix

### Problem 1: Console Entry Points & Schema-Driven CLI Parity
- **Implementation:**
  - `mcp/pyproject.toml` (lines 43-47): Registered console scripts `kanban-cli = "mcp.cli.main:main"`, `kanban-cli-agent = "mcp.cli.main:agent_main"`, `kanban-cli-docs = "mcp.cli.main:docs_main"`, `kanban-cli-admin = "mcp.cli.main:admin_main"`.
  - `mcp/cli/schema_cli.py`: Introspects `create_agent_registry()`, `build_docs_registry()`, and `build_admin_registry()`. Mappings accept both `kebab-case` and `snake_case` command forms.
  - Global flags (`--url`, `--workspace`, `--project`, `--token`, `--lod`, `--filter`, `--json`, `--jsonl`, `--no-color`) are bound to root and subparser levels with `default=argparse.SUPPRESS` to prevent command-line option clashes.
  - Reuses `_validate_tool_arguments_schema` (exported via `validate_tool_arguments_schema` in `mcp/protocol.py`) for progressive error reporting.
  - Output engine renders compact YAML (`dump_yaml`), deterministic `--json`, or streaming `--jsonl` with automatic pagination handling (`next_cursor`).
  - Terminal formatting disables ANSI color sequences automatically when stdout is redirected or `--no-color` is passed.
- **Verification:**
  - Verified by `mcp/tests/cli/test_kanban_cli_parity.py`:
    - `test_positive_1_to_1_mcp_tool_execution_parity`: Proves byte-for-byte YAML equality between MCP server handler and CLI output.
    - `test_negative_self_correcting_error_parity`: Proves invalid arguments trigger exit code 2 and structured self-correcting error output.
    - `test_100_percent_tool_coverage_inventory`: Proves all 24 tools across agent, docs, and admin registries are reachable.
    - `test_all_24_mcp_tools_dispatch_roundtrip`: Verifies dispatch for every single tool.
    - `test_standalone_bin_entry_points`: Validates `kanban-cli-agent`, `kanban-cli-docs`, `kanban-cli-admin`.
    - `test_json_and_jsonl_output_formatting`: Verifies JSON and JSONL output structures.
    - `test_snake_and_kebab_case_parity`: Verifies both naming conventions execute identically.
    - `test_jsonl_streaming_with_cursor`: Verifies multi-page cursor-based streaming.

### Problem 2: Network Transport Security & Double-Submit CSRF Exemption
- **Implementation:**
  - `mcp/internal_client.py` (lines 98-150): Added `cli_remote` mode to `KanbanApiClient`.
    - Loopback check enforces that plaintext `http://` is strictly limited to `localhost`, `127.0.0.1`, `::1`, and `[::1]`.
    - Non-loopback hosts strictly require `https://`. Any plaintext `http://` for remote hosts raises `ValueError`.
    - Sets `follow_redirects=False` to prevent token leakage across open redirects.
    - Automatically injects `Authorization: Bearer <token>` when a token is configured.
  - `kanban/auth/sessions/csrf.py` (lines 351-365):
    - Stateless bearer requests bypass double-submit CSRF checks when `Authorization: Bearer <token>` is present without an ambient session cookie.
    - If a session cookie is present, CSRF validation is strictly enforced regardless of the bearer header to defend browser users against cross-site requests.
  - `mcp/cli/auth.py`:
    - Configuration resolution cascade: CLI flags > environment variables (`KANBAN_*`) > `credentials.toml` > `config.toml` > default (`http://localhost:8080`).
    - Permission hardening: `credentials.toml` requires mode `0o600`. File write uses `os.open` with `O_WRONLY | O_CREAT | O_TRUNC` and `0o600`. Symlinks are rejected with security errors.
    - Supports `kanban-cli auth login [--device]`, `kanban-cli auth status`, `kanban-cli auth logout`.
- **Verification:**
  - Verified by `mcp/tests/cli/test_kanban_cli_auth_and_io.py`:
    - `test_config_precedence`: Verifies flags > env > files > default fallback.
    - `test_credentials_file_security_permissions`: Verifies 0600 mode enforcement and symlink rejection.
    - `test_cli_remote_security_loopback_and_https`: Verifies HTTP allowed on loopback, rejected on remote, and HTTPS enforced.
    - `test_auth_login_device_flow` and `test_auth_login_pkce_flow`: Verifies headless and browser auth login flows.
    - `test_auth_status_variants`: Verifies status reporting for unauthenticated, connected, and error states.
  - Verified by `kanban/tests/auth/test_csrf_bearer_exemption.py`:
    - `test_stateless_bearer_bypasses_csrf`: Stateless bearer request succeeds with 200 without CSRF token.
    - `test_cookie_authenticated_request_requires_csrf`: Requests with session cookie return 403 when CSRF token is missing or mismatched, even if bearer token is present.
    - `test_empty_or_malformed_bearer_does_not_bypass`: Empty or malformed bearer headers return 403.
    - `test_safe_get_with_cookie_always_allowed`: Safe GET requests continue to succeed.

### Problem 3 & Addenda: Unix I/O, File Redirection, Predicate Filter, and Shell Completions
- **Implementation:**
  - `mcp/cli/schema_cli.py`:
    - File input redirection: Supports `--<field>-file <path>` (including `--description-file <path>`), `-` for reading standard input, and structured `@path.json`, `@path.yaml`, or `@-`.
    - Predicate filter: `--filter "<predicate>"` on `search-tickets` and `issue list` delegates to KAN-78 predicate compiler tokenizer and parser without violating architectural import layering (`mcp` forbidden from importing `database`).
    - Shell completions: `kanban-cli completions <bash|zsh|fish>` generates completion scripts dynamically using pure Python introspection (zero `shell=True` subprocess invocation).
    - Subprocess safety: Zero `shell=True` invocations across the entire codebase.
    - Signal handling: SIGINT / KeyboardInterrupt exits cleanly with Unix return code 130.
- **Verification:**
  - Verified by `mcp/tests/cli/test_kanban_cli_auth_and_io.py`:
    - `test_cli_prose_file_and_structured_flags`: Tests prose file aliases and structured file parsing.
    - `test_array_and_stdin_and_null_arg_normalization`: Tests stdin (`-`), arrays, and null arguments.
    - `test_cli_filter_predicate_delegation`: Tests predicate filter clauses and client-side priority filter.
    - `test_shell_completions_generation`: Tests bash, zsh, and fish completion scripts.
    - `test_main_entry_points_and_interrupt`: Tests entry points and KeyboardInterrupt exit code 130.

---

## Clean-Room Verification Checklist
- [x] Branch: `feat/KAN-48-kanban-cli-parity`
- [x] Modified files confined strictly to slice boundaries.
- [x] Unit test suite: 52 passed, 0 failed.
- [x] Test coverage: 95% on `mcp/cli/`.
- [x] `make check` passing: ruff, format, mypy, lint-imports, migrations, check_no_dashes.
- [x] `make license` passing: 0 non-permissive violations.
- [x] Zero em-dash or en-dash characters present in code, commits, or documentation.
- [x] Ticket is NOT closed and `complete_work` has NOT been called. Handoff to API specialist on swarm board.
