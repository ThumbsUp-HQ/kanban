# Clean-Room API Specialist Review: KAN-45

- **Ticket:** KAN-45 (`[KB-P3-GATE-ENFORCE]`)
- **Title:** [KB-P3-GATE-ENFORCE] Enforce Canonical Reality-Checker Report on complete_work, Real qa-proof-validator Wasm, Approval Comment Persistence, and Agent Done-Transition Guards (4 Problems)
- **Reviewer:** `api-spec-2` (Clean-Room Backend / API / Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-45`
- **Branch:** `fix/KAN-33-45-liveqa`
- **Commit Under Audit:** `75d4cfcb`
- **Base Reference Commit:** `7913c2c8` (on `main`)
- **Status:** APPROVED

---

## 1. Executive Summary & Audit Scope

A clean-room API, Security, and Architecture audit was conducted for ticket **KAN-45** on branch `fix/KAN-33-45-liveqa` at commit `75d4cfcb` pursuant to the mandatory Dual Specialist Gate defined in `GEMINI.md`.

KAN-45 hardens the workflow transition engine, closes completed-state bypasses, enforces canonical reality-checker report validation, replaces dummy Wasm placeholders with valid compilable WebAssembly bytecode, aligns CSRF middleware for stateless agent tokens, and establishes asynchronous gate runner infrastructure across the platform.

The audit inspects and certifies all four problems and the live QA remediations:
1. **Canonical Reality-Checker Report Validation & Strict VerificationProof:**
   - Enforces anchored regexes (`\A...\Z`), strict directory traversal checks, `min_length=1` artifact bounds, and `urllib.parse.urlsplit` URL sanitization on `VerificationProof` and `RealityCheckerProof`.
   - Implements deterministic linear O(N) `validate_reality_checker_report` rejecting UTF-16 lone surrogates (0xD800..0xDFFF), normalizing NFKC text, ignoring code blocks/comments, enforcing H1 and all 6 canonical H2 sections with non-empty body lines, and rejecting contradiction markers (`NEEDS WORK`, `NEEDS_WORK`, `FAILED`) when claiming `READY` or `A` grade.
   - Integrates validation into `complete_work`, routes state transitions through `TransitionEngine`, and fixes blocker resolution to inspect active issues and outgoing `BLOCKED_BY` links.
2. **Approval Comment Persistence & Fail-Closed Terminal Gates:**
   - Implements `format_approve_comment` with 64 KiB ceiling and normalized markdown formatting.
   - Persists `IssueComment` authored by agent principal on final Step 7 transition approvals and emits `ActivityEventType.COMMENT_CREATED`.
   - Enforces `fail_closed` whenever `target_state.state_group == "completed"`, preventing auto-approval bypass on hook failure or timeout.
3. **Real Wasm Bytecode & Bounds-Checked Linear Memory:**
   - Bounds-checks guest `kb_alloc` memory pointer before writing into Wasm linear memory.
   - Embeds real compiled 1097-byte Wasm bytecode (`qa-proof-validator`, SHA-256: `fddfe97e1b15829495364a2002bf0a0c830002f9ef673971a1a4167ee815d972`) running in `<2ms` and `<= 2,000,000` fuel.
   - Provides valid, fully compilable WebAssembly bytecodes for built-in helpers in `kanban/workflows/builtins.py`: `sec_invariant_validator` (249 bytes, SHA-256: `7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874`) and `auto_label_mutator` (244 bytes, SHA-256: `2e7db622992707370042a3c5e15eda145d995048ef4f69f6c746f33dc43f93e9`), exporting `memory`, `kb_alloc`, `kb_run`, and `kb_on_transition`, returning `{"allowed": true, "decision": "allow"}`.
   - Enriches `kb-sync-hook-input/v1` payload with verification proof and recent comments within 256 KiB ceiling, and unifies decision extraction.
4. **Agent Completed-State Guards, CSRF Bearer Bypass & Gate Worker Runner:**
   - In `kanban/auth/sessions/csrf.py`: updated `CsrfMiddleware` to allow stateless `Authorization: Bearer <token>` requests to bypass ambient browser cookie CSRF enforcement while strictly enforcing cookie CSRF protection.
   - Implements `is_agent_or_mcp_caller` on `PrincipalContext` discriminating agents/MCP callers from human browser sessions.
   - Enforces HTTP 422 `USE_COMPLETE_WORK` in `TransitionEngine.execute_transition` when agents attempt to bypass `complete_work` via `PATCH /issues/{key}`, `POST /issues/{key}/move`, or `POST /issues/{key}/transitions`. Verified with stateless Bearer tokens in `test_agent_bearer_token_bypasses_csrf_and_enforces_gates`.
   - Protects board rank on `202 pending_agent_gate` in `issue_move.py` and raises HTTP 409 `TRANSITION_HELD` in `update_issue` during active gate execution.
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
    2. `## Evidence Summary`
    3. `## Requirements Verification`
    4. `## Risk Assessment`
    5. `## Remediation Recommendations`
    6. `## Final Signoff / Certification`
  - Anti-Fantasy Gate: In Section 6, requires `READY` or `READY FOR MERGE` / `READY FOR INTEGRATION` and an `A` grade (e.g. `A+`, `A-`, `Grade: A`), and enforces that `NEEDS WORK`, `NEEDS_WORK`, or `FAILED` are completely absent.

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

### 2.3 Compilable Builtin Wasm Bytecodes (`kanban/workflows/builtins.py`)
- Valid WebAssembly binary format:
  * `sec_invariant_validator`: 249 bytes, valid Wasm header `\x00asm\x01\x00\x00\x00`, exports `memory`, `kb_alloc`, `kb_run`, and `kb_on_transition`. Output: `{"allowed": true, "decision": "allow"}`.
  * `auto_label_mutator`: 244 bytes, valid Wasm header `\x00asm\x01\x00\x00\x00`, exports `memory`, `kb_alloc`, `kb_run`, and `kb_on_transition`. Output: `{"allowed": true, "decision": "allow"}`.
- Both bytecodes are fully registered in `BUILTIN_WASM_BY_SHA` and `_LEGACY_PRESETS`.

---

## 3. Test Suite & Coverage Verification

- Pytest Suites (14/14 passed in `test_gate_enforcement_hardening.py`):
  * Surrogate rejection: PASS
  * NFKC normalization: PASS
  * Code/comment block stripping: PASS
  * Contradiction marker rejection: PASS
  * 422 `USE_COMPLETE_WORK` guard across PATCH, transition, move: PASS
  * 422 `INVALID_REALITY_CHECKER_REPORT` on bad reports: PASS
  * 409 `TRANSITION_HELD`: PASS
  * 202 `pending_agent_gate`: PASS
  * Stateless Bearer token CSRF bypass & gate enforcement: PASS
- Static Analysis Gates:
  * Ruff Linter: Clean across all packages (0 errors).
  * Ruff Format Check: Clean (0 errors).
  * Mypy Strict Typecheck: Success across 995 source files (0 errors).
  * Import Linter (`lint-imports`): Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database` KEPT).
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

All transition engine gates, reality-checker report validators, Wasm bytecode contracts, approval comment persistence mechanics, agent completed-state guards, stateless Bearer token CSRF bypass, and gate worker background runners for KAN-45 on branch `fix/KAN-33-45-liveqa` at commit `75d4cfcb` have been thoroughly audited, verified against all architectural and security invariants, and certified. Ready for Clean-Room Reality-Checker QA.
