# UI Specialist Review: KAN-426

**Ticket:** `KAN-426` (`[SLICE-5-P1][KB-GOVERNANCE-AUDIT] Phase 1: Workspace/Project Settings, Custom Scripted Fields & Workflows Setting Inventory & Audit`)  
**Reviewer:** `@ui-spec` (UI Designer & UX Architect)  
**Branch:** `fix/KAN-426-rc1`  
**Base Commit:** `620f66cd`  
**Status:** `APPROVED`  
**Date:** 2026-11-25  

---

## 1. Visual & Interaction Design Evaluation

This review evaluated 100% of the UI screens, drawers, dialogs, form groups, and interaction states across Slice 5:
- `WorkspaceSettingsPage.tsx` (Organization profile, timeouts, member list, nested groups, trash studio)
- `ProjectSettingsPage.tsx` (Project states, WIP limits, priorities, labels, members, danger zone)
- `PersonalSettingsPage.tsx` (Profile, avatars, passwords, WebAuthn Passkeys / FIDO2, TOTP 2FA, identity linking)
- `CustomFieldsStudio.tsx` & `CustomFieldDefinitionEditor.tsx` (Calculated field editor, test panel, formatters)
- `EscalationApprovalPanel.tsx` (Dual-control escalation requests, AAL2 OTP step-up modal)
- `WorkflowStudioPage.tsx` & `AttachHookDialog.tsx` (Transition hook attachments, mutable fields)
- `DryRunDrawer.tsx` (Pre-flight simulation drawer, diff inspection, copy CLI)
- `GitRepoBindingsSection.tsx` (Bare mirror repository connection, sync trigger)

---

## 2. Evaluation of Proposed Dispositions & UX Cuts

The proposed cuts and simplifications in `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md` target real user friction points while honoring design tokens and ergonomics:
1. **Timeout Configuration Presets (`WorkspaceSettingsPage.tsx`):**
   - Adding duration pills (`15m`, `30m`, `1h`, `4h` for idle; `8h`, `24h`, `7d` for absolute) eliminates cognitive friction caused by raw minute numbers while retaining the exact underlying inputs.
2. **Progressive Disclosure for Niche Policies:**
   - Moving `workspace-default-skip-loaded-seq-checkbox` and `project-skip-loaded-seq-checkbox` into collapsible `<AdvancedSection>` panels cleans up the primary form without losing functionality.
3. **Static Callout Cleanup:**
   - Converting `workspace-webhook-restrictions` from a form group into an informational security card prevents users from expecting an editable input field.
4. **State Reordering Ergonomics (`ProjectSettingsPage.tsx`):**
   - Introducing incremental `Move Up` and `Move Down` controls removes the clunky manual editing of numeric sort order fields.
5. **WIP Limit Form Validation:**
   - Client-side validation ensuring `wip_soft_limit <= wip_hard_limit` prevents frustrating backend 400 rejection errors on submission.
6. **Execution Tier Guidance (`CustomFieldDefinitionEditor.tsx`):**
   - Automatically disabling Tier B nsjail in standalone container environments with an explanatory badge eliminates broken runs and guides users toward Tier A WebAssembly.
7. **Dual-Control Compliance Clarity (`EscalationApprovalPanel.tsx`):**
   - Explicitly displaying that the author cannot approve their own escalation request prevents confusion when the approve button is disabled.

---

## 3. Whitespace, Contrast, & Accessibility Compliance

- All inputs and buttons maintain minimum 44px touch targets.
- Text contrast ratios exceed WCAG AA (4.5:1 for body copy, 3:1 for large headers).
- Form inputs have associated `<label>` elements and descriptive `FieldHelpHint` tooltips.
- The 2-stage destructive cards in Project Settings use clear color semantics (amber warning for soft delete vs crimson danger for permanent purge).

---

## 4. Specialist Verdict

The Phase 1 inventory and simplification cut list in `01-audit-and-cuts.md` provides an outstanding, highly actionable foundation for Phase 2 implementation (`KAN-427`).

**Verdict: APPROVED**
