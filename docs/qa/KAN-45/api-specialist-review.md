# Clean-Room API Specialist Review: KAN-45

- Ticket: KAN-45 (`[KB-P3-GATE-ENFORCE]`)
- Title: [KB-P3-GATE-ENFORCE] Enforce Canonical Reality-Checker Report on complete_work, Real qa-proof-validator Wasm, Approval Comment Persistence, and Agent Done-Transition Guards (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Branch: `feat/KAN-45`
- Commit Under Audit: `5c345a8e`
- Base Reference Commit: `73caabe7` (on `main`)
- Target Directory: `docs/qa/KAN-45`
- Status: STATUS: APPROVED

---

## 1. Executive Summary & Audit Scope

A clean-room API, Security, and Architecture audit was conducted for ticket **KAN-45** on branch `feat/KAN-45` at commit `5c345a8e` pursuant to the mandatory Dual Specialist Gate defined in `GEMINI.md`.

KAN-45 hardens the workflow transition engine, closes completed-state bypasses, enforces canonical reality-checker report validation, replaces dummy Wasm placeholders with compiled bytecode, and establishes asynchronous gate runner infrastructure across the platform.

The audit inspects and certifies all four problems:
1. **Canonical Reality-Checker Report Validation & Strict VerificationProof:**
   - Enforces anchored regexes (`\A...\Z`), strict directory traversal checks, `min_length=1` artifact bounds, and `urllib.parse.urlsplit` URL sanitization on `VerificationProof` and `RealityCheckerProof`.
   - Implements deterministic linear O(N) `validate_reality_checker_report` rejecting UTF-16 lone surrogates (0xD800..0xDFFF), normalizing NFKC text, ignoring code blocks/comments, enforcing H1 and all 6 canonical H2 sections with non-empty body lines, and rejecting contradiction markers (`NEEDS WORK`, `NEEDS_WORK`, `FAILED`) when claiming `READY` or `A` grade.
   - Integrates validation into `complete_work`, routes state transitions through `TransitionEngine`, and fixes blocker resolution to inspect active issues and outgoing `BLOCKED_BY` links.
2. **Approval Comment Persistence & Fail-Closed Terminal Gates:**
   - Implements `format_approve_comment` with 64 KiB ceiling and normalized markdown formatting.
   - Persists `IssueComment` authored by agent principal on final Step 7 transition approvals and emits `ActivityEventType.COMMENT_CREATED`.
   - Enforces `fail_closed` whenever `target_state.state_group == "completed"`, preventing auto-approval bypass on hook failure or timeout.
3. **Real Wasm `qa-proof-validator` & Bounds-Checked Linear Memory:**
   - Bounds-checks guest `kb_alloc` memory pointer before writing into Wasm linear memory.
   - Embeds real compiled 1097-byte Wasm bytecode (SHA-256: `fddfe97e1b15829495364a2002bf0a0c830002f9ef673971a1a4167ee815d972`) running in `<2ms` and `<= 2,000,000` fuel.
   - Enriches `kb-sync-hook-input/v1` payload with verification proof and recent comments within 256 KiB ceiling, and unifies decision extraction.
4. **Agent Completed-State Guards & Gate Worker Runner:**
   - Implements `is_agent_or_mcp_caller` on `PrincipalContext` discriminating agents/MCP callers from human browser sessions.
   - Enforces HTTP 422 `USE_COMPLETE_WORK` in `TransitionEngine.execute_transition` when agents attempt to bypass `complete_work` via `PATCH /issues/{key}`, `POST /issues/{key}/move`, or `POST /issues/{key}/transitions`.
   - Protects board rank on `202 pending_agent_gate` in `issue_move.py` and raises HTTP 409 `TRANSITION_HELD` in `update_issue` during active gate execution (`serialize_issue` untouched).
   - Delivers `GateWorkerRunner`, CLI subcommand `kanban-agent run-gate-worker`, and lazy lifespan initialization in `kanban/app.py` preserving strict `agent -> mcp -> kanban -> database` layering.

---

## 2. Detailed Contract & Security Verification

### 2.1 Proof Validation & Linear Report Parser (`kanban/issues/proof.py`, `mcp/surfaces/agent/proof.py`)
- Regex Anchoring & Bounds:
  - `QA_DIR_REGEX`: `\Adocs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/?\Z`
  - `ARTIFACT_PATH_REGEX`: `\Adocs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/([A-Za-z0-9._/-]{1,200})\Z`
  - `REPORT_PATH_REGEX`: `\Adocs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/reality-checker-report\.md\Z`
  - `CI_RUN_URL_REGEX`: `\Ahttps://[A-Za-z0-9\-._~:/?#$!&*+,;=]{1,2048}\Z`
- CI URL Validation (`validate_ci_run_url`):
  - Validates scheme is strictly `https`.
  - Rejects embedded user credentials (`user:pass@`).
  - Enforces max length 2048 and rejects markdown delimiter characters (`[`, `]`, `(`, `)`, `<`, `>`, `"`, `'`, '`', `|`, whitespace).
- Linear O(N) Report Parser (`validate_reality_checker_report`):
  - Linear scan with zero backtracking regexes.
  - Surrogate check: detects code points between `0xD800` and `0xDFFF` and raises `ValueError`.
  - NFKC normalization: `unicodedata.normalize("NFKC", raw_line)` prevents homoglyph evasion.
  - Contextual stripping: ignores lines within fenced code blocks (``` and ~~~) and HTML comment blocks (`<!-- ... -->`).
  - Structure verification: mandates H1 `# Integration Agent Reality-Based Report` and all 6 canonical H2 sections:
    1. `## Reality Check Validation`
    2. `## Complete System Evidence`
    3. `## Integration Testing Results`
    4. `## Comprehensive Issue Assessment`
    5. `## Realistic Quality Certification`
    6. `## Deployment Readiness Assessment`
    Each section must contain non-empty body lines.
  - Anti-fantasy contradiction check: when claiming `READY` or `A` grade, rejects contradiction markers `NEEDS WORK`, `NEEDS_WORK`, or `FAILED`.

### 2.2 Approval Comment Persistence & Fail-Closed Terminal Gate (`kanban/workflows/async_gate.py`)
- Formatted Approval Comment:
  - `format_approve_comment` creates structured markdown (`## ✅🤖 Workflow Transition Gate Approved`) detailing hook name, harness label, transition states, and normalized rationale.
  - Size bounded at `MAX_APPROVE_COMMENT_BYTES = 65536`.
- Execution Step 7 Persistence:
  - On final Step 7 approval, creates `IssueComment` authored by `agent_def.principal_id` (falling back to `invoking_principal_id`).
  - Emits `ActivityEventType.COMMENT_CREATED` to the activity ledger with `{"comment_id": str(comment.id)}`.
  - Records bounded reason (<= 16384 chars) in `execution.verdict_json` and `invocation.output_json`.
- Fail-Closed Policy Enforcement:
  - `GateCoordinator.record_failure` checks:
    ```python
    is_completed_target = to_state is not None and to_state.state_group == "completed"
    if hook.failure_policy == "fail_open_warn" and not is_completed_target:
        ...
    else:
        # Terminal state always fails closed
    ```
  - Guarantees transitions into `Done` cannot be auto-approved on hook dispatch errors or timeouts.

### 2.3 Wasm Runner Memory Safety & Bytecode (`kanban/sandbox/wasm_runner.py`, `kanban/workflows/builtins.py`)
- Linear Memory Bounds Check:
  ```python
  alloc_ptr = kb_alloc(store, len(input_bytes))
  if not (
      isinstance(alloc_ptr, int)
      and alloc_ptr > 0
      and alloc_ptr + len(input_bytes) <= memory.data_len(store)
  ):
      raise WasmRunError(
          "WebAssembly guest 'kb_alloc' returned invalid or out-of-bounds pointer",
          code="SCRIPT_TRAP",
      )
  memory.write(store, input_bytes, alloc_ptr)
  ```
- Compiled Wasm Bytecode:
  - Length: 1097 bytes.
  - SHA-256: `fddfe97e1b15829495364a2002bf0a0c830002f9ef673971a1a4167ee815d972`.
  - Execution budget: `< 2ms` and `<= 2,000,000` fuel under wasmtime.
  - Parses `kb-sync-hook-input/v1` payload, verifies `docs/qa/<KEY>/reality-checker-report.md` path alignment and `READY` verdict, and returns `{"decision":"allow","allowed":true}` or `{"decision":"reject","allowed":false,"reason":"..."}`.
- Payload Enrichment & Unified Parsing:
  - Enriches `kb-sync-hook-input/v1` in `engine.py` and `dry_run.py` with `verification_proof` and recent comments (<= 10 comments, capped at 16384 bytes each, within 256 KiB total input limit).
  - Unified decision extraction: recognizes `verdict`, `decision`, `allowed`, and `allow` fields.

### 2.4 Agent Done Guards & Gate Runner (`kanban/api/deps.py`, `kanban/workflows/engine.py`, `agent/gates/runner.py`)
- Caller Discrimination:
  - `PrincipalContext.is_agent_or_mcp_caller`: evaluates `principal_type in ("AGENT", "SERVICE_PRINCIPAL")`, `agent_principal_id is not None`, `is_mcp_credential == True`, or token scopes starting with `agent:`, `docs:`, `admin:`.
  - Human browser sessions return `False`.
- Completed State Bypass Guard:
  - In `TransitionEngine.execute_transition`:
    ```python
    if (
        not is_complete_work
        and target_state.state_group == "completed"
        and actor.is_agent_or_mcp_caller
    ):
        raise ProblemException(
            code="USE_COMPLETE_WORK",
            status=422,
            title="Use Complete Work",
            detail="Agents and MCP callers must complete issues using the complete_work tool or canonical completion flow",
        )
    ```
  - Closes bypasses on `PATCH /api/v1/issues/{key}`, `POST /api/v1/issues/{key}/move`, and `POST /api/v1/issues/{key}/transition`.
  - Human board movements (`POST /api/v1/issues/{key}/move`) and detail updates execute unimpeded.
- Issue Move & Concurrency Guards:
  - `move_issue` honors `202 pending_agent_gate` and returns early without mutating `board_rank`.
  - Added `TaintGuard.check_write` on `issue_move`.
  - `update_issue` raises HTTP 409 `TRANSITION_HELD` when `issue.pending_transition_exec_id is not None`. `serialize_issue` is untouched.
- Gate Worker Background Infrastructure:
  - `agent/gates/runner.py`: `GateWorkerRunner` provides robust polling, lease management, timeout sweeping, and execution handling.
  - CLI subcommand: `kanban-agent run-gate-worker` in `agent/cli_commands/run_gate_worker.py`.
  - Lifespan integration in `kanban/app.py`: lazy import via `importlib.import_module("agent.gates.runner")` strictly preserves unidirectional architectural layering (`agent -> mcp -> kanban -> database`).

---

## 3. Test Suite & Coverage Verification

- Pytest Suites (105 passed in 33.77s across 13 test files):
  - `kanban/tests/api/test_gate_enforcement_hardening.py`: 14 passed (covers surrogate rejection, NFKC normalization, code/comment stripping, contradiction markers, 422 USE_COMPLETE_WORK guard, human exemption, 409 TRANSITION_HELD, and 202 pending_agent_gate).
  - `kanban/tests/api/test_issue_workflow.py`: 13 passed.
  - `kanban/tests/api/test_issue_patch_etag_parity.py`: 2 passed.
  - `kanban/tests/workflows/test_qa_proof_validator_wasm.py`: 6 passed (covers wasm bytecode compilation, SHA256 integrity, <2ms and fuel budget, positive allow, missing ready reject, ticket key mismatch reject, out-of-bounds alloc trap, and ensure_approved_wasm_modules idempotency).
  - `kanban/tests/workflows/test_async_gate.py`: 15 passed.
  - `kanban/tests/workflows/test_transition_engine.py`: 16 passed.
  - `kanban/tests/workflows/test_dry_run.py`: 7 passed.
  - `agent/tests/gates/test_gate_runner.py`: 3 passed.
  - `agent/tests/gates/test_worker.py`: 8 passed.
  - `mcp/tests/agent/test_workflow_tools.py`: 9 passed.
  - `mcp/tests/agent/test_transition_ticket_gate.py`: 3 passed.
  - `mcp/tests/agent/test_pending_gate_contract.py`: 3 passed.
  - `mcp/tests/agent/test_workflow_argument_validation.py`: 6 passed.
- Static Analysis Gates:
  - Ruff Linter: Clean across all packages (0 errors).
  - Ruff Format Check: 1012 files formatted (0 errors).
  - Mypy Strict Typecheck: Success across 1132 source files (0 errors).
  - Import Linter (`lint-imports`): Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database` KEPT; `mcp` forbidden from importing `database` KEPT).
  - Typography Audit (`check_no_dashes`): Clean (0 em/en-dashes across all files).
  - Brand Terminology Audit: Clean (0 forbidden terms in comments and docstrings).

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Anchored Regex Security | Strictly anchored with `\A...\Z` | Updated all proof regexes in `proof.py` | PASS |
| Report Path Traversal Guard | Canonical report path without traversal | Enforced in `RealityCheckerProof` | PASS |
| CI URL Sanitization | Validated https, no creds, <=2048 chars | `validate_ci_run_url` via `urlsplit` | PASS |
| Linear O(N) Parser | Single-pass scan without backtracking | `validate_reality_checker_report` | PASS |
| Lone Surrogate Rejection | Code points 0xD800..0xDFFF rejected | Explicit character scan in report parser | PASS |
| Anti-Fantasy Contradictions | Reject `NEEDS WORK` / `FAILED` when claiming READY | Contradiction scanner in certification | PASS |
| Step 7 Comment Persistence | Formatted approval comment authored by agent | Persisted via `format_approve_comment` | PASS |
| Fail-Closed Completed Gates | Transitions into Done cannot fail open | Enforced in `record_failure` | PASS |
| Wasm `kb_alloc` Bounds Check | Traps on invalid/out-of-bounds pointers | Verified in `TierAWasmRunner.run_sync` | PASS |
| Compiled Wasm Engine | Real bytecode (1097 bytes, SHA-256 verified) | Embedded in `builtins.py`, `<2ms` runtime | PASS |
| Agent Done Bypass Guard | Agent PATCH/move/transition blocked with 422 | `USE_COMPLETE_WORK` in `TransitionEngine` | PASS |
| Human Board Exemption | Human users can move cards to Done | Verified in `test_gate_enforcement_hardening` | PASS |
| Active Gate Concurrency Guard | Modifications blocked during pending gate | `409 TRANSITION_HELD` in `update_issue` | PASS |
| Move Hold State Preservation | Does not update board rank on 202 hold | Preserved in `services/issue_move.py` | PASS |
| Architectural Layering | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

All transition engine gates, reality-checker report validators, Wasm bytecode contracts, approval comment persistence mechanics, agent completed-state guards, and gate worker background runners for KAN-45 on branch `feat/KAN-45` at commit `5c345a8e` have been thoroughly audited, verified against all architectural and security invariants, and certified. Both Dual Specialist Gates (API Specialist + UI Specialist) are complete. Ready for Clean-Room Reality-Checker QA.
