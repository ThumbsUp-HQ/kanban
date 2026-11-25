# Integration Reality-Checker Briefing: KAN-426

- **Ticket**: `KAN-426` (`[SLICE-5-P1][KB-GOVERNANCE-AUDIT] Phase 1: Workspace/Project Settings, Custom Scripted Fields & Workflows Setting Inventory & Audit`)
- **Parent Epic**: `KAN-425` (`[EPIC][SLICE-5-WORKSPACE-PROJECT-WORKFLOWS]`)
- **Next Phase**: `KAN-427` (`Phase 2 Simplification & Wiring`)
- **Branch**: `docs/KAN-426-slice5-audit`
- **Base Commit**: `2673a4c96cb1bd2e5bd94e7e53be28d8ec2d3460`
- **Review Status**:
  - API Specialist Review: `APPROVED` (`docs/qa/KAN-426/api-specialist-review.md`)
  - UI Specialist Review: `APPROVED` (`docs/qa/KAN-426/ui-specialist-review.md`)
- **Screenshots**: `N/A - Read-Only Audit & Specification Handoff Ticket (UI screenshots captured in KAN-427 and KAN-428)`

---

## Key Verified Deliverables

1. **Complete 100% Setting-by-Setting Inventory (`docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md`)**:
   - Comprehensive structured table covering every UI control, label, data-testid, input option, default value, 1-sentence plain-English meaning, backend API route, and explicit disposition (`KEEP`, `SIMPLIFY`, `MERGE`, `MOVE_TO_ADVANCED`, `CUT`).
   - 10 Frontend Files Audited:
     - `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx`
     - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`
     - `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
     - `kanban/web/src/features/custom-fields/CustomFieldsStudio.tsx`
     - `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`
     - `kanban/web/src/features/custom-fields/EscalationApprovalPanel.tsx`
     - `kanban/web/src/features/workflows/WorkflowStudioPage.tsx`
     - `kanban/web/src/features/workflows/AttachHookDialog.tsx`
     - `kanban/web/src/features/workflows/DryRunDrawer.tsx`
     - `kanban/web/src/features/workflows/GitRepoBindingsSection.tsx`
   - 9 Backend Modules Audited:
     - `kanban/api/v1/admin/workspace_settings.py`
     - `kanban/api/v1/admin/destructive.py`
     - `kanban/api/v1/project_config.py`
     - `kanban/api/v1/custom_fields.py`
     - `kanban/api/v1/custom_field_approvals.py`
     - `kanban/api/v1/custom_field_execution.py`
     - `kanban/api/v1/workflow_hooks.py`
     - `kanban/api/v1/repo_bindings.py`
     - `kanban/api/v1/user_settings.py`

2. **Targeted Simplification Proposals & Cut List**:
   - Workspace Governance: Interactive preset pills (`15m`, `30m`, `1h`, `4h`) for idle timeout; progressive disclosure for sequence numbering; conversion of static webhook callout into documentation card.
   - Project Settings: Incremental `Move Up` / `Move Down` state ordering; client-side WIP soft vs hard limit validation; quick-pick emoji palette for priorities; color-coded 2-stage danger zone cards with blast radius counter.
   - Custom Scripted Fields: Dynamic runtime check disabling Tier B nsjail in standalone containers with guidance badge; structured format metadata inputs; dual-control escalation compliance notice (preventing author self-approval); prominent manifest SHA256 tamper warning.
   - Workflows & Transition Helpers: Clear guidance distinguishing deterministic Wasm hooks from probabilistic Agent hooks; transactional savepoint isolation banner in dry-run drawer; helpful SSRF validation hints on git mirror URLs.
   - Personal Settings: Timezone auto-detection; client-side 2 MiB avatar file validation; clear terminology distinguishing platform Passkeys from physical FIDO2 Security Keys.

3. **Phase 2 (`KAN-427`) File-Scoped Action Checklist**:
   - Detailed task-by-task checklist mapped directly to target frontend and backend files, deduplicated against `KAN-404` (WebSudo), `KAN-402`, and `KAN-403`.

4. **Phase 3 (`KAN-428`) Credential & Container Checklist**:
   - Exhaustive prerequisite matrix documenting container runtimes (multi-container vs standalone), test principals (`@admin`, `@security-admin` for dual-control sign-off, `@developer`), and test fixtures (Wasm binary, bare git mirror, local AI provider).

5. **Compliance & Invariants**:
   - Zero Unicode em/en-dashes (`check_no_dashes.py` exits 0 with 0 violations).
   - 100% of cited repository file paths verified to exist.
   - Zero source code mutations in Phase 1 (read-only audit).
