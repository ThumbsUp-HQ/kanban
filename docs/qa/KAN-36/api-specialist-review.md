# API Specialist Review: KAN-36 (KB-P3-PENTEST-01)

- Ticket: KAN-36
- Title: [KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan36-6b065404`
- Target Branch: `feat/KAN-36`
- Commit: `9cd41e24bcbb678c1c4fecbb58ff175d0fe8a149`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-36 on branch `feat/KAN-36` (commit `9cd41e24`), incorporating concrete evidence from the implementation source files, unit test execution logs (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

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
3. Issue PATCH ETag Parity and Drift Elimination (`kanban/services/issues.py`):
   - In `serialize_issue`, loads `ObjectRecord` with `populate_existing=True` to guarantee spine record timestamps reflect current database state.
   - In `update_issue`, after applying column updates, tags/modules flushes, and activity ledger entries, invokes `await session.flush()`, `await session.refresh(issue)`, and explicitly refreshes `ObjectRecord`.
   - Guarantees that PATCH response `ETag` header and `body.etag` strictly equal the subsequent GET `ETag` header with zero drift.
4. Workflow Transition Dual ETag Acceptance & MCP Parity (`kanban/workflows/engine.py`, `kanban/issues/workflow_service.py`, `mcp/`):
   - Accepts both composite `compute_issue_etag` and backward-compatible `description_sha256` in `If-Match` headers.
   - Passes `headers={"ETag": serialized.etag}` directly on JSON responses for `api_begin_work`, `api_transition_ticket`, and `api_complete_work`.
   - MCP surfaces (`update_ticket.py` and `read_ticket.py`) prioritize `etag` ahead of `description_sha256` and strip quotes, ensuring full parity between MCP agent actions and REST API contracts.

All API contracts, security invariants, transaction boundaries, import layering constraints, and test coverage requirements are verified and certified:
- Zero new external runtime dependencies introduced (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Schema integrity: All 62 migrations valid with single head `p4_23_oidc_link_intent_fk` (`check-migrations`).
- High test coverage: 97 sequential Pytest tests pass in 129.47s with 0 warnings and 95% overall statement coverage across touched modules (`issue_provenance.py` 100%, `issues.py` 97%, `sessions/service.py` 97%, `issue_workflow.py` 97%, `update_ticket.py` 97%, `read_ticket.py` 95%, `engine.py` 94%, `workflow_service.py` 93%, `workspaces.py` 88%).
- Admin route protection: `assert_admin_routes_protected` passed 100%.
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
  - Verifies that transient session cookies (`remember_me=False`) remain transient, and absolute expiration is preserved verbatim across switches.

### 2.2 Caller Authentication Gate (`kanban/api/v1/workspaces.py`)
- Source: `kanban/api/v1/workspaces.py` (`switch_workspace_endpoint`)
- Security Boundary:
  - Caller check:
    ```python
    if caller.session_id is None:
        raise ProblemException(
            status=status.HTTP_401_UNAUTHORIZED,
            title="Session Required",
            detail="Workspace switching with session cookie rotation requires an active browser session.",
            code="SESSION_REQUIRED",
        )
    ```
  - Prevents non-browser callers (e.g. MCP clients or CLI runners authenticating via API keys) from triggering browser session cookie minting.
  - Re-checks that caller has an active role binding in the target workspace via `assert_workspace_access`.

### 2.3 Stale PATCH ETag Drift Elimination (`kanban/services/issues.py`)
- Source: `kanban/services/issues.py` (`update_issue`, `serialize_issue`)
- Problem: Previously, cached ORM models in SQLAlchemy sessions resulted in PATCH responses returning ETags computed from in-memory objects whose spine timestamps diverged slightly from database trigger updates. Subsequent immediate GET requests computed a different ETag, breaking optimistic concurrency chains and causing false HTTP 412 Precondition Failed errors.
- Fix:
  - `serialize_issue` executes `await session.get(ObjectRecord, issue.id, populate_existing=True)`.
  - `update_issue` calls `await session.flush()`, `await session.refresh(issue)`, and reloads `ObjectRecord` before calling `serialize_issue`.
  - Test `kanban/tests/api/test_issue_patch_etag_parity.py` verifies chained operations: PATCH -> GET -> PATCH with exact ETag parity (0 drift), HTTP 304 on `If-None-Match`, and HTTP 412 on actual stale revisions.

### 2.4 Workflow Dual ETag & MCP Parity (`kanban/workflows/engine.py`, `mcp/`)
- Dual ETag Acceptance:
  - Transition endpoints support both `compute_issue_etag(issue, spine)` and SHA-256 of `description_markdown`.
  - Workflow endpoints (`api_begin_work`, `api_transition_ticket`, `api_complete_work`) attach the refreshed ETag header directly to the HTTP response.
  - MCP tools `update_ticket` and `read_ticket` accept and emit unquoted ETags matching REST standards.

---

## 3. Test Suite & Coverage Verification

- Sequential Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/auth/test_workspace_switch_session_persistence.py`: 3 passed.
  - `kanban/tests/api/test_issue_patch_etag_parity.py`: 2 passed.
  - `kanban/tests/auth/test_session_persistence.py`: 4 passed.
  - `kanban/tests/api/test_workspaces_api.py`: 9 passed.
  - `kanban/tests/api/test_issues.py`: 16 passed.
  - `kanban/tests/api/test_issue_workflow.py`: 13 passed.
  - `kanban/tests/api/test_issue_provenance.py`: 8 passed.
  - `mcp/tests/agent/test_update_ticket.py`: 12 passed.
  - `mcp/tests/agent/test_read_ticket.py`: 14 passed.
  - `kanban/tests/workflows/test_transition_engine.py`: 16 passed.
  - Total: 97 passed in 129.47s with 0 warnings.
- Statement Coverage across Touched Modules:
  - `kanban/api/v1/issue_workflow.py`: 97% (98 stmts, 0 miss)
  - `kanban/api/v1/workspaces.py`: 88% (188 stmts, 14 miss)
  - `kanban/auth/sessions/service.py`: 97% (158 stmts, 2 miss)
  - `kanban/issues/workflow_service.py`: 93% (255 stmts, 9 miss)
  - `kanban/services/issue_provenance.py`: 100% (96 stmts, 0 miss)
  - `kanban/services/issues.py`: 97% (451 stmts, 8 miss)
  - `kanban/workflows/engine.py`: 94% (261 stmts, 10 miss)
  - `mcp/surfaces/agent/read_ticket.py`: 95% (244 stmts, 4 miss)
  - `mcp/surfaces/agent/update_ticket.py`: 97% (251 stmts, 2 miss)
  - Total: 2002 stmts, 49 miss, 95% overall coverage.
- Static Analysis (`build-or-typecheck.txt`):
  - `kanban-ctl db check-migrations`: Clean (All 62 migrations valid, single head: `p4_23_oidc_link_intent_fk`).
  - `ruff check kanban mcp`: Clean (All checks passed).
  - `ruff format --check kanban mcp`: Clean (659 files already formatted).
  - `mypy kanban mcp`: Clean (Success: no issues found in 655 source files).
  - `lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `assert_admin_routes_protected`: Clean (2/2 passed).
  - `scripts.check_no_dashes`: Clean (0 em/en-dashes across repository).

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Session Rotation Lineage | Old session revoked; new session links to old ID | `revoked_at = now`, `rotated_from_id = orig.id` | PASS |
| Persistence Preservation | Transient sessions remain session-only cookies | `is_persistent = orig.is_persistent` preserved | PASS |
| Absolute Expiration Bound | Cannot extend session lifetime via workspace switch | `absolute_expires_at = orig.absolute_expires_at` | PASS |
| Idle Timeout Bounded | Idle timeout never exceeds absolute expiration | `min(now + idle, orig.absolute_expires_at)` | PASS |
| Stale AAL2 Integrity | Stale AAL2 verifications (>900s) stay stale | `orig.aal2_verified_at` preserved verbatim | PASS |
| Non-Cookie Caller Gate | Block API key / Bearer tokens from minting cookies | Raises HTTP 401 `SESSION_REQUIRED` | PASS |
| HTTPS Cookie Hygiene | Clear un-prefixed fallback cookies on HTTPS | `Clear-Cookie` headers for `kb_session`/`kb_csrf` | PASS |
| Zero PATCH ETag Drift | PATCH ETag and body.etag match immediate GET ETag | `populate_existing=True` and explicit refresh | PASS |
| Dual If-Match Support | Accept composite ETag and description_sha256 | Supported in `TransitionEngine` & workflow service | PASS |
| MCP ETag Roundtrip | Unquoted ETag strings match REST contracts | Updated `read_ticket.py` and `update_ticket.py` | PASS |
| Unidirectional Layering | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

All API endpoints, session rotation workflows, CWE-613 mitigation boundaries, ETag parity synchronizations, MCP tool schemas, and unit test suites for KAN-36 on branch `feat/KAN-36` at commit `9cd41e24` have been thoroughly audited, verified against all security invariants, and certified. Ready for Reality-Checker QA and merge into `main`.
