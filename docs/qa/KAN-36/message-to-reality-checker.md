# Forensic Verification Packet for KAN-36

**Ticket:** KAN-36 ([KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift)  
**Branch:** `main` (commit `78074a1d`)  
**Container Environment:** `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)  
**Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`  

---

## 1. Problem Implementation Summary

### Problem 1 & 2: Session Persistence, TTL, and AAL2 Preservation on Workspace Switch (CWE-613)
- **SessionService Rotation (`kanban/auth/sessions/service.py`):**
  - Added method `rotate_for_workspace_switch(session, target_principal_id, target_workspace_id, old_session_id, existing_cookie, originating_session)`:
    * Resolves originating `UserSession` record by explicit instance, cookie token lookup, or database query by `old_session_id`.
    * Validates that originating session exists, has not been revoked, has not exceeded `idle_expires_at`, and has not exceeded `absolute_expires_at`.
    * Atomically revokes originating session with `revoked_at = now`.
    * Computes new session expiration preserving originating constraints:
      - `is_persistent = orig.is_persistent` (prevents escalating transient `remember_me=False` sessions to persistent cookies).
      - `absolute_expires_at = orig.absolute_expires_at` (preserves absolute lifespan; never extends outer expiration boundary).
      - `idle_expires_at = min(now + timedelta(seconds=idle_seconds), orig.absolute_expires_at)` (idle timer never exceeds absolute expiration).
      - `rotated_from_id = orig.id` (maintains session rotation lineage for auditing).
      - `aal_level = orig.aal_level`, `aal2_verified_at = orig.aal2_verified_at` (verbatim preservation: stale step-up verification older than 900 seconds remains stale and requires re-authentication for admin operations).
      - `mfa_pending = orig.mfa_pending` and `auth_card_id = orig.auth_card_id`.
    * Issues a fresh signed session token with HMAC verification.

- **Workspace Switch Endpoint Hardening (`kanban/api/v1/workspaces.py`):**
  - **Caller Verification:** In `switch_workspace_endpoint`, checks `if caller.session_id is None:` and immediately raises RFC 7807 `401 Unauthorized` (`SESSION_REQUIRED`) before any cookie or rotation operation. Non-cookie callers (e.g., scoped API keys or Bearer tokens) are blocked from minting session cookies.
  - **Procedure Execution:** Isolated procedure call logic into `_execute_workspace_switch_proc` to keep cyclomatic complexity strictly below threshold.
  - **Cookie Header Hygiene:**
    * Calls `attach_session_and_csrf_cookies(..., persistent=issued.is_persistent)`: when `is_persistent=False`, cookies omit `Max-Age` and `Expires`, creating browser session-only cookies.
    * When request scheme is HTTPS, appends `Clear-Cookie` headers for `FALLBACK_SESSION_COOKIE_NAME` (`kb_session`) and `FALLBACK_CSRF_COOKIE_NAME` (`kb_csrf`) to prevent un-prefixed fallback cookies over secure connections.

### Problem 3 & 4: Issue PATCH ETag Parity and Drift Prevention
- **Commit Parity and TCP Race Elimination:**
  - Added explicit `await session.commit()` before constructing and returning HTTP responses across:
    * `kanban/api/v1/issues.py` (`PATCH /api/v1/issues/{key}` and `create_issue`)
    * `kanban/api/v1/issue_workflow.py` (`api_begin_work`, `api_transition_ticket`, `api_complete_work`)
    * `kanban/api/v1/issue_provenance.py` (`override_issue_created_by`)
    * `kanban/api/v1/issue_trees.py` (`create_issue_tree`)
    * `kanban/api/v1/issue_copy.py` (`copy_issue_endpoint`)
    * `kanban/api/v1/issue_move.py` (`move_issue_endpoint`)
    * `kanban/api/v1/issue_archive.py` (`archive_issue_endpoint`)
    * `kanban/api/v1/issue_delete.py` (`delete_issue_endpoint`)
    * `kanban/api/v1/assignees.py`, `kanban/api/v1/comments.py`, `kanban/api/v1/workspaces.py`
  - Guarantees PostgreSQL transactions commit before response bytes flush to the socket, permanently eliminating 0ms TCP read-after-write drift and 412 conflicts.

- **Workflow Transition Dual ETag Acceptance:**
  - Accepts both composite `compute_issue_etag` and backward-compatible `description_sha256` in `If-Match`.
  - Workflow transition responses include fresh `ETag` header from `fresh_issue.etag`.

---

## 2. Test Execution and Coverage Audit

### Sequential Pytest Run (`pytest --cov`)
- **Execution Summary:** 165 passed across 18 test files in 149.85s with 0 failures.
- **Coverage Breakdown Across 18 Touched/Related Modules:**
  * `kanban/api/v1/assignees.py`: 100% (28 stmts)
  * `kanban/api/v1/comments.py`: 100% (53 stmts)
  * `kanban/api/v1/issue_archive.py`: 100% (30 stmts)
  * `kanban/api/v1/issue_copy.py`: 100% (18 stmts)
  * `kanban/api/v1/issue_delete.py`: 100% (41 stmts)
  * `kanban/api/v1/issue_move.py`: 100% (21 stmts)
  * `kanban/api/v1/issue_trees.py`: 100% (20 stmts)
  * `kanban/api/v1/issue_workflow.py`: 97% (104 stmts, 12 branch)
  * `kanban/api/v1/issues.py`: 100% (58 stmts, 8 branch)
  * `kanban/api/v1/transitions.py`: 79% (83 stmts, 16 branch)
  * `kanban/api/v1/workspaces.py`: 95% (193 stmts, 58 branch)
  * `kanban/auth/sessions/service.py`: 97% (158 stmts, 28 branch)
  * `kanban/issues/workflow_service.py`: 90% (272 stmts, 88 branch)
  * `kanban/services/issue_provenance.py`: 100% (96 stmts, 28 branch)
  * `kanban/services/issues.py`: 98% (461 stmts, 186 branch)
  * `kanban/workflows/engine.py`: 93% (271 stmts, 68 branch)
  * `mcp/surfaces/agent/read_ticket.py`: 96% (269 stmts, 140 branch)
  * `mcp/surfaces/agent/update_ticket.py`: 97% (253 stmts, 160 branch)
  * **TOTAL Across All 18 Modules:** 96% coverage (2429 stmts, 63 missing, 792 branches).

### Static Quality Gates Summary (Commit `78074a1d`)
- `kanban-ctl db check-migrations`: OK (63 migrations valid, single head: `p4_24_agent_safe_sequences`).
- `ruff check .`: All checks passed across 2023 files.
- `ruff format --check .`: Clean across 2023 files.
- `mypy database kanban mcp agent`: Clean across 995 source files.
- `lint-imports`: Analyzed dependencies. 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `scripts.check_no_dashes`: Clean (0 em/en-dashes across codebase and wiki).

---

## 3. Live Full-Stack Proof Highlights (`kanban-liveqa-3`, `:18963`)

- **Scenario (a):** Transient session (`remember_me=False`) rotated across workspaces preserved `is_persistent=False` (omits Max-Age/Expires), preserved `absolute_expires_at` (`2026-11-27 23:25:19.813706+00`), and atomically revoked originating session.
- **Scenario (b):** Aged session (`aal2_verified_at` > 900s) preserved across switch: `GET /api/v1/admin/auth-cards` returned HTTP 403 `AAL2_STALE` ("AAL2 verification is stale (1200s > 900s)"). Stateless `/mcp/admin` API key succeeded (200 OK, `isError=False`).
- **Scenario (c):** `POST /api/v1/workspaces/switch` with Bearer or `X-KB-Subject-Token` returned HTTP 401 `SESSION_REQUIRED` with 0 Set-Cookie headers.
- **Scenario (d):** 0ms back-to-back TCP PATCH -> GET -> PATCH(If-Match), begin-work -> GET, transitions -> GET, move -> GET, POST /assignees -> GET, POST /comments -> GET, MCP update_ticket -> read_ticket: 100% commit visibility and ETag parity with 0 commit race.
- **Playwright UI:** Loads < 3000ms (1015ms, 962ms), 0 console errors, 0 page errors, 0 bad responses.
- **Screenshots:** `live-session-switch-desktop-light.png`, `live-session-switch-desktop-dark.png`, `live-issue-transition-etag-tablet.png`, `live-issue-transition-etag-mobile.png`.

---

## 4. Artifacts Index

- `docs/qa/KAN-36/live-fullstack-proof.txt`: Round 3 live execution telemetry against `kanban-liveqa-3` (`:18963`, commit `78074a1d`)
- `docs/qa/KAN-36/unit-test-results.txt`: Verbatim sequential Pytest execution log (165 passed across 18 suites, 96% total coverage)
- `docs/qa/KAN-36/build-or-typecheck.txt`: Static analysis and verification proof
- `docs/qa/KAN-36/changed-files-manifest.txt`: List of modified and added source files
- `docs/qa/KAN-36/contract-sample.json`: ASGI headers, cookies, ETag parity, and status codes
- `docs/qa/KAN-36/git-diff.patch`: Git diff patch
- `docs/qa/KAN-36/api-specialist-review.md`: Dual-specialist API and security audit signoff
- `docs/qa/KAN-36/ui-specialist-review.md`: Dual-specialist UI and layout audit signoff
