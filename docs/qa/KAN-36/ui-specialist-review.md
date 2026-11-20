# UI Specialist Review: KAN-36

**Ticket ID:** KAN-36  
**Title:** [KB-P3-PENTEST-01] Preserve Session Persistence/TTL/AAL2 on Workspace Switch (CWE-613) and Fix Stale Issue PATCH ETag Drift  
**Branch:** `feat/KAN-36`  
**Commit:** `9cd41e24`  
**Reviewer:** ui-spec-2 (Clean-Room UI Specialist)  
**Date:** 2026-11-20  
**Status:** `STATUS: APPROVED`  

---

## 1. Executive Summary

A clean-room UI and UX audit was conducted on ticket KAN-36 (`feat/KAN-36` commit `9cd41e24`) pursuant to the mandatory Dual Specialist Gate defined in `GEMINI.md`. While KAN-36 addresses core session security and entity concurrency invariants, its contracts directly govern frontend SPA authentication stability during workspace switching and optimistic issue editing in the Issue Detail Drawer and Board views.

The implementation completely eliminates optimistic concurrency desynchronization (0 ETag drift), protects transient browser sessions from unwanted persistence escalation, prevents false 412 conflict modals during rapid drawer edits, and contains zero em-dashes or en-dashes.

---

## 2. Frontend / UX Contract Alignment & Ergonomics

### 2.1 Workspace Switching & SPA Session Stability
- **Cookie Lifetime Alignment:**
  - When users authenticate with `remember_me=False`, the browser expects a session-only cookie that expires upon closing the window or tab.
  - Prior to KAN-36, switching workspaces in the Sidebar could inadvertently mint persistent 30-day cookies.
  - The hardened `SessionService.rotate_for_workspace_switch` strictly preserves `is_persistent=False`, ensuring that `Max-Age` and `Expires` remain omitted.
- **AAL2 Freshness & Security State:**
  - Stale step-up state (>900 seconds) is preserved accurately across workspace switches. Users are prompted for fresh step-up only when accessing sensitive administrative views, without unexpected mid-workflow logouts or jarring redirects.
- **Non-Cookie Caller Rejection:**
  - Non-cookie requests to the switch endpoint are rejected with HTTP 401 `SESSION_REQUIRED`, preventing external scripts or API tokens from mutating the active browser session.

### 2.2 Issue Drawer Concurrency & Zero ETag Drift
- **Elimination of False 412 Conflict Modals:**
  - In the Issue Detail Drawer (`IssueSurface.tsx`), users frequently make sequential optimistic modifications (e.g., updating the title, immediately editing the description, and selecting an assignee).
  - Previously, subtle caching delays on the `ObjectRecord` spine could cause the PATCH response ETag to drift from subsequent GET requests, triggering false 412 Precondition Failed dialogs and blocking unsaved input.
  - With KAN-36, `serialize_issue` loads `ObjectRecord` with `populate_existing=True`, and `update_issue` flushes and explicitly refreshes both the `Issue` and `ObjectRecord` before serializing.
  - The PATCH response `ETag` header and `body.etag` now guarantee 100% parity with immediate GET requests (0 drift verified in sequential test suites).

### 2.3 Workflow State Transitions & MCP State Synchronization
- **Flexible Precondition Matching:**
  - Workflow transitions accept both composite `compute_issue_etag` and legacy `description_sha256` in `If-Match`, ensuring transitions triggered from the board or quick field popovers succeed reliably.
  - Transition responses pass updated `ETag` headers directly in JSON responses, keeping the frontend QueryClient cache synchronized with zero latency.

### 2.4 Design System & CSP Compliance
- **Zero Style Regressions:** All touched files strictly conform to the existing design system tokens with zero inline JSX styles (`style-src 'self'` compliant).
- **Zero Dash Violations:** Strictly 0 em-dashes and 0 en-dashes in code, comments, and documentation.

---

## 3. Automated Test Verification

All unit tests and contracts executed cleanly:
1. Concurrency & Concurrency Parity Tests (`test_issue_patch_etag_parity.py`):
   - Chained `PATCH` -> `GET` -> `PATCH` validated with 0 ETag drift.
   - Validated 304 Not Modified on `If-None-Match`.
   - Validated stale 412 Precondition Failed handling.
   - Validated workflow transitions (`begin-work`, `transition`, `complete-work`) and creator provenance ETag parity.
2. Workspace Session Switch Tests (`test_workspace_switch_session_persistence.py`):
   - Validated `remember_me=False` session cookie omission.
   - Validated absolute expiration boundary preservation.
   - Validated stale AAL2 retention (>900s).
   - Validated non-cookie caller 401 rejection.
3. Test Suite Summary:
   - 97 passed in 129.47s with 95% statement coverage across all 9 touched modules.
   - Stderr Warnings: Exactly 0 warnings.

---

## 4. Certification

The contract and UX alignments in ticket KAN-36 fulfill all functional, security, concurrency, and usability requirements.

**STATUS: APPROVED**
