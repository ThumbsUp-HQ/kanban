# API Specialist Review: KAN-71 (KB-AGENT-WORKPAD-01)

- Ticket: KAN-71
- Title: [KB-AGENT-WORKPAD-01] Add Silent Per-Issue Agent Workpad Slot, Rework Loop Circuit Breaker, Real BudgetEnforcer Wiring & MCP Rate Limits
- Reviewer: api-spec (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-23
- Target Directory: `docs/qa/KAN-71`
- Branch: `feat/KAN-71`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-71 on branch `feat/KAN-71`, verifying the 4 coupled architectural problems specified in the ticket:
1. Silent Per-Issue Agent Workpad Slot (`GET/PUT /api/v1/issues/{issue_key}/workpad`, `update_workpad` on `/mcp/agent`, `use_workpad` on `begin_work`, and workpad attached in `read_ticket(lod="full")`).
2. Per-Issue Rework Loop Circuit Breaker (`rework_rejection_streak`, `rework_tripped_at`, `max_rework_attempts`, 409 transition block for agents, human transition auto-reset, and human-only `POST /api/v1/issues/{issue_key}/reset-rework-breaker`).
3. Real `BudgetEnforcer` Wiring in Gate Worker (`agent/gates/runner.py` and `agent/harnesses/in_app_sdk.py`, with strict cap preservation in `agent/budget.py`).
4. MCP and Workflow Sliding-Window Rate Limiting (`MCP_TOOLS_CALL_RATE_LIMIT` on `/mcp/*` tools/call returning 429 with `Retry-After`, plus rate limiting on issue workflow and workpad routes).

All API schemas, security controls, database migrations, rate limit protections, and unit tests have been audited and verified.

---

## 2. Detailed Contract & Security Verification

### 2.1 Problem 1: Silent Per-Issue Agent Workpad Slot
- Database Model: `IssueWorkpad` (`issue_workpads` table) in `database/models/issue_workpad.py`.
  - Primary key: `id UUID PRIMARY KEY DEFAULT uuidv7()`.
  - Foreign keys: `workspace_id`, `project_id`, `issue_id REFERENCES issues(id) ON DELETE CASCADE`, `principal_id REFERENCES principals(id)`.
  - Generated column: `body_sha256 BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED`.
  - Revision: `revision BIGINT NOT NULL DEFAULT 1`.
  - Unique constraint: `UNIQUE (issue_id, principal_id)`.
  - RLS: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` inheriting parent issue visibility.
- Service Layer: `kanban/issues/workpad_service.py`:
  - `get_issue_workpad`: returns existing workpad or clean default with `revision=0` and empty body without raising 404.
  - `put_issue_workpad`: validates UTF-8 byte length (rejecting > 65536 bytes with `422 WORKPAD_PAYLOAD_TOO_LARGE`), detects lone surrogates (rejecting with `422 INVALID_UTF8_SURROGATE`), and enforces CAS revision matching (`412 PRECONDITION_FAILED` on mismatch).
  - Suppression of noise: zero `@mention` extractions, zero activity records, and zero comments created.
- REST Endpoint: `kanban/api/v1/issue_workpad.py`:
  - `GET /api/v1/issues/{issue_key}/workpad`: timing floor 25ms, ETag header `"{revision}"`, rate limited via `ISSUE_WORKPAD_RATE_LIMIT`.
  - `PUT /api/v1/issues/{issue_key}/workpad`: timing floor 25ms, If-Match header / body revision check, rate limited via `ISSUE_WORKPAD_RATE_LIMIT`.
- MCP Surfaces:
  - `mcp/surfaces/agent/workpad.py`: `update_workpad` tool registered on `/mcp/agent`. Total `/mcp/agent` schema stays within budget (1,674 tokens <= 1,800 tokens).
  - `mcp/surfaces/agent/read_ticket.py`: attaches `workpad` slot when `lod == "full"`.
  - `mcp/surfaces/agent/begin_work.py`: accepts `use_workpad: bool = True` and calls `workflow_service.begin_work` with workpad storage.

### 2.2 Problem 2: Per-Issue Rework Loop Circuit Breaker
- Schema Migration: `p6_10_issue_workpads_and_rework_breaker.py`:
  - `workflow_transition_hooks`: `max_rework_attempts SMALLINT NOT NULL DEFAULT 3 CHECK (max_rework_attempts BETWEEN 1 AND 20)`.
  - `issues`: `rework_rejection_streak SMALLINT NOT NULL DEFAULT 0 CHECK (rework_rejection_streak >= 0)` and `rework_tripped_at TIMESTAMPTZ NULL`.
- Workflow Engine: `kanban/workflows/engine.py` and `kanban/workflows/async_gate.py`:
  - Transition rejections increment `rework_rejection_streak`.
  - When `rework_rejection_streak >= max_rework_attempts`, `rework_tripped_at` is set.
  - In `execute_transition`, if `issue.rework_tripped_at is not None` and caller is agent (`actor.is_agent_or_mcp_caller`), raises `409 REWORK_LOOP_LIMIT_EXCEEDED`.
  - Successful human transitions reset `rework_rejection_streak = 0` and clear `rework_tripped_at = None`.
- Reset Endpoint: `POST /api/v1/issues/{issue_key}/reset-rework-breaker`:
  - Human users (`caller.is_user`) can reset the breaker, setting `rework_rejection_streak = 0` and `rework_tripped_at = None`.
  - Agent or MCP callers are strictly rejected with `403 FORBIDDEN` (`AGENT_BREAKER_RESET_FORBIDDEN`).

### 2.3 Problem 3: Real BudgetEnforcer Wiring
- Gate Worker Runner: `agent/gates/runner.py`:
  - `_load_entities()` instantiates live `BudgetEnforcer(session=session)` and passes it to `InAppSdkHarness`.
  - Propagates real `workspace_id`, `project_id`, and `provider_config_id` to `agent_dict`.
- In-App SDK Harness: `agent/harnesses/in_app_sdk.py`:
  - Extracts real `ws_id`, `proj_id`, `cfg_id` from `agent_dict` / `agent_def` / `ctx` instead of hardcoded dummy UUIDs.
  - Reserves tokens against `self.budget_enforcer.reserve()`.
- Token Cap Preservation: `agent/budget.py`:
  - In `settle()`, preserves strict `token_cap` using `tokens_used = LEAST(token_cap, tokens_used + :actual)` instead of expanding `token_cap` via `GREATEST(...)`.

### 2.4 Problem 4: MCP and Workflow Rate Limiting
- MCP Protocol: `mcp/protocol.py`:
  - Resolves `RateLimiter` from application state and checks `MCP_TOOLS_CALL_RATE_LIMIT`.
  - Exceeding rate limit returns HTTP 429 with `Retry-After` header and JSON Problem response.
- REST Routes:
  - `kanban/api/v1/issue_workpad.py` uses `ISSUE_WORKPAD_RATE_LIMIT`.
  - `kanban/api/v1/comments.py` uses `ISSUE_COMMENTS_RATE_LIMIT`.
  - `kanban/api/v1/issue_workflow.py` uses `ISSUE_WORKFLOW_RATE_LIMIT`.

---

## 3. Test Coverage & Verification

- `kanban/tests/issues/test_issue_workpad.py`: 4 passing tests verifying CRUD, CAS revision conflict, lone surrogate rejection, byte bounds, zero comment noise, and silent `begin_work`.
- `kanban/tests/workflows/test_rework_circuit_breaker.py`: 3 passing tests verifying agent block on trip, human reset endpoint (agent 403 rejection), and human transition auto-reset.
- `agent/tests/test_budget_real_wiring.py`: 2 passing tests verifying strict `token_cap` preservation and `BudgetExceeded` halts.
- `mcp/tests/test_mcp_rate_limits.py`: 1 passing test verifying MCP `tools/call` burst returns 429 with `Retry-After`.
- `database/tests/migrations/test_p6_10_issue_workpads_and_rework_breaker_migration.py`: 1 passing test verifying up/down DDL migration.
- `database/tests/test_p1_17_models.py`: 6 passing tests verifying ORM schema parity and `IssueWorkpad` roundtrip.
- `mcp/tests/test_schema_budget.py`: 2 passing tests verifying `/mcp/agent` schema stays within 1,800 token budget.

Total Python tests: 19 passed in 3.81s.
Code quality: `make check` passed (ruff 0 errors, mypy 0 errors, lint-imports 0 broken contracts, check_no_dashes 0 dash errors, check-migrations 0 errors).

---

## 4. Certification

The implementation of KAN-71 strictly fulfills all security, API, and architectural requirements.
STATUS: APPROVED
