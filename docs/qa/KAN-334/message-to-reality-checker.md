# Message to Reality-Checker: KAN-334 (`[KB-REDTEAM-03]`)

## Ticket Scope & Browser Screenshot Classification
- **Ticket:** `KAN-334` - `[KB-REDTEAM-03] Enforce security_invoker on module_issues View to Prevent Row-Level Security Bypass`
- **Branch:** `feat/KAN-329-336`
- **Browser Screenshots:** `N/A - Non-UI Security Ticket` (Database Migration, PostgreSQL View Security Invoker, and RLS)
- **Owned Slice Modified:**
  - `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.up.sql`
  - `database/migrations/sql/p6_15_hardened_workspace_switch_and_module_issues.down.sql`
  - `database/migrations/versions/p6_15_hardened_workspace_switch_and_module_issues.py`
  - `database/tests/test_module_issues_rls.py`
  - `database/tests/migrations/test_p6_15_hardened_workspace_switch_and_module_issues_migration.py`
  - `docs/qa/KAN-334/*`

## Requirement-to-Evidence Mapping

1. **Enforce security_invoker = true on module_issues:**
   - **Implementation:** Added `CREATE OR REPLACE VIEW module_issues WITH (security_invoker = true)` in linear migration `p6_15_hardened_workspace_switch_and_module_issues`.
   - **Evidence:** `docs/qa/KAN-334/git-diff.patch` and `test_module_issues_view_has_security_invoker_enabled` in `database/tests/test_module_issues_rls.py`.

2. **Prevent RLS Bypass on Issues Joined in module_issues:**
   - **Implementation:** Validated under `kanban_app` with `FORCE ROW LEVEL SECURITY`. Queries by users without issue view permissions return 0 rows for restricted issues.
   - **Evidence:** `test_module_issues_view_enforces_rls_for_unauthorized_user` in `database/tests/test_module_issues_rls.py`.

3. **Permit Authorized Queries:**
   - **Implementation:** Users with valid permissions read module issues normally.
   - **Evidence:** `test_module_issues_view_returns_rows_for_authorized_user` in `database/tests/test_module_issues_rls.py`.

4. **Migration Verification:**
   - **Implementation:** Migration upgraded and downgraded successfully; single linear migration head verified.
   - **Evidence:** `database/tests/migrations/test_p6_15_hardened_workspace_switch_and_module_issues_migration.py` and `uv run kanban-ctl db check-migrations --static-only`.

5. **Mandatory Quality & Code Hygiene:**
   - Zero em-dashes or en-dashes (`uv run python -m scripts.check_no_dashes --all` exits 0).
   - Full static validation passed (`make check` exits 0).

All artifacts and checksums are verified in `docs/qa/KAN-334/changed-files-manifest.txt`.
