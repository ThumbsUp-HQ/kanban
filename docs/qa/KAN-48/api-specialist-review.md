# API and Security Specialist Review: KAN-48

- **Ticket:** KAN-48 ([KB-MCP-CLI]) - Build Schema-Driven kanban-cli with 1:1 MCP Tool Parity, --filter Predicate DSL, & Deterministic --json/--jsonl Unix Output
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-48-kanban-cli-parity`
- **Commit Under Audit:** `8a3f8e4a` (`feat(mcp): implement schema-driven kanban-cli with 1:1 tool parity and auth (KAN-48)`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan48-fb1ff863`
- **Status:** APPROVED

---

## 1. Executive API, Security, and Architecture Evaluation

Ticket KAN-48 delivers a schema-driven, Unix-composable command-line interface (`kanban-cli`, along with sub-surface entry points `kanban-cli-agent`, `kanban-cli-docs`, `kanban-cli-admin`) providing 1:1 parity with the 24 Model Context Protocol tools.

Key architecture and security capabilities audited:
1. **Schema-Driven Tool Execution & Parity (`mcp/cli/schema_cli.py`):**
   - Directly inspects `create_agent_registry()`, `build_docs_registry()`, and `build_admin_registry()`.
   - Supports both `kebab-case` and `snake_case` tool and flag invocations.
   - Reuses `validate_tool_arguments_schema` for progressive error disclosure, returning self-correcting hints and exiting with code 2 on argument errors.
   - Supports `-` (stdin), `@path.json`, `@path.yaml`, and dedicated file aliases (`--description-file`, `--assignees-file`, etc.).
   - Emits deterministic compact YAML, formatted JSON (`--json`), and streaming JSON Lines (`--jsonl`) with automated cursor-based pagination.
   - Automatically suppresses ANSI escape codes when stdout is redirected or `--no-color` is passed.
2. **Double-Submit CSRF Stateless Bearer Exemption (`kanban/auth/sessions/csrf.py`):**
   - Correctly permits stateless programmatic API mutations with `Authorization: Bearer <token>` when no ambient session cookie is present.
   - Defends browser users by strictly enforcing CSRF tokens whenever an ambient session cookie is detected, regardless of whether a Bearer header was passed.
3. **Transport Security & Credential Protection (`mcp/internal_client.py` & `mcp/cli/auth.py`):**
   - Enforces HTTPS for all non-loopback network destinations. Plaintext `http://` is allowed strictly for `localhost`, `127.0.0.1`, and `[::1]`.
   - Disables open HTTP redirects (`follow_redirects=False`) to prevent bearer token leakage.
   - Restricts `credentials.toml` permissions to `0o600`, creates files securely via `os.open`, and rejects symlinks with security errors.
   - Implements `kanban-cli auth login [--device]`, `status`, and `logout`.
4. **Predicate Compiler Integration & Subprocess Invariants:**
   - `--filter "<predicate>"` integrates with the KAN-78 predicate compiler tokenizer without violating architectural layer boundaries (`mcp` forbidden from importing `database`).
   - Shell completion generation (`completions <bash|zsh|fish>`) executes pure Python introspection with zero `shell=True` subprocess calls.

---

## 2. Wire Contracts & Security Invariants

### A. 1:1 Parity Wire Contracts
- Invocations through `kanban-cli` produce byte-for-byte identical tool execution to native JSON-RPC MCP handlers.
- Errors map to structured progressive disclosure payloads with exit codes:
  - 0: Successful execution.
  - 1: Upstream application or execution error.
  - 2: CLI argument or schema validation error.
  - 130: User interrupt (SIGINT / KeyboardInterrupt).

### B. Anti-Enumeration & Tenancy Invariants
- `kanban-cli` obeys caller token credential boundaries, project narrowing, and workspace scoping.
- Unauthenticated requests cannot probe or enumerate objects across tenants.

---

## 3. Unit Test Coverage & Verification Metrics

- **Unit Test Results:** 52 passed, 0 failed in 7.87s (`mcp/tests/cli/test_kanban_cli_auth_and_io.py`, `mcp/tests/cli/test_kanban_cli_parity.py`, `kanban/tests/auth/test_csrf_bearer_exemption.py`, `kanban/tests/auth/test_csrf.py`, `mcp/tests/test_internal_client.py`).
- **Statement & Branch Coverage:**
  - `mcp/cli/` package achieved 95% coverage overall (771 statements, 24 misses, 316 branches, 31 partial branches).
  - `mcp/cli/__init__.py`: 100%.
  - `mcp/cli/auth.py`: 96%.
  - `mcp/cli/main.py`: 100%.
  - `mcp/cli/schema_cli.py`: 94%.
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2193 files formatted.
  - `mypy`: 0 issues found in 1214 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.
  - `check-migrations`: Valid single head `p6_04_enforce_credential_boundary_rls_gucs`.
  - `check_no_dashes`: Clean across all files (0 violations).

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review (or non-UI validation note) and routing to `@merge-ci`.
