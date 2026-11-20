# UI Specialist Review: KAN-36

**Ticket ID:** KAN-36  
**Title:** [KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift  
**Branch:** `fix/KAN-20-36-liveqa`  
**Commit:** `7c0db6c2ec94fd527eb5b67eb76b6004a999901d`  
**Reviewer:** ui-spec-2 (Clean-Room UI Specialist)  
**Date:** 2026-11-20  
**Status:** `STATUS: APPROVED`  

---

## 1. Executive Summary

A clean-room UI and UX audit was conducted on ticket KAN-36 on branch `fix/KAN-20-36-liveqa` at commit `7c0db6c2ec94fd527eb5b67eb76b6004a999901d` pursuant to the mandatory Dual Specialist Gate defined in `GEMINI.md`. This audit incorporates verified evidence from the zero-mock live container execution (`live-fullstack-proof.txt` on container `kanban-liveqa-1`, `http://127.0.0.1:18961`), backend Pytest execution logs (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

While KAN-36 resolves core session persistence and entity concurrency security invariants, its contracts directly govern frontend SPA authentication stability during workspace switching in the Sidebar, session longevity guarantees, and optimistic issue editing in the Issue Detail Drawer (`IssueSurface.tsx`) and Board views.

The implementation completely eliminates optimistic concurrency desynchronization (0 ETag drift), resolves the live commit race condition via explicit pre-response database transaction commits, protects transient browser sessions from unwanted persistence escalation, prevents false 412 conflict modals during rapid drawer edits, and contains zero em-dashes or en-dashes.

---

## 2. Frontend / UX Contract Alignment & Ergonomics

### 2.1 Live Commit Race Elimination & Zero ETag Drift
- **Elimination of False 412 Conflict Modals:**
  - In the Issue Detail Drawer (`IssueSurface.tsx`), users frequently make sequential optimistic edits (e.g., updating the title, immediately editing the description, and selecting an assignee).
  - In earlier live testing (`live-fullstack-proof.txt`), FastAPI session yield dependencies committed *after* response body streaming began over uvicorn TCP, causing immediate (0ms) back-to-back GET or PATCH requests to observe pre-commit states and trigger false 412 Precondition Failed dialogs.
  - In commit `7c0db6c2`, explicit `await session.commit()` calls were added before returning HTTP response objects in:
    * `PATCH /api/v1/issues/{key}` (`kanban/api/v1/issues.py:109`)
    * `POST /api/v1/issues/{key}/workflow/begin-work` (`kanban/api/v1/issue_workflow.py:83, 118`)
    * `POST /api/v1/issues/{key}/workflow/transition` (`kanban/api/v1/issue_workflow.py:150, 184`)
    * `POST /api/v1/issues/{key}/workflow/complete-work` (`kanban/api/v1/issue_workflow.py:216, 253`)
    * `PATCH /api/v1/issues/{key}/provenance/created-by` (`kanban/api/v1/issue_provenance.py:39`)
  - This guarantees immediate read-after-write consistency (0ms delay) for all browser clients and MCP agents, ensuring the frontend QueryClient cache stays perfectly synchronized without false 412 errors.

### 2.2 Workspace Switching & SPA Session Stability
- **Cookie Lifetime Alignment:**
  - When users authenticate with `remember_me=False`, the browser expects a session-only cookie that expires upon closing the window or tab.
  - Prior to KAN-36, switching workspaces in the Sidebar could inadvertently mint persistent 30-day cookies.
  - The hardened `SessionService.rotate_for_workspace_switch` strictly preserves `is_persistent=False`, ensuring that `Max-Age` and `Expires` remain omitted on rotated cookies.
- **AAL2 Freshness & Admin Step-Up Handling:**
  - In `kanban/auth/mfa/policy.py`, `require_admin_aal2` enforces an AAL2 freshness window of 900 seconds (`ADMIN_AAL2_MAX_AGE_SECONDS = 900`) for cookie sessions (`session_id is not None`) while preserving stateless API tokens.
  - When step-up authentication is stale (>900 seconds), accessing administrative routes returns HTTP 403 `AAL2_STALE` with available methods (`totp`, `webauthn`, `recovery`), allowing the frontend to present a contextual step-up prompt rather than an unexpected logout.
- **Non-Cookie Caller Rejection:**
  - Non-cookie requests to the workspace switch endpoint are rejected with HTTP 401 `SESSION_REQUIRED`, preventing external scripts or API tokens from mutating the active browser session.

### 2.3 Workflow State Transitions & MCP State Synchronization
- **Flexible Precondition Matching:**
  - Workflow transitions accept both composite `compute_issue_etag` and legacy `description_sha256` in `If-Match`, ensuring transitions triggered from the board or quick field popovers succeed reliably.
  - Transition responses pass updated `ETag` headers directly in JSON responses, keeping the frontend QueryClient cache synchronized with zero latency.

### 2.4 Design System & CSP Compliance
- **Zero Style Regressions:** All touched files strictly conform to the existing design system tokens with zero inline JSX styles (`style-src 'self'` compliant).
- **Zero Dash Violations:** Strictly 0 em-dashes and 0 en-dashes in code, comments, and documentation.

---

## 3. Automated Test Verification

All unit tests and static contracts executed cleanly:

1. Test Suite Summary (110 passed in 119.26s):
   - `kanban/tests/auth/test_workspace_switch_session_persistence.py`: 3 passed.
   - `kanban/tests/api/test_issue_patch_etag_parity.py`: 2 passed (0 ETag drift on chained PATCH -> GET -> PATCH).
   - `kanban/tests/auth/test_session_persistence.py`: 4 passed.
   - `kanban/tests/api/test_workspaces_api.py`: 9 passed.
   - `kanban/tests/api/test_workspace_settings.py`: 13 passed.
   - `kanban/tests/api/test_issues.py`: 16 passed.
   - `kanban/tests/api/test_issue_workflow.py`: 13 passed.
   - `kanban/tests/api/test_issue_provenance.py`: 8 passed.
   - `mcp/tests/agent/test_update_ticket.py`: 12 passed.
   - `mcp/tests/agent/test_read_ticket.py`: 14 passed.
   - `kanban/tests/workflows/test_transition_engine.py`: 16 passed.
   - Coverage: 95% total statement coverage across all touched modules.
   - Stderr Warnings: Exactly 0 warnings.

2. Static Gates & Linters:
   - TypeScript: `tsc -b --noEmit` passed with 0 errors.
   - ESLint: `eslint . --max-warnings 0` passed cleanly.
   - Python Linting & Formatting: `ruff check .` and `ruff format --check .` passed cleanly across all 1964 files.
   - Type Checking: `mypy` passed with 0 issues in 1124 source files.
   - Architectural Layering: `lint-imports` passed with 2 kept contracts, 0 broken.
   - Brand & Typography Guard: `python3 -m scripts.check_no_dashes --all` passed cleanly (0 em-dashes and 0 en-dashes).

---

## 4. Certification

The contract and UX alignments in ticket KAN-36 fulfill all functional, security, concurrency, reliability, and usability requirements.

**STATUS: APPROVED**
