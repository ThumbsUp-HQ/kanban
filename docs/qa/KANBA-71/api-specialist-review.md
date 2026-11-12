# API Specialist Gate Final Audit: APPROVED for KANBA-71 (KB-P5-16)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-71`
- Branch: `feat/KANBA-71`
- Commit: `bb243bd`
- Ticket: `KANBA-71` (`KB-P5-16`: `[Phase 5 / Database + API] agent_definitions registry, CLI binary allowlist & banned-flag validation (save + runtime)`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive systems architecture, database schema, and security policy audit was conducted for `KANBA-71` (`KB-P5-16`) in `/tmp/kb-wt-KANBA-71`. The ticket implements the `agent_definitions` registry, double-gated CLI argument and binary validation, transactional `AGENT` principal provisioning, and REST API management routes. The implementation was evaluated against specification sections 14.2, 14.3, 3.2, and 3.5.

| Verification Dimension | Specification Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **DDL & CHECK Constraints** | S14.2 `agent_definitions` table + 3 CHECKs | Added `agent_def_harness_fields`, `agent_def_mcp_tools_subset`, `agent_def_args_is_array` | PASS |
| **Row-Level Security** | S14.2 `FORCE RLS` on `agent_definitions` | `ENABLE RLS` + `FORCE RLS` asserted in `schema-dump.sql` (`relrowsecurity = t`, `relforcerowsecurity = t`) | PASS |
| **Transactional Principal Creation** | S3.2 agent as `AGENT` principal | Atomically provisions `principals` row (`principal_type='AGENT'`) alongside definition row | PASS |
| **Double-Gated CLI Validation** | S14.3 save-time + runtime enforcement | `validate_cli_args` in schema/service + `assert_runtime_argv` prior to execution | PASS |
| **Banned Flags & Sandbox Pins** | S14.3 5 banned flags + codex prefix | Rejects `--yolo`, `--full-auto`, `--dangerously*`, `<banned>=`; pins codex `("-p", "-s", "read-only")` | PASS |
| **Binary Allowlist** | S14.2 allowlist: agy, codex, gemini, claude | `BINARY_ALLOWLIST` enforces allowlist; rejects non-allowlisted binaries with `422` | PASS |
| **Argument Bounds & Control Chars** | 1..32 args, 1..256 bytes, no NUL/CR/LF | Rejects > 32 args, > 256 bytes, NUL, CR, LF (`422 CLI_ARGS_INVALID`) | PASS |
| **Deletion In-Use Protection** | FK RESTRICT on bound hooks | Catches `23503` foreign key violation on DELETE and maps to RFC 7807 `409 AGENT_IN_USE` | PASS |
| **Anti-Enumeration Protection** | S3.4 25.0ms timing floor + 404 | GET/PATCH/DELETE execute under `timing_floor(floor_ms=25.0)`; cross-workspace returns 404 | PASS |
| **Markdown Instructions Safety** | Canonical Markdown, 64 KiB cap | `system_instructions_md` normalized via `normalize_to_markdown()`; surrogate safe | PASS |
| **Activity Ledger Auditing** | Category `ADMIN` event types | Records `AGENT_DEFINITION_CREATED`, `UPDATED`, `DELETED` with validated argv | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>= 95%) | 53/53 passed in 3.87s; 97.76% combined coverage across `kanban.agents` | PASS |
| **Quality & Static Analysis** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean, Mypy strict clean (212 files), Lint-imports clean (2 kept) | PASS |

---

### 2. Forensic Architectural & Security Invariant Audit

#### A. Database Schema, Constraints & RLS Boundaries (`database/migrations/`)
- **Table Definition (`p5_16_agent_definitions.up.sql`)**:
  - Primary key uses `uuidv7()`.
  - Workspace uniqueness enforced via `UNIQUE (workspace_id, slug)`.
  - Slugs strictly validated by regex `CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$')`.
  - Foreign key to `principals(id)` enforces `ON DELETE RESTRICT`, preventing orphaned agent records.
- **Harness Consistency Constraint (`agent_def_harness_fields`)**:
  - Enforces that `in_app_sdk` has `provider_kind` and `model_id` while omitting CLI binary and remote runner fields.
  - Enforces that `cli_pipe` specifies `cli_binary_allowlist_id` while omitting remote runner fields.
  - Enforces that `remote_runner` specifies `remote_runner_pool_slug`.
- **Tool Allowlist Subset (`agent_def_mcp_tools_subset`)**:
  - Enforces `mcp_allowed_tools <@ ARRAY['search_tickets','read_ticket','search_knowledge','read_doc']::text[]`.
  - Disallows dangerous mutation tools (e.g. `update_ticket`, `delete_ticket`) from being assigned to read-only agent profiles.
- **Row-Level Security Invariants**:
  - `agent_definitions` has both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
  - SELECT policy scopes reads to `workspace_id = app_current_workspace_id()`, requiring non-empty principal context, and checks `VIEW` capability on `project_id` when project-scoped.
  - INSERT/UPDATE/DELETE policies restrict workspace-scoped agents to `WORKSPACE_ADMIN` and project-scoped agents to `PROJECT_ADMIN`.
  - Least-privilege grants: `kanban_app` receives CRUD; `app_rls_reader` receives `SELECT` only.

#### B. Double-Gated CLI Policy Enforcement (`kanban/agents/cli_policy.py`)
- **Architecture & Layering**:
  - Located in `kanban/agents/cli_policy.py` within `kanban/`, satisfying the unidirectional layering contract: `agent -> mcp -> kanban -> database`. Both API endpoints (save-time) and runtime runners (`agent/` in future waves) can import and execute the policy without circular dependencies.
- **Save-Time Gate (`validate_cli_args`)**:
  - Executed during `POST` and `PATCH` requests via Pydantic model validation and service logic.
  - Banned flag detection checks casefolded arguments against `BANNED_FLAGS = frozenset({"--yolo", "--dangerously-bypass-approvals-and-sandbox", "--dangerously-skip-permissions", "--full-auto", "--allow-all-tools"})`.
  - Detects flag assignment variants (`<banned>=<val>`) and any flag starting with `--dangerously` (e.g., `--dangerously-foo`).
  - Limits total argument count to `<= 32`, individual argument byte length to `1..256` UTF-8 bytes, and disallows control characters (`\x00`, `\r`, `\n`).
  - Enforces `CODEX_PINNED_PREFIX = ("-p", "-s", "read-only")` as the first three arguments for `codex`, and forbids any subsequent `-s`, `--sandbox`, `-c`, or `--config` arguments, preventing sandbox escapes.
  - Returns `ValidatedArgv` as an immutable tuple `(binary_path, *args)`. Never a shell command string, preventing `sh -c` shell injection vulnerabilities.
- **Runtime Gate (`assert_runtime_argv`)**:
  - Re-evaluates stored `AgentDefinition` rows immediately prior to subprocess spawn.
  - Guards against direct database manipulation, manual DBA inserts, or historical definitions created before policy hardening.

#### C. REST API & Lifecycle Management (`kanban/api/v1/agent_definitions.py`)
- **Endpoints**:
  - `POST /api/v1/workspaces/{workspace}/agent-definitions`: Creates agent definition and `AGENT` principal in one atomic transaction.
  - `GET /api/v1/workspaces/{workspace}/agent-definitions`: Lists workspace agents visible to caller.
  - `GET /api/v1/agent-definitions/{agent}`: Retrieves definition by UUID or slug with `timing_floor(floor_ms=25.0)`.
  - `PATCH /api/v1/agent-definitions/{agent}`: Updates mutable fields with CLI re-validation under `timing_floor(floor_ms=25.0)`.
  - `DELETE /api/v1/agent-definitions/{agent}`: Deletes agent definition with `timing_floor(floor_ms=25.0)`; maps `23503` FK violations to RFC 7807 409 `AGENT_IN_USE`.
- **Anti-Enumeration (S3.4)**:
  - Single-resource routes execute inside `async with timing_floor(floor_ms=25.0):`.
  - Non-existent agents and agents in other workspaces return indistinguishable 404 Problem Details responses.
- **Audit Trails**:
  - Ingestion, modification, and deletion emit `AGENT_DEFINITION_CREATED`, `AGENT_DEFINITION_UPDATED`, and `AGENT_DEFINITION_DELETED` events to the activity ledger with the validated argv payload.

---

### 3. Test Suite & Verification Matrix

1. **Mandatory Test Cases Verified**:
   - Case 1 (Positive): Create `cli_pipe` agent with `agy ["-p"]` and `codex ["-p", "-s", "read-only", "--model", "o3-mini"]`.
   - Case 2 (Banned Flags): Rejection of `--yolo`, `--YOLO`, `--yolo=true`, `--dangerously*`, `--full-auto`, `--allow-all-tools=1` with RFC 7807 422 `BANNED_CLI_FLAG`.
   - Case 3 (Codex Sandbox): Rejection of unpinned sandbox mode or subsequent override flags with RFC 7807 422 `CODEX_SANDBOX_OVERRIDE`. Rejection of non-allowlisted binary (`bash`) with `CLI_BINARY_NOT_ALLOWLISTED`.
   - Case 4 (Arg Sanitization): Arguments with `\n` or `\x00`, > 32 arguments, or > 256 bytes rejected with `CLI_ARGS_INVALID`.
   - Case 5 (Runtime Assertion): Direct database row with `--yolo` caught by `assert_runtime_argv()`.
   - Case 6 (RLS Enforcement): Member context fails `WITH CHECK` on create; query without workspace ID returns 0 rows; cross-workspace lookup returns 404.
   - Case 7 (Boundaries & DDL): Slug length/character bounds; `timeout_ms` bounds (1000..300000); tool allowlist subset CHECK; harness field consistency CHECK.
   - Case 8 (In-Use Deletion): Deleting an agent referenced by a transition hook produces RFC 7807 409 `AGENT_IN_USE`.
2. **Execution Results**:
   - Test suite: 53/53 passed in 3.87s across `test_cli_policy.py`, `test_agent_definitions_api.py`, and `test_agent_definitions_ddl.py`.
   - Test coverage: `kanban.agents` achieved **97.76%** branch+line coverage (exceeds >= 95% mandate).
3. **Static Quality Verification**:
   - `uv run ruff check .`: Clean (0 errors).
   - `uv run ruff format --check .`: Clean (582 files formatted).
   - `uv run mypy --strict database kanban`: Clean (0 errors across 212 source files).
   - `uv run lint-imports`: Clean (2 kept, 0 broken).
   - `python -m scripts.check_no_dashes --all`: Clean (0 non-ASCII dashes repo-wide).
   - `make license`: Clean (violations=0).
4. **Typography**: Plain ASCII hyphens `-` only throughout. Zero non-ASCII Unicode dashes (`U+2014` / `U+2013`).

---

### 4. Gate Sign-Off

The `agent_definitions` registry, CLI binary allowlist, and double-gated sandboxing policy in `/tmp/kb-wt-KANBA-71` fully satisfy all architectural, security, database constraint, and contract requirements of ticket `KANBA-71` (`KB-P5-16`).

Verdict: APPROVED
