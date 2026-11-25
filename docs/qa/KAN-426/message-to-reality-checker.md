# Integration Reality-Checker Briefing: KAN-426

- **Ticket**: `KAN-426` (`[SLICE-5-P1][KB-GOVERNANCE-AUDIT] Phase 1: Workspace/Project Settings, Custom Scripted Fields & Workflows Setting Inventory & Audit`)
- **Parent Epic**: `KAN-425` (`[EPIC][SLICE-5-WORKSPACE-PROJECT-WORKFLOWS]`)
- **Next Phase**: `KAN-427` (`Phase 2 Simplification & Wiring`)
- **Branch**: `fix/p1-audits-rc2` (consolidated Round 2 on `main` at `71b847ba`, base branch `fix/KAN-426-rc1`)
- **Base Commit**: `71b847ba`
- **Review Status**:
  - API Specialist Review: `APPROVED` (`docs/qa/KAN-426/api-specialist-review.md`)
  - UI Specialist Review: `APPROVED` (`docs/qa/KAN-426/ui-specialist-review.md`)
  - Reality Checker Gate: `Pending Clean-Room Reality-Checker re-audit`
- **Screenshots**: `N/A - Read-Only Audit & Specification Handoff Ticket (UI screenshots captured in KAN-427 and KAN-428)`

---

## 1. Key Verified Deliverables

1. **Complete 100% Setting-by-Setting Inventory (`docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md`)**:
   - Comprehensive structured table covering every UI control, label, data-testid, input option, default value, 1-sentence plain-English meaning, backend API route, and explicit disposition.
   - Exact Inventory Summary:
     - Total Settings Audited: `184`
     - Keep (`KEEP`): `175`
     - Simplify (`SIMPLIFY`): `7`
     - Merge (`MERGE`): `2`
     - Move to Advanced (`MOVE_TO_ADVANCED`): `0`
     - Cut (`CUT`): `0`
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

2. **Targeted Simplification Proposals & Cut List (All 9 Implemented Items Removed)**:
   - Workspace Governance: Interactive preset pills (`15m`, `30m`, `1h`, `4h` for idle; `8h`, `24h`, `7d` for absolute) and live human-readable text; convert static webhook restrictions callout into documentation card; inline error pill for circular group hierarchy; remove duplicate trash retention input and button from Trash tab.
   - Project Settings: Quick-pick priority emoji palette; distinctly color-code Stage 1 soft-delete vs Stage 2 permanent purge cards with blast radius counter.
   - Custom Scripted Fields: Structured form inputs for format metadata schema with raw JSON toggle; prominent script tamper warning banner showing old vs new manifest SHA256 hashes.
   - Workflows & Transition Helpers: Differentiate `sync_validator`, `sync_mutator`, and `agent_interceptor` in attach hook dialog; add prominent top simulation banner (`DRY-RUN SIMULATION: No database changes were committed.`) and visual before/after field diff display in dry-run drawer; helpful SSRF validation hints on git mirror URLs.
   - Personal Settings: Timezone auto-detection button and search filter; clarifying subtext distinguishing platform Passkeys from physical FIDO2 Security Keys.

3. **Phase 2 (`KAN-427`) File-Scoped Action Checklist**:
   - Detailed task-by-task checklist mapped directly to target frontend and backend files, deduplicated against `KAN-404` (WebSudo), `KAN-402`, and `KAN-403`, with all 9 already-implemented features cleanly removed.

4. **Phase 3 (`KAN-428`) Credential & Container Checklist**:
   - Exhaustive prerequisite matrix documenting container runtimes (multi-container vs standalone), test principals (`@admin`, `@security-admin` for dual-control sign-off, `@developer`), and test fixtures (Wasm binary, bare git mirror, local AI provider).

5. **Compliance & Invariants**:
   - Zero Unicode em/en-dashes (`check_no_dashes.py` exits 0 with 0 violations).
   - 100% of cited repository file paths verified to exist (23/23 paths including `kanban/repos/url_policy.py`).
   - Zero source code mutations in Phase 1 (read-only audit).
   - Posted updated Phase 1 Handoff Packet comments to both `KAN-425` (comment ID `KAN-425#c-01a2116e`) and `KAN-427` (comment ID `KAN-427#c-01a2116e`) via kanban MCP `add_comment`.
