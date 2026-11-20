# API Specialist Review: KAN-41

- Ticket: KAN-41
- Title: Fix create_ticket children JSON Schema ($ref root mismatch), add MCP agent instructions, and emit child parameter hints
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan41-3ac81419`
- Branch: `feat/KAN-41`
- Commit: `1d2fd39cb2c8f6bd03de89565fc4b692a7a18671`
- Wiki Commit: `62204208deb2a152d4b0e3266210bdfffa3b5672`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Architecture, and Security audit inspects ticket KAN-41 on branch `feat/KAN-41` (commit `1d2fd39c`, wiki commit `62204208`). The ticket fixes a critical schema discrepancy in the `create_ticket` MCP tool where child items referenced the root schema (`{"$ref": "#"}`) which required `project` on every child node. The ticket establishes a dedicated `$defs.child` JSON schema omitting `project` and `parent`, emits actionable self-correcting inheritance hints when clients supply redundant keys, bounds hierarchy recursion to depth <= 6 before traversal, rejects UTF-16 lone surrogates, injects agent guidance into MCP `initialize`, and updates wiki documentation.

All API contracts, schema validation rules, security invariants, and test coverage requirements are verified and approved:
1. Exact JSON Schema 2020-12 alignment in `CREATE_TICKET_SCHEMA` with a dedicated `$defs.child` schema omitting `project` and `parent`.
2. Actionable self-correcting progressive-disclosure error hints and CLI examples for invalid child keys (`project` and `parent`).
3. Structural depth bound of <= 6 enforced before recursion, and UTF-16 lone surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF`) prior to UTF-8 encoding.
4. Agent initialization instructions added to `McpProtocolHandler` initialize responses for `Surface.AGENT`.
5. High unit test coverage: 43 Pytest tests passing in 9.17s with all touched files reaching >= 95% coverage (`help.py`: 100%, `surfaces/agent/__init__.py`: 100%, `create_ticket.py`: 98%, `protocol.py`: 96%).
6. Zero new external dependencies introduced.
7. Strict 0 em-dashes and en-dashes across code, tests, and wiki documentation.

---

## 2. Detailed Contract & Security Verification

### 2.1 Schema Definition & $defs.child Extraction (`create_ticket.py`)
- Tool Schema Source: `mcp/surfaces/agent/create_ticket.py`
- Root vs Child Contracts:
  - Root schema requires `project` and `summary`, allowing optional `parent` for linking under an existing issue.
  - Replaced recursive root reference `"items": {"$ref": "#"}` with `"items": {"$ref": "#/$defs/child"}`.
  - Dedicated `$defs.child` schema:
    * `type`: `"object"`
    * `required`: `["summary"]`
    * `additionalProperties`: `False`
    * Omits `project` and `parent` fields entirely.
    * Recursive child nesting: `children: {"type": "array", "items": {"$ref": "#/$defs/child"}}`.
- Single-Source of Truth:
  - `_ALLOWED_CHILD_KEYS` is derived directly from `CREATE_TICKET_SCHEMA["$defs"]["child"]["properties"].keys()`.
  - Guarantees schema declaration and runtime validation logic remain in lockstep.

### 2.2 Progressive-Disclosure Error Guidance & Self-Correction
- Inheritance Hints:
  - When a client supplies `project` in a child node: raises `VALIDATION_FAILED` with hint "Omit 'project' inside children[]; child issues automatically inherit the root project." and pre-populated CLI example.
  - When a client supplies `parent` in a child node: raises `VALIDATION_FAILED` with hint "Omit 'parent' inside children[]; each child's parent is its enclosing node in children[]." and pre-populated CLI example.
  - Unknown child parameters report permitted child keys dynamically.

### 2.3 Structural Hierarchy Bounds & Hostile Input Sanitization
- Tree Limits:
  - Max children per node: 49.
  - Max total nodes in tree: 50.
  - Max hierarchy depth: <= 6. Evaluated before traversing child nodes to fail closed early on cyclic or deeply nested payloads.
- Volatile String Sanitization:
  - Checks summary and description for UTF-16 lone surrogates (`0xD800 <= ord(c) <= 0xDFFF`).
  - Raises `VALIDATION_FAILED` ("INVALID_UTF8_SURROGATE") before executing `.encode("utf-8")`, preventing byte serialization crashes.
  - Enforces summary length <= 500 characters and description <= 1 MiB (1,048,576 bytes).

### 2.4 MCP Protocol Agent Instructions & JIT Defaults
- Surface Agent Guidance:
  - In `mcp/protocol.py`, `McpProtocolHandler._handle_initialize` emits an `instructions` field for `Surface.AGENT`:
    `Use human keys (e.g. KAN, KAN-142, @handle). Pass identifier='help' (or project='help' on create_ticket) for live project options. On create_ticket, set 'project' and optional 'parent' on the root object only; omit 'project' and 'parent' inside children[].`
- Tool Parameter Defaults:
  - `mcp/help.py`: `_TOOL_PARAM_DEFAULTS["create_ticket"]` updated to clarify root-only `parent` and child inheritance constraints.

### 2.5 Wiki Documentation Alignment
- `thumbs-up-kanban.wiki/MCP-Tools-Reference.md`:
  - Updated tool description and parameter table for `create_ticket`.
  - Added Example 3 showcasing atomic child tree creation with explicit note on parameter inheritance.

---

## 3. Layering, Static Quality & Security Verification

- Layering Invariant: Zero direct `database` runtime imports from `mcp/` (`uv run lint-imports` confirmed 2 kept, 0 broken).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run ruff format --check .`: Clean (1900 files formatted).
  - `uv run mypy mcp/`: 0 errors across 113 source files.
  - `python3 -m scripts.check_no_dashes --all`: 0 em-dashes, 0 en-dashes.
  - `python3 -m scripts.check_no_dashes /home/adamoutler/kanban/thumbs-up-kanban.wiki`: 0 em-dashes, 0 en-dashes.
- Clean Patch Artifacts: `docs/qa/KAN-41/git-diff.patch` and `wiki-diff.patch` verified to exclude extraneous temporary files.

---

## 4. Test Coverage Audit

- Pytest Suite:
  - 43 passed in 9.17s across `mcp/tests/agent/test_create_ticket.py`, `test_protocol.py`, `test_lod_help.py`, and `test_schema_budget.py`.
  - Coverage Breakdown on Touched Files:
    * `mcp/help.py`: 100% Stmts / 100% Branch
    * `mcp/surfaces/agent/__init__.py`: 100% Stmts / 100% Branch
    * `mcp/surfaces/agent/create_ticket.py`: 98% Stmts / 96% Branch
    * `mcp/protocol.py`: 96% Stmts / 92% Branch
    * Every touched file satisfies the >= 95% coverage requirement.
- Verbatim raw test output is preserved in `docs/qa/KAN-41/unit-test-results.txt`.

---

## 5. Verification Verdict

The dedicated child JSON schema, inheritance progressive-disclosure hints, structural hierarchy bounds, agent instructions, and test coverage standards are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
