# UI Specialist Gate Review: KANBA-145 (KB-P5-14)

- **Ticket**: `KANBA-145` (`KB-P5-14`: `[Phase 5 / Sandbox + Deploy] Tier B nsjail runner, seccomp-BPF sandbox-profile.json, Unix-socket token-injecting proxy & standalone CLONE_NEWUSER probe`)
- **Reviewer**: `@ui-specialist` (Frontend/UX Architect & UI Specialist Gate)
- **Branch**: `feat/KANBA-145` (`HEAD: f82ae29`)
- **Worktree**: `/tmp/kb-wt-KANBA-145`
- **Scope**: `deploy/standalone/storage_probe.py`, `kanban/sandbox/probe.py`, `kanban/api/middleware/script_depth.py`

---

### 1. Executive Summary & Verification Matrix

A forensic UI/UX contract audit was conducted for `KANBA-145` in `/tmp/kb-wt-KANBA-145`. `KB-P5-14` delivers backend sandboxing infrastructure, standalone probe status extensions, and re-entrancy depth guards. The error responses, problem shapes, and status fields were evaluated against frontend presentation contracts for the custom field configuration screen (`KB-P3-52`), system admin status dashboard (`KB-P5-15`), and spec sections 13.3, 14.1, and 15.5.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Standalone Status Fields** | `tier_b_sandbox_available` & `tier_b_unavailable_reason` | Cleanly exposed on `StandaloneStatus` with `bool` and `str \| None` | PASS |
| **Admin UI Diagnostics** | Human-readable diagnosis of sandbox state | Reason strings provide clear guidance (e.g. missing userns, missing binary) | PASS |
| **RFC 7807 Error Shape** | `SANDBOX_UNAVAILABLE_IN_STANDALONE` problem details | Returns structured JSON with `detail`, `title`, and `status: 503` | PASS |
| **Recursion Error Shape** | `SCRIPT_RECURSION_BLOCKED` problem details | Returns structured JSON with `detail`, `title`, and `status: 409` | PASS |
| **Screenshots Compliance** | N/A - Non-UI Ticket | Confirmed non-UI ticket (sandbox and system middleware layer) | PASS |
| **Typography Compliance** | Plain ASCII hyphens `-` only | Strictly plain ASCII hyphens used throughout code, comments, and reviews | PASS |

---

### 2. Frontend Error & Status Contract Review

1. **System Health & Admin Dashboard Alignment (`KB-P5-15`):**
   - The `StandaloneStatus` model in `deploy/standalone/storage_probe.py` exposes:
     * `tier_b_sandbox_available: bool = False`
     * `tier_b_unavailable_reason: str | None = None`
   - These attributes allow the admin UI status dashboard to render a dedicated status badge (green "Sandboxed" vs amber "Tier B Unavailable") with a tooltipped explanation without requiring arbitrary shell introspection.

2. **Custom Fields Editor & Execution Modal (`KB-P3-52`):**
   - When a user tests or executes a custom script in a standalone deployment where user namespaces are disabled, the endpoint returns:
     ```json
     {
       "title": "Service Unavailable",
       "status": 503,
       "detail": "SANDBOX_UNAVAILABLE_IN_STANDALONE: Standalone deployment host does not support unprivileged user namespaces (CLONE_NEWUSER) for Tier B script sandboxing."
     }
     ```
   - When a script re-entrantly calls back into the API with `X-Kanban-Script-Depth: 1`, the endpoint returns:
     ```json
     {
       "title": "Conflict",
       "status": 409,
       "detail": "SCRIPT_RECURSION_BLOCKED: Script depth limit exceeded for endpoint /api/v1/issues/123/custom-fields/456/execute"
     }
     ```
   - Both RFC 7807 payloads integrate seamlessly into the standard toast notifications and error dialog components in the web frontend.

---

### 3. Screenshots Verification

- Status: N/A - Non-UI Ticket (verified per Ticket Spec: `Screenshots: N/A - Non-UI Ticket`).

---

### 4. Gate Sign-Off

The standalone status and error structures align cleanly with frontend error presentation contracts.

STATUS: APPROVED
Verdict: APPROVED
