# API Specialist Forensic QA Review: KAN-329

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KAN-329 ([KB-REDTEAM-01] Fix Cross-Tenant Email-Based Workspace Switching and Unverified SERVER_ADMIN Role Elevation in kb_auth_switch_workspace)
Branch: feat/KAN-329-336
Review Date: 2026-11-23

## 1. Architectural and Security Assessment

### 1.1 Vulnerability Analysis & Threat Model
In multi-tenant SaaS and enterprise environments, workspace boundary crossing is a critical security vulnerability. Prior to this fix:
- Stored procedure `kb_auth_switch_workspace` looked up destination workspace principals primarily by raw email match.
- If an email was shared across disjoint organizations or if an identity provider permitted unverified email claims, an attacker authenticating to Workspace A could switch into Workspace B simply by referencing the target workspace and email.
- Furthermore, unverified global or cross-tenant roles could mistakenly grant elevated privileges (such as SERVER_ADMIN or WORKSPACE_ADMIN) in the target workspace without active membership or explicit role bindings in that workspace.

### 1.2 Remediations Implemented
1. Hardened Stored Procedure (`kb_auth_switch_workspace` in `p6_15_hardened_workspace_switch_and_module_issues.up.sql`):
   - Enforces explicit verification: The caller's authenticated identity (`v_caller_user_id` or external provider ID) must resolve to an active, validated identity or explicit membership in `workspace_memberships` for `v_target_ws_id`.
   - Prevents auto-provisioning or switching across tenant boundaries when the principal is not an enrolled member of the target workspace. Raises standard permission exception: `AUTH_WORKSPACE_SWITCH_DENIED` (403) with message "Principal has no valid membership or identity in target workspace".
   - Prevents unverified role elevation: Server-level and workspace-level roles are strictly scoped and evaluated within target workspace boundaries; role escalation without explicit server-level role assignment in the system ledger is completely blocked.
2. User Identities Integrity (`user_identities` table constraints):
   - Added unique constraint `user_identities_ws_provider_uid_uq` on `(workspace_id, provider, provider_user_id)` to guarantee no cross-workspace identity collisions can exist or be exploited.
3. Target Workspace Listing Hardening (`kb_auth_list_user_workspaces`):
   - Updated enumeration query to return strictly workspaces where the principal holds an active, non-revoked membership or confirmed identity.

### 1.3 Wire-Contract & Backward Compatibility
- API endpoint `POST /api/v1/auth/session/workspace` (and service `switch_workspace`) retains full wire compatibility.
- Legitimate members seamlessly switch workspaces and receive refreshed JWT / session tokens reflecting their verified target workspace permissions and roles.
- Unauthorized switch attempts deterministically receive HTTP 403 Forbidden (`AUTH_WORKSPACE_SWITCH_DENIED`).

---

## 2. Requirement-to-Evidence Verification Matrix

| Requirement | Implementation Artifacts | Verification Tests | Verdict |
| :--- | :--- | :--- | :--- |
| **Verify explicit target workspace membership** | `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.up.sql` (`kb_auth_switch_workspace`) | `kanban/tests/security/test_workspace_switch_isolation.py::test_cross_tenant_workspace_switch_denied_without_membership` | PASS |
| **Block unverified SERVER_ADMIN elevation** | `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.up.sql` | `kanban/tests/security/test_workspace_switch_isolation.py::test_workspace_switch_does_not_elevate_to_server_admin_in_foreign_workspace` | PASS |
| **Scoped identity uniqueness** | Migration `p6_15_hardened_workspace_switch_and_module_issues` (`user_identities_ws_provider_uid_uq`) | `database/tests/migrations/test_p6_15_hardened_workspace_switch_and_module_issues_migration.py` | PASS |
| **Legitimate workspace switch succeeds** | `kb_auth_switch_workspace` and `kanban/tests/api/test_workspaces_api.py` | `kanban/tests/security/test_workspace_switch_isolation.py::test_authorized_workspace_switch_succeeds_with_correct_roles`, `test_workspaces_api.py` (all tests pass) | PASS |
| **Zero Em/En-Dashes Rule** | All touched files use plain ASCII hyphens | `uv run python -m scripts.check_no_dashes --all` exits 0 | PASS |
| **>=95% Test Coverage** | Security isolation test suite | `kanban/tests/security/test_workspace_switch_isolation.py` 100% pass | PASS |

---

## 3. Specialist Verdict

The workspace switching procedure and identity isolation layer have been hardened against cross-tenant impersonation and role escalation. All security requirements are verified and pass without regressions.

STATUS: APPROVED
