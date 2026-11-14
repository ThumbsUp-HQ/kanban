# API Specialist Gate Review: KANBA-137 (KB-P4-10)

- **Ticket**: `KANBA-137` (`KB-P4-10`: `[Phase 4 / MCP] /mcp/admin tools 5-6: architect_project (declarative plan/apply) & manage_cycles_and_modules`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-137`
- **Branch**: `feat/KANBA-137`
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Verification Matrix

As Systems/Backend Architect & API Specialist, I have performed an exhaustive architectural and API wire contract review of the implementation for `KANBA-137` (`KB-P4-10`), implementing declarative project blueprinting REST API (`POST /api/v1/admin/projects/blueprint:plan`, `POST /api/v1/admin/projects/blueprint:apply`, `GET /api/v1/admin/projects/{project_ref}/blueprint`) and MCP Admin tools (`architect_project` and `manage_cycles_and_modules` on Surface.ADMIN), plus cycle rollover (`POST /api/v1/cycles/{cycle_id}/rollover`), according to `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 11.4, 7.2, 12.2, 6.4), `AGENTS.md`, and `docs/tickets/KB-P4-10.md`.

The implementation satisfies all architectural, data consistency, and security invariant requirements:
- **Declarative Blueprint Engine (`ProjectBlueprint`)**: The Pydantic model strictly enforces `extra="forbid"`, valid identifier regex `^[A-Z][A-Z0-9]{1,9}$`, state bounds (`<= 30` states, `>= 1` in `started` and `>= 1` in `completed`), priority bounds (`<= 10` priorities), label bounds (`<= 200` labels with `^[a-z0-9_-]{1,32}$` exclusive groups), module bounds (`<= 100` modules), and `auto_archive_days` between 1 and 365.
- **TOCTOU Plan Hashing (`PLAN_STALE`)**: `compute_plan` calculates a deterministic SHA-256 hash across canonical JSON diff changes. On `apply`, the engine re-evaluates the live project state against the submitted blueprint and verifies `plan_sha256`. If live state was modified concurrently, HTTP 409 `PLAN_STALE` is raised and no mutations are applied.
- **In-Use Protection & Controlled Migration (`STATE_IN_USE`, `PRIORITY_IN_USE`)**:
  - Removing a workflow state with active issues without an explicit `state_migrations` mapping raises HTTP 409 `STATE_IN_USE` detailing the issue count.
  - Specifying valid state migrations atomically reassigns all issues before deleting the obsolete state.
  - Removing a custom priority currently assigned to issues raises HTTP 409 `PRIORITY_IN_USE`.
  - State mutations execute creation and update operations prior to deletions, ensuring PostgreSQL terminal state triggers (`workflow_states_group_guard_bd_trg`) maintain `>= 1` completed and `>= 1` cancelled state at all times.
- **Cycle Rollover & Monotonicity (`INVALID_TRANSITION`)**:
  - Iteration status transitions strictly enforce `upcoming -> active -> completed`. Backward or skipped transitions raise HTTP 409 `INVALID_TRANSITION`.
  - Rollover atomically transitions unfinished issues (issues not in `completed` or `cancelled` state groups) from the source cycle into an upcoming or active target cycle.
- **Module Safeguards (`MODULES_DISABLED`)**:
  - Creating or managing modules in a project with `modules_enabled = false` raises HTTP 409 `MODULES_DISABLED`.
- **AAL2 & Admin Route Protection**:
  - All `/api/v1/admin/projects/blueprint*` endpoints enforce `Depends(require_admin_aal2)`.
  - Caller must hold `PROJECT_ADMIN` or `WORKSPACE_ADMIN` capabilities for existing project blueprints.
- **Activity & Audit Logging**:
  - Applying a blueprint atomically appends a `PROJECT_BLUEPRINT_APPLIED` activity ledger entry with the applied plan.
  - Cycle rollover records `CYCLE_ROLLOVER_EXECUTED` entries with moved issue counts.
- **MCP Surface & Tool Isolation**:
  - `architect_project` exposes `get` (`admin:read`), `plan` (`admin:write`), `apply` (`admin:write`), and `help`.
  - `manage_cycles_and_modules` exposes exactly 13 operations across cycles, modules, and saved views with zero delete actions and zero `bind_project_repo` references.
- **Clean Architecture & Layering**:
  - Zero database imports in `mcp/` (`lint-imports` contract: 2 kept, 0 broken).
  - Strict typing (`mypy --strict`) passes with 0 errors across all 13 modified files.
  - Zero Unicode dashes (`U+2014`, `U+2013`) repo-wide (plain ASCII `-` only).

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Blueprint Plan / Apply API** | POST /admin/projects/blueprint:plan & :apply | Verified in `test_project_blueprint.py` (6/6 pass) | PASS |
| **TOCTOU Stale Plan Gate** | plan_sha256 mismatch -> 409 PLAN_STALE | Verified in API and MCP tests | PASS |
| **In-Use Protection** | STATE_IN_USE & PRIORITY_IN_USE on active entities | Verified in API and MCP tests | PASS |
| **State Group Invariant** | >= 1 started, >= 1 completed, terminal guards | Verified in boundary & update tests | PASS |
| **Cycle Rollover** | Atomically moves unfinished issues, validates target | Verified in API & MCP rollover tests | PASS |
| **Monotonic Cycle States** | upcoming -> active -> completed only | Verified: INVALID_TRANSITION on skips | PASS |
| **Module Gating** | modules_enabled=false -> MODULES_DISABLED | Verified across API & MCP tools | PASS |
| **Tool Spec Invariant** | No bind_project_repo or delete action in tool 6 | Verified in test_contract_no_bind_or_delete | PASS |
| **Layering Integrity** | mcp forbidden from importing database | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| **Unit Test Coverage** | >= 95% line and branch coverage across touched modules | Total Coverage: **96%** (22/22 tests pass) | PASS |
| **Static Analysis** | Ruff clean, Mypy strict clean, no Unicode dashes | Verified in `build-check.txt` | PASS |

---

## 2. Architectural Audit Findings

### 2.1 Atomic Execution & Rollback Safety
The blueprint apply implementation is encapsulated inside a single database transaction. All state renamings, state additions, issue migrations, state deletions, priority creations/updates, label adjustments, and module allocations execute sequentially with immediate flush. If any validation fails (e.g., duplicate unique constraint, invalid foreign key, or missing migration target), the entire transaction rolls back cleanly without leaving orphan states or partial configurations.

### 2.2 Entity Resolution & Human-Readable Keys
The MCP admin tools provide transparent entity resolution: callers can pass either UUIDs or human-readable names (`cycle: "Cycle 1"`, `module: "Core"`, `view: "Sprint Board"`). The tool resolves names to project-scoped UUIDs prior to invoking REST endpoints, improving agent conversational UX without compromising API precision.

---

## 3. Verdict

The implementation of `KANBA-137` (`KB-P4-10`) satisfies all architectural specifications, data integrity invariants, and wire contract requirements.

**Verdict: APPROVED**
