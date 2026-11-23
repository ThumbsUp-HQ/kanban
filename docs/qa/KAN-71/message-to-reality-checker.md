# Forensic QA Packet: KAN-71 (KB-AGENT-WORKPAD-01)

- Ticket: KAN-71
- Title: [KB-AGENT-WORKPAD-01] Add Silent Per-Issue Agent Workpad Slot, Rework Loop Circuit Breaker, Real BudgetEnforcer Wiring & MCP Rate Limits
- Author: b-kan71
- Reviewers: api-spec, ui-designer, reality-checker
- Branch: `feat/KAN-71`
- Date: 2026-11-23

---

## 1. Scope & Objective

This packet delivers complete forensic proof for KAN-71 addressing 4 coupled problems:
1. **Silent Per-Issue Agent Workpad Slot & Collapsible UI Tab**:
   - PostgreSQL table `issue_workpads` with RLS inheriting parent issue visibility (`database/models/issue_workpad.py`, migration `p6_10_issue_workpads_and_rework_breaker`).
   - Service layer `kanban/issues/workpad_service.py` enforcing canonical UTF-8 normalization, surrogate rejection (`INVALID_UTF8_SURROGATE`), 65536 byte payload bounds (`WORKPAD_PAYLOAD_TOO_LARGE`), and CAS revision matching (`PRECONDITION_FAILED`).
   - REST endpoints `GET/PUT /api/v1/issues/{issue_key}/workpad` with timing floor, ETag, and `ISSUE_WORKPAD_RATE_LIMIT`.
   - MCP tool `update_workpad` on `/mcp/agent` within schema budget (1,674 tokens <= 1,800 tokens), `use_workpad: bool = True` on `begin_work`, and workpad attached in `read_ticket(lod="full")`.
   - Collapsible `🤖 Workpad` tab rendered in `IssueSurface.tsx` with zero human comment spam.
2. **Per-Issue Rework Loop Circuit Breaker**:
   - `max_rework_attempts` on `workflow_transition_hooks` (default 3), `rework_rejection_streak` and `rework_tripped_at` on `issues`.
   - Async and sync hook rejections increment streak; reaching threshold sets `rework_tripped_at`.
   - Agent-initiated transitions rejected with `409 REWORK_LOOP_LIMIT_EXCEEDED` when tripped.
   - Human transitions auto-reset streak and clear tripped status.
   - Dedicated human reset route `POST /api/v1/issues/{issue_key}/reset-rework-breaker` (agent callers rejected with 403).
   - `🛑🤖` tripped rework loop banner with `Reset Breaker` action in `IssueSurface.tsx`.
3. **Real `BudgetEnforcer` Wiring in Gate Worker**:
   - `GateWorkerRunner._load_entities()` passes live `BudgetEnforcer(session=session)` into `InAppSdkHarness`.
   - `InAppSdkHarness.run()` reserves and settles against real `(workspace_id, project_id, provider_config_id)`.
   - `BudgetEnforcer.settle()` preserves strict `token_cap` using `LEAST(token_cap, tokens_used + :actual)`.
4. **MCP and Workflow Sliding-Window Rate Limiting**:
   - `MCP_TOOLS_CALL_RATE_LIMIT` wired onto `/mcp/*` tools/call returning `429 RATE_LIMITED` with `Retry-After`.
   - Sliding-window rate limiters wired on `/api/v1/issues/{issue_key}/{begin-work,transition,complete-work,comments,workpad}`.

---

## 2. Gate Approvals & Artifacts

- **API Specialist Review**: `docs/qa/KAN-71/api-specialist-review.md` -> STATUS: APPROVED
- **UI Specialist Review**: `docs/qa/KAN-71/ui-specialist-review.md` -> STATUS: APPROVED
- **Unit Test Results**: `docs/qa/KAN-71/unit-test-results.txt` (19 passing Python tests, 3,447 passing Vitest tests)
- **Build & Quality Check**: `docs/qa/KAN-71/build-check.txt` (ruff, mypy, lint-imports, check-migrations, check_no_dashes all passing)
- **Git Diff**: `docs/qa/KAN-71/git-diff.patch`
- **File Manifest**: `docs/qa/KAN-71/changed-files-manifest.txt` with SHA-256 hashes verified via `sha256sum -c`
- **Responsive Visual Screenshots**: `docs/qa/KAN-71/screenshots/`
  - `01-workpad-breaker-desktop-light.png`: Desktop 1440x900 Light Mode
  - `02-workpad-breaker-desktop-dark.png`: Desktop 1440x900 Dark Mode
  - `03-workpad-breaker-tablet.png`: Tablet 768x1024
  - `04-workpad-breaker-mobile-portrait.png`: Mobile 390x844 Portrait
  - `05-workpad-breaker-mobile-landscape.png`: Mobile 844x390 Landscape

---

## 3. Definition of Done Compliance

- [x] Schema migration linear single-head chain verified (`p6_10_issue_workpads_and_rework_breaker`).
- [x] `issue_workpads` table with `FORCE ROW LEVEL SECURITY` and `body_sha256` generated column.
- [x] Zero comments created and zero notification events on workpad updates.
- [x] CAS revision matching and lone-surrogate rejection enforced.
- [x] Circuit breaker trips at max rework attempts and rejects subsequent agent transitions with 409.
- [x] Human reset endpoint allows human resets and rejects agent callers with 403.
- [x] Real `BudgetEnforcer` wiring verified without dummy UUIDs or silent cap expansion.
- [x] Sliding-window rate limiting on MCP tools/call returns 429 with `Retry-After`.
- [x] Vitest and pytest test coverage >= 95% on touched files.
- [x] Zero em-dashes and en-dashes anywhere in touched files.
- [x] Zero compiler, linter, or typecheck warnings.
