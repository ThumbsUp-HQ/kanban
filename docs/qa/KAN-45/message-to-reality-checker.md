# Reality-Checker Verification Packet: KAN-45

**Ticket:** `KAN-45`  
**Title:** `[KB-P3-GATE-ENFORCE] Enforce Canonical Reality-Checker Report on complete_work, Real qa-proof-validator Wasm, Approval Comment Persistence, and Agent Done-Transition Guards (4 Problems)`  
**Branch:** `feat/KAN-45`  
**Base Commit:** `73caabe7` (main)  

---

## 1. Executive Summary & Problem Resolution

This deliverable implements all 4 problems specified in `KAN-45` to enterprise security and architectural standards:

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

### Problem 3: Real Wasm `qa-proof-validator` & Bounds-Checked Linear Memory
- **Memory Safety in Wasm Runner:** In `kanban/sandbox/wasm_runner.py` (`TierAWasmRunner.run_sync`), validates `kb_alloc` return pointer (`isinstance(alloc_ptr, int) and alloc_ptr > 0 and alloc_ptr + len(input_bytes) <= memory.data_len(store)`) before writing to linear memory.
- **Compiled Real Bytecode:** Replaced the 176-byte no-op with compiled 1097-byte Wasm module (`kanban/workflows/builtins.py`, SHA-256: `fddfe97e1b15829495364a2002bf0a0c830002f9ef673971a1a4167ee815d972`).
- **Deterministic Validation Contract:** Parses `kb-sync-hook-input/v1` payload within `<2ms` and `<= 2,000,000` fuel. Verifies that `docs/qa/<ISSUE_KEY>/reality-checker-report.md` and `READY` appear in `verification_proof` or issue body/comments. Returns `{"decision":"allow","allowed":true}` or `{"decision":"reject","allowed":false,"reason":"..."}`.
- **Enriched Hook Input Payload:** Enriches `kb-sync-hook-input/v1` in `engine.py` and `dry_run.py` with bounded `verification_proof` and recent issue comments within 256 KiB ceiling.
- **Unified Output Parsing:** Unified decision/allowed/allow/verdict extraction across `engine.py` and `dry_run.py`.

### Problem 4: Close REST completed-State Bypasses & Wire GateWorker Runner
- **PrincipalContext Extension:** Added `principal_type` and `is_mcp_credential` to `PrincipalContext` (`kanban/api/deps.py`) and session cookie resolver (`kanban/auth/sessions/resolver.py`). `is_agent_or_mcp_caller` returns `True` for agents, service principals, MCP credentials, and agent token scopes, while returning `False` for human browser cookies.
- **Agent Bypass Guard:** In `TransitionEngine.execute_transition`, enforces `422 USE_COMPLETE_WORK` whenever `target_state.state_group == "completed"` and caller is an agent or MCP client, closing `PATCH /api/v1/issues/{key}`, `POST /api/v1/issues/{key}/move`, and `POST /api/v1/issues/{key}/transitions` while preserving human board interactions.
- **Issue Move Hardening:** `kanban/services/issue_move.py` returns `202 pending_agent_gate` without prematurely updating `board_rank`. Added `TaintGuard.check_write` in `kanban/api/v1/issue_move.py`.
- **Transition Held Guard:** In `kanban/services/issues.py` (`update_issue` only; `serialize_issue` untouched), raises `409 TRANSITION_HELD` when `issue.pending_transition_exec_id is not None`.
- **Gate Worker Runner:** Created `agent/gates/runner.py` with polling loop, lease claim, timeout sweeping, and execution handling. Added `kanban-agent run-gate-worker` CLI command (`agent/cli_commands/run_gate_worker.py`). Added lazy lifespan startup hook in `kanban/app.py` gated on `enable_background_jobs`, strictly preserving `agent -> mcp -> kanban -> database` import layering.

---

## 2. Verification Artifacts & Test Evidence

All required proof artifacts have been generated in `docs/qa/KAN-45/`:
- `docs/qa/KAN-45/changed-files-manifest.txt`: Complete manifest of modified and created files.
- `docs/qa/KAN-45/contract-sample.json`: Validated contract payloads for proof, Wasm inputs/outputs, and error structures.
- `docs/qa/KAN-45/build-or-typecheck.txt`: Clean static analysis logs (ruff, ruff format, mypy, import-linter, check_no_dashes).
- `docs/qa/KAN-45/unit-test-results.txt`: Comprehensive unit and regression test results (105 tests passing).
- `docs/qa/KAN-45/git-diff.patch`: Exact patch against base commit `73caabe7`.

### Quality Gate Summary:
- **Pytest Suites (105 passed in 33.77s):**
  - `kanban/tests/api/test_gate_enforcement_hardening.py`: 14 passed
  - `kanban/tests/api/test_issue_workflow.py`: 13 passed
  - `kanban/tests/api/test_issue_patch_etag_parity.py`: 2 passed
  - `kanban/tests/workflows/test_qa_proof_validator_wasm.py`: 6 passed
  - `kanban/tests/workflows/test_async_gate.py`: 15 passed
  - `kanban/tests/workflows/test_transition_engine.py`: 16 passed
  - `kanban/tests/workflows/test_dry_run.py`: 7 passed
  - `agent/tests/gates/test_gate_runner.py`: 3 passed
  - `agent/tests/gates/test_worker.py`: 8 passed
  - `mcp/tests/agent/test_workflow_tools.py`: 9 passed
  - `mcp/tests/agent/test_transition_ticket_gate.py`: 3 passed
  - `mcp/tests/agent/test_pending_gate_contract.py`: 3 passed
  - `mcp/tests/agent/test_workflow_argument_validation.py`: 6 passed
- **Ruff Linting:** 0 errors across `kanban`, `database`, `mcp`, `agent`, and `scripts`.
- **Ruff Formatting:** 1012 files formatted cleanly.
- **Mypy Strict Typechecking:** Success: 0 errors across 1132 source files.
- **Import Layering (`lint-imports`):** 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- **Typography Check (`check_no_dashes`):** 0 em-dashes and 0 en-dashes across all modified files.
- **Brand Hygiene:** 0 occurrences of forbidden terms in diff comments and docstrings.
- **Scope Invariants:** `serialize_issue` in `kanban/services/issues.py` untouched; `.backup_schedule.json` and `backups/` strictly unstaged.
