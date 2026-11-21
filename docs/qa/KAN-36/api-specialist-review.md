# API Specialist Review: KAN-36 (KB-P3-PENTEST-01)

- **Ticket:** KAN-36
- **Title:** [KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift (4 Problems)
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-36`
- **Branch:** `main` (commit `78074a1d`)
- **Container Environment:** `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket **KAN-36** on branch `main` at commit `78074a1d`. This audit incorporates verified evidence from the zero-mock live container execution against `kanban-liveqa-3` (`http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-36/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-36/screenshots/`, unit test execution logs (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

The ticket resolves four critical security, session management, and HTTP caching problems:
1. **Session Persistence, TTL, and AAL2 Preservation on Workspace Switch (CWE-613):**
   - In `kanban/auth/sessions/service.py`, implemented `SessionService.rotate_for_workspace_switch` to resolve the originating session, atomically revoke it with `revoked_at = now`, and preserve originating security properties:
     * `is_persistent = orig.is_persistent` (prevents escalating transient `remember_me=False` sessions to persistent cookies).
     * `absolute_expires_at = orig.absolute_expires_at` (preserves outer lifespan; prevents indefinite session lifespan extension attacks).
     * `idle_expires_at = min(now + timedelta(seconds=idle_seconds), orig.absolute_expires_at)` (idle timer bounded by absolute expiration).
     * `rotated_from_id = orig.id` (maintains session rotation lineage for audit trails).
     * `aal_level = orig.aal_level`, `aal2_verified_at = orig.aal2_verified_at` (verbatim preservation: step-up verifications older than 900 seconds remain stale, requiring re-authentication for sensitive operations).
     * `mfa_pending = orig.mfa_pending` and `auth_card_id = orig.auth_card_id`.
2. **Workspace Switch Endpoint Hardening (`kanban/api/v1/workspaces.py`):**
   - Caller Verification: In `switch_workspace_endpoint`, explicitly verifies `caller.session_id is not None`. Callers lacking a browser cookie session (such as API keys or Bearer tokens) are immediately rejected with HTTP 401 `SESSION_REQUIRED`, preventing unauthorized session cookie minting.
   - Procedure Isolation: Extracted `_execute_workspace_switch_proc` to keep function complexity strictly within architectural guidelines.
   - Cookie Header Hygiene: Passes `persistent=issued.is_persistent` to `attach_session_and_csrf_cookies` (omitting `Max-Age` and `Expires` for transient sessions). When the request is HTTPS, appends `Clear-Cookie` headers for un-prefixed fallback cookies (`kb_session`, `kb_csrf`).
3. **Elimination of Live 0ms TCP Commit-After-Response Race & Issue ETag Parity:**
   - Defect Identified in Live QA: In FastAPI, the `get_rls_session` dependency commits transactions during generator exit, which flushes AFTER the `JSONResponse` body is transmitted over Uvicorn's TCP socket. Consequently, immediate back-to-back `PATCH -> GET` requests at 0ms latency observe pre-commit PostgreSQL state, causing stale ETag reads and 412 Precondition Failed errors.
   - Root-Cause Resolution: Added explicit `await session.commit()` before returning the response in:
     * `PATCH /api/v1/issues/{key}` (`kanban/api/v1/issues.py`)
     * `api_begin_work`, `api_transition_ticket`, `api_complete_work` (`kanban/api/v1/issue_workflow.py`)
     * `override_issue_created_by` (`kanban/api/v1/issue_provenance.py`)
     * `create_issue` (`kanban/api/v1/issues.py`)
     * `create_issue_tree` (`kanban/api/v1/issue_trees.py`)
     * `copy_issue_endpoint` (`kanban/api/v1/issue_copy.py`)
     * `issue_move`, `issue_archive`, `issue_delete`, `assignees`, `comments`, `cancel_transition`, `workspaces`
   - Guarantees that the transaction is committed to PostgreSQL before headers and body are transmitted over the TCP wire, completely eliminating the 0ms commit-after-response race.
4. **Cookie Session AAL2 Stale Enforcement (`kanban/auth/mfa/policy.py`):**
   - In `require_admin_aal2`, added `ADMIN_AAL2_MAX_AGE_SECONDS = 900` enforcement for cookie sessions (`session_id is not None`).
   - If `aal2_verified_at` is older than 900 seconds, raises HTTP 403 `AAL2_STALE`, while preserving stateless tokens (e.g. `/mcp/admin` tokens without `session_id`).
   - Dual ETag acceptance: workflow transition endpoints accept both composite `compute_issue_etag` and backward-compatible `description_sha256` in `If-Match` headers.

All API contracts, security invariants, transaction boundaries, import layering constraints, and test coverage requirements are verified and certified:
- Zero new external runtime dependencies introduced (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- High test coverage: 165 Pytest tests pass across 18 suites in 149.85s with 96% total coverage across all 18 modified/related modules.
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

### 2.2 Live Stack Execution on Container `kanban-liveqa-3` (`:18963`, Commit `78074a1d`)
1. **Scenario (a): remember_me=false & absolute_expires_at on workspace switch:**
   - Login (remember_me=false) returned HTTP 200 with cookies omitting Max-Age/Expires.
   - Originating DB row before switch had `is_persistent=False`, `absolute_expires_at=2026-11-27 23:25:19.813706+00`.
   - Switched workspace -> HTTP 200 with rotated cookies.
   - Originating session row marked revoked (`revoked_at=2026-11-20 23:25:19.940725+00`).
   - New rotated row preserved `is_persistent=False` and identical `absolute_expires_at=2026-11-27 23:25:19.813706+00` (`rotated_from_id=01a1fb47-5a69-7460-b53c-1268205dccac`).
2. **Scenario (b): Stale aal2_verified_at (>900s) Enforcement:**
   - Aged session `aal2_verified_at` by 1200s (older than 900s limit).
   - `GET /api/v1/admin/auth-cards` returned HTTP 403 `AAL2_STALE` ("AAL2 verification is stale (1200s > 900s)").
   - Stateless `/mcp/admin` configure_workspace(get) succeeded with HTTP 200 (`isError=False`), confirming stateless tokens are unaffected.
3. **Scenario (c): Bearer / X-KB-Subject-Token Rejection on Switch:**
   - `POST /api/v1/workspaces/switch` with Bearer token returned HTTP 401 `SESSION_REQUIRED` with 0 Set-Cookie headers.
   - `POST /api/v1/workspaces/switch` with `X-KB-Subject-Token` returned HTTP 401 `SESSION_REQUIRED` with 0 Set-Cookie headers.
4. **Scenario (d): Immediate 0ms Back-to-Back TCP ETag Parity:**
   - Created issue KAN-6 (ETag: `"eb4de9ca..."`).
   - Immediate 0ms PATCH_1 returned ETag `"1b611e0b..."` matching 0ms GET header and body ETag.
   - 0ms PATCH_2 with `If-Match="1b611e0b..."` returned HTTP 200 OK and new ETag `"d75d6d9d..."`.
   - Stale If-Match returned HTTP 412 Precondition Failed.
   - Begin-work, transitions (state Done, hdr ETag === body etag === 0ms GET ETag), move -> Todo, POST /assignees, POST /comments, MCP update_ticket -> read_ticket all exhibited 100% commit visibility and ETag parity with 0 commit race.
5. **Playwright UI Telemetry:**
   - Desktop Light/Dark, Tablet, Mobile loads: 1015ms, 962ms (< 3000ms threshold).
   - Zero document overflow, 0 console errors, 0 page errors, 0 bad responses (>= 500 or 412).
   - Visual screenshots: `live-session-switch-desktop-light.png`, `live-session-switch-desktop-dark.png`, `live-issue-transition-etag-tablet.png`, `live-issue-transition-etag-mobile.png`.

---

## 3. Test Suite & Coverage Verification

- Pytest Test Suite (`unit-test-results.txt`):
  * 165 passed across 18 test files in 149.85s with 0 failures.
  * Line and branch coverage breakdown on 18 touched/related modules:
    - `kanban/api/v1/assignees.py`: 100% (28 stmts)
    - `kanban/api/v1/comments.py`: 100% (53 stmts)
    - `kanban/api/v1/issue_archive.py`: 100% (30 stmts)
    - `kanban/api/v1/issue_copy.py`: 100% (18 stmts)
    - `kanban/api/v1/issue_delete.py`: 100% (41 stmts)
    - `kanban/api/v1/issue_move.py`: 100% (21 stmts)
    - `kanban/api/v1/issue_trees.py`: 100% (20 stmts)
    - `kanban/api/v1/issue_workflow.py`: 97% (104 stmts, 12 branch)
    - `kanban/api/v1/issues.py`: 100% (58 stmts, 8 branch)
    - `kanban/api/v1/transitions.py`: 79% (83 stmts, 16 branch)
    - `kanban/api/v1/workspaces.py`: 95% (193 stmts, 58 branch)
    - `kanban/auth/sessions/service.py`: 97% (158 stmts, 28 branch)
    - `kanban/issues/workflow_service.py`: 90% (272 stmts, 88 branch)
    - `kanban/services/issue_provenance.py`: 100% (96 stmts, 28 branch)
    - `kanban/services/issues.py`: 98% (461 stmts, 186 branch)
    - `kanban/workflows/engine.py`: 93% (271 stmts, 68 branch)
    - `mcp/surfaces/agent/read_ticket.py`: 96% (269 stmts, 140 branch)
    - `mcp/surfaces/agent/update_ticket.py`: 97% (253 stmts, 160 branch)
    - **Total Across All 18 Modules:** 96% coverage (2429 stmts, 63 miss, 792 branch, 77 brpart).
- Static Analysis Gates (Commit `78074a1d`):
  * `uv run kanban-ctl db check-migrations`: OK: 63 migrations valid, single head (`p4_24_agent_safe_sequences`).
  * `uv run ruff check .`: Clean across 2023 files.
  * `uv run ruff format --check .`: Clean across 2023 files.
  * `uv run mypy database kanban mcp agent`: Clean (Success: 995 source files).
  * `uv run lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
  * `pnpm --dir kanban/web run typecheck`: Clean (0 errors).
  * `pnpm --dir kanban/web run lint`: Clean (0 errors, 0 warnings).
  * `pnpm --dir kanban/web run build`: Clean production build in 1.15s.
  * `python3 -m scripts.check_no_dashes --all` and `thumbs-up-kanban.wiki`: Clean (0 em/en-dashes).
  * Untracked Hygiene: `.backup_schedule.json` and `backups/` untouched and unstaged.

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **CWE-613 Session Rotation** | Atomic revocation and lineage linking | `rotate_for_workspace_switch` with `revoked_at` | PASS |
| **Transient Cookie Protection** | `remember_me=False` preserves transient cookie | `is_persistent` preserved; Max-Age omitted | PASS |
| **Outer TTL Preservation** | `absolute_expires_at` unextendable on switch | Outer lifespan preserved across rotations | PASS |
| **AAL2 Timestamp Preservation** | Step-up timestamp retained across switches | `aal2_verified_at` preserved verbatim | PASS |
| **Cookie Session AAL2 Stale** | Enforce 900s max-age on cookie sessions | Checked in `require_admin_aal2` | PASS |
| **Stateless Token Exemption** | Stateless MCP admin tokens preserved | Exempted when `session_id is None` | PASS |
| **Session Required Gate** | Non-session callers rejected on switch | HTTP 401 `SESSION_REQUIRED` | PASS |
| **Pre-Flush Commit Guarantee** | Explicit commit before response return | Added `await session.commit()` | PASS |
| **Zero 0ms ETag Drift** | PATCH ETag equals subsequent immediate GET | Verified in test and live execution | PASS |
| **Unidirectional Layering** | Layer hierarchy preserved | `lint-imports` confirms 2 kept, 0 broken | PASS |
| **Style Compliance** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

All session rotation procedures, security invariants, cookie hygiene routines, explicit response transaction commits, and unit test suites for KAN-36 on branch `main` at commit `78074a1d` have been thoroughly audited, verified against all architectural and security invariants, and certified on live stack `kanban-liveqa-3` with `OVERALL LIVE_STACK_VERDICT: PASS`. Ready for reality-checker QA gate closure.
