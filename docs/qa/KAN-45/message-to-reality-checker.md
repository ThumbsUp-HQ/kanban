# Reality-Checker Verification Packet: KAN-45

**Ticket:** `KAN-45`  
**Title:** `[KB-P3-GATE-ENFORCE] Enforce Canonical Reality-Checker Report on complete_work, Real qa-proof-validator Wasm, Approval Comment Persistence, and Agent Done-Transition Guards (4 Problems)`  
**Branch:** `main` (Post-Merge at commit `78074a1d`)  
**Base Commit:** `78074a1d`  
**Live Stack Container:** `kanban-liveqa-4` (`http://127.0.0.1:18964`, PostgreSQL 16 + FORCE RLS)  
**Live Stack Verdict:** `OVERALL LIVE_STACK_VERDICT: PASS`  

---

## 1. Executive Summary & Problem Resolution

This deliverable implements all 4 problems specified in `KAN-45` to enterprise security and architectural standards, verified against live unmocked container execution:

### Problem 1: Canonical Reality-Checker Report & Strict VerificationProof in complete_work
- **Anchored Regex Security:** All path validation regexes in `kanban/issues/proof.py` and `mcp/surfaces/agent/proof.py` are strictly anchored with `\A...\Z`.
- **RealityCheckerProof Schema:** Requires `report_path` matching `\Adocs/qa/[A-Z][A-Z0-9]{1,9}-[0-9]{1,18}/reality-checker-report\.md\Z` and forbids traversal (`.` or `..`).
- **Artifacts Path Enforcement:** Requires non-empty list (`min_length=1`), forbids `.` segments, `..` directory traversal, and trailing slashes.
- **CI Run URL Validation:** Validates `ci_run_url` via `urllib.parse.urlsplit` requiring `https` scheme, non-empty network location, rejection of embedded credentials (`user:pass@`), length `<= 2048`, and rejection of markdown delimiter injection.
- **Linear O(N) Report Parser (`validate_reality_checker_report`):**
  - Linear scan with zero backtracking regexes.
  - Rejects UTF-16 lone surrogates (`0xD800 <= ord(c) <= 0xDFFF`).
  - Normalizes lines via `unicodedata.normalize("NFKC", ...)` to prevent homoglyph evasion.
  - Ignores lines within fenced code blocks (` ``` ` and `~~~`) and HTML comment blocks (`<!-- ... -->`).
  - Enforces mandatory `# Integration Agent Reality-Based Report` H1 heading.
  - Enforces all 6 canonical H2 sections (`Reality Check Validation`, `Complete System Evidence`, `Integration Testing Results`, `Comprehensive Issue Assessment`, `Realistic Quality Certification`, `Deployment Readiness Assessment`) each containing non-empty body lines.
  - Rejects anti-fantasy contradiction markers (`NEEDS WORK`, `NEEDS_WORK`, `FAILED`) inside certification and readiness sections when verdict claims `READY` or grade claims `A`.
- **Workflow Service Integration:**
  - `complete_work` in `kanban/issues/workflow_service.py` executes `validate_reality_checker_report(summary_markdown)` raising `422 INVALID_REALITY_CHECKER_REPORT` on structural or contradiction failure.
  - Routes state transitions through `TransitionEngine` when configured transition hooks target `(from_state, target_state)`.
  - Fixes `_collect_open_blockers` to filter `deleted_at IS NULL` on ancestor and child issues, and inspects outgoing `BLOCKED_BY` links in addition to incoming `BLOCKS` links.

### Problem 2: Persist Approval Report Comment & Fail-Closed Terminal Gates
- **Comment Formatter:** Implemented `format_approve_comment(hook_name, harness_label, from_state_name, to_state_name, reason_markdown)` in `kanban/workflows/async_gate.py` with bounded size (`MAX_APPROVE_COMMENT_BYTES = 65536`) and normalized content.
- **Comment Persistence on Step 7 Approve:**
  - On final Step 7 approval (preserving sequential multi-hook chaining without spurious intermediate comments), persists an `IssueComment` authored by `agent_def.principal_id` (falling back safely to invoking principal).
  - Emits `ActivityEventType.COMMENT_CREATED` to the immutable audit ledger.
  - Stores bounded `reason` (`<= 16384` chars within `65536` DB check) in `execution.verdict_json` and `invocation.output_json`.
- **Fail-Closed Terminal Gates:**
  - In `GateCoordinator.record_failure`, enforces `fail_closed` whenever `target_state.state_group == "completed"`. Timeouts or hook dispatch failures for transitions into `Done` never auto-approve into completed states.

### Problem 3: Real Wasm `qa-proof-validator` & Compilable Builtin Presets
- **Memory Safety in Wasm Runner:** In `kanban/sandbox/wasm_runner.py` (`TierAWasmRunner.run_sync`), validates `kb_alloc` return pointer (`isinstance(alloc_ptr, int) and alloc_ptr > 0 and alloc_ptr + len(input_bytes) <= memory.data_len(store)`) before writing to linear memory.
- **Compiled Real Bytecodes in `kanban/workflows/builtins.py`:**
  * `qa-proof-validator`: Compiled 1097-byte Wasm module (SHA-256: `fddfe97e1b15829495364a2002bf0a0c830002f9ef673971a1a4167ee815d972`), `<2ms` and `<= 2,000,000` fuel.
  * `sec_invariant_validator`: Valid compilable 249-byte Wasm module (SHA-256: `7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874`), exports `memory`, `kb_alloc`, `kb_run`, `kb_on_transition`, returns `{"allowed": true, "decision": "allow"}`.
  * `auto_label_mutator`: Valid compilable 244-byte Wasm module (SHA-256: `2e7db622992707370042a3c5e15eda145d995048ef4f69f6c746f33dc43f93e9`), exports `memory`, `kb_alloc`, `kb_run`, `kb_on_transition`, returns `{"allowed": true, "decision": "allow"}`.
- **Deterministic Validation Contract:** Parses `kb-sync-hook-input/v1` payload within `<2ms` and `<= 2,000,000` fuel. Verifies that `docs/qa/<ISSUE_KEY>/reality-checker-report.md` and `READY` appear in `verification_proof` or issue body/comments.
- **Enriched Hook Input Payload:** Enriches `kb-sync-hook-input/v1` in `engine.py` and `dry_run.py` with bounded `verification_proof` and recent issue comments within 256 KiB ceiling.

### Problem 4: Close REST completed-State Bypasses, Stateless Bearer CSRF Bypass & GateWorker Runner
- **CsrfMiddleware Stateless Bearer Bypass:** In `kanban/auth/sessions/csrf.py`, requests with `Authorization: Bearer <token>` bypass ambient cookie CSRF checks, allowing stateless agents and MCP clients to execute without CSRF token headers while preserving cookie CSRF protection.
- **PrincipalContext Extension:** Added `principal_type` and `is_mcp_credential` to `PrincipalContext` (`kanban/api/deps.py`) and session cookie resolver (`kanban/auth/sessions/resolver.py`). `is_agent_or_mcp_caller` returns `True` for agents, service principals, MCP credentials, and agent token scopes, while returning `False` for human browser cookies.
- **Agent Bypass Guard:** In `TransitionEngine.execute_transition`, enforces `422 USE_COMPLETE_WORK` whenever `target_state.state_group == "completed"` and caller is an agent or MCP client, closing `PATCH /api/v1/issues/{key}`, `POST /api/v1/issues/{key}/move`, and `POST /api/v1/issues/{key}/transitions` while preserving human board interactions.
- **Issue Move Hardening:** `kanban/services/issue_move.py` returns `202 pending_agent_gate` without prematurely updating `board_rank`. Added `TaintGuard.check_write` in `kanban/api/v1/issue_move.py`.
- **Transition Held Guard:** In `kanban/services/issues.py` (`update_issue`), raises `409 TRANSITION_HELD` when `issue.pending_transition_exec_id is not None`.
- **Gate Worker Runner:** Created `agent/gates/runner.py` with polling loop, lease claim, timeout sweeping, and execution handling. Added `kanban-agent run-gate-worker` CLI command (`agent/cli_commands/run_gate_worker.py`). Added lazy lifespan startup hook in `kanban/app.py` preserving strict `agent -> mcp -> kanban -> database` import layering.

---

## 2. Verification Artifacts & Live Container Evidence

### Live Container Verification (`kanban-liveqa-4`, `:18964`, commit `78074a1d`):
- `Guard 1`: Stateless Bearer `PATCH`, `POST move`, `POST transition` into Done -> HTTP 422 `USE_COMPLETE_WORK` (88ms, 65ms, 37ms). Human cookie `POST move` -> HTTP 200 (human allowed).
- `Guard 2`: MCP tool calls and Bearer REST `complete_work` with short summary or contradictory reports -> HTTP 422 `INVALID_REALITY_CHECKER_REPORT` (`isError=true`).
- `Guard 3`: Dry-Run UI and API with missing proof -> rejected by `require-qa-proof-link` (381us, 0 Wasm compile errors); valid proof -> allowed by `require-qa-proof-link` (299us) and `auto-label-verified` (149us).
- `Guard 4`: Valid `/mcp/agent complete_work` -> HTTP 200 (124ms, `isError=false`, state: Done, comment: `KAN-2#c-01a1fb44`).
- Telemetry: console errors 0, page errors 0, 5xx responses 0. `OVERALL LIVE_STACK_VERDICT: PASS`.

### Quality Gate Summary:
- **Pytest Suites (44 passed across API and Wasm suites):**
  - `kanban/tests/api/test_gate_enforcement_hardening.py`: 15 passed in 1.42s
  - `kanban/tests/workflows/test_qa_proof_validator_wasm.py`: 6 passed
  - `kanban/tests/workflows/test_dry_run.py`: 7 passed
  - `kanban/tests/workflows/test_workflow_hooks_api.py`: 16 passed
- **Static Gate Verification:**
  - `kanban-ctl db check-migrations`: 63 migrations valid.
  - `ruff check .`: All checks passed.
  - `ruff format --check .`: Clean across 2023 files.
  - `mypy database kanban mcp agent`: Success: 0 issues in 995 source files.
  - `lint-imports`: Contracts: 2 kept, 0 broken.
  - `scripts.check_no_dashes --all`: Clean (0 forbidden dashes).
- **Scope Invariants:** `.backup_schedule.json` and `backups/` strictly unstaged.
