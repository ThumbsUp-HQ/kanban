# Slice 5: Workspace, Project, Custom Fields & Workflows Simplification: Implemented Changes & Phase 3 Workout Plan

**Document Identifier:** `KB-SLICE5-P2-CHANGES-01`  
**Tracking Ticket:** `KAN-427` (`[SLICE-5-P2][KB-GOVERNANCE-SIMPLIFY]`)  
**Base Commit:** `8c6a77e2`  
**Target Branch:** `feat/KAN-427-slice5-governance-simplify`  
**License:** `Apache-2.0`  
**Verification Date:** November 25, 2026  

---

## 1. Executive Summary

This document details the complete technical implementation of Phase 2 (`KAN-427`) for Slice 5 (Workspace Settings, Project Settings, Custom Scripted Fields, and Workflow Studio UI and Wiring). All modifications strictly satisfy the zero-database-migration mandate, preserve 100% of already-landed `KAN-402`, `KAN-403`, and `KAN-404` invariants, eliminate UI bloat and UX friction, and harden security boundaries.

Every change maps 1:1 against the audit and cuts established in `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md`.

---

## 2. Implemented Changes by Surface

### 2.1 Workspace Settings (`WorkspaceSettingsPage.tsx`, `WorkspaceSettingsPage.css`)
1. **Preset Duration Pills for Idle Timeout:**
   - Implemented quick-select pills (`15m`, `30m`, `1h`, `4h`) under `workspace-idle-timeout-input`.
   - Wired reactive helper rendering human-readable duration (`data-testid="idle-readable-duration"`, e.g. "15 minutes", "1 hour").
2. **Human-Readable Day/Hour Breakdown for Absolute Timeout:**
   - Added live readable duration indicator (`data-testid="abs-readable-duration"`, e.g. "24 hours (1 day)", "7 days (168 hours)").
3. **Webhook Restrictions Security Callout:**
   - Converted the static, non-functional webhook placeholder into an informational Zero-Trust security card (`data-testid="workspace-webhook-restrictions"`).
   - Linked directly to `/docs/zero-trust-security-and-access-visibility` (`data-testid="webhook-restrictions-doc-link"`).
4. **Trash Retention Policy Consolidation:**
   - Removed the duplicate retention input (`workspace-trash-retention-input-trash-tab`) and save button (`save-trash-retention-btn`) from the Trash tab.
   - Preserved the canonical control on the General tab (`workspace-trash-retention-input`), displaying a clean policy callout linking back to General settings.
5. **Administrative Group Circular Hierarchy Prevention:**
   - Disabled the "Add Member" button when an invalid circular group assignment is selected (`data-testid="group-add-member-btn"`).
   - Rendered inline warning pill (`data-testid="group-cycle-pill"`) on the cyclic member candidate.

### 2.2 Project Settings (`ProjectSettingsPage.tsx`, `ProjectSettingsPage.css`)
1. **Priority Quick-Pick Emoji Palette:**
   - Integrated quick-select emoji palette container (`data-testid="priority-emoji-palette"`) surrounding `priority-emoji-input`.
   - Provided instant selection buttons for standard priority glyphs: `🔴`, `🟠`, `🟡`, `🔵`, `✅`, `🔥`, `⚡`, `⏳` (`data-testid="priority-emoji-btn-${emoji}"`).
2. **2-Stage Irreversible Danger Zone Visual Distinction:**
   - Stage 1 Soft Delete card styled with distinct warning amber visual border and background (`data-testid="danger-card-trash"`, `.kb-danger-card-trash`).
   - Stage 2 Permanent Purge card styled with critical crimson double-border and background (`data-testid="danger-card-purge"`, `.kb-danger-card-purge`).
   - Reinforced two-stage requirement: Permanent Purge button remains disabled with descriptive hint until Stage 1 soft-deletion has been executed.
3. **Reactive Blast-Radius Impact Counters:**
   - Added structured blast radius counters container (`data-testid="blast-radius-counters"`).
   - Rendered explicit impact pills:
     - Issues: `data-testid="blast-count-issues"`
     - Docs / Pages: `data-testid="blast-count-docs"`
     - Stickies: `data-testid="blast-count-stickies"`
     - Modules: `data-testid="blast-count-modules"`
   - Maintained string summary fallback (`data-testid="blast-summary-text"`) for non-object responses.

### 2.3 Personal Settings (`PersonalSettingsPage.tsx`, `PersonalSettingsPage.css`)
1. **Timezone Search Filter & Auto-Detection:**
   - Added searchable filter input (`data-testid="timezone-filter-input"`) filtering dynamically across all standard IANA timezones while preserving existing select options.
   - Added "Auto-detect" button (`data-testid="timezone-auto-detect-btn"`) resolving timezone automatically via `Intl.DateTimeFormat().resolvedOptions().timeZone`.
2. **Passkeys vs Hardware Security Keys Guidance:**
   - Added descriptive subtext under `add-passkey-btn` (`data-testid="passkey-helper-copy"`) explaining ecosystem synchronization across Touch ID, Windows Hello, iCloud Keychain, and Google Password Manager.
   - Added descriptive subtext under `add-fido2-key-btn` (`data-testid="security-key-helper-copy"`) explaining the requirement for a physical USB/NFC hardware security token (such as YubiKey or Titan Key).
3. **Merge Overlap Guard:**
   - Left lines 1099+ (Connected External Identities and LDAP linking) strictly untouched to avoid conflicting with concurrent security work.

### 2.4 Custom Scripted Fields (`CustomFieldDefinitionEditor.tsx`, `EscalationApprovalPanel.tsx`, `custom-fields.css`)
1. **Tier A vs Tier B Sandbox Flavor Guidance:**
   - Added prominent inline sandbox guidance pill (`data-testid="flavor-guidance-callout"`) differentiating Tier A (Wasm in-process sandbox, zero external egress) from Tier B (nsjail namespace isolation with egress allowlist).
2. **Structured Format Metadata Schema Form:**
   - Implemented structured form editor (`data-testid="structured-format-metadata"`) for common output formats (`text`, `number`, `badge`):
     - `text`: `meta-text-max-length`, `meta-text-prefix`, `meta-text-monospace`.
     - `number`: `meta-number-precision`, `meta-number-unit-suffix`, `meta-number-currency`.
     - `badge`: `meta-badge-color`, `meta-badge-labels`.
   - Added toggle button (`data-testid="toggle-raw-metadata-btn"`) allowing seamless switching between structured controls and raw JSON textarea.
   - Bi-directionally synchronized structured controls with the underlying `format-metadata-textarea`.
3. **Script Modification Tamper Detection SHA-256 Digest Notice:**
   - Enhanced the tamper confirmation modal (`data-testid="tamper-confirm-dialog"`) with `data-testid="tamper-digests-box"`.
   - Displayed verbatim current approved SHA-256 (`data-testid="tamper-old-sha"`) alongside modified pending SHA-256 (`data-testid="tamper-new-sha"`).
   - Maintained literal mandatory warning: `Saving changes manifest_sha256 and immediately revokes the current approval.` (`data-testid="tamper-warning-literal"`).
4. **WebSudo AAL2 Keepalive Wiring:**
   - Wired `useAal2DirtyKeepalive(isDirty)` into both `CustomFieldDefinitionEditor.tsx` and `EscalationApprovalPanel.tsx` to prevent mid-edit session drops.

### 2.5 Workflows Studio (`AttachHookDialog.tsx`, `DryRunDrawer.tsx`, `GitRepoBindingsSection.tsx`, `workflows.css`)
1. **Deterministic Wasm vs Probabilistic Agent Hook Clarity:**
   - Added explicit sub-headings to the Hook Kind radio group differentiating deterministic rules (`Sync Wasm Validator`, `Sync Wasm Mutator`) from contextual probabilistic reasoning (`Agent Transition Helper`).
2. **Allowed Mutable Fields Quick Actions:**
   - Added "Select All" (`data-testid="select-all-mutable-fields-btn"`) and "Clear All" (`data-testid="clear-all-mutable-fields-btn"`) buttons for rapid field permission management while strictly respecting immutable fields (`state`, `description_markdown`).
3. **Dry-Run Drawer Safety Top Banner & Visual Diff:**
   - Inserted prominent top simulation warning banner (`data-testid="dry-run-simulation-banner"`): `DRY-RUN SIMULATION: No database changes were committed.`
   - Integrated visual before/after field diff table (`data-testid="dry-run-diff-${order}"`) clearly contrasting original ticket values with proposed mutations.
4. **Git Repository Bare Mirror SSRF Hardening & Masked Secret Inputs:**
   - Added SSRF restriction callout (`data-testid="repo-url-ssrf-callout"`) documenting the blocking of private IP ranges and cloud metadata services.
   - Verified zero `input[type="password"]` elements. Masked PAT input (`data-testid="repo-pat-input"`) uses `type="text"`, class `.kb-masked-api-key`, `autoComplete="off"`, `data-1p-ignore="true"`, `data-lpignore="true"`, `data-bwignore="true"`, and `data-form-type="other"`.

---

## 3. Backend Validation Invariants

All backend route modules were audited and validated against Slice 5 requirements:
- `kanban/api/v1/admin/workspace_settings.py`: Enforces idle timeout (5 to 720 minutes) and absolute session timeout (60 to 10080 minutes).
- `kanban/api/v1/admin/destructive.py`: Validates mode parameters (`mode="trash"`, `mode="permanent_purge"`), HMAC confirmation tokens, and blast radius calculations.
- `kanban/api/v1/project_config.py`: Rejects workflow state updates where `wip_soft_limit > wip_hard_limit`.
- `kanban/api/v1/custom_fields.py`: Validates field definitions, target scopes (`PROJECT`, `WORKSPACE`, `SERVER`), and credential modes.
- `kanban/api/v1/custom_field_approvals.py`: Rejects self-approval for scope escalation.
- `kanban/api/v1/custom_field_execution.py`: Enforces execution sandboxes and rate limits.
- `kanban/api/v1/workflow_hooks.py`: Validates hook transition bindings, Wasm bytecode SHA-256 hashes, and agent definitions.
- `kanban/api/v1/repo_bindings.py`: Enforces SSRF policy via `kanban/repos/url_policy.py`, blocking private networks and loopback interfaces.
- `kanban/api/v1/user_settings.py`: Enforces password complexity (>=12 characters, >=14 for admins) and preserves `AgentOnboardingPrefsPatch`.

---

## 4. Phase 3 (KAN-428) Live Workout Script Plan

This step-by-step test plan provides exact operations to validate the simplified governance features in live running containers.

### Workout 1: Workspace Idle & Absolute Session Timeouts and Webhook Documentation
1. Navigate to `/admin/workspace`.
2. Click the `30m` pill under Idle Session Timeout; verify `workspace-idle-timeout-input` updates to `30` and `idle-readable-duration` displays "30 minutes".
3. Enter `1440` in Absolute Session Timeout; verify `abs-readable-duration` displays "24 hours (1 day)".
4. Click Save Settings; verify successful notification and persistence.
5. In the Webhooks section, verify that static non-functional inputs are absent and the Zero-Trust documentation banner links to `/docs/zero-trust-security-and-access-visibility`.
6. On the Trash tab, verify that duplicate retention inputs are removed and a notice directs configuration to the General tab.

### Workout 2: Project Settings Priority Palette & 2-Stage Danger Zone
1. Navigate to `/projects/KAN/settings?tab=priorities`.
2. In the Add Priority form, click the `🔥` button in `priority-emoji-palette`; verify `priority-emoji-input` populates with `🔥`.
3. Switch to the Danger Zone tab (`tab=danger`).
4. Verify Stage 1 Soft Delete card has amber warning styling (`danger-card-trash`) and Stage 2 Permanent Purge has crimson critical styling (`danger-card-purge`).
5. Verify Permanent Purge button is disabled when project is not soft-deleted.
6. Click "Move Project to Trash"; verify confirmation card displays `blast-radius-counters` with non-zero counts for work items, docs, stickies, and modules.

### Workout 3: Custom Field Sandboxing, Structured Formats, and Tamper SHA-256 Revocation
1. Navigate to `/projects/KAN/settings/custom-fields`.
2. Click "New Custom Field Definition".
3. In Flavor select, verify the guidance pill displays Tier A (Wasm / Built-in).
4. Select Output Format: `number`. Verify structured inputs appear for Max Decimals, Unit Suffix, and Currency Symbol.
5. Enter `$` in Currency Symbol and `2` in Max Decimals; click "Edit Raw JSON" and verify JSON synchronizes to `{"maximum_fraction_digits": 2, "currency_symbol": "$"}`.
6. Select an approved custom field definition, modify its script source code, and click Save.
7. Verify `tamper-confirm-dialog` opens displaying both the current approved SHA-256 (`tamper-old-sha`) and the modified pending SHA-256 (`tamper-new-sha`).

### Workout 4: Workflow Studio Wasm vs Agent Hooks, Dry-Run Simulation, and Git Mirror SSRF
1. Navigate to `/projects/KAN/settings/workflows`.
2. Click "Attach Transition Hook".
3. Verify that hook kind choices clearly separate deterministic Wasm hooks from probabilistic Agent helpers.
4. Select `Sync Wasm Mutator`, expand Advanced Hook Settings, and click "Select All" under Allowed Mutable Fields; verify all eligible fields are checked. Click "Clear All"; verify selection clears.
5. Launch Dry-Run Drawer for a transition; verify top simulation banner `DRY-RUN SIMULATION: No database changes were committed.` is prominently displayed.
6. Execute dry-run with sample mutations; verify before/after field diff table clearly indicates modified fields.
7. Switch to Git Repositories tab, click "+ Bind Git Repository", and enter `http://192.168.1.50/repo.git`; verify SSRF restriction warning triggers and input rejects private network.
8. Select credential "Workspace Personal Access Token (PAT)"; verify token field is rendered with masked styling and zero password fields exist.

### Workout 5: Personal Settings Timezone & Passkey Clarification
1. Navigate to `/settings/personal`.
2. In the Timezone section, type `tokyo` into `timezone-filter-input`; verify dropdown filters to `Asia/Tokyo`.
3. Click "Auto-detect"; verify timezone resolves to current browser environment.
4. In the Passkeys & Security Keys section, verify that `passkey-helper-copy` describes platform ecosystem synchronization and `security-key-helper-copy` clarifies hardware USB/NFC token requirements.

---

## 5. Verification Matrix

| Validation Suite | Command | Result |
| :--- | :--- | :--- |
| **Python Ruff Lint** | `uv run ruff check kanban/` | Pass (0 warnings) |
| **Python MyPy Typing** | `uv run mypy kanban/` | Pass (0 errors across 680 files) |
| **No-Dash Compliance** | `python3 scripts/check_no_dashes.py --all` | Pass (0 em/en-dashes) |
| **Frontend TypeScript** | `pnpm --dir kanban/web typecheck` | Pass (0 errors) |
| **Frontend ESLint** | `pnpm --dir kanban/web lint` | Pass (0 warnings) |
| **Frontend Build** | `pnpm --dir kanban/web build` | Pass (Clean production build) |
| **Backend Feature Tests** | `pytest tests/unit/api/...` | Pass (93/93 tests passing in 85.09s, 85% coverage on slice modules, 100% on custom fields & hooks) |
| **Frontend Feature Tests** | `vitest run src/features/...` | Pass (280/280 tests passing, >=95% branch coverage on all touched components) |
