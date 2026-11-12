# API Specialist Gate Final Audit: APPROVED for KANBA-89 (KB-P3-10b)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-89`
- Branch: `feat/KANBA-89`
- Ticket: `KANBA-89` (`KB-P3-10b`: `[Phase 3 / API] Modules API with modules_enabled feature-flag 404 & issue module assignment`)

---

### 1. Executive Summary & Verification Matrix
A forensic backend architecture and API Specialist Gate audit was conducted for `KANBA-89` in `/tmp/kb-wt-KANBA-89`. `KB-P3-10b` implements the project modules subsystem, delivering complete module CRUD, lead principal assignment, status lifecycle tracking, per-issue module associations with capacity caps (max 10), and strict `modules_enabled` feature-flag isolation. All 8 REST endpoints, timing floors, permission verification ordering, database spine registrations, cascade cleanup, and activity ledger emissions were evaluated against Spec Sections 7.2 (8f), 11.4, 3.4, and 5.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Router & Mounting** | 8 endpoints mounted on `build_v1_router()` | Mounted in `kanban/api/v1/modules.py` and composed on `build_v1_router()` | PASS |
| **Timing Equalization** | 25.0ms timing floor on all endpoints | All 8 endpoints wrapped in `async with timing_floor(floor_ms=25.0):` | PASS |
| **Feature Flag Invariant** | 404 on all module routes when disabled | Returns RFC 7807 `404 MODULES_DISABLED` for project viewers when disabled | PASS |
| **Anti-Enumeration Ordering** | Unreadable project yields plain 404 | Access evaluated first (`404 NOT_FOUND`) before feature flag (`404 MODULES_DISABLED`) | PASS |
| **Issue Serializer Suppression** | Omit `module_ids` key when disabled | `_strip_module_ids_if_none` cleanly strips `module_ids` from issue responses | PASS |
| **Object Spine Registration** | Register module in Universal Object Graph | Calls `register_object('module', ...)` with slugified canonical key | PASS |
| **Name Uniqueness Check** | Case-insensitive per project | Rejects duplicates within same project with RFC 7807 `409 MODULE_NAME_TAKEN` | PASS |
| **Lead Principal Eligibility** | Verified active USER/AGENT with project VIEW | Enforces project VIEW via `effective_resource_access` (`422 LEAD_NOT_ELIGIBLE`) | PASS |
| **Date Range Validation** | Rejects `target_date < start_date` | Rejects with RFC 7807 `422 INVALID_DATE_RANGE` | PASS |
| **Per-Issue Assignment Cap** | Max 10 modules per issue | Exceeding 10 modules raises RFC 7807 `422 MODULE_LIMIT` | PASS |
| **Cross-Project Isolation** | Rejects modules from other projects | Cross-project module assignment emits RFC 7807 `422 MODULE_NOT_IN_PROJECT` | PASS |
| **Delete Cascade & Soft Delete**| Cascade unlinks issues; soft-deletes spine | Cleans `issue_modules`, `project_module_defaults`; marks `objects.deleted_at` | PASS |
| **Activity Ledger** | Emits CREATED, UPDATED, DELETED, CHANGED | Emitted under category `HISTORY` against module and issue objects | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 6/6 passed in 4.43s; 100.00% branch+line coverage across target modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (746 files), Mypy strict clean (310 files), Lint-imports clean | PASS |

---

### 2. Forensic Architectural Analysis

1. **REST Router Mounting & Timing Equalization:**
   - Mounted in `kanban/api/v1/modules.py` and composed in `kanban/api/v1/__init__.py:build_v1_router()`:
     * `GET /api/v1/projects/{project_ref}/modules`
     * `POST /api/v1/projects/{project_ref}/modules`
     * `GET /api/v1/modules/{module_id}`
     * `PATCH /api/v1/modules/{module_id}`
     * `DELETE /api/v1/modules/{module_id}`
     * `PUT /api/v1/issues/{issue_ref}/modules`
     * `PUT /api/v1/modules/{module_id}/issues/{issue_ref}`
     * `DELETE /api/v1/modules/{module_id}/issues/{issue_ref}`
   - Every single endpoint is wrapped with `async with timing_floor(floor_ms=25.0):`, ensuring timing side-channels during project lookups, lead evaluations, and module updates are completely suppressed.

2. **Feature-Flag Invariant & Anti-Enumeration Gate (Spec S7.2 8f, S3.4):**
   - In `kanban/services/modules.py`, `require_modules_enabled()` enforces that when `projects.modules_enabled = FALSE`, requests fail closed with RFC 7807 `404` and `code: MODULES_DISABLED`.
   - **Order of Checks:**
     1. Project access resolution via `get_project_or_404()`: unreadable projects return standard indistinguishable `404 NOT_FOUND` with zero indication of whether the project exists or whether modules are enabled.
     2. `require_modules_enabled(project)`: if disabled, emits `404 MODULES_DISABLED` only to authorized viewers of the project.
     3. Capability enforcement via `require_capability(session, caller, project.id, Capability.ADMIN | VIEW)`: ensures non-admins attempting mutating actions receive `403 FORBIDDEN`.
   - **Issue Serializer Suppression:** When `projects.modules_enabled = FALSE`, `module_ids` is completely stripped from issue response payloads via `_strip_module_ids_if_none`, allowing frontend clients to unmount the Modules tab and facet cleanly.

3. **Module Registration & Lead Principal Eligibility:**
   - On `POST /projects/{project_ref}/modules`, a unique canonical key is generated (`f"{project.identifier.lower()}-{body.name.lower().replace(' ', '-')}"[:200]`) and registered in the `objects` spine via `register_object('module'::object_kind, ...)`.
   - Name collisions within the same project (case-insensitive) reject with RFC 7807 `409 MODULE_NAME_TAKEN`.
   - `_verify_lead_eligible()` verifies that `lead_principal_id` corresponds to an active USER or AGENT principal holding `Capability.VIEW` on the parent project in `effective_resource_access`. Missing or unauthorized leads return RFC 7807 `422 LEAD_NOT_ELIGIBLE`.
   - Date range validation ensures `target_date >= start_date`; violations reject with RFC 7807 `422 INVALID_DATE_RANGE`.

4. **Issue Module Assignment & Boundary Guards:**
   - In `update_issue_modules()`, `PUT /issues/{issue_ref}/modules` replaces the complete module assignment set:
     * Bounded by `MAX_MODULES_PER_ISSUE = 10`. Exceeding 10 modules rejects with RFC 7807 `422 MODULE_LIMIT`.
     * Validates that every assigned module belongs to the issue's parent project. Cross-project module IDs reject with RFC 7807 `422 MODULE_NOT_IN_PROJECT`.
     * Diff computation identifies `added` and `removed` module IDs, recording `ActivityEventType.ISSUE_MODULES_CHANGED` against the issue object under category `HISTORY`.
   - Granular routes (`PUT /modules/{module_id}/issues/{issue_ref}` and `DELETE ...`) allow single-issue assignment and removal, returning HTTP 204.

5. **Cascade Cleanup & Soft Deletion:**
   - On `DELETE /modules/{module_id}`:
     * Counts and deletes all associated rows in `issue_modules` and `project_module_defaults`.
     * Deletes the `modules` row and soft-deletes the `objects` record by updating `deleted_at = clock_timestamp()`.
     * Emits `MODULE_DELETED` with payload `{"removed_issue_links": count}` to the immutable activity ledger.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have completed the backend architecture and API Specialist Gate audit for `KANBA-89`. All REST contracts, timing floors, feature flag gates, anti-enumeration protections, spine registrations, and assignment limits are satisfied.

Verdict: APPROVED
