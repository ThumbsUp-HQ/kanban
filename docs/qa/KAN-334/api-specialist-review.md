# API Specialist Forensic QA Review: KAN-334

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KAN-334 ([KB-REDTEAM-03] Enforce security_invoker on module_issues View to Prevent Row-Level Security Bypass)
Branch: feat/KAN-329-336
Review Date: 2026-11-23

## 1. Architectural and Security Assessment

### 1.1 Threat Model & PostgreSQL View Semantics
In PostgreSQL 15+, views by default execute using the permissions and security context of the view owner (`security_definer` behavior).
Prior to this remediation:
- The `module_issues` view joined `issue_modules` and `issues`.
- Because the view was defined under migration owner permissions without `WITH (security_invoker = true)`, unprivileged users querying the view could bypass `FORCE ROW LEVEL SECURITY` on `issues`.
- An attacker querying `SELECT * FROM module_issues` could enumerate issue IDs linked to modules across private projects or restricted workspaces that they had no permission to view.

### 1.2 Remediations Implemented
1. Single Linear Migration (`p6_15_hardened_workspace_switch_and_module_issues.up.sql`):
   - Defined `CREATE OR REPLACE VIEW module_issues WITH (security_invoker = true) AS SELECT im.module_id, im.issue_id, im.workspace_id, im.added_at, im.added_by_id FROM issue_modules im JOIN issues i ON im.issue_id = i.id;`.
   - Explicitly verified column alignment against `issue_modules` schema (`module_id`, `issue_id`, `workspace_id`, `added_at`, `added_by_id`).
   - Down migration cleanly restores the previous view state.
2. PostgreSQL RLS Enforcement Verification:
   - When queried under `kanban_app` session authority with caller GUCs (`request.jwt.claim.sub`, `request.jwt.claim.workspace_id`), PostgreSQL evaluates all row security policies on the underlying `issues` and `issue_modules` tables using the invoking user's context.
   - Any issue row denied by RLS policies is completely omitted from the view result set.

---

## 2. Requirement-to-Evidence Verification Matrix

| Requirement | Implementation Artifacts | Verification Tests | Verdict |
| :--- | :--- | :--- | :--- |
| **Enforce security_invoker on module_issues** | `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.up.sql` | `database/tests/test_module_issues_rls.py::test_module_issues_view_has_security_invoker_enabled` | PASS |
| **RLS prevents unauthorized issue row visibility** | `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.up.sql` | `database/tests/test_module_issues_rls.py::test_module_issues_view_enforces_rls_for_unauthorized_user` | PASS |
| **Authorized user sees legitimate module issues** | `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.up.sql` | `database/tests/test_module_issues_rls.py::test_module_issues_view_returns_rows_for_authorized_user` | PASS |
| **Linear migration upgrade and downgrade** | `database/migrations/versions/p6_15_hardened_workspace_switch_and_module_issues.py` | `database/tests/migrations/test_p6_15_hardened_workspace_switch_and_module_issues_migration.py` (both upgrade and downgrade tests pass) | PASS |
| **Zero Em/En-Dashes Rule** | All touched files use plain ASCII hyphens | `uv run python -m scripts.check_no_dashes --all` exits 0 | PASS |

---

## 3. Specialist Verdict

The `module_issues` view is hardened with `security_invoker = true`. Row-Level Security policies on `issues` and `issue_modules` are rigorously applied to all invoking queries.

STATUS: APPROVED
