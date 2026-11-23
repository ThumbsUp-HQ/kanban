# API Specialist Forensic QA Review: KAN-83

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KAN-83 ([KB-GRANULAR-RBAC] Add Narrative Workspace/Issue/Field RBAC Policy Builder, Custom Multi-Role User Labels, and Granular API Permission Enforcement)
Branch: feat/KAN-83
Review Date: 2026-11-22

## 1. Architectural and Engineering Assessment

### 1.1 Granular Permissions Catalog and Security Evaluator (kanban/security/granular_permissions.py)
- Implements all 30 canonical permissions across three distinct tiers:
  - workspace (8): workspace:create, workspace:edit_settings, workspace:delete, workspace:manage_members, workspace:manage_billing, workspace:export_data, workspace:manage_integrations, workspace:view_audit_log
  - issue (10): issue:create, issue:view, issue:edit, issue:delete, issue:transition, issue:assign, issue:comment, issue:move, issue:archive, issue:link
  - field (12): field:title, field:description, field:state, field:priority, field:assignees, field:dates, field:cycle_id, field:modules, field:custom_fields, field:subtasks, field:attach_files, field:estimate_sp
- evaluate_granular_permissions() seamlessly unions built-in role capabilities with assigned principal_role_labels.
- Evaluates token scope and credential boundaries: Project-scoped tokens cannot access workspace-scoped permissions; User-credential tokens cannot exercise server-admin permissions.
- Zero-leakage error semantics: returns 404 NOT_FOUND if issue:view or Capability.VIEW is absent, or 403 INSUFFICIENT_PERMISSION with detailed missing_permissions payload when entity is readable but caller lacks required mutation permissions.

### 1.2 Multi-Role Labels and Additive ERA Rebuild (Problem 1)
- Schema additions in migration p6_12_granular_rbac_roles:
  - rbac_roles, rbac_role_permissions, and principal_role_labels with ENABLE and FORCE ROW LEVEL SECURITY.
  - Automatically derives 8-bit base_capability_mask per role from assigned granular permissions.
  - rebuild_effective_access_for_workspace() incorporates principal_role_labels across principal_group_closure, performing additive bitwise OR into effective_role_bindings.

### 1.3 Strict Tier Governance and Escalation Prevention (Problem 3)
- Rule 1: WORKSPACE_ADMIN cannot modify workspace:* permissions or bind roles granting workspace:* permissions (enforced with 403 WORKSPACE_PERMISSION_LOCKED at API layer and SQLSTATE 42501 DB trigger trg_enforce_rbac_tier_governance).
- Rule 1 (System Admin Protection): WORKSPACE_ADMIN cannot delete or modify system-admin role (SQLSTATE 42501).
- Rule 2: Standard User cannot modify issue:* or field:* permissions (403 INSUFFICIENT_CAPABILITY).
- Rule 3: WORKSPACE_ADMIN and SERVER_ADMIN can create custom roles (POST /api/v1/admin/rbac/roles with Depends(require_admin_aal2)). If cloned from system-admin by a WORKSPACE_ADMIN, workspace:* permissions are stripped automatically.

### 1.4 API-Wide Enforcement Across Endpoints (Problem 2)
- POST /api/v1/workspaces checks workspace:create.
- PATCH /api/v1/workspaces/{id} checks workspace:edit_settings and requires require_admin_aal2.
- POST/DELETE /api/v1/workspaces/{id}/role-bindings checks workspace:manage_members and requires require_admin_aal2.
- POST /api/v1/projects/{ref}/attachments checks field:attach_files, permanently closing the VIEWER upload bug.
- PATCH /api/v1/issues/{key} and sibling mutation endpoints (/assignees, /cycles, /modules, /transitions, /begin-work, /transition, /complete-work, /move, /custom-fields, /links, /comments, /archive, /delete) check specific granular issue:* and field:* permissions.

## 2. Test Verification and Quality Metrics

- Database RLS and Trigger Tests: database/tests/test_granular_rbac_rls.py (8/8 tests PASSED)
- API and Endpoint Enforcement Tests: kanban/tests/api/test_granular_rbac_api.py (7/7 tests PASSED)
- Migration Lifecycle Tests: database/tests/migrations/test_p6_12_granular_rbac_roles_migration.py (1/1 test PASSED)
- Total Python Backend Tests: 16/16 PASSED in 5.98s
- Static Analysis: ruff check (0 errors), ruff format (0 errors), lint-imports (0 errors, 2 kept), single-head migration check (valid head p6_12_granular_rbac_roles)
- Plain ASCII Check: scripts.check_no_dashes --all passed with 0 errors.

## 3. Specialist Verdict

The granular RBAC implementation, multi-role label assignments, tier governance rules, and API-wide enforcement satisfy all security, architectural, and data integrity invariants.

STATUS: APPROVED
