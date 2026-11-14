# UI Specialist Gate Review: KANBA-139 (KB-P4-12)

- **Ticket**: `KANBA-139` (`KB-P4-12`: `[Phase 4 / MCP] /mcp/admin tool 12: two-stage destructive_lifecycle (request_delete -> execute_delete with 5m blast-hash token)`)
- **Reviewer**: `@ui-specialist` (UI Designer & UX Architect)
- **Branch**: `feat/KANBA-139`
- **Worktree**: `/tmp/kb-wt-KANBA-139`
- **Scope**:
  - `kanban/api/v1/admin/destructive.py`
  - `kanban/services/destructive_lifecycle.py`
  - `mcp/surfaces/admin/destructive_lifecycle.py`

---

### 1. Executive Summary & Verification Matrix

A comprehensive UI, UX, and human ergonomics audit was performed for `KANBA-139`. Although `KANBA-139` is an administrative REST API and MCP tool implementation without client-side component code modifications, it defines the essential data contracts and preview payloads directly driving:
1. The **Two-Stage Destructive Confirmation Dialog** in the Web UI (`KB-P3-43` & `KB-P3-09b`), rendering the blast radius summary and requiring manual keyboard typing of the exact confirmation phrase.
2. The **MCP Admin Autonomous Tool Ergonomics** (`/mcp/admin` tool 12), ensuring administrative AI agents receive crystal-clear blast radius feedback, single-use token boundaries, and actionable guidance rather than cryptic errors.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Blast Radius Preview (`blast_summary`)** | S7.2 8q human-readable impact description | Emits clear summaries (e.g. "2 sub-issues unparented, 3 inbound links flagged") | PASS |
| **Confirmation Phrase Ergonomics** | S11.4 explicit uppercase phrase matching entity | Enforces uppercase `TRASH|RESTORE|PURGE <KIND> <KEY>` preventing ambiguity | PASS |
| **Fail-Closed Feedback** | S11.4 token burning on caller/phrase mismatch | Returns actionable error details explaining why token was burned | PASS |
| **MCP Summary YAML Projection** | S11.4 Tool 12 structured YAML presentation | Clean `confirmation_required` stage with 5-minute countdown | PASS |
| **Screenshots Compliance** | N/A - Non-UI Ticket | Confirmed non-UI ticket; verified in `contract-sample.json` | PASS |
| **Typography Compliance** | Plain ASCII hyphens `-` only | Strictly plain ASCII hyphens used throughout code, comments, and documentation | PASS |

---

### 2. Human Ergonomics & UX Consumer Contract Analysis

#### A. Human Confirmation Dialog Alignment (KB-P3-43, S7.2 8q)
- The response from `POST /api/v1/admin/destructive:request` delivers:
  - `stage`: `"confirmation_required"`
  - `target`: Human-readable identifier or title (e.g. `"SEC-1"`, `"Architecture Plan"`, `"Platform Core"`)
  - `target_kind`: Entity type indicator (`"issue"`, `"project"`, `"doc"`, `"page"`, `"sticky"`, `"cycle"`, `"module"`, `"view"`)
  - `blast_summary`: Natural language description of cascading effects (e.g. `"2 sub-issues unparented, 0 inbound object_links flagged"`, `"3 child pages, 1 versions to be removed"`, `"5 assigned issues to be unassigned"`)
  - `confirm_phrase`: Literal text string required to be typed verbatim into the confirmation modal (e.g. `"TRASH ISSUE SEC-1"`, `"PURGE PROJECT SEC"`)
  - `expires_in_sec`: Exact remaining seconds (`300`) for the client countdown timer.
- This format provides the Web UI confirmation dialog (`KB-P3-43`) with all data required to render:
  1. A red danger badge indicating the action mode (`TRASH` vs `PERMANENT PURGE`).
  2. An itemized impact list preventing accidental destruction of dependent child records.
  3. A disabled `[Confirm]` button that activates only when the user types the exact matching phrase.

#### B. Autonomous MCP Agent Safety & Ergonomics (S11.4 Tool 12)
- In `/mcp/admin`, `destructive_lifecycle` acts as the definitive safety gate against AI tool hallucination:
  - An LLM cannot execute a destructive action in a single step; attempting `execute_delete` without a token immediately fails with `VALIDATION_FAILED`.
  - When `request_delete` is invoked, the agent receives an unmistakable signal:
    ```yaml
    stage: confirmation_required
    target: SEC-1
    mode: trash
    blast_summary: "2 sub-issues unparented, 0 inbound object_links flagged"
    blast_hash: a4d3f572834b6e51c890...
    confirm_phrase: "TRASH ISSUE SEC-1"
    confirmation_token: kb_del_...
    expires_in_sec: 300
    ```
  - The agent is forced to process the blast radius and submit the exact `confirm_phrase` and `confirmation_token` to Stage 2.
  - If the agent hallucinates or mutates parameters, the token burns immediately, protecting workspace data integrity.

#### C. TOCTOU Protection & Visual Stale State Feedback
- If any concurrent modification alters the target entity between Stage 1 and Stage 2 (such as attaching a new blocker link or sub-issue), Stage 2 rejects the call with HTTP 412 `BLAST_RADIUS_CHANGED`.
- This ensures neither human administrators nor AI agents can approve a deletion based on obsolete blast-radius assumptions.

---

### 3. Screenshots Verification
- Status: N/A - Non-UI Ticket (verified per Ticket Spec: `Screenshots: N/A - Non-UI Ticket`).
- Verified wire exchanges in `contract-sample.json`:
  * `destructive_request_trash_issue_200`: Stage 1 blast preview with confirmation token.
  * `destructive_execute_trash_issue_200`: Stage 2 execution with status `trashed`.
  * `destructive_restore_issue_200`: Restore execution with status `restored`.
  * `destructive_execute_confirm_phrase_mismatch_422`: Phrase mismatch rejection and token burn.
  * `destructive_execute_token_caller_mismatch_403`: Caller mismatch rejection and token burn.
  * `destructive_execute_blast_radius_changed_412`: TOCTOU blast-hash change rejection.
  * `destructive_request_permanent_purge_server_admin_required_403`: Role hierarchy enforcement.

---

### 4. Gate Verdict

The data schemas, preview messages, and confirmation phrases provide exceptional safety, clear human readability, and seamless integration with the Web UI confirmation dialogs.

**Verdict: APPROVED**
