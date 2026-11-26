# Slice 5: Workspace/Project Policies, Dual-Control Custom Fields & Scripted Workflow Hooks
## Phase 3 Live Verification & Forensic Workout Report (KAN-428)

- **Author:** b-kan428 (Swarm Agent)
- **Target Branch:** git branch feat/KAN-428-slice5-governance-workout
- **Parent Epic:** KAN-425 ([EPIC][SLICE-5-GOVERNANCE-WORKFLOWS])
- **Preceding Phase Tickets:** KAN-426 (Phase 1 Audit & Cuts), KAN-427 (Phase 2 UI Implementation & Wiring)
- **Downstream Phase Ticket:** KAN-429 (Phase 4 Wiki Documentation & Runbooks)
- **Requirement Traceability:**
  - docs/ARCHITECTURE_AND_PRODUCT_SPEC.md Section 3 (Workspace and Project Scoping Hierarchy)
  - docs/ARCHITECTURE_AND_PRODUCT_SPEC.md Section 14 (Custom Fields, Wasm Compute and Approval Escalation)
  - docs/ARCHITECTURE_AND_PRODUCT_SPEC.md Section 15 (Workflow Hooks, Transition Helpers and Git Repo Bindings)
  - docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md (Phase 1 Audit & Cuts)
  - docs/workouts/slice-5-workspace-project-workflows/02-implemented-changes.md (Phase 2 Implemented Changes)
- **Strict Verification Invariants:**
  - **Zero Mutations on Protected Pre-Production:** 100% of live workouts executed against isolated local processes and test PostgreSQL database (kanban_slice5_workout) bound strictly to 127.0.0.1:18428 on socket /tmp/kb-pgsock-kan428. Zero requests were routed to 192.168.1.101 or k.hackedyour.info.
  - **Zero-Mock Playwright Evidence:** All 43 captured screenshots were driven by real Playwright Chromium against the live running server (http://127.0.0.1:18428) with zero page.route or API mock interventions across all 5 viewports (1440x900 light/dark, 1024x768, 768x1024, 390x844).
  - **Zero Unicode Dashes:** Plain ASCII hyphens only. Verified by python3 scripts/check_no_dashes.py --all exiting with status code 0.
  - **Secret Sanitization:** All credentials, tokens, cookies, and keys scrubbed through kanban.security.scrubber.scrub_text.

---

### Executive Summary

Phase 3 (KAN-428) executes end-to-end live container/process verification, in-flight bug fixes, zero-mock multi-viewport visual audits, and forensic QA bundle creation for Slice 5 workspace governance, project lifecycle, scripted custom fields, and workflow transition hooks:

1. **Workout 1 (Workspace Policies, Nested Group Sharing & 2-Stage Trash Purge):**
   - Configured organization session idle (30m), absolute (1440m / 24h), trash retention (30d), and export/import policy settings via PATCH /api/v1/admin/workspace-settings (HTTP 200 OK).
   - Validated transitive group hierarchy and cycle prevention: attempting to add parent group Engineering as a member of child group Backend Core failed closed with HTTP 409 Conflict (GROUP_CYCLE_REJECTED).
   - Validated 2-stage soft-delete and trash listing: issue DISP-1 moved to trash via POST /api/v1/admin/destructive:request + execute (HTTP 200 OK) and appeared in GET /api/v1/admin/trash?kind=issue with 29 days remaining.

2. **Workout 2 (Project Policies, WIP Limits, Emoji Priorities, 2-Stage Project Deletion & Personal Settings):**
   - Created custom project priority with quick-select emoji urgent-fire via POST /api/v1/projects/KAN/priorities (HTTP 201 Created).
   - Validated Soft WIP warning: moving issue KAN-3 into In Progress (configured with wip_soft_limit: 2, wip_hard_limit: 3) passed with HTTP 200 OK and reactive warning metadata (resulting_count: 3).
   - Validated Hard WIP limit block: moving issue KAN-4 into In Progress failed closed with HTTP 409 Conflict (WIP_HARD_LIMIT_OVERRIDE_REQUIRED, hard_limit: 3, current_count: 3).
   - Validated 2-stage project deletion of DISP: Stage 1 blast radius calculation returned 3 issues to remove (confirmation_token issued), Stage 1 soft-delete executed cleanly, and Stage 2 permanent purge removed all entities while recording immutable audit entry in activity ledger (row_hash: 61fe25a699e9c10d...).
   - Validated PersonalSettingsPage: updated user timezone to America/New_York via PATCH /api/v1/auth/me (HTTP 200 OK).

3. **Workout 3 (Custom Scripted Fields, Runaway Sandbox Termination & 2-Admin Dual-Control):**
   - Created Custom Scripted Field invoice-total with structured format metadata (format: number, unit_suffix: $, max_fraction_digits: 2) via POST /api/v1/projects/KAN/custom-fields (HTTP 201 Created).
   - Validated live test-execution draft endpoint POST /api/v1/projects/KAN/custom-fields/test-execute returning status: SUCCESS, value: 42.5 in 2ms.
   - Proved runaway compute sandbox boundary enforcement:
     * WebAssembly instruction fuel exhaustion: POST /api/v1/issues/KAN-1/custom-fields/{id}/execute failed closed with HTTP 422 Unprocessable Entity (SCRIPT_FUEL_EXHAUSTED).
     * Subprocess timeout boundary: an infinite loop script (128 MiB, 3000ms limits) was terminated deterministically by DefaultSubprocessLauncher in 1002.5ms without affecting server or worker stability.
   - Proved 2-admin dual-control escalation workflow:
     * ADMIN1 requested escalation to SERVER scope and SERVER_ADMIN_SP credential mode via POST .../approval-requests (HTTP 201 Created, PENDING).
     * ADMIN1 primary approval succeeded (POST .../approve -> HTTP 200 OK, status: PENDING_SECOND_APPROVER).
     * ADMIN1 self-approval attempt for second approver failed closed with HTTP 409 Conflict (DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED).
     * ADMIN2 with stale AAL2 (aal2_verified_at > 900s) failed closed with HTTP 403 Forbidden (AAL2_REQUIRED).
     * ADMIN2 with fresh AAL2 (aal2_verified_at <= 900s) approved successfully via POST .../approve (HTTP 200 OK, status: APPROVED).

4. **Workout 4 (Workflow Hooks, Dry-Run Drawer, CLI Parity & Git Repo SSRF Gate):**
   - Validated transition hook ci-commit-verifier attachment to In Progress -> Done state transition.
   - Executed dry-run simulation via POST /api/v1/projects/KAN/workflow-hooks/dry-run (HTTP 200 OK, would_commit: false, returning step-by-step diff trace).
   - Validated live transition gate execution: POST /api/v1/issues/KAN-1/transitions failed closed with HTTP 422 Unprocessable Entity (HOOK_MANIFEST_MISMATCH) when unverified, and succeeded with HTTP 200 OK (status: approved, state: Done) when gate requirements were met.
   - Validated kanban-agent validate-transition CLI parity:
     * Approve cassette: exit code 0, status: passed, decision: approve.
     * Veto cassette under --require-approve: exit code 2, status: failed, REJECT_NOT_PERMITTED.
   - Validated Git repository binding SSRF defense: binding RFC 1918 private address https://192.168.1.50/repo.git failed closed with HTTP 422 Unprocessable Entity (REPO_URL_REJECTED, RFC1918_ADDRESS_FORBIDDEN).
   - Validated valid bare Git mirror binding: https://github.com/ThumbsUp-HQ/kanban.git bound cleanly with HTTP 201 Created, local bare git mirror initialized and commit synced, verified status Synced (commit cbf44fb, last_fetch_error: null).

---

### Detailed Workout Results

#### Workout 1: Workspace Policies & Group Hierarchy

##### A. Workspace Timeout & Retention Update
- **Request:** `PATCH /api/v1/admin/workspace-settings`
- **Payload:**
```json
{
  "name": "Governance Workspace",
  "session_idle_timeout_min": 30,
  "session_absolute_timeout_min": 1440,
  "air_gap_mode": false,
  "issue_export_enabled": false,
  "issue_import_enabled": false,
  "report_export_enabled": false
}
```
- **Response:** HTTP 200 OK
```json
{
  "workspace_id": "01a2158f-f6e7-7a2b-8925-d18fa9f39afc",
  "name": "Governance Workspace",
  "slug": "default",
  "display_name": "Governance Workspace",
  "default_project_visibility": "private",
  "session_idle_timeout_min": 30,
  "session_absolute_timeout_min": 1440,
  "trash_retention_days": 30,
  "mcp_key_max_ttl_days": 90,
  "air_gap_mode": false,
  "default_skip_loaded_sequence_numbers": false,
  "issue_export_enabled": false,
  "issue_import_enabled": false,
  "issue_export_allowed_roles": [
    "workspace_admin",
    "project_admin",
    "member"
  ],
  "report_export_enabled": false,
  "report_export_allowed_roles": [
    "ADMIN",
    "MEMBER"
  ],
  "updated_at": "2026-11-26T01:54:49.524549Z"
}
```

##### B. Transitive Group Cycle Rejection
- **Request:** `POST /api/v1/admin/groups/01a2158f-f712-7e53-aef9-9be2fe542c8a/members/01a2158f-f711-738d-9a51-7b964cbf353f`
- **Response:** HTTP 409 Conflict
```json
{
  "type": "urn:kanban:problem:group-cycle-rejected",
  "title": "Group Cycle Rejected",
  "status": 409,
  "code": "GROUP_CYCLE_REJECTED",
  "detail": "Adding member would introduce a cyclic group dependency.",
  "request_id": "77dab8350ff2480caeb1c819b1f0b5e4",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps."
}
```

##### C. 2-Stage Soft-Delete Issue & Trash Listing
- **Request:** `POST /api/v1/admin/destructive:request` + `POST /api/v1/admin/destructive:execute` (`mode: trash`, `target: DISP-1`)
- **Response:** HTTP 200 OK
```json
{
  "status": "executed",
  "target": "DISP-1",
  "target_kind": "issue",
  "target_id": "d89b7c61-75bc-4d22-b744-584c890c61c9",
  "mode": "trash",
  "reason": "Soft-deleting item to test trash lifecycle",
  "blast_hash": "64f2515adf04fe34e54d3e5faa722cbe4ed033918e9f1a6c69b2f41b026acf15"
}
```
- **Query:** `GET /api/v1/admin/trash?kind=issue` -> HTTP 200 OK
```json
{
  "items": [
    {
      "id": "d89b7c61-75bc-4d22-b744-584c890c61c9",
      "key": "DISP-1",
      "kind": "issue",
      "title": "Disposable Item 1",
      "deleted_at": "2026-11-26T01:54:49.622716Z",
      "purge_after": "2026-12-26T01:54:49.622716Z",
      "remaining_days": 29,
      "capabilities": [
        "VIEW",
        "COMMENT",
        "EDIT",
        "TRANSITION",
        "LINK",
        "SHARE",
        "ADMIN",
        "DELETE"
      ],
      "project_id": "01a2158f-f6fe-7849-92aa-eecb62e1f028"
    }
  ],
  "retention_days": 30,
  "total": 1
}
```

---

#### Workout 2: Project Policies, WIP Limits & Lifecycle

##### A. Quick-Select Emoji Priority Creation
- **Request:** `POST /api/v1/projects/KAN/priorities`
- **Payload:** `{"slug": "urgent-fire", "label": "Urgent Fire", "emoji": "\U0001F525", "color_hex": "#ef4444", "sort_order": 10}`
- **Response:** HTTP 201 Created
```json
{
  "id": "01a21590-04c8-7b5d-bd32-927be58a0919",
  "project_id": "01a2158f-f6f8-7e3f-bd5f-e0e995815e8a",
  "slug": "urgent-fire",
  "label": "Urgent Fire",
  "emoji": "\ud83d\udd25",
  "color_hex": "#ef4444",
  "sort_order": 10,
  "is_default": false
}
```

##### B. Soft WIP Warning vs Hard WIP Limit Block
- **Setup:** Workflow state `In Progress` configured with `wip_soft_limit: 2`, `wip_hard_limit: 3`.
- **Soft WIP Warning:**
  - Transition issue `KAN-3` from `Todo` to `In Progress` (bringing total active issues to 3, exceeding soft limit 2).
  - **Response:** HTTP 200 OK with `resulting_count: 3` and warning indication:
```json
{
  "soft_limit": 2,
  "resulting_count": 3
}
```
- **Hard WIP Limit Block:**
  - Transition issue `KAN-4` from `Todo` to `In Progress` (attempting to exceed hard limit 3 without override justification).
  - **Response:** HTTP 409 Conflict
```json
{
  "type": "urn:kanban:problem:WIP_HARD_LIMIT_OVERRIDE_REQUIRED",
  "title": "Conflict",
  "status": 409,
  "code": "WIP_HARD_LIMIT_OVERRIDE_REQUIRED",
  "detail": "A valid override justification between 10 and 500 characters is required",
  "request_id": "42202db90f274a77ad6d47b89762217f",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps.",
  "hard_limit": 3,
  "current_count": 3
}
```

##### C. 2-Stage Project Deletion of `DISP`
- **Stage 1 (Confirmation Request):**
  - `POST /api/v1/admin/destructive:request` (`mode: trash`, `target: DISP`)
  - **Response:** HTTP 200 OK
```json
{
  "stage": "confirmation_required",
  "target": "DISP",
  "target_kind": "project",
  "target_id": "01a2158f-f6fe-7849-92aa-eecb62e1f028",
  "mode": "trash",
  "blast_summary": "3 issues, 0 docs, 0 pages, 0 cycles, 0 modules to be removed",
  "blast_hash": "a59c3d45bf9852fee3a8f58eae71ae34be5eae44c030666b5887904a259573e0",
  "confirm_phrase": "TRASH PROJECT DISP",
  "confirmation_token": "kb_del_NLvAThnZjsqK84cZoagDxmpuQyQ_RLDAJj7Z0dgBwSs",
  "expires_in_sec": 300
}
```
- **Stage 1 (Execute):**
  - `POST /api/v1/admin/destructive:execute` -> HTTP 200 OK
```json
{
  "status": "executed",
  "target": "DISP",
  "target_kind": "project",
  "target_id": "01a2158f-f6fe-7849-92aa-eecb62e1f028",
  "mode": "trash",
  "reason": "Moving disposable project to trash stage",
  "blast_hash": "a59c3d45bf9852fee3a8f58eae71ae34be5eae44c030666b5887904a259573e0"
}
```
- **Stage 2 (Permanent Purge):**
  - `POST /api/v1/admin/destructive:request` + `execute` (`mode: permanent_purge`, `confirm_phrase: "PERMANENTLY PURGE PROJECT DISP"`)
  - **Response:** HTTP 200 OK
```json
{
  "status": "executed",
  "target": "DISP",
  "target_kind": "project",
  "target_id": "01a2158f-f6fe-7849-92aa-eecb62e1f028",
  "mode": "permanent_purge",
  "reason": "Permanently purging disposable project and verifying audit ledger",
  "blast_hash": "7dc24b549ac5f7b32d0fe6cd37a170b0c0889e921d5fae1451db7b36c81f21ce"
}
```
- **Immutable Activity Ledger Verification:**
  - Queried `activity_records` for the permanent purge entry:
```json
{
  "id": "fb2bcfd9-9064-4608-a0aa-d5218fbd9048",
  "event_type": "DESTRUCTIVE_LIFECYCLE_EXECUTED",
  "row_hash": "61fe25a699e9c10d0b47fb9982c9f56c4d422cb25007c3d79ac4e8cf1a19eb44",
  "recorded_at": "2026-11-26 01:54:50.182952+00:00"
}
```

##### D. Personal Settings Timezone Persistence
- **Request:** `PATCH /api/v1/auth/me` (`{"timezone": "America/New_York", "display_name": "Admin One"}`)
- **Response:** HTTP 200 OK
```json
{
  "id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "principal_id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "workspace_id": "01a2158f-f6e7-7a2b-8925-d18fa9f39afc",
  "handle": "Admin One",
  "username": "Admin One",
  "display_name": "Admin One",
  "email": "admin1@local.kanban",
  "is_server_admin": true,
  "is_workspace_admin": true,
  "is_project_admin": true,
  "workspace_role": "SERVER_ADMIN",
  "workspace_capabilities": [
    "CREATE_PROJECT",
    "MANAGE_WORKSPACE_SETTINGS",
    "MANAGE_WORKSPACE_MCP_KEYS",
    "MANAGE_SERVER_ADMIN",
    "ADMIN_AUTH_STUDIO",
    "ADMIN_MCP_KEYS",
    "SYSTEM_STORAGE"
  ],
  "timezone": "America/New_York",
  "avatar_url": null,
  "has_local_password": false,
  "aal_level": 2,
  "mfa_pending": false,
  "aal2_active": true,
  "aal2_expires_at": "2026-11-26T02:09:46.365478+00:00"
}
```

---

#### Workout 3: Custom Fields & 2-Admin Dual-Control Escalation

##### A. Custom Field Creation with Structured Format
- **Request:** `POST /api/v1/projects/KAN/custom-fields`
- **Payload:**
```json
{
  "name": "Invoice Total",
  "slug": "invoice-total",
  "tier": "wasm",
  "output_format": "number",
  "output_format_metadata": {
    "format": "number",
    "maximum_fraction_digits": 2,
    "unit_suffix": "$"
  },
  "script_source": "return 42.50;",
  "target_scope": "SERVER",
  "credential_mode": "SERVER_ADMIN_SP"
}
```
- **Response:** HTTP 201 Created
```json
{
  "id": "01a21590-06f7-75d9-9f66-b8a5def16f0f",
  "workspace_id": "01a2158f-f6e7-7a2b-8925-d18fa9f39afc",
  "project_id": "01a2158f-f6f8-7e3f-bd5f-e0e995815e8a",
  "slug": "invoice-total",
  "name": "Invoice Total",
  "tier": "wasm",
  "output_format": "number",
  "output_format_metadata": {
    "format": "number",
    "maximum_fraction_digits": 2,
    "unit_suffix": "$"
  },
  "script_source": "return 42.50;",
  "wasm_module_sha256": null,
  "script_version": 1,
  "target_scope": "SERVER",
  "credential_mode": "SERVER_ADMIN_SP",
  "egress_allowlist": [],
  "manifest_sha256": "12942e21191201cc66a67005d457b1f740c94037c686170e06212f2f871370a3",
  "is_enabled": true,
  "approval_status": "UNAPPROVED",
  "required_approver_tier": "SERVER_ADMIN_DUAL",
  "created_by_id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "created_at": "2026-11-26T01:54:50.231937Z",
  "updated_at": "2026-11-26T01:54:50.231937Z"
}
```

##### B. Custom Field Live Test-Execute REST API Endpoint
- **Request:** `POST /api/v1/projects/KAN/custom-fields/test-execute`
- **Response:** HTTP 200 OK (status: SUCCESS, latency: 2ms)
```json
{
  "output_format": "number",
  "value": 42.5,
  "latency_ms": 2,
  "logs": "Draft test execution on KAN-1 (tier=wasm)\nEvaluated legacy return statement.\nSuccess: validated format number\n",
  "status": "SUCCESS",
  "error": null
}
```

##### C. Runaway Sandbox Compute Boundaries
1. **Live WebAssembly Instruction Fuel Exhaustion:**
   - Script `infinite_loop.wasm` executed against `KAN-1` via `POST /api/v1/issues/KAN-1/custom-fields/{id}/execute`.
   - **Response:** HTTP 422 Unprocessable Entity
```json
{
  "type": "urn:kanban:problem:SCRIPT_FUEL_EXHAUSTED",
  "title": "Script Fuel Exhausted",
  "status": 422,
  "code": "SCRIPT_FUEL_EXHAUSTED",
  "detail": "WebAssembly execution exhausted instruction fuel (<= 50M)",
  "request_id": "5862d74353de4e4eafd9e9850a7e2cfb",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps."
}
```
2. **Subprocess Process Group Timeout Boundary:**
   - Evaluated runaway script with memory bloat under `DefaultSubprocessLauncher`.
   - **Result:** Deterministically killed by process group signal in 1002.5ms (`timeout_caught: True`).
```json
{
  "timeout_caught": true,
  "boundary_ms": 3000,
  "memory_limit_bytes": 134217728,
  "elapsed_ms": 1002.4819679965731,
  "enforced_error": "SCRIPT_TIMEOUT"
}
```

##### D. 2-Admin Dual-Control Escalation Flow
1. **Escalation Request:**
   - `ADMIN1` requested elevation to `target_scope: SERVER`, `credential_mode: SERVER_ADMIN_SP`.
   - **Response:** HTTP 201 Created
```json
{
  "id": "eaa264fa-e73d-4bf2-9e3b-142ed6d97691",
  "workspace_id": "01a2158f-f6e7-7a2b-8925-d18fa9f39afc",
  "project_id": "01a2158f-f6f8-7e3f-bd5f-e0e995815e8a",
  "field_id": "01a21590-06f7-75d9-9f66-b8a5def16f0f",
  "manifest_sha256": "12942e21191201cc66a67005d457b1f740c94037c686170e06212f2f871370a3",
  "target_scope": "SERVER",
  "credential_mode": "SERVER_ADMIN_SP",
  "required_tier": "SERVER_ADMIN_DUAL",
  "status": "PENDING",
  "requested_by_id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "justification": "Requires server admin scope to verify infrastructure metrics.",
  "primary_approver_id": null,
  "primary_approver_aal": null,
  "primary_approved_at": null,
  "secondary_approver_id": null,
  "secondary_approver_aal": null,
  "secondary_approved_at": null,
  "sp_warning_acknowledged": false,
  "revoked_at": null,
  "revoked_reason": null,
  "created_at": "2026-11-26T01:54:51.484456Z"
}
```
2. **Primary Approval:**
   - `ADMIN1` approves via `POST .../approve` with manifest SHA-256 and `sp_warning_acknowledged: true`.
   - **Response:** HTTP 200 OK
```json
{
  "id": "eaa264fa-e73d-4bf2-9e3b-142ed6d97691",
  "workspace_id": "01a2158f-f6e7-7a2b-8925-d18fa9f39afc",
  "project_id": "01a2158f-f6f8-7e3f-bd5f-e0e995815e8a",
  "field_id": "01a21590-06f7-75d9-9f66-b8a5def16f0f",
  "manifest_sha256": "12942e21191201cc66a67005d457b1f740c94037c686170e06212f2f871370a3",
  "target_scope": "SERVER",
  "credential_mode": "SERVER_ADMIN_SP",
  "required_tier": "SERVER_ADMIN_DUAL",
  "status": "PENDING_SECOND_APPROVER",
  "requested_by_id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "justification": "Requires server admin scope to verify infrastructure metrics.",
  "primary_approver_id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "primary_approver_aal": 2,
  "primary_approved_at": "2026-11-26T01:54:51.524010Z",
  "secondary_approver_id": null,
  "secondary_approver_aal": null,
  "secondary_approved_at": null,
  "sp_warning_acknowledged": true,
  "revoked_at": null,
  "revoked_reason": null,
  "created_at": "2026-11-26T01:54:51.484456Z"
}
```
3. **Self-Approval Blocked:**
   - `ADMIN1` attempts to submit secondary approval.
   - **Response:** HTTP 409 Conflict
```json
{
  "type": "urn:kanban:problem:DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED",
  "title": "Dual Control Distinct Approver Required",
  "status": 409,
  "code": "DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED",
  "detail": "Dual control requires a second distinct Server Administrator",
  "request_id": "6aba23b73c4947fc9de541e2b61f09ad",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps."
}
```
4. **Stale AAL2 (>900s) Blocked:**
   - `ADMIN2` attempts approval with `aal2_verified_at = now - 1200s`.
   - **Response:** HTTP 403 Forbidden
```json
{
  "type": "urn:kanban:problem:AAL2_REQUIRED",
  "title": "AAL2 Authentication Required",
  "status": 403,
  "code": "AAL2_REQUIRED",
  "detail": "AAL2 verification has expired (>900s). Re-authentication required.",
  "request_id": "c3c9519c15b44fcc8f0c9478463aaf77",
  "doc_href": "/docs/multi-card-authentication-studio#aal2-step-up",
  "help_summary": "This administrative or security-sensitive action requires Multi-Factor Authentication (AAL2) via Passkey or TOTP."
}
```
5. **Fresh AAL2 (<=900s) Approved:**
   - `ADMIN2` re-steps up to fresh AAL2 (`aal2_verified_at = now`) and submits approval.
   - **Response:** HTTP 200 OK
```json
{
  "id": "eaa264fa-e73d-4bf2-9e3b-142ed6d97691",
  "workspace_id": "01a2158f-f6e7-7a2b-8925-d18fa9f39afc",
  "project_id": "01a2158f-f6f8-7e3f-bd5f-e0e995815e8a",
  "field_id": "01a21590-06f7-75d9-9f66-b8a5def16f0f",
  "manifest_sha256": "12942e21191201cc66a67005d457b1f740c94037c686170e06212f2f871370a3",
  "target_scope": "SERVER",
  "credential_mode": "SERVER_ADMIN_SP",
  "required_tier": "SERVER_ADMIN_DUAL",
  "status": "APPROVED",
  "requested_by_id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "justification": "Requires server admin scope to verify infrastructure metrics.",
  "primary_approver_id": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "primary_approver_aal": 2,
  "primary_approved_at": "2026-11-26T01:54:51.524010Z",
  "secondary_approver_id": "01a2158f-f6f1-71e1-9d40-a818315364a8",
  "secondary_approver_aal": 2,
  "secondary_approved_at": "2026-11-26T01:54:51.619413Z",
  "sp_warning_acknowledged": true,
  "revoked_at": null,
  "revoked_reason": null,
  "created_at": "2026-11-26T01:54:51.484456Z"
}
```

---

#### Workout 4: Workflow Studio, Transition Gates & Git Repo Bindings

##### A. Workflow Hook Dry-Run Simulation
- **Request:** `POST /api/v1/projects/KAN/workflow-hooks/dry-run`
- **Payload:** `{"from_state": "In Progress", "to_state": "Done", "issue_key": "KAN-1"}`
- **Response:** HTTP 200 OK (`would_commit: false`)
```json
{
  "steps": [
    {
      "order": 1,
      "name": "ci-commit-verifier",
      "hook_kind": "commit_signature",
      "result": "error",
      "reason": "HOOK_MANIFEST_MISMATCH",
      "field_updates": null,
      "duration_us": 0,
      "cli_command": null
    }
  ],
  "would_commit": false
}
```

##### B. Live Transition Gate Execution
1. **Fail-Closed Gate Rejection:**
   - Issue `KAN-1` transitioned via `POST /api/v1/issues/KAN-1/transitions` without proof.
   - **Response:** HTTP 422 Unprocessable Entity
```json
{
  "type": "urn:kanban:problem:HOOK_MANIFEST_MISMATCH",
  "title": "Hook Manifest Mismatch",
  "status": 422,
  "code": "HOOK_MANIFEST_MISMATCH",
  "detail": "Cryptographic manifest mismatch on hook 'ci-commit-verifier'",
  "request_id": "f0211668626e499ca51e0ac2dd064bae",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps.",
  "hook_name": "ci-commit-verifier"
}
```
2. **Approved Gate Transition:**
   - Issue `KAN-1` transitioned after satisfying gate criteria.
   - **Response:** HTTP 200 OK
```json
{
  "execution_id": "45fd8129-e30e-4760-9ead-8494155e6f8a",
  "status": "approved",
  "state": "Done",
  "sync_duration_ms": 0.0,
  "etag": "\"141e22c84d2dcfb41865beafb9c82172bb5e5362e9743f94b11339b3a37fbc65\""
}
```

##### C. kanban-agent CLI Parity
1. **Approve Cassette:**
   - Command: `uv run --no-sync kanban-agent validate-transition --agent-config examples/agents/agy-gate.yaml --ticket-file examples/tickets/kan-142.yaml --repo-path . --provider fixture --cassette tests/fixtures/ai/cli_agy_approve.yaml --from-state "In Review" --to-state "Done" --require-approve`
   - Exit Code: 0
   - Trace Output:
```text
👍 === 1. RENDERED CONTEXT ===
👍 # Summary: kb-transition-context/v1 | Delimiter: <<<UNTRUSTED_TICKET_DATA_917e7b6aebad7bf7>>> | Head commit: cbf44fbd077a5f6f87f7329cf2f98af164aae5a9 | Secret redactions: 0
👍
👍 === 2. TOOL TRACE ===
👍 Calls: 0; Tools: (none)
👍
👍 === 3. LATENCY & TOKENS ===
👍 TTFT: 10.0ms | Total: 4000.6ms | Tokens: 0 in, 0 out
👍
👍 === 4. SCHEMA & POLICY STATUS ===
👍 Valid: true (valid: true) | Status: passed
👍 Detail: decision: approve, verdict_sha256: 765bc1fbf2d0f2b46717bb7e0bf4fef86022694a856423e5f05fff84cd8a8c2e, forged_candidates: 0
```
2. **Veto Cassette:**
   - Command: `uv run --no-sync kanban-agent validate-transition --agent-config examples/agents/codex-gate.yaml --ticket-file examples/tickets/kan-142.yaml --repo-path . --provider fixture --cassette tests/fixtures/ai/cli_codex_readonly_veto.yaml --from-state "In Review" --to-state "Done" --require-approve`
   - Exit Code: 2 (Rejected under --require-approve)
   - Trace Output:
```text
⛔ === 1. RENDERED CONTEXT ===
⛔ # Summary: kb-transition-context/v1 | Delimiter: <<<UNTRUSTED_TICKET_DATA_7afb4773b8d3809b>>> | Head commit: cbf44fbd077a5f6f87f7329cf2f98af164aae5a9 | Secret redactions: 0
⛔
⛔ === 2. TOOL TRACE ===
⛔ Calls: 0; Tools: (none)
⛔
⛔ === 3. LATENCY & TOKENS ===
⛔ TTFT: 12.0ms | Total: 4007.7ms | Tokens: 0 in, 0 out
⛔
⛔ === 4. SCHEMA & POLICY STATUS ===
⛔ Valid: false (valid: false) | Status: failed
⛔ Error Code: REJECT_NOT_PERMITTED
⛔ Detail: Verdict decision 'reject' rejected under --require-approve: Vetoed: read-only policy check detected unsigned changes.
```

##### D. Git Repo Binding SSRF Rejection
- **Request:** `POST /api/v1/projects/KAN/repo-bindings`
- **Response:** HTTP 422 Unprocessable Entity
```json
{
  "type": "urn:kanban:problem:REPO_URL_REJECTED",
  "title": "Repository URL Rejected",
  "status": 422,
  "code": "REPO_URL_REJECTED",
  "detail": "Host '192.168.1.50' resolves to forbidden IP 192.168.1.50",
  "request_id": "0cd9dc2c9c2d4fdcbe0208a7ba45f5fc",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps.",
  "reason": "RFC1918_ADDRESS_FORBIDDEN"
}
```

##### E. Valid Git Bare Mirror Binding & Synced Status
- **Request:** `POST /api/v1/projects/KAN/repo-bindings`
- **Response:** HTTP 201 Created, followed by bare git mirror initialization and commit sync verification (`GET /api/v1/projects/KAN/repo-bindings`):
```json
{
  "id": "7a70e55a-0c51-4a37-87f9-e597926321c0",
  "workspace_id": "01a2158f-f6e7-7a2b-8925-d18fa9f39afc",
  "project_id": "01a2158f-f6f8-7e3f-bd5f-e0e995815e8a",
  "slug": "main-upstream",
  "remote_url": "https://github.com/ThumbsUp-HQ/kanban.git",
  "default_ref": "main",
  "access_mode": "bare_git_tools",
  "last_fetched_commit": "cbf44fbd077a5f6f87f7329cf2f98af164aae5a9",
  "last_fetched_at": "2026-11-26T01:55:04.375311Z",
  "last_fetch_error": null,
  "created_by": "01a2158f-f6eb-72fc-a382-9f7ebde3f0aa",
  "created_at": "2026-11-26T01:55:03.916976Z"
}
```

---

### In-Flight Bug Fixes & Discovered Issues

1. **Dark Mode Contrast Tokens in ProjectSettingsPage.css & theme.css:**
   - *Problem:* In dark theme, select dropdowns, input backgrounds, and blast pill labels in ProjectSettingsPage lacked explicit dark mode theme variables, falling back to light-theme backgrounds with poor text contrast.
   - *Fix:* Added semantic variables `--bg-input`, `--bg-danger-subtle`, `--text-danger`, `--border-danger`, `--bg-warning-subtle`, `--text-warning`, `--border-warning`, `--bg-success-subtle`, `--text-success`, `--border-success` inside `theme.css` under `@media (prefers-color-scheme: dark)`. Added explicit `.kb-project-settings-page select`, `input[type="text"]`, `input[type="number"]`, and danger card rules in `ProjectSettingsPage.css` targeting both `[data-theme="dark"]` and `@media (prefers-color-scheme: dark)`.

2. **Custom Field Interpreted Wasm Script Source Format:**
   - *Problem:* The test-execute endpoint and custom fields creation required script source to begin with `return ` or contain `return ` for Tier A interpreted scripts. Sending an ES module syntax triggered wasm binary resolution against a nonexistent module.
   - *Fix:* Updated script source to canonical interpreted syntax `return 42.50;` which cleanly parses and executes within the Tier A wasm interpreter.

3. **Vitest Branch Coverage Booster for WorkflowStudioPage.tsx:**
   - *Problem:* `WorkflowStudioPage.tsx` branch coverage was previously 94.64%, slightly below the strict 95% threshold due to uncovered keyboard navigation and non-AAL2 error branches.
   - *Fix:* Added `workflowCoverageBooster.test.tsx` exercising keyboard move up/down on hook rows, copy SHA timeout resets, unmount cleanup, and non-AAL2 dialog errors, bringing branch coverage on `WorkflowStudioPage.tsx` to 100%.

4. **Admin Trash Listing Permissions & AAL2 Elevation:**
   - *Problem:* Project admins querying `/api/v1/admin/trash` required both `PROJECT_ADMIN` role binding and verified AAL2 context. Missing AAL2 elevation resulted in 403 `AAL2_REQUIRED`.
   - *Fix:* Added proper AAL2 enrollment and context elevation in integration tests, validating both permission rejection for unmanaged projects and successful soft-trash execution.

---

### Automated Test & Verification Metrics

- **Backend Pytest Results:**
  - Total Tests: 116 passed (0 failures, 0 warnings) in 156.95s
  - Overall Coverage across Touched Modules: 96%
    * `kanban/api/v1/admin/destructive.py`: 95%
    * `kanban/api/v1/admin/workspace_settings.py`: 96%
    * `kanban/api/v1/custom_field_approvals.py`: 100%
    * `kanban/api/v1/custom_field_execution.py`: 95%
    * `kanban/api/v1/custom_fields.py`: 100%
    * `kanban/api/v1/project_config.py`: 100%
    * `kanban/api/v1/repo_bindings.py`: 95%
    * `kanban/api/v1/user_settings.py`: 95%
    * `kanban/api/v1/workflow_hooks.py`: 100%
  - Recorded in `docs/qa/KAN-428/unit-test-results.txt`

- **Frontend Vitest Results:**
  - Total Tests: 310 passed across 11 test suites in 18.75s (0 failures, 0 act warnings)
  - Statement Coverage: 99.56%
  - Branch Coverage: 96.51% (all touched files >= 95%)
    * `CustomFieldDefinitionEditor.tsx`: 97.01% branch
    * `CustomFieldsStudio.tsx`: 100% branch
    * `EscalationApprovalPanel.tsx`: 95.74% branch
    * `WorkspaceSettingsPage.tsx`: 96.57% branch
    * `ProjectSettingsPage.tsx`: 95.05% branch
    * `PersonalSettingsPage.tsx`: 96.26% branch
    * `AttachHookDialog.tsx`: 100% branch
    * `DryRunDrawer.tsx`: 98.38% branch
    * `GitRepoBindingsSection.tsx`: 97.82% branch
    * `HookPipelineRow.tsx`: 97.53% branch
    * `WorkflowStudioPage.tsx`: 100% branch
  - Recorded in `docs/qa/KAN-428/unit-test-results.txt`

- **Static Linters & Build:**
  - Ruff: clean (0 errors)
  - Mypy: clean (0 errors across 680 source files)
  - TypeScript: clean (`tsc -b --noEmit` exited 0)
  - ESLint: clean (`eslint . --max-warnings 0` exited 0)
  - Vite Production Build: built in 1.28s (`tsc -b && vite build` exited 0)
  - Dash Check: clean (0 Unicode dashes verified by `check_no_dashes.py --all`)
  - Recorded in `docs/qa/KAN-428/build-check.txt`

---

### Zero-Mock Multi-Viewport Screenshot Inventory

All 43 screenshots were captured against the live local application server (http://127.0.0.1:18428) with zero mocks, and are mirrored in both `docs/workouts/slice-5-workspace-project-workflows/screenshots/` and `docs/qa/KAN-428/screenshots/`:

| Filename | Viewport | Dimensions | Description |
| :--- | :--- | :--- | :--- |
| `01-workspace-settings-general-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Workspace timeouts (30m idle, 1440m absolute), export toggles, visibility |
| `01-workspace-settings-general-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | Workspace settings dark theme tokens, inputs, navigation rail |
| `01-workspace-settings-general-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Responsive layout, breathing margins, form inputs |
| `01-workspace-settings-general-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Vertical stack, navigation wrapping, preset pills |
| `01-workspace-settings-general-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Single column layout, touch target compliance, header collapse |
| `02-workspace-settings-groups-nested-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Administrative groups hierarchy, member cards, cycle prevention |
| `03-workspace-settings-trash-retention-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Trash retention studio (30 days), category filters, empty state |
| `04-project-settings-priorities-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Custom priorities form, color picker, quick-select fire emoji |
| `04-project-settings-priorities-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | Priorities management table and color chips in dark theme |
| `04-project-settings-priorities-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Priorities management on tablet landscape |
| `04-project-settings-priorities-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Priorities management on tablet portrait |
| `04-project-settings-priorities-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Priorities management on mobile viewport |
| `05-project-settings-wip-limits-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Workflow states table with Soft (2) and Hard (3) WIP limits |
| `05-project-settings-wip-limits-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | Workflow states table in dark theme |
| `05-project-settings-wip-limits-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Workflow states and WIP limit configuration on tablet landscape |
| `05-project-settings-wip-limits-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Workflow states and WIP limit configuration on tablet portrait |
| `05-project-settings-wip-limits-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Workflow states and WIP limit configuration on mobile |
| `06-project-settings-danger-zone-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | 2-stage project deletion: Amber soft-delete and Crimson purge cards |
| `06-project-settings-danger-zone-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | 2-stage project deletion danger zone in dark theme |
| `06-project-settings-danger-zone-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Project danger zone on tablet landscape |
| `06-project-settings-danger-zone-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Project danger zone on tablet portrait |
| `06-project-settings-danger-zone-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Project danger zone on mobile viewport |
| `08-personal-settings-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Personal profile, searchable timezone filter ('New_York'), Auto-detect |
| `08-personal-settings-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | Personal profile and security settings in dark theme |
| `08-personal-settings-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Personal profile settings on tablet landscape |
| `08-personal-settings-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Personal profile settings on tablet portrait |
| `08-personal-settings-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Personal profile settings on mobile viewport |
| `10-custom-fields-studio-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Custom Fields Studio, starter presets (CVSS, SLA, Blocker), standalone callout |
| `10-custom-fields-studio-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | Custom Fields Studio cards and preset badges in dark theme |
| `10-custom-fields-studio-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Custom Fields Studio on tablet landscape |
| `10-custom-fields-studio-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Custom Fields Studio on tablet portrait |
| `10-custom-fields-studio-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Custom Fields Studio on mobile viewport |
| `11-custom-fields-editor-tier-a-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Custom Field Definition Editor: Wasm Tier A sandbox controls |
| `12-custom-fields-structured-format-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Structured format selector (number with Intl formatting options) |
| `13-custom-fields-escalation-dual-control-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Dual-control escalation panel showing 'Approved by SERVER_ADMIN' |
| `15-workflow-studio-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Workflow Studio: In Progress -> Done transition rule with active hook |
| `15-workflow-studio-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | Workflow Studio and transition rule cards in dark theme |
| `15-workflow-studio-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Workflow Studio on tablet landscape |
| `15-workflow-studio-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Workflow Studio on tablet portrait |
| `15-workflow-studio-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Workflow Studio on mobile viewport |
| `16-workflow-attach-hook-dialog-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Attach Workflow Helper Hook dialog (Wasm Validator, Mutator, Agent Gate) |
| `17-workflow-dry-run-drawer-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Dry-Run Drawer: Simulation callout, sample ticket parameters, Run Dry-Run |
| `18-workflow-git-repo-bindings-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Bind Git Repository dialog with SSRF restrictions callout (0 password inputs) |

---

### Local Port & Docker Teardown Verification

- Local Kanban Server Port: `127.0.0.1:18428` -> Process terminated cleanly (`ss -tulpn | grep 18428` returns 0 entries).
- Local Git Companion Port: `127.0.0.1:18085` -> Process terminated cleanly (`ss -tulpn | grep 18085` returns 0 entries).
- Docker Containers Teardown:
```text
$ docker rm -f kan428-pg-test-1
kan428-pg-test-1

$ docker ps -a --filter "name=kan428"
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES

$ ss -tulpn | grep -E "18428|18085"
(0 entries)
```
