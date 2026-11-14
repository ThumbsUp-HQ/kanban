# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-130 (KB-P4-05)

- Ticket: `KANBA-130` (`KB-P4-05`): `[Phase 4 / MCP] /mcp/agent tools: create_ticket (incl. parent+sub-issue trees) & update_ticket`
- Auditor: `arch-reviewer` (Systems Architect & API Specialist Gate Auditor)
- Date: 2026-11-13
- Worktree: `/tmp/kb-wt-KANBA-130` on branch `feat/KANBA-130`
- Scope: `kanban/api/v1/issue_trees.py`, `kanban/api/v1/schemas/issue_trees.py`, `kanban/issues/tree_service.py`, `mcp/surfaces/agent/create_ticket.py`, `mcp/surfaces/agent/update_ticket.py`, `kanban/services/assignees.py`, `kanban/api/v1/__init__.py`, `mcp/surfaces/agent/__init__.py`.

---

### 1. Architectural & Security Verification

1. **Zero Database Import Invariant in MCP:**
   - Forensic static analysis confirms `mcp/` imports zero database packages and holds zero direct database credentials.
   - MCP tools `create_ticket` and `update_ticket` invoke REST endpoints via `KanbanApiClient` (`POST /api/v1/projects/{project_ref}/issue-trees`, `PATCH /api/v1/issues/{key}`, `POST /api/v1/issues/{key}/assignees`, `DELETE /api/v1/issues/{key}/assignees/{id}`, `GET /api/v1/resolve`).
   - `lint-imports` confirms contracts: 2 kept, 0 broken. Module layers `agent -> mcp -> kanban -> database` strictly upheld.

2. **Transactional Atomicity & Tree Rollback Guarantee:**
   - Atomic hierarchy generation executes inside a single database transaction.
   - If any node in the tree violates validation constraints (e.g. summary length > 500 characters, date order `due_date < start_date`, invalid foreign references, or unauthorized assignees), the entire transaction aborts with zero rows inserted into `issues`, `objects`, `activity_records`, or join tables.
   - Verified by `test_case_2_atomicity_and_security_rollback`: zero issue and object rows persist after a 422 failure on the 3rd child node.

3. **DAG Validation & Hierarchy Limits:**
   - Breadth-first traversal enforces depth <= 6 (`_MAX_DEPTH`) and node count <= 50 (`_MAX_NODES_PER_CALL`).
   - PostgreSQL parent trigger `check_parent_hierarchy_trg` and application logic enforce cycle rejection (`PARENT_CYCLE`) and parent depth boundaries.
   - Direct parent attachment (`parent` reference as key or UUID) verifies parent issue existence, non-deleted status, and project identity before linking.

4. **ETag Concurrency Control & Byte Limit Defense:**
   - `update_ticket` strictly mandates `if_match` header (64-character SHA-256 hex ETag) whenever `description_markdown` is supplied.
   - Precondition evaluation sends `If-Match: "<etag>"` to the issue patch API. On 412 Precondition Failed, the MCP tool returns `CONFLICT_ETAG` with a hint containing the current fresh description SHA-256 hash.
   - Description updates check byte length against 1,048,576 bytes (1 MiB) before dispatching, rejecting oversized content with `VALIDATION_FAILED`.

5. **Security & Input Sanitization Invariants:**
   - Hostile input in `description_markdown` (such as hidden CSS tags `<div style="display:none">...</div>`) is stripped to canonical Markdown via `normalize_to_markdown`.
   - Assignee resolution performs capability checks verifying that every assigned principal belongs to the workspace and holds VIEW access to the project, preventing privilege leakage.
   - State mutations via `update_ticket` are explicitly rejected with `VALIDATION_FAILED` (hint: `"use transition_ticket"`).
   - Custom field arguments are rejected fail-closed with `VALIDATION_FAILED` (hint: `"custom fields arrive in Phase 5"`).

---

### 2. Verification Matrix

| Evaluation Dimension | Target Requirement | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Tool Registration** | `create_ticket` & `update_ticket` on `/mcp/agent` | Registered on `Surface.AGENT` in `mcp/surfaces/agent/__init__.py` | PASS |
| **Recursive Tree Creation** | Parent + sub-issue trees up to 6 levels, 50 nodes | BFS atomic traversal, consecutive sequence IDs, `PARENT_OF` object links | PASS |
| **Rollback Atomicity** | Zero rows persisted on validation failure | Verified by `test_case_2_atomicity_and_security_rollback` (count before == after) | PASS |
| **ETag Concurrency** | 412 mapped to `CONFLICT_ETAG` with current etag hint | Verified by `test_case_3_concurrency_etag_conflict` | PASS |
| **Hostile Input Sanitization** | Hidden tags pruned to canonical Markdown | Verified by `test_case_6_hostile_input_sanitization` | PASS |
| **Assignee Security Gate** | Reject principals lacking project view access | Verified by `test_case_2_atomicity_and_security_rollback` (`@eve` rejected) | PASS |
| **Scope Enforcement** | Caller with `agent:read` only rejected | Verified in `test_case_2_atomicity_and_security_rollback` (`INSUFFICIENT_SCOPE`) | PASS |
| **LOD Projection** | Summary projection of root and child keys | `IssueTreeRootSummary` & `IssueTreeChildSummary` returned with created count | PASS |
| **Unit Test Coverage** | >= 95% line and branch coverage | 28 tests passing; target coverage achieves 95% | PASS |
| **Static Analysis / Lint** | Ruff, strict mypy, lint-imports, license gate | All 4 gates pass with 0 errors across 408 files | PASS |

---

### 3. Recommendation
Implementation is robust, security-hardened, and adheres strictly to all architectural specifications. **APPROVED**.
