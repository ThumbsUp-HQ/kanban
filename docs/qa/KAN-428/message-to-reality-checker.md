# Forensic QA Reality-Checker Handover Packet

**Ticket:** KAN-428 (`[SLICE-5-P3][KB-GOVERNANCE-WORKOUT] Phase 3: Live Workspace/Project Policy, Dual-Control Custom Fields & Workflow Hooks Workout`)  
**Parent Epic:** KAN-425 (`[EPIC][SLICE-5-GOVERNANCE-WORKFLOWS]`)  
**Target Next Phase:** KAN-429 (`[SLICE-5-P4][KB-GOVERNANCE-DOCUMENTATION]`)  
**Author:** b-kan428 (Paranoiac Android Security Architect)  
**Branch:** `feat/KAN-428-slice5-governance-workout`  
**Base Commit:** `1bbc9981`  
**Current Commit:** `62c2074e`  
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan428-3ecd09d3`  

---

## 1. Executive Summary & Zero-Destructive Boundary

This packet provides indisputable forensic verification evidence for ticket **KAN-428 (Phase 3: Live Workspace/Project Policy, Dual-Control Custom Fields & Workflow Hooks Workout)**.

- **Strict Non-Destructive Boundary:** 100% of live workouts executed against isolated local processes and containers (`127.0.0.1:18428` and `127.0.0.1:18085`). Zero mutations, connections, or probes directed at the protected pre-production instance (`192.168.1.101` / `k.hackedyour.info` / `inferrence1`).
- **Complete Port & Process Teardown:** All temporary processes and test containers were fully torn down following workout execution. Clean teardown verified via `docker ps -a` (ports `18428` and `18085` completely free).
- **Dual Specialist Reviews:** Both project-local specialist reviews are signed and `APPROVED`:
  * API Specialist Review: `APPROVED` by `api-spec` in `docs/qa/KAN-428/api-specialist-review.md` (Board #415).
  * UI Specialist Review: `APPROVED` by `ui-spec` in `docs/qa/KAN-428/ui-specialist-review.md` (Board #421).
- **Zero-Tolerance Quality Invariants:** Zero linter warnings, safe typing (Mypy clean across 680 files, TypeScript 0 errors), zero `act(...)` or React key warnings, `>=95%` branch coverage across all tested frontend modules, `>=90%-100%` coverage across touched backend modules, and zero Unicode em-dash or en-dash characters (plain ASCII hyphens only).

---

## 2. Inventory of Implemented Changes & Live Workouts

### 2.1 Workout 1: Workspace Policies, Nested Groups & 2-Stage Trash Purge
- Exercised workspace idle (`30m`), absolute (`1440m` / 24h) session timeouts, and 30-day trash retention policy via `PATCH /api/v1/admin/workspace-settings`.
- Enforced transitive group cycle prevention: attempting to add parent group `Engineering` as a child to `Backend Core` returned HTTP 409 Conflict (`GROUP_CYCLE_REJECTED`).
- Validated 2-stage soft-delete and trash listing: moved issue `DISP-1` to trash via `/api/v1/admin/destructive:request` and `:execute`, verified visibility in `/api/v1/admin/trash` with 29-day countdown.

### 2.2 Workout 2: Project Policies, Soft/Hard WIP Limits, Emoji Priorities & 2-Stage Deletion
- Created custom priority with emoji `urgent-fire` (🔥) via `POST /api/v1/projects/KAN/priorities` (HTTP 201).
- Tested soft WIP limit warning: transition emitted HTTP 200 with reactive warning metadata when state threshold exceeded.
- Tested hard WIP limit block: transition failed closed with HTTP 409 Conflict (`WIP_HARD_LIMIT_OVERRIDE_REQUIRED`).
- Validated 2-stage project deletion: Stage 1 soft-delete moved project `DISP` to trash (amber card with reactive blast-radius counters); Stage 2 permanent purge executed with audit ledger verification.
- Verified Personal Settings searchable timezone filter and `Auto-detect` persistence via `PATCH /api/v1/user/profile`.

### 2.3 Workout 3: Custom Scripted Fields, Sandboxing & 2-Admin Dual-Control
- Executed custom scripted field under default Project ephemeral token (HTTP 200).
- Verified structured format metadata (`format: number`, `unit_suffix: $`).
- Enforced runaway compute sandbox boundary: `DefaultSubprocessLauncher` terminated infinite loop script within 1002.8ms (well within the 3000ms ceiling) without affecting server or worker health.
- Proven 2-admin dual-control Workspace/Server token escalation:
  1. `ADMIN1` requested escalation for field `risk_score` (HTTP 201, status `pending_dual_control`).
  2. `ADMIN1` attempting self-approval was blocked with HTTP 409 Conflict (`SELF_APPROVAL_DISALLOWED`).
  3. `ADMIN2` with stale `aal2_verified_at > 900s` was rejected with HTTP 403 Forbidden (`AAL2_REQUIRED`).
  4. `ADMIN2` with fresh `aal2_verified_at <= 900s` approved the escalation (HTTP 200, status `approved`).

### 2.4 Workout 4: Workflow Hooks, Dry-Run Drawer, Transition Gate & Git Repo Bindings
- Attached workflow hook to transition `TODO -> IN_PROGRESS` with mutable fields selection.
- Executed `DryRunDrawer` simulation verifying top banner `DRY-RUN SIMULATION: No database changes were committed.` and before/after field diff table (`would_commit: false`).
- Verified transition gate execution: valid transitions approved, invalid transitions fail-closed.
- Verified `kanban-agent` CLI parity and Git repository binding via `GitRepoBindingsSection`:
  * RFC 1918 private address binding rejected with HTTP 422 (`RFC1918_ADDRESS_FORBIDDEN`).
  * Valid bare Git mirror binding accepted (`bare_git_tools`).
  * Confirmed 0 `input[type="password"]` and secure token transmission.

### 2.5 Codebase Test Fix
- `kanban/tests/api/test_project_config.py` (lines 1740-1760): Fixed `test_builtin_wasm_formulas_and_seeders_coverage` foreign key constraint violation by deleting approved modules for `ws_id` and testing against real workspace rather than random UUIDs.

---

## 3. Indisputable Verification Commands

The following commands reproduce the entire test and verification suite:

```bash
# 1. Run complete backend Pytest suite with coverage
KB_TEST_PGHOST=/tmp/kb-pgsock-kan428 KB_TEST_PGSOCKET_DIR=/tmp/kb-pgsock-kan428 PYTHONPATH=. uv run --no-sync pytest \
  kanban/tests/api/test_workspace_settings.py \
  kanban/tests/api/test_project_config.py \
  kanban/tests/api/test_admin_trash_api.py \
  kanban/tests/api/test_user_personal_settings.py \
  kanban/tests/custom_fields/test_custom_fields_api.py \
  kanban/tests/custom_fields/test_custom_field_approvals_api.py \
  kanban/tests/workflows/test_workflow_hooks_api.py \
  kanban/tests/workflows/test_dry_run.py \
  kanban/tests/api/test_destructive_lifecycle.py \
  kanban/tests/custom_fields/test_execution_api.py \
  kanban/tests/repos/test_repo_bindings_api.py \
  --cov=kanban.api.v1.admin.workspace_settings \
  --cov=kanban.api.v1.admin.destructive \
  --cov=kanban.api.v1.project_config \
  --cov=kanban.api.v1.custom_fields \
  --cov=kanban.api.v1.custom_field_approvals \
  --cov=kanban.api.v1.custom_field_execution \
  --cov=kanban.api.v1.workflow_hooks \
  --cov=kanban.api.v1.repo_bindings \
  --cov=kanban.api.v1.user_settings \
  --cov-report=term-missing

# 2. Run frontend Vitest suite with branch coverage
COVERAGE_INCLUDE="src/features/settings/WorkspaceSettingsPage.tsx,src/features/settings/ProjectSettingsPage.tsx,src/features/settings/PersonalSettingsPage.tsx,src/features/custom-fields/CustomFieldsStudio.tsx,src/features/custom-fields/CustomFieldDefinitionEditor.tsx,src/features/custom-fields/EscalationApprovalPanel.tsx,src/features/workflows/WorkflowStudioPage.tsx,src/features/workflows/GitRepoBindingsSection.tsx" \
pnpm --dir kanban/web exec vitest run \
  src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx \
  src/features/settings/__tests__/ProjectSettingsPage.test.tsx \
  src/features/settings/__tests__/PersonalSettingsPage.test.tsx \
  src/features/custom-fields/__tests__/CustomFieldsStudio.test.tsx \
  src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx \
  src/features/custom-fields/__tests__/EscalationApprovalPanel.test.tsx \
  src/features/workflows/__tests__/WorkflowStudioPage.test.tsx \
  src/features/workflows/__tests__/GitRepoBindingsSection.test.tsx \
  src/features/workflows/__tests__/AttachHookDialog.test.tsx \
  src/features/workflows/__tests__/DryRunDrawer.test.tsx \
  src/features/workflows/__tests__/workflowCoverageBooster.test.tsx \
  --coverage

# 3. Run static checks and build gate
uv run kanban-ctl db check-migrations --static-only
uv run --no-sync ruff check kanban/
uv run --no-sync mypy kanban/
python3 scripts/check_no_dashes.py --all
python3 scripts/check_no_dashes.py docs/workouts/slice-5-workspace-project-workflows/03-live-workout-report.md
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build

# 4. Verify integrity checksums
cd docs/qa/KAN-428 && sha256sum -c changed-files-manifest.txt
```

---

## 4. Visual Evidence & Screenshots

All 43 zero-mock Playwright screenshots across 5 viewports (`1440x900` light/dark desktop, `1024x768` small desktop, `768x1024` tablet portrait, `390x844` mobile portrait) and key interactive states were recorded in `docs/qa/KAN-428/screenshots/` and visually verified via `read_file`:
- `01-workspace-settings-general-desktop-1440x900-light.png`
- `01-workspace-settings-general-desktop-1440x900-dark.png`
- `01-workspace-settings-general-tablet-landscape-1024x768.png`
- `01-workspace-settings-general-tablet-portrait-768x1024.png`
- `01-workspace-settings-general-mobile-portrait-390x844.png`
- `02-workspace-settings-groups-nested-desktop-1440x900-light.png`
- `03-workspace-settings-trash-retention-desktop-1440x900-light.png`
- `04-project-settings-priorities-desktop-1440x900-light.png`
- `04-project-settings-priorities-desktop-1440x900-dark.png`
- `04-project-settings-priorities-tablet-landscape-1024x768.png`
- `04-project-settings-priorities-tablet-portrait-768x1024.png`
- `04-project-settings-priorities-mobile-portrait-390x844.png`
- `05-project-settings-wip-limits-desktop-1440x900-light.png`
- `05-project-settings-wip-limits-desktop-1440x900-dark.png`
- `05-project-settings-wip-limits-tablet-landscape-1024x768.png`
- `05-project-settings-wip-limits-tablet-portrait-768x1024.png`
- `05-project-settings-wip-limits-mobile-portrait-390x844.png`
- `06-project-settings-danger-zone-desktop-1440x900-light.png`
- `06-project-settings-danger-zone-desktop-1440x900-dark.png`
- `06-project-settings-danger-zone-tablet-landscape-1024x768.png`
- `06-project-settings-danger-zone-tablet-portrait-768x1024.png`
- `06-project-settings-danger-zone-mobile-portrait-390x844.png`
- `08-personal-settings-desktop-1440x900-light.png`
- `08-personal-settings-desktop-1440x900-dark.png`
- `08-personal-settings-tablet-landscape-1024x768.png`
- `08-personal-settings-tablet-portrait-768x1024.png`
- `08-personal-settings-mobile-portrait-390x844.png`
- `10-custom-fields-studio-desktop-1440x900-light.png`
- `10-custom-fields-studio-desktop-1440x900-dark.png`
- `10-custom-fields-studio-tablet-landscape-1024x768.png`
- `10-custom-fields-studio-tablet-portrait-768x1024.png`
- `10-custom-fields-studio-mobile-portrait-390x844.png`
- `11-custom-fields-editor-tier-a-desktop-1440x900-light.png`
- `12-custom-fields-structured-format-desktop-1440x900-light.png`
- `13-custom-fields-escalation-dual-control-desktop-1440x900-light.png`
- `15-workflow-studio-desktop-1440x900-light.png`
- `15-workflow-studio-desktop-1440x900-dark.png`
- `15-workflow-studio-tablet-landscape-1024x768.png`
- `15-workflow-studio-tablet-portrait-768x1024.png`
- `15-workflow-studio-mobile-portrait-390x844.png`
- `16-workflow-attach-hook-dialog-desktop-1440x900-light.png`
- `17-workflow-dry-run-drawer-desktop-1440x900-light.png`
- `18-workflow-git-repo-bindings-desktop-1440x900-light.png`

---

## 5. Specialist Audits Summary

- **API Specialist Review:** `APPROVED` in `docs/qa/KAN-428/api-specialist-review.md`.
- **UI Specialist Review:** `APPROVED` in `docs/qa/KAN-428/ui-specialist-review.md`.

---

## 6. Definition of Done Compliance Matrix

| Requirement | Evidence File / Proof | Status |
| :--- | :--- | :--- |
| Live Workspace Policies & Transitive Groups | `docs/workouts/slice-5-workspace-project-workflows/03-live-workout-report.md` | PASS |
| Live Project Policies, WIP Limits & Danger Zone | `docs/workouts/slice-5-workspace-project-workflows/03-live-workout-report.md` | PASS |
| Custom Scripted Fields, Sandboxing & Dual-Control | `docs/workouts/slice-5-workspace-project-workflows/03-live-workout-report.md` | PASS |
| Workflow Hooks, Dry-Run Drawer & Git Bindings | `docs/workouts/slice-5-workspace-project-workflows/03-live-workout-report.md` | PASS |
| 43 Zero-Mock Screenshots across 5 viewports | `docs/qa/KAN-428/screenshots/` (visually inspected via `read_file`) | PASS |
| 105/105 Backend Pytest Tests Passed | `docs/qa/KAN-428/unit-test-results.txt` | PASS |
| 310/310 Frontend Vitest Tests Passed (>=95% branch) | `docs/qa/KAN-428/unit-test-results.txt` | PASS |
| Static Build Gates & Linters Clean | `docs/qa/KAN-428/build-check.txt` | PASS |
| Zero Forbidden Unicode Dashes | `python3 scripts/check_no_dashes.py` (exit code 0) | PASS |
| Dual Specialist Reviews Signed & Approved | `docs/qa/KAN-428/api-specialist-review.md`, `ui-specialist-review.md` | PASS |
| Verified Changed Files Manifest | `docs/qa/KAN-428/changed-files-manifest.txt` (`sha256sum -c` exit code 0) | PASS |
