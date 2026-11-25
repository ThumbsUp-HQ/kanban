# UI Specialist Review: KAN-426

**Ticket:** `KAN-426` (`[SLICE-5-P1][KB-GOVERNANCE-AUDIT] Phase 1: Workspace/Project Settings, Custom Scripted Fields & Workflows Setting Inventory & Audit`)  
**Reviewer:** `@ui-spec` (UI Designer & UX Architect)  
**Branch:** `fix/p1-audits-rc2` (consolidated Round 2 on `main` at `71b847ba`)  
**Base Commit:** `71b847ba`  
**Status:** `APPROVED`  
**Date:** 2026-11-25  

---

## 1. Visual & Interaction Design Evaluation

This review evaluated 100% of the UI screens, drawers, dialogs, form groups, and interaction states across Slice 5:
- `WorkspaceSettingsPage.tsx`: Organization profile, timeouts (`session_idle_timeout_min` bounded to 12 hours / 720 minutes; `session_absolute_timeout_min` bounded to 7 days / 10080 minutes), member list, nested groups, 4-tier issue export roles (`workspace_admin`, `project_admin`, `member`, `guest`), and trash studio (`restore-btn-${item.id}`, `permanent-purge-btn-${item.id}`, phrase confirmation, and audit reason input).
- `ProjectSettingsPage.tsx`: Project states, sort order, WIP limits (`state-wip-soft-input` and `state-wip-hard-input` bounded to `ge=1, le=999` with `0` blocked), priorities, labels, members, and danger zone.
- `PersonalSettingsPage.tsx`: Profile, avatars (handled via `PUT /api/v1/auth/me/avatar` with 2 MiB ceiling and SVG rejection), passwords, WebAuthn Passkeys / FIDO2 (`delete-passkey-${pk.id}`), TOTP 2FA, and identity linking (`unlink-identity-${ident.id}`).
- `CustomFieldsStudio.tsx` & `CustomFieldDefinitionEditor.tsx`: Calculated field editor, test panel, formatters, and tier selection.
- `EscalationApprovalPanel.tsx`: Dual-control escalation requests and AAL2 OTP step-up modal.
- `WorkflowStudioPage.tsx` & `AttachHookDialog.tsx`: Transition hook attachments, authorized `MUTABLE_FIELD_UNIVERSE` (`labels, priority, assignees, start_date, due_date, cycle, custom_fields.risk_rating, custom_fields.qa_status, custom_fields.security_review`), with `IMMUTABLE_FIELDS_NOTICE` asserting that `summary, description_markdown, state, parent, created_by` are strictly immutable.
- `DryRunDrawer.tsx`: Pre-flight simulation drawer with `<input type="text">` for `dry-run-priority`, sample ticket tabs, visual diff inspection, and copy CLI command.
- `GitRepoBindingsSection.tsx`: Bare mirror repository connection with `bare_git_tools` and `ro_vfs_mount` access modes, SSRF validation via `url_policy.py`, and mirror actions using accessible labels (`aria-label="Refresh mirror ${b.slug}"` and `aria-label="Remove mirror ${b.slug}"`).

---

## 2. Evaluation of Proposed Dispositions & UX Cuts

The genuine Phase 2 proposals in `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md` Sections 3 & 4 target real user friction points while honoring design tokens and ergonomics:
1. **Timeout Configuration Presets & Informational Security Banner (`WorkspaceSettingsPage.tsx`):**
   Adding duration pills (`15m`, `30m`, `1h`, `4h` for idle up to 12h / 720m; `8h`, `24h`, `7d` for absolute) eliminates cognitive friction, while converting `workspace-webhook-restrictions` from a static form group into an informational security callout clarifies read-only network restrictions.
2. **Trash Retention Consolidation (`MERGE`):**
   Consolidating duplicate trash retention controls from the Trash tab into the canonical General tab eliminates setting divergence and confusion.
3. **Circular Hierarchy Prevention:**
   Disabling member additions and highlighting invalid rows when circular group inheritance is detected prevents submission failures.
4. **Project Settings Danger Zone & Priority Palette (`ProjectSettingsPage.tsx`):**
   Adding a quick-select emoji palette for `priority-emoji-input`, and applying distinct color styling and blast radius counters to Stage 1 soft-delete (`mode="trash"`) versus Stage 2 permanent purge cards.
5. **Custom Field Format Metadata Form & Tamper Diff Notice (`CustomFieldDefinitionEditor.tsx`):**
   Providing structured inputs for text, number, and badge formats (with raw JSON fallback toggle) reduces schema syntax errors, while making the tamper warning alert display old versus new manifest SHA256 digests prior to saving.
6. **Workflow Hook Kind Clarity & Mutable Field Toggles (`AttachHookDialog.tsx`):**
   Adding descriptive copy differentiating `sync_validator`, `sync_mutator`, and `agent_interceptor` hooks, paired with quick "Select All" and "Clear All" toggles for authorized mutable fields.
7. **DryRunDrawer Simulation Banner & Visual Field Diff (`DryRunDrawer.tsx`):**
   Adding a prominent top banner asserting simulation isolation (`DRY-RUN SIMULATION: No database changes were committed.`) and a unified visual before-and-after field diff display for proposed mutations.
8. **Git Repository Bare Mirror SSRF Hints (`GitRepoBindingsSection.tsx`):**
   Providing informative error callouts explaining SSRF blocks on private/internal IP ranges and cloud metadata endpoints.
9. **Timezone Auto-Detection & Passkey vs Security Key Terminology (`PersonalSettingsPage.tsx`):**
   Adding an "Auto-Detect Timezone" button with search filter for `timezone-select`, and updating explanatory subtext distinguishing synced biometric Passkeys from physical hardware Security Keys.

---

## 3. Inventory Parity & Accessibility Compliance

- **Exact Inventory Parity (184 items):**
  - Total Cataloged Settings: 184
  - KEEP: 175
  - SIMPLIFY: 7
  - MERGE: 2
  - MOVE_TO_ADVANCED: 0
  - CUT: 0
- **Whitespace & Contrast:**
  All inputs and buttons maintain minimum 44px touch targets. Text contrast ratios exceed WCAG AA standards.
- **Typography & Dashes:**
  Strict plain ASCII hyphens verified across all files (0 forbidden Unicode em/en-dashes).

---

## 4. Specialist Verdict

The Phase 1 inventory and simplification cut list in `01-audit-and-cuts.md` provides an outstanding, highly actionable foundation for Phase 2 implementation (`KAN-427`).

**Verdict: APPROVED**
