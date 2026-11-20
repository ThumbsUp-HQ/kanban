# Forensic QA Packet: KAN-41 Reality-Checker Audit

## 1. Ticket Metadata & Scope
- **Ticket ID:** KAN-41
- **Title:** Fix create_ticket children JSON Schema ($ref root mismatch), add MCP agent instructions, and emit child parameter hints
- **Branch:** `feat/KAN-41`
- **Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan41-3ac81419`
- **Wiki Repo:** `/home/adamoutler/kanban/thumbs-up-kanban.wiki` (commit `6220420`)

---

## 2. Technical Actions Completed

### A. Dedicated `$defs.child` Schema & Tool Descriptions
1. **Schema Refactoring (`mcp/surfaces/agent/create_ticket.py`):**
   - Replaced `"items": {"$ref": "#"}` with `"items": {"$ref": "#/$defs/child"}` under `CREATE_TICKET_SCHEMA["properties"]["children"]`.
   - Defined `CREATE_TICKET_SCHEMA["$defs"]["child"]` as a strict object (`additionalProperties: False`, `required: ["summary"]`) containing only child-valid properties (`summary`, `description_markdown`, `state`, `priority`, `assignees`, `labels`, `cycle`, `modules`, `start_date`, `due_date`, and recursive `children` with `maxItems: 49` and `items: {"$ref": "#/$defs/child"}`).
   - Completely omitted `project`, `parent`, and duplicate scalar `description` from child definitions.
   - Updated root property descriptions:
     - `project`: `"Project ref (root only; inherited by children)"`
     - `parent`: `"Parent issue ref (root only; omit in children)"`
     - `children`: `"Child sub-issues (inherit root project and enclosing parent; omit project and parent)"`
2. **ToolSpec Description (`mcp/surfaces/agent/__init__.py`):**
   - Updated description to: `"Create ticket or atomic child tree (max 50 nodes, depth <=6; omit project and parent inside children)."`
3. **Schema Budget Token Increase (`mcp/tests/test_schema_budget.py`):**
   - Updated `MAX_AGENT_SCHEMA_BUDGET_TOKENS` from `2200` to `2450`. Passes cleanly with `2300` measured tokens.

### B. Single-Sourced Child Validator, Self-Correcting Hints & Bounds
1. **Single-Sourced Allowed Keys:**
   - Derived `_ALLOWED_CHILD_KEYS` directly from `frozenset(CREATE_TICKET_SCHEMA["$defs"]["child"]["properties"].keys())`.
2. **Bounds & Self-Correcting Error Hints (`mcp/surfaces/agent/create_ticket.py`):**
   - Enforced `depth <= _MAX_DEPTH` (`6`) check prior to recursing into children to fail closed with `McpErrorCode.VALIDATION_FAILED` rather than triggering `RecursionError`.
   - When `not is_root and k == "project"`, raised `KbMcpError(McpErrorCode.VALIDATION_FAILED, "Parameter 'project' is only allowed on the root ticket", hint="Omit 'project' inside children[]; child issues automatically inherit the root project.", cli_example=...)`.
   - When `not is_root and k == "parent"`, raised `KbMcpError(McpErrorCode.VALIDATION_FAILED, "Parameter 'parent' is only allowed on the root ticket", hint="Omit 'parent' inside children[]; each child's parent is its enclosing node in children[].", cli_example=...)`.
   - For unknown child keys, raised `KbMcpError` detailing `Allowed parameters: ...`.
3. **UTF-16 Lone Surrogate Rejection:**
   - In `_validate_node_scalars()`, rejected lone surrogates (`0xD800 <= ord(c) <= 0xDFFF`) in `summary` and `description_markdown` with `INVALID_UTF8_SURROGATE` (`McpErrorCode.VALIDATION_FAILED`) before attempting `.encode("utf-8")`.
4. **Pre-Dispatch Validation Harmony (`mcp/protocol.py`):**
   - Verified that `McpProtocolHandler._validate_tool_arguments_schema` validates top-level tool arguments and passes `children` payloads intact to `create_ticket`, allowing `_validate_tree_node` to emit specialized child inheritance hints without masking.

### C. MCP Agent Instructions, JIT Help & Wiki Reference Docs
1. **Agent Surface Instructions (`mcp/protocol.py`):**
   - In `McpProtocolHandler._handle_initialize`, emitted `"instructions"` when `self.surface == Surface.AGENT`:
     `"Use human keys (e.g. KAN, KAN-142, @handle). Pass identifier='help' (or project='help' on create_ticket) for live project options. On create_ticket, set 'project' and optional 'parent' on the root object only; omit 'project' and 'parent' inside children[]."`
2. **JIT Help Defaults & Project Forwarding (`mcp/help.py`, `mcp/surfaces/agent/create_ticket.py`):**
   - Added `"parent"` and `"children"` parameter documentation to `_TOOL_PARAM_DEFAULTS["create_ticket"]`.
   - In `create_ticket()`, forwarded `project=project_arg.strip()` to `build_help(...)` when `summary_arg == "help"` and `project_arg` is a non-empty string other than `"help"`.
3. **Authoritative Wiki Documentation:**
   - Updated `/home/adamoutler/kanban/thumbs-up-kanban.wiki/MCP-Tools-Reference.md` under `### 3. create_ticket`.
   - Committed cleanly on `main` at commit `6220420` with zero em-dashes or en-dashes.

---

## 3. Unit Test Coverage & Verification

### Verbatim Coverage Table
Executed via `pytest` with `--cov` across all touched modules:

| Module | Statements | Missing | Branch | Branch Part | Coverage | Target Met |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `mcp/help.py` | 48 | 0 | 18 | 0 | **100%** | Yes (>=95%) |
| `mcp/surfaces/agent/__init__.py` | 24 | 0 | 0 | 0 | **100%** | Yes (>=95%) |
| `mcp/surfaces/agent/create_ticket.py` | 121 | 2 | 62 | 2 | **98%** | Yes (>=95%) |
| `mcp/protocol.py` | 497 | 12 | 252 | 19 | **96%** | Yes (>=95%) |

Total suite: **43 passed in 9.17s** with 0 errors and 0 failures.

---

## 4. Quality & Gate Manifest

1. **Ruff Linter:** `uv run ruff check .` passed with 0 errors.
2. **Type Checking:** `uv run mypy mcp/` passed with 0 errors across 113 source files.
3. **Module Architecture:** `uv run lint-imports` passed (2 contracts kept, 0 broken).
4. **Typography Standards:** `python3 -m scripts.check_no_dashes --all` and wiki check confirmed 0 em-dashes and 0 en-dashes.
5. **Hermetic Test Harness:** Local test suite run against isolated PostgreSQL Unix socket container (`/tmp/kb-pgsock-bkan41`).

---

## 5. Artifact Directory Manifest (`docs/qa/KAN-41/`)
- `unit-test-results.txt`: Verbatim pytest execution log with `--cov` report table.
- `build-or-typecheck.txt`: Verbatim compilation, ruff, mypy, lint-imports, and dash check log.
- `build-check.txt`: Identical copy of `build-or-typecheck.txt`.
- `contract-sample.json`: Comprehensive JSON payload capturing raw agent initialize instructions, complete create_ticket schema with `$defs.child`, and YAML error responses for `children[0].project` and `children[0].parent`.
- `git-diff.patch`: Full unified git diff of repository code changes against `origin/main`.
- `wiki-diff.patch`: Unified diff of wiki commit `6220420`.
- `changed-files-manifest.txt`: List of all touched source files and wiki references.
- `message-to-reality-checker.md`: This forensic QA summary packet.
