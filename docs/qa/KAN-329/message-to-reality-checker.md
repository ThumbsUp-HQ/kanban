# Message to Reality-Checker: KAN-329 (`[KB-REDTEAM-01]`)

## Ticket Scope & Browser Screenshot Classification
- **Ticket:** `KAN-329` - `[KB-REDTEAM-01] Fix Cross-Tenant Email-Based Workspace Switching and Unverified SERVER_ADMIN Role Elevation in kb_auth_switch_workspace`
- **Branch:** `feat/KAN-329-336`
- **Browser Screenshots:** `N/A - Non-UI Security Ticket` (Database Migration, Stored Procedure, and Session Security)
- **Owned Slice Modified:**
  - `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.up.sql`
  - `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.down.sql`
  - `database/migrations/versions/p6_15_hardened_workspace_switch_and_module_issues.py`
  - `kanban/tests/security/test_workspace_switch_isolation.py`
  - `kanban/tests/api/test_workspaces_api.py`
  - `docs/qa/KAN-329/*`

## Requirement-to-Evidence Mapping

1. **Prevent Cross-Tenant Email-Based Workspace Switching:**
   - **Implementation:** Hardened `kb_auth_switch_workspace` stored procedure in migration `p6_15_hardened_workspace_switch_and_module_issues`. The procedure now requires the caller to hold a verified identity mapping or existing workspace membership in `workspace_memberships` for the target workspace ID before granting a switch. It strictly denies switching with `AUTH_WORKSPACE_SWITCH_DENIED` if membership is missing.
   - **Evidence:** `docs/qa/KAN-329/git-diff.patch` and `test_cross_tenant_workspace_switch_denied_without_membership` in `kanban/tests/security/test_workspace_switch_isolation.py`.

2. **Deny Unverified Role Elevation to SERVER_ADMIN or WORKSPACE_ADMIN:**
   - **Implementation:** Explicitly verified that role assignment during workspace switch resolves only local target-workspace scoped bindings and valid system-level roles from the system ledger, preventing unverified privilege escalation.
   - **Evidence:** `test_workspace_switch_does_not_elevate_to_server_admin_in_foreign_workspace` in `kanban/tests/security/test_workspace_switch_isolation.py`.

3. **Workspace-Scoped Identity Uniqueness:**
   - **Implementation:** Added unique constraint `user_identities_ws_provider_uid_uq` on `user_identities (workspace_id, provider, provider_user_id)` to eliminate cross-workspace identity collisions.
   - **Evidence:** Migration `p6_15_hardened_workspace_switch_and_module_issues` and `database/tests/migrations/test_p6_15_hardened_workspace_switch_and_module_issues_migration.py`.

4. **Preserve Valid Workspace Switching:**
   - **Implementation:** Legitimate members switch workspaces cleanly with updated JWT and permissions.
   - **Evidence:** `test_authorized_workspace_switch_succeeds_with_correct_roles` and all tests passing in `kanban/tests/api/test_workspaces_api.py`.

5. **Mandatory Quality & Code Hygiene:**
   - Zero em-dashes or en-dashes (`uv run python -m scripts.check_no_dashes --all` exits 0).
   - Full static validation passed (`make check` exits 0).
   - Unit test results: 3/3 passed in `kanban/tests/security/test_workspace_switch_isolation.py` and 2/2 passed in `kanban/tests/api/test_workspaces_api.py`.

All artifacts and checksums are verified in `docs/qa/KAN-329/changed-files-manifest.txt`.
