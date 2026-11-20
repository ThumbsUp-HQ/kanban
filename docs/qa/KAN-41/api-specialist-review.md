# API Specialist Review: KAN-41

- Ticket: KAN-41
- Title: Fix create_ticket children JSON Schema ($ref root mismatch), add MCP agent instructions, and emit child parameter hints
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-41`
- Branch: `main`
- Commit: `23ae056d9d6cf0f8614c82a6c04701b8ae536e18`
- Wiki Commit: `62204208deb2a152d4b0e3266210bdfffa3b5672`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Architecture, and Security audit inspects ticket KAN-41 on `main` (commit `23ae056d`, wiki commit `62204208`), incorporating evidence from live full-stack verification (`live-fullstack-proof.txt`). The ticket fixes a critical schema discrepancy in the `create_ticket` MCP tool where child items referenced the root schema (`{"$ref": "#"}`) which required `project` on every child node. The ticket establishes a dedicated `$defs.child` JSON schema omitting `project` and `parent`, emits actionable self-correcting inheritance hints when clients supply redundant keys, bounds hierarchy recursion to depth <= 6 before traversal, rejects UTF-16 lone surrogates, injects agent guidance into MCP `initialize`, and updates wiki documentation.

All API contracts, schema validation rules, security invariants, and test coverage requirements are verified and approved:
1. Exact JSON Schema 2020-12 alignment in `CREATE_TICKET_SCHEMA` with a dedicated `$defs.child` schema omitting `project` and `parent`.
2. Actionable self-correcting progressive-disclosure error hints and CLI examples for invalid child keys (`project` and `parent`).
3. Structural depth bound of <= 6 enforced before recursion, and UTF-16 lone surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF`) prior to UTF-8 encoding.
4. Agent initialization instructions added to `McpProtocolHandler` initialize responses for `Surface.AGENT`.
5. High unit test coverage: 43 Pytest tests passing in 9.17s with all touched files reaching >= 95% coverage (`help.py`: 100%, `surfaces/agent/__init__.py`: 100%, `create_ticket.py`: 98%, `protocol.py`: 96%).
6. Zero new external dependencies introduced.
7. Strict 0 em-dashes and en-dashes across code, tests, wiki, and documentation.
8. Live full-stack proof: 100% pass across all 7 JSON-RPC MCP operational checks on containerized live environment.

---

## 2. Detailed Contract & Security Verification

### 2.1 Dedicated `$defs.child` Schema (`mcp/surfaces/agent/create_ticket.py`)
- Problem: `CREATE_TICKET_SCHEMA["properties"]["children"]["items"]` previously referenced `{"$ref": "#"}`. Because `project` is required at the root level (`required: ["project", "summary"]`), strict MCP JSON Schema validators rejected valid child payloads that omitted `project`.
- Solution:
  - Backed `children` items with `{"$ref": "#/$defs/child"}`.
  - Defined `CREATE_TICKET_SCHEMA["$defs"]["child"]` with:
    - `type: "object"`
    - `required: ["summary"]`
    - `additionalProperties: False`
    - Child properties only: `summary`, `description_markdown`, `state`, `priority`, `assignees`, `labels`, `cycle`, `modules`, `start_date`, `due_date`, and recursive `children` (maxItems: 49).
    - Excludes `project` and `parent`.
  - Root parameter descriptions updated:
    - `project`: "Project ref (root only; inherited by children)"
    - `parent`: "Parent issue ref (root only; omit in children)"
    - `children`: "Child sub-issues (inherit root project and enclosing parent; omit project and parent)"
  - Tool description updated: "Create ticket or atomic child tree (max 50 nodes, depth <=6; omit project and parent inside children)."

### 2.2 Self-Correcting Inheritance Hints & Validation (`create_ticket.py`)
- `_ALLOWED_CHILD_KEYS` is single-sourced directly from `frozenset(CREATE_TICKET_SCHEMA["$defs"]["child"]["properties"].keys())`.
- In `_validate_tree_node(node, *, is_root, depth=1)`:
  - If `not is_root and k == "project"`: raises `KbMcpError(VALIDATION_FAILED, "Parameter 'project' is only allowed on the root ticket", hint="Omit 'project' inside children[]; child issues automatically inherit the root project.", cli_example=...)`.
  - If `not is_root and k == "parent"`: raises `KbMcpError(VALIDATION_FAILED, "Parameter 'parent' is only allowed on the root ticket", hint="Omit 'parent' inside children[]; each child's parent is its enclosing node in children[].", cli_example=...)`.
  - Unknown keys raise validation error with `hint="Allowed parameters: ..."`.

### 2.3 Hierarchy Bounds & UTF-16 Lone Surrogate Rejection
- Depth Enforcement: Evaluates `if depth > _MAX_DEPTH: raise KbMcpError(VALIDATION_FAILED, f"Tree depth ({depth}) exceeds maximum hierarchy depth of {_MAX_DEPTH}")` prior to child iteration, preventing stack overflows or unbounded recursion on deep inputs.
- Scalar Validation: In `_validate_node_scalars`:
  - Scans `summary` and `description_markdown` for UTF-16 lone surrogates: `0xD800 <= ord(c) <= 0xDFFF`.
  - Fails closed with `McpErrorCode.VALIDATION_FAILED` (`INVALID_UTF8_SURROGATE`) before calling `.encode("utf-8")`.

### 2.4 Agent Initialization Guidance (`mcp/protocol.py` & `mcp/help.py`)
- Protocol Instructions: `McpProtocolHandler._handle_initialize` emits instructions on `Surface.AGENT`:
  "Use human keys (e.g. KAN, KAN-142, @handle). Pass identifier='help' (or project='help' on create_ticket) for live project options. On create_ticket, set 'project' and optional 'parent' on the root object only; omit 'project' and 'parent' inside children[]."
- JIT Defaults: Updated `_TOOL_PARAM_DEFAULTS["create_ticket"]` in `mcp/help.py` to document `parent` and `children`.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt`)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-41/live-fullstack-proof.txt` against commit `23ae056d`:
1. Check 1 (initialize): `POST /mcp/agent` method `initialize` -> HTTP 200 OK. Returned `instructions` guiding human keys and `create_ticket` child parameter inheritance.
2. Check 2 (tools/list schema): `POST /mcp/agent` method `tools/list` -> HTTP 200 OK. Returned `create_ticket` with `$defs.child` schema omitting `project` and `parent`.
3. Check 3 (3-level hierarchy creation): Created root KAN-2, child KAN-3, grandchild KAN-4 atomically in a single JSON-RPC call (`created: 3`).
4. Check 4 (children[0].project hint): Supplying `project` inside `children[0]` returned `VALIDATION_FAILED` with actionable hint: "Omit 'project' inside children[]; child issues automatically inherit the root project."
5. Check 5 (children[0].parent hint): Supplying `parent` inside `children[0]` returned `VALIDATION_FAILED` with actionable hint: "Omit 'parent' inside children[]; each child's parent is its enclosing node in children[]."
6. Check 6 (Depth 7 nesting): Supplying a 7-level tree failed closed before recursion with: "Tree depth (7) exceeds maximum hierarchy depth of 6".
7. Check 7 (summary="help" with project="KAN"): Returned live tool parameter defaults and options.
8. Overall Stability: `LIVE_STACK_VERDICT: PASS (All 7 KAN-41 live /mcp/agent JSON-RPC checks passed)`.

---

## 4. Test Suite & Coverage Verification

- Pytest Test Suite:
  - `mcp/tests/agent/test_create_ticket.py`: 21/21 passed.
  - `mcp/tests/agent/test_schema_budget.py`: 4/4 passed (budget verified <= 2450 tokens).
  - `mcp/tests/test_protocol.py`: 18/18 passed.
  - Total: 43/43 passed in 9.17s.
- Coverage Breakdown:
  - `mcp/help.py`: 100%
  - `mcp/surfaces/agent/__init__.py`: 100%
  - `mcp/surfaces/agent/create_ticket.py`: 98%
  - `mcp/protocol.py`: 96%
  - All touched source files exceed 95% threshold.
- Static Analysis: `ruff check` (clean), `mypy` (0 errors), `lint-imports` (2 kept, 0 broken), `check_no_dashes` (0 em/en-dashes across repo and wiki).

---

## 5. Specialist Checklist

1. [x] Dedicated `$defs.child` schema cleanly omits `project` and `parent`
2. [x] Root schema marks `project` and `summary` required
3. [x] Actionable self-correcting hints emitted for invalid child `project` and `parent`
4. [x] Hierarchy depth <= 6 enforced fail-closed before recursion
5. [x] UTF-16 lone surrogate rejection prevents malformed payload crashes
6. [x] MCP agent instructions emitted on initialize for Surface.AGENT
7. [x] Live full-stack verification proves all 7 JSON-RPC MCP checks pass
8. [x] All 43 unit tests passing with >= 95% coverage on touched files
9. [x] Static typecheck and linting clean across mcp module
10. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 6. Verdict & Certification

STATUS: APPROVED

All schema contracts, self-correcting inheritance hints, security bounds, agent initialization instructions, and live full-stack proof for KAN-41 on `main` (commit `23ae056d`) are fully verified and certified.
