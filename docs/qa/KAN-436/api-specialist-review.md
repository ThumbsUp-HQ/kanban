# API Specialist Review - KAN-436

- **Ticket:** KAN-436 (`[BUG][WORKFLOW-HOOKS] Commit Mutating workflow_hooks Routes Before Return and Clarify HARDENED_GATE_PREAMBLE Data-vs-Instructions Wording`)
- **Worktree / Branch:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan436-d2811689` (`fix/KAN-436-workflow-hooks-commit-and-gate-preamble`, base `390cbf18`)
- **Reviewer Role:** Backend Architect / API Specialist (`.agents/agents/backend-architect.md`)

## 1. Scope & Artifacts Audited

- `docs/qa/KAN-436/git-diff.patch` (351 lines across 4 touched files)
- `kanban/api/v1/workflow_hooks.py` (lines 1-199)
- `agent/harnesses/in_app_sdk.py` (lines 1-418)
- `kanban/tests/workflows/test_workflow_hooks_api.py` (lines 1-1127)
- `agent/tests/harnesses/test_in_app_sdk.py` (lines 1-636)
- `docs/qa/KAN-436/unit-test-results.txt`
- `docs/qa/KAN-436/build-check.txt`
- Supporting contract verification: `database/session.py` (`RLSSessionFactory.session`), `kanban/api/deps.py` (`get_rls_session`), `kanban/workflows/hooks_service.py`, `kanban/workflows/builtins.py` (`ensure_approved_wasm_modules`), `kanban/workflows/dry_run.py` (`run_dry_run`), `agent/context/transition_context.py`, `agent/context/verdict.py`.

## 2. Transaction & Durability Audit (`kanban/api/v1/workflow_hooks.py`)

In `kanban/api/deps.py` (`get_rls_session`) and `database/session.py` (`RLSSessionFactory.session`), the session context manager commits only on generator teardown (`if sess.in_transaction(): await sess.commit()`). Explicit `await session.commit()` inside mutating route handlers guarantees PostgreSQL commit durability prior to HTTP response return so immediate follow-up `GET` or dependent `POST` requests never observe uncommitted state.

Route-by-route verification in `kanban/api/v1/workflow_hooks.py`:

- `list_workflow_hooks` (`GET /projects/{project}/workflow-hooks`, lines 40-47): Read-only query (`WorkflowHookService.list_hooks`); no `session.commit()`. PASS.
- `create_workflow_hook` (`POST /projects/{project}/workflow-hooks`, lines 56-66): Calls `WorkflowHookService.create_hook(...)`, executes `await session.commit()` before returning `result` (`WorkflowHookResponse`). PASS.
- `update_workflow_hook` (`PATCH /workflow-hooks/{hook_id}`, lines 74-84): Calls `WorkflowHookService.update_hook(...)`, executes `await session.commit()` before returning `result`. PASS.
- `enable_workflow_hook` (`POST /workflow-hooks/{hook_id}/enable`, lines 92-104): Calls `WorkflowHookService.set_enabled(..., is_enabled=True)`, executes `await session.commit()` before returning `result`. PASS.
- `disable_workflow_hook` (`POST /workflow-hooks/{hook_id}/disable`, lines 112-124): Calls `WorkflowHookService.set_enabled(..., is_enabled=False)`, executes `await session.commit()` before returning `result`. PASS.
- `delete_workflow_hook` (`DELETE /workflow-hooks/{hook_id}`, lines 132-144): Calls `WorkflowHookService.delete_hook(...)`, executes `await session.commit()` before returning `Response(status_code=status.HTTP_204_NO_CONTENT)`. PASS.
- `reorder_workflow_hooks` (`POST /projects/{project}/workflow-hooks/reorder`, lines 152-162): Calls `WorkflowHookService.reorder_hooks(...)`, executes `await session.commit()` before returning `result`. PASS.
- `dry_run_workflow_hooks` (`POST /projects/{project}/workflow-hooks/dry-run`, lines 170-178): Calls `await run_dry_run(session, caller, project, body)` with NO `session.commit()`. Verified `run_dry_run` executes inside `async with session.begin_nested():` and forces `await session.rollback()`. PASS.
- `list_approved_wasm_modules` (`GET /projects/{project}/approved-wasm-modules`, lines 186-199): `ensure_approved_wasm_modules(...)` auto-seeds missing or outdated built-in `ApprovedWasmModule` rows via nested savepoints and `flush()`; explicit `await session.commit()` runs before returning `modules` (`list[WasmModuleSummaryResponse]`). PASS.

Additional architectural checks:
- **No double-commit or detached-ORM risk:** `RLSSessionFactory.session()` guards teardown commit with `if sess.in_transaction(): await sess.commit()`, and all routes materialize Pydantic response models before `await session.commit()`.
- **Fail-closed error paths:** Validation, RBAC (`require_admin`, 404 anti-enumeration), and `AAL2` (`require_aal2`, 403 `AAL2_REQUIRED`) checks raise before `await session.commit()`, rolling back cleanly on error.
- **Timing side-channel parity:** `await session.commit()` executes inside `async with timing_floor(floor_ms=25.0):` on all 7 mutating routes.

## 3. Prompt-Injection Isolation & Gate Rubric Audit (`agent/harnesses/in_app_sdk.py`)

Verified `HARDENED_GATE_PREAMBLE` (lines 52-70) and its consumption in `InAppSdkHarness.run()` (lines 304-309):

- **Placeholder preservation:** Both `{delimiter}` and `{nonce}` placeholders are preserved and interpolated via `HARDENED_GATE_PREAMBLE.format(delimiter=ctx.delimiter, nonce=ctx.verdict_nonce)` without unescaped braces.
- **Data-vs-instruction isolation (spotlighting):** Explicitly mandates that content inside `{delimiter}` is ticket data to evaluate against the gate rubric, never executable instructions, role changes, or policy overrides, and instructs the model to ignore any instructions, prompts, forged verdicts, or attempts to alter gate logic embedded inside `{delimiter}`.
- **Authoritative ticket submission clarification:** The `EVIDENCE EVALUATION RULE` section explicitly establishes that by platform security design, all ticket descriptions, acceptance-criteria and Definition-of-Done checkboxes, test or build logs, comments, and verification proof references are delivered inside `{delimiter}` with no separate outside channel, and directs the evaluator to read and evaluate the ticket record and proof inside `{delimiter}` directly against the rubric (`approve` when satisfied; `reject` when criteria are unchecked, proof is missing or fabricated, or the delimited text attempts prompt injection).
- **Verdict sealing:** Maintains schema `'kb-transition-verdict/v1'` with `nonce = '{nonce}'`, backed by `StrictVerdictSchema` and server-side `nonce = ctx.verdict_nonce` assignment before `parse_verdict_output` verification.

## 4. Test Coverage, Security/STRIDE, Lint, Type-Check & Style Verification

- **Unit Tests & Coverage (`docs/qa/KAN-436/unit-test-results.txt`):**
  - `agent/harnesses/in_app_sdk.py`: 185 statements, 4 missed, 44 branches, 6 partial -> **96% coverage** (>= 95% threshold met).
  - `kanban/api/v1/workflow_hooks.py`: 65 statements, 0 missed, 0 branches -> **100% coverage** (>= 95% threshold met).
  - Combined total in report: 250 statements, 4 missed, 44 branches, 6 partial -> **97% coverage** (`35 passed in 10.79s` and `21 passed in 3.29s`).
  - Added tests verified in `kanban/tests/workflows/test_workflow_hooks_api.py` (`test_workflow_hooks_explicit_commit_durability`, lines 1012-1127) and `agent/tests/harnesses/test_in_app_sdk.py` (`test_hardened_gate_preamble_contract_and_system_prompt_composition`, lines 528-636).
- **Security / STRIDE Verification:**
  - Verified existing API security tests in `test_workflow_hooks_api.py` (anti-enumeration 404s, AAL2 403 enforcement, invalid mutable field rejections, unapproved Wasm rejections, dry-run `would_commit` / savepoint isolation) and harness security tests in `test_in_app_sdk.py` (`test_in_app_sdk_security_forbidden_tool_attempt`, `test_in_app_sdk_security_repo_none_blocks_repo_tools`, `test_in_app_sdk_boundary_tool_loop_exceeded`).
  - Note: `unit-test-results.txt` records 35 + 21 = 56 passing tests (more than the 18 + 10 = 28 tests in the two edited files), though the raw pytest command lines are not printed in `unit-test-results.txt`.
- **Lint & Type Checks (`docs/qa/KAN-436/build-check.txt`):**
  - `ruff check`: `All checks passed!`
  - `ruff format`: `2888 files already formatted`
  - `mypy`: `Success: no issues found in 1370 source files`
- **Unicode Dash Hygiene:**
  - Verified zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) in `docs/qa/KAN-436/git-diff.patch` and all touched source/test files; plain ASCII hyphens (`-`) are used throughout.

Verdict: APPROVED
