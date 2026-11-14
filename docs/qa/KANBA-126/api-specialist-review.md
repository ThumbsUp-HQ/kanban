# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-126 (KB-P4-04)

- Ticket: `KANBA-126` (`KB-P4-04`): `[Phase 4 / MCP] /mcp/agent tools: search_tickets & read_ticket`
- Auditor: `arch-reviewer` (Systems Architect & API Specialist Gate Auditor)
- Date: 2026-11-13
- Worktree: `/tmp/kb-wt-KANBA-126` on branch `feat/KANBA-126`
- Scope: `mcp/surfaces/agent/search_tickets.py`, `mcp/surfaces/agent/read_ticket.py`, `mcp/context.py`, `mcp/protocol.py`, `kanban/api/v1/schemas/search.py`, `kanban/services/search.py`, `kanban/auth/sessions/csrf.py`, and `pyproject.toml`.

---

### 1. Architectural & Security Verification

1. **Zero Database Import Invariant in MCP:**
   - Forensic import analysis confirms that `mcp/` holds zero PostgreSQL credentials and zero runtime imports from `database/`.
   - All tool invocations interact exclusively with `kanban-api` via internal `KanbanApiClient` (`httpx.ASGITransport`), forwarding `X-KB-Subject-Token`.
   - `lint-imports` validates all module boundaries: 2 contracts kept, 0 broken.

2. **RLS & Security Boundary Enforcement:**
   - Every internal HTTP call forwards `X-KB-Subject-Token` from the caller's MCP session.
   - Project-level authorization evaluates `User ∩ AgentGrant ∩ TokenScope`.
   - In `search_tickets`, an unreadable or non-existent project returns `total: 0` and empty `items: []`, preventing enumeration of private projects.
   - In `read_ticket`, unreadable tickets in restricted projects (e.g. `SEC-1`) and non-existent tickets (e.g. `KAN-99999`) produce byte-identical YAML error output (`error: {code: NOT_FOUND, message: ticket not found}`) with identical timing floors.

3. **Schema Validation & Boundary Constraints:**
   - Strict JSON Schema constraints: `additionalProperties: false`, `limit` clamped to 1..50 (default 20), query length capped at 500 chars, cursor length capped at 200 chars.
   - Array filters (`states`, `assignees`, `modules`, `labels`) validated to <= 20 string items.
   - Non-primitive types rejected fail-closed with `VALIDATION_FAILED`.

4. **Filter Composition & Server-Side Integration:**
   - Lexical query and structured DSL filters compose cleanly in a single `POST /api/v1/search/issues` call.
   - `mode: hybrid` cleanly defaults to lexical search and reflects `mode: lexical` in response metadata.
   - `gate_status: pending` filters on `pending_transition_exec_id IS NOT NULL`; `approved` and `rejected` return empty lists with Phase 5 advisory note.

---

### 2. Verification Matrix

| Evaluation Dimension | Target Requirement | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Tool Registration** | `search_tickets` and `read_ticket` on `/mcp/agent` | `create_agent_registry()` registers both tools with complete JSON schemas | PASS |
| **Search Functionality** | Lexical + structured filter composition | `POST /api/v1/search/issues` handles combined query and `FilterSpec` predicates | PASS |
| **Read Ticket Details** | Markdown, manifest, links, comments, activity | Normalized issue model projected through `project_issue(..., lod)` | PASS |
| **LOD Projection** | Summary, Standard, Full progressive disclosure | Verified across all 3 tiers with additive disclosure | PASS |
| **Anti-Enumeration** | Byte-identical 404 for unreadable / missing | Verified in `test_case_2_rls_security_identical_404` | PASS |
| **CSRF Handling** | Internal subject-token machine bypass | CSRF middleware safely bypasses verified subject-token calls | PASS |
| **Test Coverage** | >= 95% across MCP test suite | 73 unit tests pass; `mcp` coverage reaches 96% | PASS |
| **Linter / Type / Gate** | Zero warnings, strict mypy, 0 dash defects | `make check && make license` exits 0 cleanly | PASS |

---

### 3. Recommendation
Implementation is fully verified, robust against hostile inputs, and satisfies all architectural invariants. **APPROVED**.
