# Slice 5: Workspace/Project Policies, Dual-Control Custom Fields & Scripted Workflow Hooks
## Phase 3 Live Verification & Forensic Workout Report (`KAN-428`)

- **Author:** `b-kan428` (Swarm Agent)
- **Target Branch:** git branch `feat/KAN-428-slice5-governance-workout`
- **Parent Epic:** `KAN-425` (`[EPIC][SLICE-5-GOVERNANCE-WORKFLOWS]`)
- **Preceding Phase Tickets:** `KAN-426` (Phase 1 Audit & Cuts), `KAN-427` (Phase 2 UI Implementation & Wiring)
- **Downstream Phase Ticket:** `KAN-429` (Phase 4 Wiki Documentation & Runbooks)
- **Requirement Traceability:**
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 3 (Workspace and Project Scoping Hierarchy)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 14 (Custom Fields, Wasm Compute and Approval Escalation)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 15 (Workflow Hooks, Transition Helpers and Git Repo Bindings)
  - `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md` (Phase 1 Audit & Cuts)
  - `docs/workouts/slice-5-workspace-project-workflows/02-implemented-changes.md` (Phase 2 Implemented Changes)
- **Strict Verification Invariants:**
  - **Zero Mutations on Protected Pre-Production:** 100% of live workouts executed against isolated local processes and test PostgreSQL database (`kanban_slice5_workout`) bound strictly to `127.0.0.1:18428`. Zero requests were routed to `192.168.1.101` or `k.hackedyour.info`.
  - **Zero-Mock Playwright Evidence:** All 43 captured screenshots were driven by real Playwright Chromium against the live running server (`http://127.0.0.1:18428`) with zero `page.route` or API mock interventions across all 5 viewports (`1440x900` light/dark, `1024x768`, `768x1024`, `390x844`).
  - **Zero Unicode Dashes:** Plain ASCII hyphens only. Verified by `python3 scripts/check_no_dashes.py --all` exiting with status code 0.
  - **Secret Sanitization:** All credentials, tokens, cookies, and keys scrubbed through `kanban.security.scrubber.scrub_text`.

---

### Executive Summary

Phase 3 (`KAN-428`) executes end-to-end live container/process verification, in-flight bug fixes, zero-mock multi-viewport visual audits, and forensic QA bundle creation for Slice 5 workspace governance, project lifecycle, scripted custom fields, and workflow transition hooks:

1. **Workout 1 (Workspace Policies, Nested Group Sharing & 2-Stage Trash Purge):**
   - Configured organization session idle (`30m`), absolute (`1440m` / 24h), trash retention (`30d`), and export/import policy settings via `PATCH /api/v1/admin/workspace-settings` (HTTP 200 OK).
   - Validated transitive group hierarchy and cycle prevention: attempting to add parent group `Engineering` as a member of child group `Backend Core` failed closed with HTTP 409 Conflict (`GROUP_CYCLE_REJECTED`).
   - Validated 2-stage soft-delete and trash listing: issue `DISP-1` moved to trash via `POST /api/v1/admin/destructive:request` + `execute` (HTTP 200 OK) and appeared in `GET /api/v1/admin/trash?kind=issue` with 29 days remaining.

2. **Workout 2 (Project Policies, WIP Limits, Emoji Priorities, 2-Stage Project Deletion & Personal Settings):**
   - Created custom project priority with quick-select emoji `urgent-fire` (🔥) via `POST /api/v1/projects/KAN/priorities` (HTTP 201 Created).
   - Validated Soft WIP warning: moving issue `KAN-3` into `In Progress` (configured with `wip_soft_limit: 2`, `wip_hard_limit: 3`) passed with HTTP 200 OK and reactive warning metadata (`resulting_count: 3`).
   - Validated Hard WIP limit block: moving issue `KAN-4` into `In Progress` failed closed with HTTP 409 Conflict (`WIP_HARD_LIMIT_OVERRIDE_REQUIRED`, `hard_limit: 3`, `current_count: 3`).
   - Validated 2-stage project deletion of `DISP`: Stage 1 blast radius calculation returned 3 issues to remove (`confirmation_token` issued), Stage 1 soft-delete executed cleanly, and Stage 2 permanent purge removed all entities while recording immutable audit entry in activity ledger.
   - Validated `PersonalSettingsPage`: updated user timezone to `America/New_York` via `PATCH /api/v1/auth/me` (HTTP 200 OK).

3. **Workout 3 (Custom Scripted Fields, Runaway Sandbox Termination & 2-Admin Dual-Control):**
   - Created Custom Scripted Field `invoice-total` with structured format metadata (`format: number`, `unit_suffix: $`, `max_fraction_digits: 2`) via `POST /api/v1/projects/KAN/custom-fields` (HTTP 201 Created).
   - Proved runaway compute sandbox boundary enforcement: an infinite-loop/memory exhaustion script (`128 MiB`, `3000ms` limits) was terminated deterministically by `DefaultSubprocessLauncher` in 1002.8ms without affecting server or worker stability.
   - Proved 2-admin dual-control escalation workflow:
     * `ADMIN1` requested escalation to `SERVER` scope and `SERVER_ADMIN_SP` credential mode via `POST .../approval-requests` (HTTP 201 Created, `PENDING_PRIMARY_APPROVER`).
     * `ADMIN1` primary approval succeeded (`POST .../approve` -> HTTP 200 OK, `status: PENDING_SECOND_APPROVER`).
     * `ADMIN1` self-approval attempt for second approver failed closed with HTTP 409 Conflict (`DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED`).
     * `ADMIN2` with stale AAL2 (`aal2_verified_at > 900s`) failed closed with HTTP 403 Forbidden (`AAL2_REQUIRED`).
     * `ADMIN2` with fresh AAL2 (`aal2_verified_at <= 900s`) approved successfully via `POST .../approve` (HTTP 200 OK, `status: APPROVED`).

4. **Workout 4 (Workflow Hooks, Dry-Run Drawer, CLI Parity & Git Repo SSRF Gate):**
   - Validated transition hook `ci-commit-verifier` attachment to `In Progress -> Done` state transition.
   - Executed dry-run simulation via `POST /api/v1/projects/KAN/workflow-hooks/dry-run` (HTTP 200 OK, `would_commit: false`, returning before/after evaluation trace).
   - Validated Git repository binding SSRF defense: binding RFC 1918 private address `https://192.168.1.50/repo.git` failed closed with HTTP 422 Unprocessable Entity (`REPO_URL_REJECTED`, `RFC1918_ADDRESS_FORBIDDEN`).
   - Validated valid bare Git mirror binding: `https://github.com/ThumbsUp-HQ/kanban.git` bound cleanly with HTTP 201 Created (`access_mode: bare_git_tools`).

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
  "trash_retention_days": 30,
  "air_gap_mode": false
}
```
- **Response:** HTTP 200 OK
```json
{
  "workspace_id": "01a2153a-7ee5-7587-851e-2c46a74efc74",
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
  "issue_export_enabled": true,
  "issue_import_enabled": true,
  "issue_export_allowed_roles": [
    "workspace_admin",
    "project_admin",
    "member"
  ],
  "report_export_enabled": true,
  "report_export_allowed_roles": [
    "ADMIN",
    "MEMBER"
  ],
  "updated_at": "2026-11-26T00:21:29.150066Z"
}
```

##### B. Transitive Group Cycle Rejection
- **Request:** `POST /api/v1/admin/groups/{child_group_id}/members/{parent_group_id}`
- **Response:** HTTP 409 Conflict
```json
{
  "type": "urn:kanban:problem:group-cycle-rejected",
  "title": "Group Cycle Rejected",
  "status": 409,
  "code": "GROUP_CYCLE_REJECTED",
  "detail": "Adding member would introduce a cyclic group dependency.",
  "request_id": "707f46d711ce4ed09c23b9e51e86b223",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps."
}
```

##### C. 2-Stage Soft-Delete Issue & Trash Listing
- **Request:** `POST /api/v1/admin/destructive:request` + `POST /api/v1/admin/destructive:execute` (`mode: trash`, `target: DISP-1`)
- **Response:** HTTP 200 OK (`status: executed`, `blast_hash: 44a0140b...`)
- **Query:** `GET /api/v1/admin/trash?kind=issue` -> HTTP 200 OK (`total: 1`, `remaining_days: 29`, `retention_days: 30`)

---

#### Workout 2: Project Policies, WIP Limits & Lifecycle

##### A. Quick-Select Emoji Priority Creation
- **Request:** `POST /api/v1/projects/KAN/priorities`
- **Payload:** `{"slug": "urgent-fire", "label": "Urgent Fire", "emoji": "🔥", "color_hex": "#ef4444", "sort_order": 10}`
- **Response:** HTTP 201 Created (`id: 01a2153a-9098-7e2d-aa52-87abae46999e`)

##### B. Soft WIP Warning vs Hard WIP Limit Block
- **Setup:** Workflow state `In Progress` configured with `wip_soft_limit: 2`, `wip_hard_limit: 3`.
- **Soft WIP Warning:**
  - Transition issue `KAN-3` from `Todo` to `In Progress` (bringing total active issues to 3, exceeding soft limit 2).
  - **Response:** HTTP 200 OK with `resulting_count: 3` and warning indication.
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
  "request_id": "dbce35f4044443f9950a3dd2e49081c2",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps.",
  "hard_limit": 3,
  "current_count": 3
}
```

##### C. 2-Stage Project Deletion of `DISP`
- **Stage 1 (Confirmation Request):**
  - `POST /api/v1/admin/destructive:request` (`mode: trash`, `target: DISP`)
  - **Response:** HTTP 200 OK (`blast_summary: "3 issues, 0 docs, 0 pages, 0 cycles, 0 modules to be removed"`, `confirm_phrase: "TRASH PROJECT DISP"`, `confirmation_token: "kb_del_..."`)
- **Stage 1 (Execute):**
  - `POST /api/v1/admin/destructive:execute` -> HTTP 200 OK (`status: executed`)
- **Stage 2 (Permanent Purge):**
  - `POST /api/v1/admin/destructive:request` + `execute` (`mode: permanent_purge`, `confirm_phrase: "PERMANENTLY PURGE PROJECT DISP"`)
  - **Response:** HTTP 200 OK (`status: executed`, immutable activity ledger verified)

##### D. Personal Settings Timezone Persistence
- **Request:** `PATCH /api/v1/auth/me` (`{"timezone": "America/New_York", "display_name": "Admin One"}`)
- **Response:** HTTP 200 OK (`timezone: America/New_York`)

---

#### Workout 3: Custom Fields & 2-Admin Dual-Control Escalation

##### A. Custom Field Creation with Structured Format
- **Request:** `POST /api/v1/projects/KAN/custom-fields`
- **Payload:**
```json
{
  "name": "Invoice Total",
  "slug": "invoice-total",
  "field_flavor": "wasm",
  "tier": "wasm",
  "output_format": "number",
  "output_format_metadata": {
    "unit_suffix": "$",
    "max_fraction_digits": 2,
    "use_grouping": true
  },
  "script_source": "export function evaluate(ctx) { return 1250.50; }"
}
```
- **Response:** HTTP 201 Created (`id: 01a2153a-92f4-75cb-bc3f-d36258de4b91`)

##### B. Runaway Sandbox Termination Boundary
- **Test:** Evaluated runaway script with infinite loop / memory bloat under `DefaultSubprocessLauncher`.
- **Result:** Deterministically killed by process group signal in 1002.8ms (`timeout_caught: True`). Zero resource leakage to parent daemon.

##### C. 2-Admin Dual-Control Escalation Flow
1. **Escalation Request:**
   - `ADMIN1` requested elevation to `target_scope: SERVER`, `credential_mode: SERVER_ADMIN_SP`.
   - **Response:** HTTP 201 Created (`id: 105c8b80-392c-4abd-aac6-8860ca3360c3`, `status: PENDING_PRIMARY_APPROVER`).
2. **Primary Approval:**
   - `ADMIN1` approves via `POST .../approve` with manifest SHA-256 and `sp_warning_acknowledged: true`.
   - **Response:** HTTP 200 OK (`status: PENDING_SECOND_APPROVER`, `primary_approver_id: ADMIN1`).
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
  "request_id": "e8a4d29ec80d42e5ab0dcbaa9862fa17",
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
  "request_id": "d04e1104cdc54457bdc09c75cb9075c8",
  "doc_href": "/docs/multi-card-authentication-studio#aal2-step-up",
  "help_summary": "This administrative or security-sensitive action requires Multi-Factor Authentication (AAL2) via Passkey or TOTP."
}
```
5. **Fresh AAL2 (<=900s) Approved:**
   - `ADMIN2` re-steps up to fresh AAL2 (`aal2_verified_at = now`) and submits approval.
   - **Response:** HTTP 200 OK
```json
{
  "id": "105c8b80-392c-4abd-aac6-8860ca3360c3",
  "workspace_id": "01a2153a-7ee5-7587-851e-2c46a74efc74",
  "project_id": "01a2153a-7efc-7a85-8f0b-21eed3cf96e8",
  "field_id": "01a2153a-92f4-75cb-bc3f-d36258de4b91",
  "manifest_sha256": "86006c23008f8f82082733e2b675ca65452452fc59249384e6beaa93fe9afbfa",
  "target_scope": "SERVER",
  "credential_mode": "SERVER_ADMIN_SP",
  "required_tier": "SERVER_ADMIN_DUAL",
  "status": "APPROVED",
  "requested_by_id": "01a2153a-7ee9-719e-a4c4-b670dd718137",
  "justification": "Requires server admin scope to verify infrastructure metrics.",
  "primary_approver_id": "01a2153a-7ee9-719e-a4c4-b670dd718137",
  "primary_approver_aal": 2,
  "primary_approved_at": "2026-11-26T00:21:31.062016Z",
  "secondary_approver_id": "01a2153a-7ef1-71c2-a555-e91baabc26a4",
  "secondary_approver_aal": 2,
  "secondary_approved_at": "2026-11-26T00:21:31.163453Z",
  "sp_warning_acknowledged": true,
  "revoked_at": null,
  "revoked_reason": null,
  "created_at": "2026-11-26T00:21:31.026307Z"
}
```

---

#### Workout 4: Workflow Studio & Git Repo Bindings

##### A. Workflow Hook Dry-Run Simulation
- **Request:** `POST /api/v1/projects/KAN/workflow-hooks/dry-run`
- **Payload:** `{"from_state": "In Progress", "to_state": "Done", "issue_key": "KAN-1"}`
- **Response:** HTTP 200 OK (`would_commit: false`, returning step-by-step diff and validation logs without persisting database state)

##### B. Git Repo Binding SSRF Rejection
- **Request:** `POST /api/v1/projects/KAN/repo-bindings`
- **Payload:**
```json
{
  "slug": "ssrf-test",
  "remote_url": "https://192.168.1.50/repo.git",
  "default_ref": "main",
  "access_mode": "bare_git_tools",
  "credential": "REDACTED"
}
```
- **Response:** HTTP 422 Unprocessable Entity
```json
{
  "type": "urn:kanban:problem:REPO_URL_REJECTED",
  "title": "Repository URL Rejected",
  "status": 422,
  "code": "REPO_URL_REJECTED",
  "detail": "Host '192.168.1.50' resolves to forbidden IP 192.168.1.50",
  "request_id": "5a2bd3720f9348dcb9197f62b07156be",
  "doc_href": "/docs/admin-diagnostics-and-link-inspector-studio",
  "help_summary": "Review the error details and open the platform documentation for troubleshooting steps.",
  "reason": "RFC1918_ADDRESS_FORBIDDEN"
}
```

##### C. Valid Git Bare Mirror Binding
- **Request:** `POST /api/v1/projects/KAN/repo-bindings` (`remote_url: "https://github.com/ThumbsUp-HQ/kanban.git"`, `access_mode: "bare_git_tools"`)
- **Response:** HTTP 201 Created (`slug: main-upstream`, `access_mode: bare_git_tools`, `id: ea321096-2815-4b92-926a-cf55dbbc2e0d`)

---

### In-Flight Bug Fixes & Discovered Issues

1. **Uvicorn Subprocess Pipe Buffer Deadlock:**
   - *Problem:* In `execute_slice5_live_workout.py`, Uvicorn was initially started with `stdout=subprocess.PIPE, stderr=subprocess.STDOUT` without background pipe drain threads. Once the OS pipe buffer (64 KB) filled with access logs during multi-viewport screenshot captures, Uvicorn blocked on `write(1, ...)` calls, freezing all incoming HTTP requests.
   - *Fix:* Redirected Uvicorn stdout/stderr directly to an unbuffered log file (`/tmp/slice5_uvicorn.log`). The server now processes hundreds of concurrent requests without blocking.

2. **Playwright SPA Navigation Loading State Race:**
   - *Problem:* Fast viewport navigations via `safeNavigate` previously used fixed millisecond sleep timers. When React Query was still fetching data, screenshots occasionally captured intermediate "Loading..." states (e.g. `Loading workspace settings...`), causing downstream locator queries to fail.
   - *Fix:* Updated `safeNavigate` to explicitly wait for deterministic page anchor elements (e.g. `[data-testid="idle-preset-30m"]` on Workspace Settings, `[data-testid="tab-priorities"]` on Project Settings, `[data-testid="personal-settings-page"]` on Personal Settings). All 43 screenshots now capture fully rendered, interactive components.

3. **Custom Field Definition Editor Select Locator Parity:**
   - *Problem:* The Playwright script searched for `select[name="output_format"]` or `[data-testid="cf-output-format-select"]`, whereas `CustomFieldDefinitionEditor.tsx` renders `[data-testid="output-format-select"]`.
   - *Fix:* Aligned the locator in `scripts/capture_kan428_zero_mock_screenshots.mjs` to `[data-testid="output-format-select"]`, enabling clean automated capture of structured format configuration (`12-custom-fields-structured-format`).

---

### Zero-Mock Multi-Viewport Screenshot Inventory

All 43 screenshots were captured against the live local application server (`http://127.0.0.1:18428`) with zero mocks, and are mirrored in both `docs/workouts/slice-5-workspace-project-workflows/screenshots/` and `docs/qa/KAN-428/screenshots/`:

| Filename | Viewport | Dimensions | Description |
| :--- | :--- | :--- | :--- |
| `01-workspace-settings-general-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Workspace timeouts (30m idle, 1440m absolute), export toggles, visibility |
| `01-workspace-settings-general-desktop-1440x900-dark.png` | Desktop | 1440x900 (Dark) | Workspace settings dark theme tokens, inputs, navigation rail |
| `01-workspace-settings-general-tablet-landscape-1024x768.png` | Tablet Landscape | 1024x768 (Light) | Responsive layout, breathing margins, form inputs |
| `01-workspace-settings-general-tablet-portrait-768x1024.png` | Tablet Portrait | 768x1024 (Light) | Vertical stack, navigation wrapping, preset pills |
| `01-workspace-settings-general-mobile-portrait-390x844.png` | Mobile Portrait | 390x844 (Light) | Single column layout, touch target compliance, header collapse |
| `02-workspace-settings-groups-nested-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Administrative groups hierarchy, member cards, cycle prevention |
| `03-workspace-settings-trash-retention-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Trash retention studio (30 days), category filters, empty state |
| `04-project-settings-priorities-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Custom priorities form, color picker, quick-select fire emoji (🔥) |
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
| `08-personal-settings-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Personal profile, searchable timezone filter ('New York'), Auto-detect |
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
| `12-custom-fields-structured-format-desktop-1440x900-light.png` | Desktop | 1440x900 (Light) | Structured format selector (`number` with Intl formatting options) |
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

### Local Port Teardown Verification

- Local Kanban Server Port: `127.0.0.1:18428` -> Process terminated cleanly (`lsof -i :18428` returns 0 entries).
- Local Git Companion Port: `127.0.0.1:18085` -> Process terminated cleanly (`lsof -i :18085` returns 0 entries).
- Docker Containers: `0` temporary containers running (`docker ps -a` verified).
