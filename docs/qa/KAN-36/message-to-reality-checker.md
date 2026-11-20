# Forensic Verification Packet for KAN-36

**Ticket:** KAN-36 ([KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift)  
**Branch:** `feat/KAN-36`  
**Base Commit:** `b3b0f4ba`  

---

## 1. Problem Implementation Summary

### Problem 1 & 2: Session Persistence, TTL, and AAL2 Preservation on Workspace Switch (CWE-613)
- **SessionService Rotation (`kanban/auth/sessions/service.py`):**
  - Added method `rotate_for_workspace_switch(session, target_principal_id, target_workspace_id, old_session_id, existing_cookie, originating_session)`:
    * Resolves the originating `UserSession` record by explicit instance, cookie token lookup, or database query by `old_session_id`.
    * Validates that the originating session exists, has not been revoked, has not exceeded `idle_expires_at`, and has not exceeded `absolute_expires_at`.
    * Atomically revokes the originating session with `revoked_at = now`.
    * Computes new session expiration preserving originating constraints:
      - `is_persistent = orig.is_persistent` (prevents escalating transient `remember_me=False` sessions to persistent cookies).
      - `absolute_expires_at = orig.absolute_expires_at` (preserves the absolute lifespan; never extends the outer expiration boundary).
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
- **Issue Service Synchronization (`kanban/services/issues.py`):**
  - In `serialize_issue`, loads `ObjectRecord` with `await session.get(ObjectRecord, issue.id, populate_existing=True)` so cached spine records do not report stale modification timestamps.
  - In `update_issue`, after executing all column updates, tags/modules flushes, and `record_activity()` ledger entries, invokes `await session.flush()`, `await session.refresh(issue)`, and explicitly refreshes `ObjectRecord`.
  - Guarantees that PATCH response `ETag` header and `body.etag` strictly equal the immediate GET `ETag` header with zero drift.

- **Workflow Transition Dual ETag Acceptance (`kanban/workflows/engine.py` & `kanban/issues/workflow_service.py`):**
  - In `TransitionEngine.execute_transition` (`kanban/workflows/engine.py`) and `_check_if_match_etag` (`kanban/issues/workflow_service.py`), accepts BOTH the current composite `compute_issue_etag` AND backward-compatible `description_sha256` in `If-Match`.
  - In `kanban/api/v1/issue_workflow.py`, after completing transitions (`api_begin_work`, `api_transition_ticket`, `api_complete_work`), flushes the session, refreshes `issue` and `ObjectRecord`, and passes `headers={"ETag": serialized.etag}` directly into the returned `JSONResponse`.

- **Provenance Override and MCP Parity (`kanban/services/issue_provenance.py` & `mcp/surfaces/agent/`):**
  - In `issue_provenance.py` (`override_issue_created_by`), returns `resp.etag` instead of `description_sha256`.
  - In `mcp/surfaces/agent/update_ticket.py` and `read_ticket.py`, prefers `etag` ahead of `description_sha256` and strips enclosing quotes to ensure MCP roundtrips match REST API contracts.

---

## 2. Test Execution and Coverage Audit

### Sequential Pytest Run (`pytest --cov`)
- **Execution Summary:** 97 passed in 129.47 seconds with 0 warnings.
- **Test Suites Executed:**
  - `kanban/tests/auth/test_workspace_switch_session_persistence.py` (3 passed: covers remember_me=False cookie omission, absolute expiry preservation, stale AAL2 retention, non-cookie caller 401 rejection, and unit service rotation).
  - `kanban/tests/api/test_issue_patch_etag_parity.py` (2 passed: chained PATCH -> GET -> PATCH 0 drift parity, 304 If-None-Match, stale 412 handling, workflow begin-work/transition/complete-work parity, creator provenance parity, and MCP update_ticket/read_ticket parity).
  - `kanban/tests/auth/test_session_persistence.py` (4 passed: session remember-me duration, cookie omission, and session rotation).
  - `kanban/tests/api/test_workspaces_api.py` (9 passed: full workspace CRUD, switch, and role binding coverage).
  - `kanban/tests/api/test_issues.py` (16 passed: issue CRUD, listing, tags, and lifecycle).
  - `kanban/tests/api/test_issue_workflow.py` (13 passed: begin-work, transitions, complete-work, and validation).
  - `kanban/tests/api/test_issue_provenance.py` (8 passed: creator overrides and activity audit logging).
  - `mcp/tests/agent/test_update_ticket.py` (12 passed: MCP ticket updates and field transformations).
  - `mcp/tests/agent/test_read_ticket.py` (14 passed: MCP ticket reading and LOD tier serialization).
  - `kanban/tests/workflows/test_transition_engine.py` (16 passed: state machine transitions and hook execution).

### Coverage Table on Touched Modules
| Module | Statements | Missing | Branches | Branch Partials | Coverage |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `kanban/api/v1/issue_workflow.py` | 98 | 0 | 12 | 3 | 97% |
| `kanban/api/v1/workspaces.py` | 188 | 14 | 58 | 16 | 88% |
| `kanban/auth/sessions/service.py` | 158 | 2 | 28 | 3 | 97% |
| `kanban/issues/workflow_service.py` | 255 | 9 | 84 | 15 | 93% |
| `kanban/services/issue_provenance.py` | 96 | 0 | 28 | 0 | 100% |
| `kanban/services/issues.py` | 451 | 8 | 182 | 9 | 97% |
| `kanban/workflows/engine.py` | 261 | 10 | 64 | 11 | 94% |
| `mcp/surfaces/agent/read_ticket.py` | 244 | 4 | 124 | 14 | 95% |
| `mcp/surfaces/agent/update_ticket.py` | 251 | 2 | 160 | 11 | 97% |
| **TOTAL** | **2002** | **49** | **740** | **82** | **95%** |

### Static Analysis and Linters
- `kanban-ctl db check-migrations`: OK (62 migrations valid, single head: `p4_23_oidc_link_intent_fk`).
- `ruff check kanban mcp`: All checks passed (0 errors, 0 warnings).
- `ruff format --check kanban mcp`: 659 files already formatted (0 changes required).
- `mypy kanban mcp`: Success (no issues found in 655 source files).
- `lint-imports`: Analyzed 977 files, 3475 dependencies. 2 kept, 0 broken.
- `assert_admin_routes_protected`: Passed 100% (2 passed in `test_aal2_policy.py` and `test_system_status.py`).
- `scripts.check_no_dashes`: Clean (0 em-dashes, 0 en-dashes across codebase and QA documentation).

---

## 3. Artifacts Index
- `docs/qa/KAN-36/unit-test-results.txt`: Verbatim sequential pytest execution log with 95% statement coverage.
- `docs/qa/KAN-36/build-or-typecheck.txt`: Static analysis and verification proof.
- `docs/qa/KAN-36/changed-files-manifest.txt`: List of all 13 modified and added source files.
- `docs/qa/KAN-36/artifacts/contract-sample.json`: ASGI headers, cookies, ETag parity, and status codes.
- `docs/qa/KAN-36/git-diff.patch`: Git diff against `b3b0f4ba`.
