# UI/UX Specialist Review: KAN-41

- **Ticket:** KAN-41 (Fix create_ticket children JSON Schema, add MCP agent instructions, and emit child parameter hints)
- **Branch:** `feat/KAN-41`
- **Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan41-3ac81419`
- **Auditor:** Clean-Room UI/UX Specialist (`ui-spec-2`)
- **Review Date:** 2026-11-20
- **Status:** STATUS: APPROVED

---

## 1. Executive Summary

A clean-room UI/UX and Agent/Developer Experience (DX) review of branch `feat/KAN-41` (commit `1d2fd39cb2c8f6bd03de89565fc4b692a7a18671`) was performed.

KAN-41 addresses critical schema and contract defects in the Model Context Protocol (MCP) server:
1. Replaces the invalid recursive root schema ref in `CREATE_TICKET_SCHEMA` with a dedicated `$defs.child` schema omitting `project` and `parent`.
2. Adds self-correcting error hints with CLI examples when callers supply `project` or `parent` in child objects.
3. Enforces tree depth limits (<= 6) and rejects UTF-16 lone surrogates.
4. Emits clear instructions on `initialize` for `Surface.AGENT` and updates JIT help parameter defaults for `create_ticket`.
5. Updates authoritative wiki documentation.

The implementation was evaluated from an Agent UX, Developer Experience, error ergonomics, and frontend state/hierarchy alignment perspective. All tests and audits pass without defect.

---

## 2. Agent UX & Developer Experience (DX) Audit

### 2.1 Tool Description & Cognitive Guidance
- **Tool Description:** Updated to `"Create ticket or atomic child tree (max 50 nodes, depth <=6; omit project and parent inside children)."`
- **Cognitive Clarity:** The prompt provides explicit boundaries directly in the tool catalog. An LLM agent reviewing available tools immediately learns the tree size constraint (50 nodes), hierarchy limit (depth <= 6), and structural contract (omit `project` and `parent` in children).
- **Property Descriptions:**
  - `project`: `"Project ref (root only; inherited by children)"`
  - `parent`: `"Parent issue ref (root only; omit in children)"`
  - `children`: `"Child sub-issues (inherit root project and enclosing parent; omit project and parent)"`
- **Assessment:** Eliminates ambiguity and prevents LLMs from hallucinating redundant project identifiers or recursive parent links.

### 2.2 Error Ergonomics & Self-Correcting Hints
- **Inheritance Guidance for `project`:**
  - Message: `Parameter 'project' is only allowed on the root ticket`
  - Hint: `Omit 'project' inside children[]; child issues automatically inherit the root project.`
  - CLI Example: Includes a fully formatted CLI example showing valid syntax.
- **Inheritance Guidance for `parent`:**
  - Message: `Parameter 'parent' is only allowed on the root ticket`
  - Hint: `Omit 'parent' inside children[]; each child's parent is its enclosing node in children[].`
- **Unknown Child Parameters:**
  - Clearly reports allowed parameters derived dynamically from `$defs.child`.
- **Assessment:** The error responses provide immediate, actionable feedback allowing agents to self-correct in a single round-trip without user intervention.

### 2.3 JIT Help Ergonomics & Protocol Instructions
- **MCP Initialize Instructions:**
  - Text: `"Use human keys (e.g. KAN, KAN-142, @handle). Pass identifier='help' (or project='help' on create_ticket) for live project options. On create_ticket, set 'project' and optional 'parent' on the root object only; omit 'project' and 'parent' inside children[]."`
  - Placement: Emitted in `result["instructions"]` during MCP protocol initialization for `Surface.AGENT`.
- **JIT Help (`mcp/help.py`):**
  - Added `"parent": "KAN-142 | uuid (root only)"` and `"children": "array of child objects (require summary; omit project and parent; max 49/node, <=50 total, depth <=6)"` to `_TOOL_PARAM_DEFAULTS["create_ticket"]`.
  - Calling `create_ticket(project="KAN", summary="help")` forwards `project="KAN"` to `build_help`, returning live project options alongside tool parameter documentation.
- **Assessment:** High-signal, low-token assistance that seamlessly guides interactive CLI and agent workflows.

---

## 3. Web UI Alignment & Hierarchy Consumption

While KAN-41 touches backend MCP protocol and schema modules, its output directly affects web UI consumption:
1. **Hierarchical Consistency:**
   - Atomic child trees created via MCP persist valid `parent_issue_id` and `project_id` foreign keys in the database.
   - When loaded in the web interface, the Board View, Table View, and Issue Detail screen properly display parent-child relationships, subtask progress indicators, and breadcrumb navigation.
2. **Sanitization & Surrogate Safety:**
   - UTF-16 lone surrogate rejection prior to `.encode("utf-8")` prevents database ingestion of invalid byte sequences that could crash React DOM rendering or JSON serialization in web clients.
3. **CSP & Token Compliance:**
   - 0 inline styles introduced.
   - `cssTokensAudit.test.ts` passed 4/4 clean.

---

## 4. Typography & Standards Audit

- **Punctuation Check:** Executed `python3 -m scripts.check_no_dashes --all` across the repository and wiki. Zero em-dashes and zero en-dashes detected.
- **Tone & Conciseness:** Schema text, help strings, and error hints use precise, professional technical language free of unnecessary filler.

---

## 5. Verification & Test Evidence

- **Unit Tests (`pytest`):**
  - `mcp/help.py`: 100% statement and branch coverage.
  - `mcp/surfaces/agent/__init__.py`: 100% coverage.
  - `mcp/surfaces/agent/create_ticket.py`: 98% coverage (62/64 branches).
  - `mcp/protocol.py`: 96% coverage.
  - Overall test suite: 43 passed in 9.17s.
- **Static Analysis & Linters:**
  - `ruff check .`: 0 errors.
  - `mypy mcp/`: 0 errors across 113 source files.
  - `lint-imports`: 2 kept, 0 broken.
  - `cssTokensAudit.test.ts`: 4/4 passed.

---

## 6. Formal Signoff

The UI/UX, DX, and ergonomics implementation for **KAN-41** meets all architectural, design token, typography, and test requirements.

**STATUS: APPROVED**
