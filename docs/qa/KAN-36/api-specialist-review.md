# API Specialist Review: KAN-36 (KB-P3-PENTEST-01)

- Ticket: KAN-36
- Title: [KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-36`
- Branch: `main` (commit `7913c2c8`)
- Container Environment: `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)
- Live Stack Status: `LIVE_STACK_VERDICT: PASS`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-36 on branch `main` at commit `7913c2c8`. This audit incorporates verified evidence from the zero-mock live container execution against `kanban-liveqa-3` (`http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-36/live-fullstack-proof.txt`, unit test execution logs (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

The ticket resolves four critical security, session management, and HTTP caching problems:
1. Session Persistence, TTL, and AAL2 Preservation on Workspace Switch (CWE-613):
   - In `kanban/auth/sessions/service.py`, implemented `SessionService.rotate_for_workspace_switch` to resolve the originating session, atomically revoke it with `revoked_at = now`, and preserve originating security properties:
     - `is_persistent = orig.is_persistent` (prevents escalating transient `remember_me=False` sessions to persistent cookies).
     - `absolute_expires_at = orig.absolute_expires_at` (preserves the outer lifespan; prevents indefinite session lifespan extension attacks).
     - `idle_expires_at = min(now + timedelta(seconds=idle_seconds), orig.absolute_expires_at)` (idle timer is bounded by absolute expiration).
     - `rotated_from_id = orig.id` (maintains session rotation lineage for audit trails).
     - `aal_level = orig.aal_level`, `aal2_verified_at = orig.aal2_verified_at` (verbatim preservation: step-up verifications older than 900 seconds remain stale, requiring re-authentication for sensitive operations).
     - `mfa_pending = orig.mfa_pending` and `auth_card_id = orig.auth_card_id`.
2. Workspace Switch Endpoint Hardening (`kanban/api/v1/workspaces.py`):
   - Caller Verification: In `switch_workspace_endpoint`, explicitly verifies `caller.session_id is not None`. Callers lacking a browser cookie session (such as API keys or Bearer tokens) are immediately rejected with HTTP 401 `SESSION_REQUIRED`, preventing unauthorized session cookie minting.
   - Cyclomatic Complexity: Extracted `_execute_workspace_switch_proc` to keep function complexity strictly within architectural guidelines.
   - Cookie Header Hygiene: Passes `persistent=issued.is_persistent` to `attach_session_and_csrf_cookies` (omitting `Max-Age` and `Expires` for transient sessions). When the request is HTTPS, appends `Clear-Cookie` headers for un-prefixed fallback cookies (`kb_session`, `kb_csrf`).
3. Elimination of Live 0ms TCP Commit-After-Response Race & Issue ETag Parity:
   - Defect Identified in Live QA: In FastAPI, the `get_rls_session` dependency commits transactions during generator exit, which flushes AFTER the `JSONResponse` body is transmitted over Uvicorn's TCP socket. Consequently, immediate back-to-back `PATCH -> GET` requests at 0ms latency observe pre-commit PostgreSQL state, causing stale ETag reads and 412 Precondition Failed errors.
   - Root-Cause Resolution: Added explicit `await session.commit()` before returning the response in:
     * `PATCH /api/v1/issues/{key}` (`kanban/api/v1/issues.py`)
     * `api_begin_work` (`kanban/api/v1/issue_workflow.py`)
     * `api_transition_ticket` (`kanban/api/v1/issue_workflow.py`)
     * `api_complete_work` (`kanban/api/v1/issue_workflow.py`)
     * `override_issue_created_by` (`kanban/api/v1/issue_provenance.py`)
   - Guarantees that the transaction is committed to PostgreSQL before headers and body are transmitted over the TCP wire, completely eliminating the 0ms commit-after-response race.
4. Cookie Session AAL2 Stale Enforcement (`kanban/auth/mfa/policy.py`):
   - In `require_admin_aal2`, added `ADMIN_AAL2_MAX_AGE_SECONDS = 900` enforcement for cookie sessions (`session_id is not None`).
   - If `aal2_verified_at` is older than 900 seconds, raises HTTP 403 `AAL2_STALE`, while preserving stateless tokens (e.g. `/mcp/admin` tokens without `session_id`).
   - Dual ETag acceptance: workflow transition endpoints accept both composite `compute_issue_etag` and backward-compatible `description_sha256` in `If-Match` headers.

All API contracts, security invariants, transaction boundaries, import layering constraints, and test coverage requirements are verified and certified:
- Zero new external runtime dependencies introduced (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- High test coverage: 110 Pytest tests pass in 119.26s with 95% total line and branch coverage across touched modules (`issue_provenance.py` 100%, `issue_workflow.py` 97%, `sessions/service.py` 97%, `issues.py` 97%, `update_ticket.py` 97%, `read_ticket.py` 95%, `engine.py` 94%, `workflow_service.py` 93%, `workspaces.py` 88%).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation.

---

## 2. Detailed Contract & Security Verification

### 2.1 Workspace Switch Session Rotation (`kanban/auth/sessions/service.py`)
- Source: `kanban/auth/sessions/service.py` (`rotate_for_workspace_switch`)
- Security Analysis:
  - CWE-613 Mitigation: In multi-tenant environments, switching workspaces without proper session rotation allows stale tokens to linger or extends session lifespans beyond original authentication boundaries.
  - Implementation:
    ```python
    orig = await self.get_session_by_id(session, old_session_id)
    if orig is None or orig.revoked_at is not None:
        raise SessionExpiredError("Originating session invalid or revoked")
    orig.revoked_at = now
    new_abs = orig.absolute_expires_at
    new_idle = min(now + timedelta(seconds=idle_seconds), new_abs)
    new_session = UserSession(
        principal_id=target_principal_id,
        workspace_id=target_workspace_id,
        is_persistent=orig.is_persistent,
        absolute_expires_at=new_abs,
        idle_expires_at=new_idle,
        rotated_from_id=orig.id,
        aal_level=orig.aal_level,
        aal2_verified_at=orig.aal2_verified_at,
        mfa_pending=orig.mfa_pending,
        auth_card_id=orig.auth_card_id,
    )
    ```

### 2.2 Workspace Switch Endpoint Hardening (`kanban/api/v1/workspaces.py`)
- Source: `kanban/api/v1/workspaces.py` (`switch_workspace_endpoint`)
- Caller Invariant:
  - Requires `caller.session_id is not None`.
  - Token-only requests return HTTP 401 `SESSION_REQUIRED`.
  - Non-members attempting to switch to an unauthorized workspace receive HTTP 404 `WORKSPACE_NOT_FOUND` (preventing tenant enumeration).

### 2.3 Explicit Commit & TCP Race Elimination (`issues.py`, `issue_workflow.py`)
- Defect Root Cause:
  - When returning `JSONResponse(status_code=200, content=issue_dict, headers={"ETag": new_etag})`, Uvicorn flushes bytes to the socket before the ASGI lifespan dependency generator `get_rls_session` calls `await session.commit()`.
  - A client immediately sending a `GET` request over the same connection reads the pre-commit state from PostgreSQL.
- Fix Implementation:
  - Added explicit `await session.commit()` before constructing and returning the HTTP response across all issue update, workflow transition, and provenance override endpoints.
  - Test `test_issue_patch_etag_parity.py` validates that immediate read-after-write yields matching ETags.

### 2.4 Cookie Session AAL2 Stale Enforcement (`kanban/auth/mfa/policy.py`)
- Source: `kanban/auth/mfa/policy.py` (`require_admin_aal2`)
- Implementation:
  - For cookie-based browser sessions (`principal.session_id is not None`), enforces that `aal2_verified_at` is present and younger than `ADMIN_AAL2_MAX_AGE_SECONDS = 900`.
  - Older sessions are rejected with HTTP 403 `AAL2_STALE`.
  - Stateless API token callers (`principal.session_id is None`) without cookie sessions are exempted from the cookie max-age check, preserving MCP admin key compatibility.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt`)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-36/live-fullstack-proof.txt`:
1. Scenario (a): Remember Me & Absolute Expiration on Workspace Switch:
   - Initial transient session (`remember_me=False`) rotated across workspaces: `is_persistent=False` preserved.
   - `absolute_expires_at` maintained across rotation (`2026-11-27 19:03:03.056378+00`).
   - Originating session row marked revoked (`revoked_at: 2026-11-20 19:03:03.169229+00`).
2. Scenario (b): Stale AAL2 (>900s) Enforcement:
   - Aged session `aal2_verified_at` by 1200s.
   - `require_admin_aal2` returned HTTP 403 `AAL2_STALE` ("AAL2 verification is stale (1200s > 900s)").
3. Scenario (c): Bearer / Scoped API Key Rejection:
   - `POST /api/v1/workspaces/switch` with `X-KB-Subject-Token` returned HTTP 401 `SESSION_REQUIRED`.
4. Scenario (d): Issue PATCH / Workflow / MCP ETag Parity:
   - Verified that immediate 0ms read-after-write defect was diagnosed, isolated, and permanently solved by explicit transaction commits before response flushing.

---

## 4. Test Suite & Coverage Verification

- Pytest Test Suite (`unit-test-results.txt`):
  - 110 passed in 119.26s with 0 failures across 11 test files.
  - Line and branch coverage:
    * `kanban/api/v1/issue_workflow.py`: 97%
    * `kanban/api/v1/workspaces.py`: 88%
    * `kanban/auth/sessions/service.py`: 97%
    * `kanban/issues/workflow_service.py`: 93%
    * `kanban/services/issue_provenance.py`: 100%
    * `kanban/services/issues.py`: 97%
    * `kanban/workflows/engine.py`: 94%
    * `mcp/surfaces/agent/read_ticket.py`: 95%
    * `mcp/surfaces/agent/update_ticket.py`: 97%
    * Total Touched Modules: 95% coverage (2008 stmts, 49 miss, 740 branch, 82 brpart).
- Static Analysis:
  - `ruff check`: Clean.
  - `ruff format --check`: Clean.
  - `mypy`: Clean across 1124 source files.
  - `lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `check_no_dashes --all`: Clean (0 em/en-dashes).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| CWE-613 Session Rotation | Atomic revocation and lineage linking | `rotate_for_workspace_switch` with `revoked_at` | PASS |
| Transient Cookie Protection | `remember_me=False` preserves transient cookie | `is_persistent` preserved; Max-Age omitted | PASS |
| Outer TTL Preservation | `absolute_expires_at` unextendable on switch | Outer lifespan preserved across rotations | PASS |
| AAL2 Timestamp Preservation | Step-up timestamp retained across switches | `aal2_verified_at` preserved verbatim | PASS |
| Cookie Session AAL2 Stale | Enforce 900s max-age on cookie sessions | Checked in `require_admin_aal2` | PASS |
| Stateless Token Exemption | Stateless MCP admin tokens preserved | Exempted when `session_id is None` | PASS |
| Session Required Gate | Non-session callers rejected on switch | HTTP 401 `SESSION_REQUIRED` | PASS |
| Pre-Flush Commit Guarantee | Explicit commit before response return | Added `await session.commit()` | PASS |
| Zero 0ms ETag Drift | PATCH ETag equals subsequent immediate GET | Verified in test and live execution | PASS |
| Unidirectional Layering | Layer hierarchy preserved | `lint-imports` confirms 2 kept, 0 broken | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All session rotation procedures, security invariants, cookie hygiene routines, explicit response transaction commits, and unit test suites for KAN-36 on branch `main` at commit `7913c2c8` have been thoroughly audited, verified against all architectural and security invariants, and certified. Verified on live stack `kanban-liveqa-3` with `LIVE_STACK_VERDICT: PASS`. Ready for Clean-Room Reality-Checker QA.
