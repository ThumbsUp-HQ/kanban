# UI Specialist Review: KAN-36

**Ticket ID:** KAN-36  
**Title:** [KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift  
**Branch:** `main` (integrated at commit `78074a1d`)  
**Commit:** `78074a1d65216b6b3546b122445cdb322e0b1651`  
**Target Container:** `kanban-liveqa-3` (`http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS)  
**Live Stack Verdict:** `LIVE_STACK_VERDICT: PASS`  
**Reviewer:** ui-spec-2 (Clean-Room UI Specialist)  
**Date:** 2026-11-20  
**Status:** STATUS: APPROVED  

---

## 1. Executive Summary

A clean-room UI and UX audit was conducted on ticket KAN-36 integrated into `main` at commit `78074a1d` pursuant to the mandatory Dual Specialist Gate defined in `GEMINI.md`. This audit incorporates verified evidence from the zero-mock live container execution (`live-fullstack-proof.txt` on container `kanban-liveqa-3`, `http://127.0.0.1:18963`), backend Pytest execution logs (`unit-test-results.txt`), visual screenshots in `docs/qa/KAN-36/screenshots/`, and static build gates (`build-or-typecheck.txt`).

While KAN-36 resolves core session persistence and entity concurrency security invariants, its contracts directly govern frontend SPA authentication stability during workspace switching in the Sidebar, session longevity guarantees, and optimistic issue editing in the Issue Detail Drawer (`IssueSurface.tsx`), Table, and Board views.

The implementation completely eliminates optimistic concurrency desynchronization (0 ETag drift), resolves the live commit race condition via explicit pre-response database transaction commits across all mutation routes, protects transient browser sessions from unwanted persistence escalation, prevents false 412 conflict modals during rapid drawer edits, and contains zero em-dashes or en-dashes.

---

## 2. Frontend / UX Contract Alignment & Ergonomics

### 2.1 Live Commit Race Elimination & Zero ETag Drift
- **Elimination of False 412 Conflict Modals:**
  - In the Issue Detail Drawer (`IssueSurface.tsx`), users frequently make sequential optimistic edits (e.g., updating the title, immediately editing the description, and selecting an assignee).
  - In earlier live testing, FastAPI session yield dependencies committed after response body streaming began over uvicorn TCP, causing immediate (0ms) back-to-back GET or PATCH requests to observe pre-commit states and trigger false 412 Precondition Failed dialogs.
  - In commit `78074a1d`, explicit `await session.commit()` calls guarantee immediate read-after-write consistency (0ms delay) for all browser clients and MCP agents across all remaining issue and workspace mutation routes:
    * `PATCH /api/v1/issues/{key}` (`issues.py`)
    * `POST /api/v1/issues/{key}/workflow/begin-work` (`issue_workflow.py`)
    * `POST /api/v1/issues/{key}/workflow/transition` (`issue_workflow.py`)
    * `POST /api/v1/issues/{key}/workflow/complete-work` (`issue_workflow.py`)
    * `PATCH /api/v1/issues/{key}/provenance/created-by` (`issue_provenance.py`)
    * `POST /api/v1/issues/{key}/move` (`issue_move.py`)
    * `POST /api/v1/issues/{key}/archive` & `/unarchive` (`issue_archive.py`)
    * `DELETE /api/v1/issues/{key}` & `/restore` (`issue_delete.py`)
    * `POST /api/v1/issues/{key}/assignees` & `DELETE` (`assignees.py`)
    * `POST /api/v1/issues/{key}/comments`, `PATCH`, `DELETE`, `/reactions` (`comments.py`)
    * `POST /api/v1/issues/{key}/transitions/cancel` (`transitions.py`, including `etag` in response body matching `ETag` header)
    * `PATCH /api/v1/workspaces/{id}`, `/roles`, `/unbind` (`workspaces.py`)
  - Validated live against `kanban-liveqa-3`: 0ms back-to-back TCP PATCH_1 (`status=200`) -> 0ms GET -> 0ms PATCH_2 with `If-Match` succeeded with 100% ETag parity, 0 commit race, and stale `If-Match` properly rejected with HTTP 412.

### 2.2 Workspace Switching & SPA Session Stability
- **Cookie Lifetime Alignment:**
  - When users authenticate with `remember_me=False`, the browser expects a session-only cookie that expires upon closing the window or tab.
  - The hardened `SessionService.rotate_for_workspace_switch` strictly preserves `is_persistent=False`, ensuring that `Max-Age` and `Expires` remain omitted on rotated cookies across login, MFA verification, and workspace switching.
- **AAL2 Freshness & Admin Step-Up Handling:**
  - In `kanban/auth/mfa/policy.py`, `require_admin_aal2` enforces an AAL2 freshness window of 900 seconds (`ADMIN_AAL2_MAX_AGE_SECONDS = 900`) for cookie sessions while preserving stateless API tokens.
  - When step-up authentication is stale (>900 seconds), accessing administrative routes returns HTTP 403 `AAL2_STALE` with available methods (`totp`, `recovery`), allowing the frontend to present a contextual step-up prompt rather than an unexpected logout.
- **Non-Cookie Caller Rejection:**
  - Non-cookie requests to the workspace switch endpoint are rejected with HTTP 401 `SESSION_REQUIRED` with 0 `Set-Cookie` headers emitted, preventing external scripts or API tokens from mutating the active browser session. Verified with real valid non-cookie token (`X-KB-Subject-Token` via `mint_mcp_api_key`) in `test_workspace_switch_session_persistence.py`.

### 2.3 Workflow State Transitions & MCP State Synchronization
- **Flexible Precondition Matching:**
  - Workflow transitions accept both composite `compute_issue_etag` and legacy `description_sha256` in `If-Match`, ensuring transitions triggered from the board or quick field popovers succeed reliably.
  - Transition responses pass updated `ETag` headers and response body `etag` fields, keeping the frontend QueryClient cache synchronized with zero latency.

### 2.4 Design System & CSP Compliance
- **Zero Style Regressions:** All touched files strictly conform to the existing design system tokens with zero inline JSX styles (`style-src 'self'` compliant).
- **Zero Dash Violations:** Strictly 0 em-dashes and 0 en-dashes in code, comments, and documentation.

---

## 3. Visual Screenshot Audit (`docs/qa/KAN-36/screenshots/`)

Direct visual inspection via `read_file` confirms:
1. `live-session-switch-desktop-light.png` & `live-session-switch-desktop-dark.png` (1440x900):
   - Authenticated workspace view after workspace switch to `Kanban Primary` (`KP`).
   - Issues view loaded in 1015ms (light) and 962ms (dark) (< 3000ms threshold).
   - Issue `KAN-6 Updated via MCP` rendered with state `Todo`, Assignee `LiveQA Admin`.
   - WCAG AA contrast preserved in both themes, 0 text clipping, 0 horizontal overflow.
2. `live-issue-transition-etag-tablet.png` (768x1024) & `live-issue-transition-etag-mobile.png` (390x844):
   - Responsive issue surface renders cleanly without horizontal scroll (`docOverflow: false`).
   - State selector and action toolbar maintain stable touch targets.
   - Zero console errors, zero page errors, zero 412 conflict modals.

---

## 4. Automated Test Verification & Quality Gates

1. Test Suite Summary (165 passed across 18 suites, 96% coverage):
   - `kanban/tests/auth/test_workspace_switch_session_persistence.py`: 5 passed.
   - `kanban/tests/api/test_issue_patch_etag_parity.py`: 2 passed (0 ETag drift on chained PATCH -> GET -> PATCH).
   - `kanban/tests/auth/test_session_persistence.py`: 4 passed.
   - `kanban/tests/api/test_workspaces_api.py`: 9 passed.
   - `kanban/tests/api/test_workspace_settings.py`: 13 passed.
   - `kanban/tests/api/test_issues.py`: 16 passed.
   - `kanban/tests/api/test_issue_move.py`: 5 passed.
   - `kanban/tests/api/test_issue_archive.py`: 3 passed.
   - `kanban/tests/api/test_issue_delete.py`: 8 passed.
   - `kanban/tests/api/test_issue_workflow.py`: 13 passed.
   - `kanban/tests/api/test_assignees.py`: 7 passed.
   - `kanban/tests/api/test_comments.py`: 11 passed.
   - `kanban/tests/api/test_issue_copy.py`: 9 passed.
   - `kanban/tests/api/test_issue_trees.py`: 9 passed.
   - `kanban/tests/api/test_issue_provenance.py`: 8 passed.
   - `mcp/tests/agent/test_update_ticket.py`: 12 passed.
   - `mcp/tests/agent/test_read_ticket.py`: 15 passed.
   - `kanban/tests/workflows/test_transition_engine.py`: 16 passed.
   - Total: 165 passed in 149.85s across 18 test suites with 0 warnings.
   - Coverage: 96% total statement coverage across all 18 modified/related modules (2429 statements, 63 missed, 792 branches, 77 branch parts). Modules `assignees.py`, `comments.py`, `issue_archive.py`, `issue_copy.py`, `issue_delete.py`, `issue_move.py`, `issue_trees.py`, and `issues.py` all achieve 100% statement coverage.
   - Stderr Warnings: Exactly 0 warnings.

2. Static Gates & Linters:
   - TypeScript: `tsc -b --noEmit` passed with 0 errors.
   - ESLint: `eslint . --max-warnings 0` passed cleanly.
   - Python Linting & Formatting: `ruff check .` and `ruff format --check .` passed cleanly across all files.
   - Type Checking: `mypy` passed with 0 issues in source files.
   - Architectural Layering: `lint-imports` passed with 2 kept contracts, 0 broken.
   - Brand & Typography Guard: `python3 -m scripts.check_no_dashes --all` passed cleanly (0 em-dashes and 0 en-dashes).

---

## 5. Certification

The contract and UX alignments in ticket KAN-36 fulfill all functional, security, concurrency, reliability, and usability requirements.

**STATUS: APPROVED**
