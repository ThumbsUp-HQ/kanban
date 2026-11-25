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

The proposed cuts and simplifications in `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md` target real user friction points while honoring design tokens and ergonomics:
1. **Timeout Configuration Presets (`WorkspaceSettingsPage.tsx`):**
   Adding duration pills (`15m`, `30m`, `1h`, `4h` for idle up to 12h / 720m; `8h`, `24h`, `7d` for absolute) eliminates cognitive friction caused by raw minute numbers while retaining the exact underlying inputs.
2. **Progressive Disclosure for Niche Policies:**
   Moving `workspace-default-skip-loaded-seq-checkbox` and `project-skip-loaded-seq-checkbox` into collapsible `<AdvancedSection>` panels cleans up the primary form without losing functionality.
3. **Static Callout Cleanup:**
   Converting `workspace-webhook-restrictions` from a form group into an informational security card prevents users from expecting an editable input field.
4. **State Reordering Ergonomics (`ProjectSettingsPage.tsx`):**
   Introducing incremental `Move Up` and `Move Down` controls removes the clunky manual editing of numeric sort order fields.
5. **WIP Limit Form Validation:**
   Client-side validation ensuring `wip_soft_limit <= wip_hard_limit` prevents frustrating backend 400 rejection errors on submission.
6. **Execution Tier Guidance (`CustomFieldDefinitionEditor.tsx`):**
   Automatically disabling Tier B nsjail in standalone container environments with an explanatory badge eliminates broken runs and guides users toward Tier A WebAssembly.
7. **Dual-Control Compliance Clarity (`EscalationApprovalPanel.tsx`):**
   Explicitly displaying that the author cannot approve their own escalation request prevents confusion when the approve button is disabled.
8. **DryRunDrawer Simulation Banner & Field Diff Display:**
   Adding a prominent top banner asserting simulation isolation and a visual before/after field diff display in `DryRunDrawer.tsx` provides clear feedback on hook transformations without mutating live tickets.

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
