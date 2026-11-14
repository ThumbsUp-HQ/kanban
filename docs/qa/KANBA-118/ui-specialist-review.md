# UI Specialist Gate Review: KANBA-114 (KB-P5-12)

- **Ticket**: `KANBA-114` (`KB-P5-12`: `[Phase 5 / Hardening] Custom field escalation approvals: Scope x Principal matrix, trigger auto-revocation, HMAC signatures & dual-control API`)
- **Reviewer**: `@ui-specialist` (UI & UX Architecture Specialist Gate Auditor)
- **Worktree**: `/tmp/kb-wt-KANBA-114`
- **Branch**: `feat/KANBA-114`
- **Head Commit SHA**: `cb15fe5`
- **Audit Date**: 2026-11-12
- **Applicable Specifications**: Section 13.2 (Scope x Principal Escalation Matrix & Tamper Auto-Revocation), Section 4.2 (AAL2 Step-Up Verification), Section 3.2 (OBO vs Service Principal Credentials), Section 5.4 (Strict Content Security Policy & Safe Data Display)

---

## 1. Executive Summary

As mandated by `AGENTS.md` and Section 13.2, all API and data layer contracts introducing or modifying REST endpoints and privilege escalation flows must undergo UI/UX specialist audit to guarantee client ergonomics, state machine clarity, toast/modal feedback alignment, and secure error recovery for downstream frontend consumers (`KB-P5-15`).

The implementation in `feat/KANBA-114` provides a hardened, machine-readable approval subsystem:
1. REST endpoints emit structured RFC 7807 problem details with discrete error codes (`AAL2_REQUIRED`, `MANIFEST_MISMATCH`, `INSUFFICIENT_APPROVER_TIER`, `DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED`, `SP_WARNING_ACK_REQUIRED`, `ESCALATION_COMBO_INVALID`), enabling frictionless client modal dispatch and toast rendering.
2. The `sp_warning_acknowledged` boolean parameter maps directly to an explicit checkbox in administrative review dialogs to ensure intentional approval of Service Principal execution.
3. The dual-control status lifecycle (`PENDING` -> `PENDING_SECOND_APPROVER` -> `APPROVED`) cleanly informs UI state badges and prevents self-approval confusion by distinctly identifying `primary_approver_id` and `secondary_approver_id`.
4. Tamper auto-revocation (`status: REVOKED`, `revoked_reason: MANIFEST_SHA256_CHANGED`) provides unambiguous status cues for settings dashboards.
5. All text fields (`justification`, `revoked_reason`, `target_scope`, `credential_mode`) serialize as plain string values free of HTML markup or unsafe character entities, strictly upholding Section 5.4 Content Security Policy standards.

---

## 2. Frontend / UX Consumer Ergonomics & State Mapping

1. **AAL2 Step-Up Interaction (`403 AAL2_REQUIRED`)**:
   - When an administrator attempts to approve an escalation request without a recent AAL2 verification (session `aal_level < 2` or verification older than 900 seconds), the API responds with:
     ```json
     {
       "type": "urn:kanban:problem:AAL2_REQUIRED",
       "title": "AAL2 Authentication Required",
       "status": 403,
       "code": "AAL2_REQUIRED",
       "detail": "Approving escalation requires AAL2 authentication",
       "request_id": "..."
     }
     ```
   - **UI Consumption Pattern**: Downstream frontend components in `KB-P5-15` can intercept `AAL2_REQUIRED` via standard query interceptors to trigger the WebAuthn / Passkey / TOTP modal inline, preserving the user's form context and enabling seamless re-try without full-page reloads.

2. **Service Principal Elevated Warning (`sp_warning_acknowledged`)**:
   - Escalating credentials to `PROJECT_ADMIN_SP` or `SERVER_ADMIN_SP` introduces elevated execution risks.
   - The API mandates `sp_warning_acknowledged: true` (returning `422 SP_WARNING_ACK_REQUIRED` when false).
   - **UI Consumption Pattern**: The review modal can render a prominent warning banner with an un-checked acknowledgment checkbox:
     `"I acknowledge that this custom script will execute with elevated Service Principal authority"`.
     The `Approve` button remains disabled until the acknowledgment is checked.

3. **Dual-Control Status Progression (`SERVER_ADMIN_DUAL`)**:
   - For `SERVER` scope escalations, two distinct Server Administrators must approve:
     * Initial approval: transitions status from `PENDING` to `PENDING_SECOND_APPROVER`.
     * Second approval: transitions status from `PENDING_SECOND_APPROVER` to `APPROVED`.
     * Attempted self-second-approval: returns `409 DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED`.
   - **UI Consumption Pattern**: 
     * In the administration table, items in `PENDING_SECOND_APPROVER` display an amber badge: `⏳ Awaiting 2nd Server Admin`.
     * When viewed by the `primary_approver_id`, the approval action is disabled with tooltip guidance: `"Self-approval prohibited. A different Server Administrator must confirm this escalation."`
     * When viewed by an eligible distinct Server Administrator, the second-approval action is enabled.

4. **TOCTOU Protection & Concurrency (`409 MANIFEST_MISMATCH`)**:
   - Both request creation and approval submission require the exact 64-character hexadecimal `manifest_sha256`.
   - If an admin is reviewing a script and the definition is updated in the background, submitting the stale manifest returns `409 MANIFEST_MISMATCH`.
   - **UI Consumption Pattern**: The client can capture `409 MANIFEST_MISMATCH`, display a notification banner (`"The script source has been modified since this request was opened. Please review the updated script manifest."`), and re-fetch the latest definition diff.

5. **Tamper Auto-Revocation State Cue**:
   - Whenever an approved script's source or metadata changes, the database trigger immediately revokes prior approvals: `status = 'REVOKED'`, `revoked_reason = 'MANIFEST_SHA256_CHANGED'`.
   - **UI Consumption Pattern**: The custom fields inspector displays a red pill (`🛑 Revoked: Script modified`) and a prompt to submit a fresh approval request with updated justification.

---

## 3. Data Integrity & Security Invariants (S5.4)

1. **Zero Raw HTML Injection**:
   - `justification` is bounded between 10 and 2000 characters and contains plain text only.
   - All response properties serialize as discrete JSON primitives and render as safe React text nodes in client components.
2. **Timing Equalization**:
   - Authentication, tier evaluation, and approval routes enforce a 25.0ms timing floor to prevent timing side-channel analysis of privilege tiers or approval validity.
3. **Anti-Enumeration & Privacy**:
   - Approval queries require administrative privileges (`PROJECT_ADMIN`, `WORKSPACE_ADMIN`, or `SERVER_ADMIN`). Unauthorized members receive 403 or 404 responses with zero principal or permission metadata leakage.

---

## 4. Audit Verdict

The REST endpoints, error problem details, state machine lifecycles, and verification contracts in `KANBA-114` (`KB-P5-12`) provide robust ergonomics and state safety for downstream frontend integration.

Verdict: APPROVED
