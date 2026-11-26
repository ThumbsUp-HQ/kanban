# API Specialist Review: KAN-429 (Slice 5 Phase 4 Publish Verified Workspace/Project Settings, Custom Fields & Workflows Wiki + Docs)

**Ticket:** KAN-429 (`[SLICE-5-P4][KB-GOVERNANCE-DOCS]`)  
**Parent Epic:** KAN-425 (`[EPIC][SLICE-5-WORKSPACE-PROJECT-WORKFLOWS]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan429-cf10d648`  
**Target Commit:** `9c7ede02` (branch `docs/KAN-429-slice5-governance-docs`, base `d601e2f1`)  
**Wiki Commit:** `1e1291c` (branch `docs/KAN-429-slice5-governance-docs` inside `thumbs-up-kanban.wiki`)  

---

## 1. Executive Summary & Verdict

This API Specialist Review evaluates the documentation accuracy, protocol integrity, schema contracts, and offline in-app help integration delivered under **KAN-429: Phase 4 Publish Verified Workspace/Project Settings, Custom Fields & Workflows Wiki + Docs**.

The documentation covers the entire Slice-5 subsystem across 5 authoritative wiki chapters and the offline in-app DocsCenter manifest (`wikiManifest.ts`, 617,018 bytes, 145 images). Every setting, data type, sandbox tier, dual-control approval gate, and hook execution contract was audited directly against the backend API routers and React studio components:
1. **Workspace Policies & Project WIP Limits**:
   - Workspace policy contracts (`session_idle_timeout_min` [5..720], `session_absolute_timeout_min`, `trash_retention_days`, `mcp_key_max_ttl_days`, `air_gap_mode`, `default_project_visibility` [default "private"], `issue_export_enabled`, `issue_import_enabled`, `report_export_enabled`, `issue_export_allowed_roles` including guest) documented with exact backend defaults and type constraints in `admin/workspace_settings.py` and `admin/destructive.py`.
   - Agent-safe sequence numbering (`default_skip_loaded_sequence_numbers`) documented as skipping cultural/banned numeric sequences during sequence allocation.
   - Project lifecycle states and WIP limit validation rules (`wip_limit >= 0`, `stage` enum, `color` hex validation, project `name` max 120, `identifier` `^[A-Z][A-Z0-9]{1,9}$`) documented in `project_config.py`.
2. **Custom Fields 4 Flavors & 7 Output Formats**:
   - Field flavors (`scalar`, `safe_formula`, `wasm`, `nsjail`) and 7 output formats (`text`, `number`, `badge`, `severity_pill`, `url`, `markdown_snippet`, `json_table`) specified with literal JSON schemas and `output_format_metadata`.
   - Credential modes match implementation 1:1: `INVOKING_USER`, `PROJECT_ADMIN_SP`, `SERVER_ADMIN_SP` (zero `SERVICE_ACCOUNT`).
   - Line-delimited `\n` format for `egress_allowlist`.
   - Dual-control step-up elevation protocol: cryptographic manifest digest validation, mandatory WebSudo AAL2 step-up (`require_admin_and_aal2`), and approval states (`PENDING`, `PENDING_SECOND_APPROVER`, `APPROVED`, `REVOKED`) documented in `custom_field_approvals.py` and `custom_fields.py`.
   - Execution sandbox boundaries: `PROJECT` (ephemeral token), `WORKSPACE` (escalated scope), and `SERVER` (requires server admin cryptographic signature).
3. **Scripted Workflows, Transition Hooks & Dry-Run Engine**:
   - Hook types (`validator`, `mutator`, `agent_interceptor`) and failure policies strictly matching backend (`fail_closed`, `fail_open_warn`).
   - Allowed mutable fields strictly restricted to the 7 valid targets: `labels`, `priority`, `assignees`, `start_date`, `due_date`, `cycle`, `custom_fields.<slug>` (with `closed_at` omitted per schema).
   - Hook execution timeout enforced: `timeout_ms` validates between 1 and 300,000 ms.
   - Dry-run execution endpoint (`POST /api/v1/projects/{key}/custom-fields/test-execute` and hook dry-run) documented with execution trace logging.
4. **Read-Only Bare Git Mirror Bindings**:
   - Fields matching `RepoBindingCreateRequest`: `repo_slug`, `remote_url`, `default_ref`, `access_mode` (`ro_vfs_mount` | `bare_git_tools`), `credential` (`none` | `workspace-pat` | `ssh-key`).
   - UI buttons documented matching actual labels: **`+ Bind Git Repository`** and **`Refresh Mirror`**.
5. **In-App Help Integrity & Offline Wiki Synchronization**:
   - All 29 UI `StudioDocLink` and `FieldHelpHint` `docHref` URLs across all 10 Slice-5 components resolve to valid chapter headings and explicit anchors (0 broken links).
   - All 43 verified workout screenshots (`slice5-*.png`) embedded with 100% SHA-256 match between `thumbs-up-kanban.wiki/images/` and `kanban/web/public/docs-images/`.

**Verdict: APPROVED.** All API contracts, security invariants, setting descriptions, and operator runbooks in KAN-429 are thoroughly verified and approved.

---

## 2. API Contract & Security Invariant Audit

### 2.1 Verified REST Endpoints
- **Workspace & Project Administration:**
  - `GET/PATCH /api/v1/admin/workspace-settings`
  - `POST /api/v1/admin/destructive:request`
  - `POST /api/v1/admin/destructive:execute`
  - `GET/PATCH /api/v1/projects/{key}`
  - `GET/POST /api/v1/projects/{key}/states`
- **Custom Scripted Fields & Dual Control:**
  - `GET/POST /api/v1/projects/{key}/custom-fields`
  - `PATCH/DELETE /api/v1/projects/{key}/custom-fields/{id}`
  - `POST /api/v1/custom-fields/{id}/approval-requests`
  - `POST /api/v1/custom-field-approvals/{id}/approve`
  - `POST /api/v1/projects/{key}/custom-fields/test-execute`
- **Workflow Hooks & Git Repositories:**
  - `GET/POST /api/v1/projects/{key}/workflow-hooks`
  - `POST /api/v1/projects/{key}/workflow-hooks/dry-run`
  - `GET/POST /api/v1/projects/{key}/repo-bindings`
  - `POST /api/v1/repo-bindings/{id}/refresh`
  - `DELETE /api/v1/repo-bindings/{id}`
- **User Personal Settings:**
  - `GET/PATCH /api/v1/auth/me`

### 2.2 Security Invariants Verified
- **Sandboxed Execution Integrity:** Ephemeral execution tokens scoped strictly to project tier by default.
- **Mandatory WebSudo AAL2 Step-Up:** Admin approvals for custom field script escalation require active WebSudo elevation.
- **Air-Gapped Offline Privacy:** In-app DocsCenter renders completely offline without third-party CDN requests.

---

## 3. Automated Test Verification & Quality Gates

1. **Pytest Parity Suite (`kanban/tests/`)**:
   - **128 passed in 105.09s** across Slice-5 backend test suite.
   - Module-level coverage >=95% on all 9 touched modules: `destructive.py` 95%, `workspace_settings.py` 96%, `custom_field_approvals.py` 100%, `custom_field_execution.py` 95%, `custom_fields.py` 100%, `project_config.py` 100%, `repo_bindings.py` 95%, `user_settings.py` 95%, `workflow_hooks.py` 100% (Overall: 96%).

2. **Frontend Vitest Suite (`src/features/docs-center/`)**:
   - **71 passed across 2 suites in 7.12s** (`DocsCenter.test.tsx` and `DocsCenterImages.test.tsx`).
   - Branch coverage: **96.15%**.

3. **Playwright Visual Verification Suite**:
   - 30 unclipped Playwright screenshots across 5 viewports captured and verified via `read_file` binary viewer with 0 horizontal overflow. Port 18429 cleanly released.

4. **Build & Quality Pipeline**:
   - `scripts/check_no_dashes.py`: 0 Unicode em/en-dashes found repository-wide and across all wiki chapters.
   - `tsc -b --noEmit`: 0 TypeScript errors.
   - `eslint . --max-warnings 0`: 0 warnings, 0 errors.
   - `vite build`: Succeeded in 1.24s.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-429/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: Exit code 0 across sync, dashes, typecheck, lint, and build.
  - `unit-test-results.txt`: Documents 128 Pytest and 71 Vitest tests with >=95% branch coverage.
  - `wiki-diff.patch`: Patch of commit `1e1291c` across 5 wiki chapters.
  - `screenshots/`: 30 multi-viewport PNG captures visually verified.

The documentation, endpoint schemas, and security controls for KAN-429 are robust, verified, and approved for release.
