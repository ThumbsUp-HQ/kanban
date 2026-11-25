# Forensic QA Reality-Checker Handover Packet

**Ticket:** KAN-427 (`[SLICE-5-P2][KB-GOVERNANCE-SIMPLIFY]`)  
**Parent Epic:** KAN-425 (`[EPIC][SLICE-5-WORKSPACE-PROJECT-WORKFLOWS]`)  
**Target Next Phase:** KAN-428 (`[SLICE-5-P3][KB-GOVERNANCE-E2E]`)  
**Author:** b-kan427 (Paranoiac Android Security Architect)  
**Branch:** `feat/KAN-427-slice5-governance-simplify`  
**Base Commit:** `8c6a77e2`  
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan427-3a52f19e`  

---

## 1. Executive Summary & Zero-Mutation Boundary

This packet provides indisputable forensic verification evidence for ticket **KAN-427 (Phase 2: Simplify Workspace/Project Settings, Custom Scripted Fields & Workflow Studio UI + Wiring)**.

- **Zero Database Migrations:** 100% of existing database schema and Alembic migration chain on `main` is preserved without any new database migrations or DDL mutations.
- **Preserved Core Infrastructure:** Preserves 100% of already-landed work from `KAN-402`, `KAN-403` (`<AgentOnboardingPromptCard>`), and `KAN-404` (`isAal2StepUpCancelled`, `useAal2DirtyKeepalive`) on `main`.
- **Merge Overlap Guard:** Strictly preserved `PersonalSettingsPage.tsx` lines 1099+ (Connected External Identities / LDAP account linking) untouched to prevent merge conflict with concurrent authentication work.
- **Strict Quality Invariants:** Zero linter warnings, safe typing (Mypy clean across 680 files, TypeScript 0 errors), zero `act(...)` or React key warnings, `>=95%` branch coverage across all touched components, and zero Unicode em-dash or en-dash characters (plain ASCII hyphens only).

---

## 2. Inventory of Implemented Changes

### 2.1 Workspace Settings (`WorkspaceSettingsPage.tsx`, `WorkspaceSettingsPage.css`)
- **Idle Timeout Preset Pills:** Added 1-click preset duration pills (`15m`, `30m`, `1h`, `4h`) syncing bidirectionally with the accessible input.
- **Absolute Timeout Duration:** Added human-readable hour/day equivalents (`8h`, `24h`, `7d`) for session expiration.
- **Zero-Trust Webhook Callout:** Converted static non-functional webhook placeholder into an explicit documentation and MCP link card.
- **Consolidated Trash Retention:** Removed duplicate trash retention input and action button on the Trash tab, establishing the General tab as the single authoritative source of truth.
- **Hierarchy Cycle Detection Warning:** Added reactive cycle warning pill (`group-cycle-pill`) alerting administrators when circular group nesting is configured.

### 2.2 Project Settings (`ProjectSettingsPage.tsx`, `ProjectSettingsPage.css`)
- **Priority Quick-Select Palette:** Added quick-select emoji palette for project priorities with instant selection.
- **Danger Zone Visual Distinction:** Separated Stage 1 soft-delete (`mode="trash"`) from Stage 2 permanent purge into distinct amber vs critical warning cards.
- **Reactive Blast-Radius Counters:** Integrated reactive blast-radius counters (`issues_count`, `docs_count`/`pages_count`, `stickies_count`, `modules_count`) displaying exact cascade impacts before confirmation.

### 2.3 Personal Settings (`PersonalSettingsPage.tsx`, `PersonalSettingsPage.css`)
- **Searchable IANA Timezone Filter:** Added real-time search filter across standard IANA timezones while preserving non-standard custom timezones.
- **Auto-Detect Timezone Button:** Added `Auto-detect` button leveraging `Intl.DateTimeFormat().resolvedOptions().timeZone`.
- **Hardware vs Platform Passkey Copy:** Updated subtext and helper guidance distinguishing platform Passkeys (Apple TouchID, Windows Hello, Android) from roaming hardware Security Keys (YubiKey).
- **Preserved LDAP Section:** Preserved lines 1099+ without mutation.

### 2.4 Custom Scripted Fields (`CustomFieldDefinitionEditor.tsx`, `EscalationApprovalPanel.tsx`, `custom-fields.css`)
- **Tier A vs Tier B Flavor Guidance:** Added explicit security guidance and starter templates contrasting deterministic Wasm (Tier A, sub-millisecond, pure functions) against nsjail sandboxed CLI execution (Tier B).
- **Structured Format Metadata Schema:** Added dedicated form inputs for `text`, `number`, and `badge` output schema formats with a raw JSON editor toggle.
- **Literal Tamper Warning Banner:** Implemented modal and banner displaying old vs pending SHA-256 manifest digests when script content is modified.
- **AAL2 Session Elevation Keepalive:** Wired `useAal2DirtyKeepalive(isDirty)` to maintain elevated WebSudo session during custom field definition authoring.

### 2.5 Workflow Studio & Hooks (`AttachHookDialog.tsx`, `DryRunDrawer.tsx`, `GitRepoBindingsSection.tsx`, `workflows.css`)
- **Wasm vs Agent Guidance:** Added clarifying helper text and radio options contrasting synchronous Wasm validators/mutators with asynchronous Agent helpers.
- **Mutable Fields Toggles:** Added `Select All` and `Clear All` quick-select buttons for `allowed_mutable_fields`.
- **Dry-Run Simulation Top Banner:** Added prominent banner (`DRY-RUN SIMULATION: No database changes were committed.`) and visual before/after field diff inspection table.
- **Git PAT Masked Input:** Eliminated `input[type="password"]` on Git PAT inputs, using masked `type="text"` with `.kb-masked-api-key`, `autoComplete="off"`, and password-manager ignore attributes (`data-1p-ignore="true" data-lpignore="true" data-bwignore="true" data-form-type="other"`).
- **SSRF Restriction Guidance:** Added prominent SSRF restriction callout on git bare mirror URL inputs.

---

## 3. Replication & Verification Instructions

Execute the following commands from the workspace root to reproduce all verification results:

```bash
# 1. Run backend Pytest suite (93 passed in 85.09s, 85% coverage on slice modules, 100% on custom fields / hooks)
cat << 'EOF' > .tmp_coveragerc
[run]
branch = True
concurrency = greenlet, thread

[report]
include =
    kanban/api/v1/project_config.py
    kanban/api/v1/workflow_hooks.py
    kanban/workflows/dry_run.py
    kanban/api/v1/custom_fields.py
    kanban/api/v1/custom_field_approvals.py
    kanban/api/v1/admin/workspace_settings.py
    kanban/api/v1/admin/destructive.py
    kanban/api/v1/user_settings.py
EOF
uv run pytest \
  kanban/tests/api/test_workspace_settings.py \
  kanban/tests/api/test_project_config.py \
  kanban/tests/api/test_admin_trash_api.py \
  kanban/tests/api/test_user_personal_settings.py \
  kanban/tests/custom_fields/test_custom_fields_api.py \
  kanban/tests/custom_fields/test_custom_field_approvals_api.py \
  kanban/tests/custom_fields/test_standalone_nsjail_gate.py \
  kanban/tests/workflows/test_workflow_hooks_api.py \
  kanban/tests/workflows/test_dry_run.py \
  --cov=kanban --cov-config=.tmp_coveragerc --cov-report=term-missing
rm -f .tmp_coveragerc

# 2. Run frontend Vitest suite (279 passed in 17.14s, 96.08% overall branch coverage, >=95% on every touched file)
cd kanban/web && npx vitest run \
  src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx \
  src/features/settings/__tests__/ProjectSettingsPage.test.tsx \
  src/features/settings/__tests__/PersonalSettingsPage.test.tsx \
  src/features/custom-fields/__tests__/CustomFieldsStudio.test.tsx \
  src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx \
  src/features/custom-fields/__tests__/EscalationApprovalPanel.test.tsx \
  src/features/workflows/__tests__/WorkflowStudioPage.test.tsx \
  src/features/workflows/__tests__/AttachHookDialog.test.tsx \
  src/features/workflows/__tests__/DryRunDrawer.test.tsx \
  src/features/workflows/__tests__/GitRepoBindingsSection.test.tsx \
  --coverage \
  --coverage.include="src/features/settings/WorkspaceSettingsPage.tsx" \
  --coverage.include="src/features/settings/ProjectSettingsPage.tsx" \
  --coverage.include="src/features/settings/PersonalSettingsPage.tsx" \
  --coverage.include="src/features/custom-fields/CustomFieldDefinitionEditor.tsx" \
  --coverage.include="src/features/custom-fields/EscalationApprovalPanel.tsx" \
  --coverage.include="src/features/workflows/AttachHookDialog.tsx" \
  --coverage.include="src/features/workflows/DryRunDrawer.tsx" \
  --coverage.include="src/features/workflows/GitRepoBindingsSection.tsx" \
  --coverage.thresholds.branches=95

# 3. Run static linters and build checks
uv run ruff check kanban/
python3 scripts/check_no_dashes.py --all
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build
uv run mypy kanban/

# 4. Verify integrity checksums
cd docs/qa/KAN-427 && sha256sum -c changed-files-manifest.txt
```

---

## 4. Visual Evidence & Screenshots

All 25 unclipped multi-viewport captures were recorded via Playwright in `docs/qa/KAN-427/screenshots/` and visually verified via `read_file`:
- `01-workspace-settings-01-desktop-1440x900-light.png` (1440x900)
- `01-workspace-settings-02-desktop-1440x900-dark.png` (1440x900)
- `01-workspace-settings-03-tablet-landscape-1024x768.png` (1024x768)
- `01-workspace-settings-04-tablet-portrait-768x1024.png` (768x1024)
- `01-workspace-settings-05-mobile-portrait-390x844.png` (390x844)
- `02-project-settings-01-desktop-1440x900-light.png` (1440x900)
- `02-project-settings-02-desktop-1440x900-dark.png` (1440x900)
- `02-project-settings-03-tablet-landscape-1024x768.png` (1024x768)
- `02-project-settings-04-tablet-portrait-768x1024.png` (768x1024)
- `02-project-settings-05-mobile-portrait-390x844.png` (390x844)
- `02a-project-settings-priorities-01-desktop-1440x900-light.png` (1440x900)
- `02a-project-settings-priorities-02-desktop-1440x900-dark.png` (1440x900)
- `02a-project-settings-priorities-03-tablet-landscape-1024x768.png` (1024x768)
- `02a-project-settings-priorities-04-tablet-portrait-768x1024.png` (768x1024)
- `02a-project-settings-priorities-05-mobile-portrait-390x844.png` (390x844)
- `02b-project-settings-danger-purge-01-desktop-1440x900-light.png` (1440x900)
- `02b-project-settings-danger-purge-02-desktop-1440x900-dark.png` (1440x900)
- `02b-project-settings-danger-purge-03-tablet-landscape-1024x768.png` (1024x768)
- `02b-project-settings-danger-purge-04-tablet-portrait-768x1024.png` (768x1024)
- `02b-project-settings-danger-purge-05-mobile-portrait-390x844.png` (390x844)
- `03-personal-settings-01-desktop-1440x900-light.png` (1440x900)
- `03-personal-settings-02-desktop-1440x900-dark.png` (1440x900)
- `03-personal-settings-03-tablet-landscape-1024x768.png` (1024x768)
- `03-personal-settings-04-tablet-portrait-768x1024.png` (768x1024)
- `03-personal-settings-05-mobile-portrait-390x844.png` (390x844)

---

## 5. Specialist Audits
- **API Specialist Review:** `APPROVED` in `docs/qa/KAN-427/api-specialist-review.md`.
- **UI Specialist Review:** `APPROVED` in `docs/qa/KAN-427/ui-specialist-review.md`.
