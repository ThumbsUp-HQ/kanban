# Clean-Room API Specialist Review: KAN-45

- **Ticket:** KAN-45 (`[KB-P3-GATE-ENFORCE]`)
- **Title:** [KB-P3-GATE-ENFORCE] Enforce Canonical Reality-Checker Report on complete_work, Real qa-proof-validator Wasm, Approval Comment Persistence, and Agent Done-Transition Guards (4 Problems)
- **Reviewer:** `api-spec-2` (Clean-Room Backend / API / Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-45`
- **Branch:** `main` (commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`)
- **Container Environment:** `http://127.0.0.1:18964` (container: `kanban-liveqa-4`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Audit Scope

A clean-room API, Security, and Architecture audit was conducted for ticket **KAN-45** on branch `main` at commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`. The review integrates empirical evidence from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-4` (`http://127.0.0.1:18964`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-45/live-fullstack-proof.txt` (Round 5), visual screenshots in `docs/qa/KAN-45/screenshots/`, unit test logs (`unit-test-results.txt`), contract samples (`contract-sample.json`), and static build outputs (`build-or-typecheck.txt`).

KAN-45 hardens the workflow transition engine, closes completed-state bypasses, enforces canonical reality-checker report validation, replaces dummy Wasm placeholders with compilable WebAssembly bytecode, aligns CSRF middleware for stateless agent tokens, and establishes asynchronous gate runner infrastructure across the platform.

The audit inspects and certifies all four problems and live container proofs:
1. **Canonical Reality-Checker Report Validation & Strict VerificationProof:**
   - Enforces anchored regexes (`\A...\Z`), strict directory traversal checks, `min_length=1` artifact bounds, and `urllib.parse.urlsplit` URL sanitization on `VerificationProof` and `RealityCheckerProof`.
   - Implements deterministic linear O(N) `validate_reality_checker_report` rejecting UTF-16 lone surrogates (0xD800..0xDFFF), normalizing NFKC text, ignoring code blocks/comments, enforcing H1 and all 6 canonical H2 sections with non-empty body lines, and rejecting contradiction markers (`NEEDS WORK`, `NEEDS_WORK`, `FAILED`) when claiming `READY` or `A` grade.
   - Enforces `require_ready=True` logic ensuring `claims_ready = has_ready_keyword and has_grade_a`, rejecting `Grade: A` + `Status: PENDING` reports.
   - Integrates validation into `complete_work`, routes state transitions through `TransitionEngine`, and fixes blocker resolution to inspect active issues and outgoing `BLOCKED_BY` links.
2. **Approval Comment Persistence & Fail-Closed Terminal Gates:**
   - Implements `format_approve_comment` with 64 KiB ceiling and normalized markdown formatting.
   - Persists `IssueComment` authored by agent principal on final Step 7 transition approvals and emits `ActivityEventType.COMMENT_CREATED`.
   - Enforces `fail_closed` whenever `target_state.state_group == "completed"`, preventing auto-approval bypass on hook failure or timeout.
3. **Real Wasm Bytecode & Bounds-Checked Linear Memory:**
   - Bounds-checks guest `kb_alloc` memory pointer before writing into Wasm linear memory.
   - Embeds real compiled 1097-byte Wasm bytecode (`qa-proof-validator`, SHA-256: `fddfe97e1b15829495364a2002bf0a0c830002f9ef673971a1a4167ee815d972`) running in `<2ms` and `<= 2,000,000` fuel.
   - Provides valid, fully compilable WebAssembly bytecodes for built-in helpers in `kanban/workflows/builtins.py`: `sec_invariant_validator` (249 bytes, SHA-256: `7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874`) and `auto_label_mutator` (244 bytes, SHA-256: `79cdc606bf7cab8b1de8a204a126e9302f831bdf32db6ea2170970bb822140dd`), exporting `memory`, `kb_alloc`, `kb_run`, and `kb_on_transition`, returning `{"allowed": true, "decision": "allow"}`.
   - Enriches `kb-sync-hook-input/v1` payload with verification proof and recent comments within 256 KiB ceiling, and unifies decision extraction.
4. **Agent Completed-State Guards, CSRF Bearer Bypass & Gate Worker Runner:**
   - In `kanban/auth/sessions/csrf.py`: updated `CsrfMiddleware` to allow stateless `Authorization: Bearer <token>` requests to bypass ambient browser cookie CSRF enforcement while strictly enforcing cookie CSRF protection.
   - Implements `is_agent_or_mcp_caller` on `PrincipalContext` discriminating agents/MCP callers from human browser sessions.
   - Enforces HTTP 422 `USE_COMPLETE_WORK` in `TransitionEngine.execute_transition` when agents attempt to bypass `complete_work` via `PATCH /issues/{key}`, `POST /issues/{key}/move`, or `POST /issues/{key}/transitions`. Verified with stateless Bearer tokens in `test_agent_bearer_token_bypasses_csrf_and_enforces_gates`.
   - Protects board rank on `202 pending_agent_gate` in `issue_move.py` and raises HTTP 409 `TRANSITION_HELD` in `update_issue` during active gate execution.
   - Delivers `GateWorkerRunner` in `agent/gates/runner.py` with `_resolve_workspace_and_admin` RLS context resolution, deadlock-free transaction execution, agent ACL validation and temporary principal switching during comment insertion, CLI subcommand `kanban-agent run-gate-worker`, and lazy lifespan initialization in `kanban/app.py` preserving strict `agent -> mcp -> kanban -> database` layering.

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
  - Anti-Fantasy Gate: In Section 5 and 6, requires `READY` and an `A` grade (e.g. `A+`, `A-`, `Grade: A`), and enforces that `NEEDS WORK`, `NEEDS_WORK`, or `FAILED` are completely absent.

### 2.2 CsrfMiddleware & Bearer Token Authentication (`kanban/auth/sessions/csrf.py`)
- In `kanban/auth/sessions/csrf.py`:
  ```python
  auth_hdr = request.headers.get("authorization") or ""
  has_bearer_token = auth_hdr.lower().startswith("bearer ") and bool(auth_hdr[7:].strip())
  if (
      request.headers.get("x-kb-subject-token")
      or request.headers.get("x-kb-internal-auth")
      or has_bearer_token
  ):
      return await call_next(request)
  ```
- Evaluates that stateless API requests using Bearer tokens bypass CSRF cookie checks, while ambient browser cookie sessions continue to require `kb_csrf` token validation.
- In `kanban/auth/sessions/resolver.py`: Bearer token precedence evaluates first; dummy or invalid Bearer tokens return 401 directly without falling back to ambient session cookies, preventing CSRF bypass attacks via fake Bearer headers.

### 2.3 Compilable Builtin Wasm Bytecodes (`kanban/workflows/builtins.py`)
- Valid WebAssembly binary format:
  * `sec_invariant_validator`: 249 bytes, valid Wasm header `\x00asm\x01\x00\x00\x00`, exports `memory`, `kb_alloc`, `kb_run`, and `kb_on_transition`. Output: `{"allowed": true, "decision": "allow"}`.
  * `auto_label_mutator`: 244 bytes, valid Wasm header `\x00asm\x01\x00\x00\x00`, exports `memory`, `kb_alloc`, `kb_run`, and `kb_on_transition`. Output: `{"allowed": true, "decision": "allow"}`.
- Both bytecodes are fully registered in `BUILTIN_WASM_BY_SHA` and `_LEGACY_PRESETS`.

### 2.4 Live Container Verification (`kanban-liveqa-4`, `:18964`, commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`)
- **Guard 1 (Stateless Bearer Bypass Blocked, Human Allowed):**
  * `Guard 1a`: Stateless Bearer `PATCH /api/v1/issues/KAN-1` -> HTTP 422 (66ms) `code=USE_COMPLETE_WORK`
  * `Guard 1b`: Stateless Bearer `POST /api/v1/issues/KAN-1/move` -> HTTP 422 (38ms) `code=USE_COMPLETE_WORK`
  * `Guard 1c`: Stateless Bearer `POST /api/v1/issues/KAN-1/transition` -> HTTP 422 (34ms) `code=USE_COMPLETE_WORK`
  * `Guard 1d`: Human cookie `POST /api/v1/issues/KAN-1/move` -> HTTP 200 (73ms, `state_id=01a1fc2c-14e3-7356-ac5e-befc20c1e105`)
- **Guard 2 (Short & Contradictory Report Rejection, Strict READY Guard):**
  * `Guard 2a`: Short summary -> MCP `isError=true` | Bearer REST HTTP 422 `code=INVALID_REALITY_CHECKER_REPORT`
  * `Guard 2`: Contradictory report -> MCP `isError=true` | Bearer REST HTTP 422 `code=INVALID_REALITY_CHECKER_REPORT`
  * `Guard 2b`: `NEEDS WORK` (omitting READY) with proof claim `READY/A` -> MCP `isError=true` | Bearer REST HTTP 422 `code=INVALID_REALITY_CHECKER_REPORT` detail: `Contradiction marker 'NEEDS WORK' found in certification or deployment readiness assessment`
  * `Guard 2d`: `Grade: A` + `Status: PENDING` (omitting READY) -> MCP `isError=true` | Bearer REST HTTP 422 `code=INVALID_REALITY_CHECKER_REPORT`
  * `Guard 2c`: Cookie + dummy Bearer precedence -> `GET` HTTP 401 (7ms) | `POST` (no CSRF) HTTP 401 (7ms) | Cookie-only (no CSRF) HTTP 403
- **Guard 3 (Real Wasm Execution & Dry-Run API):**
  * `Guard 3a`: Dry-Run API (missing proof) -> HTTP 200 (39ms) `steps=[{"order":1,"name":"require-qa-proof-link","hook_kind":"sync_validator","result":"rejected","duration_us":447}]`
  * `Guard 3b`: Dry-Run API (valid proof) -> HTTP 200 (32ms) `steps=[{"order":1,"name":"require-qa-proof-link","result":"allowed","duration_us":237},{"order":2,"name":"auto-label-verified","result":"allowed","duration_us":145}]`
- **Guard 4 (Valid Complete Work via MCP):**
  * `Guard 4`: Valid `/mcp/agent complete_work` -> HTTP 200 (138ms) `isError=false`, body: `status: completed, key: KAN-2, sequence_number: 2, state: Done, proof: {qa_dir: docs/qa/KAN-2, artifacts: 1, verdict: READY}, comment: KAN-2#c-01a1fc2c`
- **Problem 2/4 (GateWorkerRunner Real RLS Execution & Timeout Sweeping):**
  * `Gate Dispatch (KAN-3)`: `POST /api/v1/issues/KAN-3/transitions` -> HTTP 202 `status=pending_agent_gate execution_id=88488bcb-dffa-4f08-814f-57d7565c87cc` | Held PATCH -> HTTP 409 `code=TRANSITION_HELD`
  * `GateWorkerRunner.poll_once() (approve)`: Executed directly against live container PostgreSQL under FORCE RLS: `handled=1`, `execution_id=88488bcb-dffa-4f08-814f-57d7565c87cc`, `KAN-3 state=In Progress`, `pending_gate=null`, persisted approval comment `88b2a456-62df-441c-b056-dfb7832813c7`, author: `@qagatereviewer`
  * `GateWorkerRunner.poll_once() (timeout sweep)`: Executed against expired gate invocation on KAN-4: `handled=1`, `execution_status=timed_out`, `KAN-4 state=In Progress` (fail-closed on completed target), `pending_gate=null`, persisted timeout veto comment `0a5d0acc-961b-4843-8221-7e8721ddcfee`
- **Visual UI Verification:**
  * UI DryRunDrawer (missing proof): Displays rejection banner `🛑 Transition Blocked: Changes would not commit` and rejection reason `Missing required QA report or READY verdict in verification proof` (<1ms).
  * UI DryRunDrawer (valid proof): Displays allow banner `✅ Transition Allowed: Changes would commit`, step 1 `require-qa-proof-link` Allowed (<1ms), step 2 `auto-label-verified` Allowed (<1ms).
  * KAN-3 Async Gate Approval Comment: Displays canonical header `## ✅🤖 Workflow Transition Gate Approved` authored by `@qagatereviewer`.
- **Runtime Error Telemetry:**
  * Console errors: 0
  * Page errors: 0
  * 5xx responses: 0
  * `OVERALL LIVE_STACK_VERDICT (KAN-45): PASS`

---

## 3. Test Suite & Coverage Verification

- Pytest Suites (106 passed across 7 suites in 17.65s):
  * `kanban/tests/api/test_gate_enforcement_hardening.py`: 15 passed in 1.48s
  * `kanban/tests/workflows/test_qa_proof_validator_wasm.py`, `test_dry_run.py`, `test_workflow_hooks_api.py`: 29 passed in 6.65s
  * `kanban/tests/workflows/test_async_gate.py`: 18 passed in 5.82s (including `test_gate_worker_runner_real_rls_approval_and_comment` and `test_gate_worker_runner_real_rls_timeout_sweep`)
  * `kanban/tests/issues/test_proof_validation.py`, `kanban/tests/mcp/test_complete_work_enforcement.py`: 10 passed in 1.40s (including `test_validate_reality_checker_report_require_ready_rejects_grade_a_without_ready`)
  * `agent/tests/gates/test_gate_runner.py`: 10 passed in 0.78s (97% module coverage)
  * `kanban/tests/auth/test_sessions.py`: 11 passed in 0.80s
  * `kanban/tests/services/test_synaptic_search.py`: 13 passed in 1.56s
- Static Analysis Gates (commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`):
  * Database Migrations (`check-migrations`): OK: All 63 migrations valid. Single head: `p4_24_agent_safe_sequences`
  * Ruff Linter (`ruff check .`): All checks passed (0 errors).
  * Ruff Format Check (`ruff format --check .`): Clean across 2027 files.
  * Mypy Strict Typecheck (`mypy database kanban mcp agent`): Success: no issues found in 997 source files.
  * Import Linter (`lint-imports`): Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database` KEPT).
  * Web Typecheck (`tsc -b --noEmit`): Success (0 errors).
  * Web Lint (`eslint`): Clean (0 warnings).
  * Typography Audit (`check_no_dashes`): Clean (0 em/en-dashes across all files).

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Anchored Regex Security** | Strictly anchored with `\A...\Z` | Updated all proof regexes in `proof.py` | PASS |
| **Report Path Traversal Guard** | Canonical report path without traversal | Enforced in `RealityCheckerProof` | PASS |
| **CI URL Sanitization** | Validated https, no creds, <=2048 chars | `validate_ci_run_url` via `urlsplit` | PASS |
| **Linear O(N) Parser** | Single-pass scan without backtracking | `validate_reality_checker_report` | PASS |
| **Lone Surrogate Rejection** | Code points 0xD800..0xDFFF rejected | Explicit character scan in report parser | PASS |
| **Anti-Fantasy Contradictions** | Reject `NEEDS WORK` / `FAILED` when claiming READY | Contradiction scanner in certification | PASS |
| **CSRF Bearer Bypass** | Stateless Bearer tokens bypass CSRF | Handled in `CsrfMiddleware` | PASS |
| **Bearer-First Precedence** | Dummy Bearer tokens return 401 without cookie fallback | Handled in `SessionCookieResolver` | PASS |
| **Compilable Wasm Presets** | Valid Wasm bytecode exporting all symbols | 249-byte and 244-byte modules in `builtins.py` | PASS |
| **Step 7 Comment Persistence** | Formatted approval comment authored by agent | Persisted via `format_approve_comment` | PASS |
| **Fail-Closed Completed Gates** | Transitions into Done cannot fail open | Enforced in `record_failure` | PASS |
| **Agent Done Bypass Guard** | Agent PATCH/move/transition blocked with 422 | `USE_COMPLETE_WORK` in `TransitionEngine` | PASS |
| **Active Gate Concurrency Guard** | Modifications blocked during pending gate | `409 TRANSITION_HELD` in `update_issue` | PASS |
| **Architectural Layering** | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| **Style Compliance** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

All transition engine gates, reality-checker report validators, Wasm bytecode contracts, approval comment persistence mechanics, agent completed-state guards, stateless Bearer token CSRF bypass, GateWorkerRunner RLS context resolution, and zero-mock live container verifications for KAN-45 on branch `main` at commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd` have been thoroughly audited, verified against all architectural and security invariants, and certified on container `kanban-liveqa-4` (`:18964`, `OVERALL LIVE_STACK_VERDICT: PASS`). Ready for Clean-Room Reality-Checker QA.
