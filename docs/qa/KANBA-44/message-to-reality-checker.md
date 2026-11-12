# Reality-Checker Verification Packet: KANBA-44 (KB-P1-13)

**Ticket:** KANBA-44 (`KB-P1-13`)
**Title:** [Phase 1 / Database] role_bindings, resource_acl_entries & materialized effective_resource_access
**Epic:** KB-E1
**Branch:** `feat/KANBA-44` (Worktree: `/tmp/kb-wt-KANBA-44`)
**Author:** `builder-20`
**Spec Traceability:** `S3.1` (Principal closure integration), `S3.2` (8 capabilities, Explicit Deny Precedence formula), `S3.3` (effective_resource_access table, app_effective_principal_set helper, RLS predicate), Requirement #1

---

## 1. Executive Summary

This ticket implements the complete access control and authorization engine for the PostgreSQL database layer:
- **Capability Bits & Enum:** 8 immutable capabilities mapped via `capability_bit(name)` (`VIEW=1`, `COMMENT=2`, `EDIT=4`, `TRANSITION=8`, `LINK=16`, `SHARE=32`, `ADMIN=64`, `DELETE=128`). `rbac_role` enum (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `WORKSPACE_MEMBER`, `WORKSPACE_GUEST`, `PROJECT_ADMIN`, `MEMBER`, `VIEWER`) and `rbac_role_mask(role)` bitmask helper.
- **DDL & Tables:**
  - `role_bindings`: Scoped RBAC bindings (`server`, `workspace`, `project`) with foreign key constraints, scope matching checks, and `UNIQUE NULLS NOT DISTINCT (workspace_id, principal_id, role, scope_type, project_id)`.
  - `resource_acl_entries`: Object-level `ALLOW` / `DENY` capability entries with `capability_mask BETWEEN 1 AND 255` and `UNIQUE (object_id, principal_id, effect)`.
  - `effective_resource_access`: Materialized access graph storing `(object_id, principal_id, workspace_id, allow_mask, deny_mask, effective_mask)` where `effective_mask GENERATED ALWAYS AS (allow_mask & (~deny_mask)) STORED`. Modifying privileges are revoked from `kanban_app` and `app_rls_reader` (`REVOKE INSERT, UPDATE, DELETE`).
- **Session Helpers:**
  - `app_effective_principal_set() RETURNS uuid[]`: Returns `{U} U {active ancestor groups of U}` if active and matching current workspace; returns empty array `'{}'` otherwise.
  - `app_principal_has_role(p_project_id uuid, p_roles text[]) RETURNS boolean`: Evaluates whether current active principal set holds any of `p_roles` at server, workspace, or project scope.
- **Materialization Engine & Triggers:**
  - `rebuild_effective_access_for_workspace(workspace_id)` & `rebuild_effective_access_for_object(object_id)` with transactional advisory locking `pg_advisory_xact_lock(hashtextextended('era:' || p_workspace_id::text, 0))`.
  - Computes rows ONLY for active non-group concrete principals (`USER`, `AGENT`, `SERVICE_PRINCIPAL`, `SCRIPT_EPHEMERAL`).
  - Implements **Explicit Deny Precedence**: Group and direct permissions fold into principal `p`'s single row. Project-level DENY entries propagate to child objects. Autonomous `AGENT` principals do not inherit broad workspace roles. Private views restrict non-owner access.
  - Automatic reactivity triggers keep `effective_resource_access` in sync across modifications to `role_bindings`, `resource_acl_entries`, `principal_group_edges`, `principals` status, `objects` project assignments, and `views` visibility. Cross-workspace guards raise `ROLE_BINDING_WORKSPACE_MISMATCH` and `ACL_WORKSPACE_MISMATCH`.

---

## 2. Definition of Done Compliance Matrix

| DoD Requirement | Status | Evidence File / Proof |
| :--- | :---: | :--- |
| **File Existence & Implementation:** `p1_13_access_control.py`, `p1_13_access_control.up.sql`, `p1_13_access_control.down.sql` | PASS | `database/migrations/versions/p1_13_access_control.py`<br>`database/migrations/sql/p1_13_access_control.up.sql`<br>`database/migrations/sql/p1_13_access_control.down.sql` |
| **Single Head:** `alembic heads` reports single head `p1_13_access_control (head)` | PASS | `docs/qa/KANBA-44/alembic-heads.txt` |
| **Unit Tests Implemented & Passing:** 7/7 tests passing in <1.0s, >=95% coverage on touched modules | PASS | `docs/qa/KANBA-44/unit-test-results.txt` (7 passed in 0.90s, 100% statement/branch coverage on migration and test modules) |
| **Build / Type / Lint Clean:** `ruff check`, `ruff format --check`, `mypy --strict`, `check_no_dashes --all` exit 0 | PASS | `docs/qa/KANBA-44/build-check.txt` |
| **Forensic Proof Packet Complete:** All artifacts populated under `docs/qa/KANBA-44/` | PASS | `git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, `alembic-heads.txt`, `schema-dump.sql`, `deny-precedence-sample.txt`, `message-to-reality-checker.md` |

---

## 3. Test Traceability Matrix

| Test Function | Scoped Requirement | Verifications |
| :--- | :--- | :--- |
| `test_01_rbac_and_nested_group_inheritance` | S3.2, S3.3 | RBAC role binding through nested groups `U in G1 -> G2 -> G3`. `G3` bound as `MEMBER` (`31`) on project `KAN`. Creating child issue `KAN-1` materializes `(KAN-1, U)` with `allow_mask = 31, deny_mask = 0, effective_mask = 31`. `app_effective_principal_set()` under `U` returns `{U, G1, G2, G3}`. |
| `test_02_explicit_deny_precedence_and_group_acls` | S3.2, S3.3 | Group `G1` holds `ALLOW VIEW|EDIT` (`5`). Direct `DENY EDIT` (`4`) on `U` and sibling-group `DENY VIEW` (`1`) on `G_contractors` fold into `(KAN-1, U)`: `allow_mask = 31, deny_mask = 5, effective_mask = 26`. S3.3 predicate returns `FALSE`. Group rows count in ERA is exactly 0. |
| `test_03_project_level_deny_and_principal_disable` | S3.2, S3.3 | `DENY VIEW` on project propagates to child issue `(deny_mask & 1 = 1)`. Setting `status = 'DISABLED'` on `U` purges ERA rows and reduces `app_effective_principal_set()` to `'{}'`. |
| `test_04_agent_non_inheritance_and_app_principal_has_role` | S3.2, S3.3 | Unbound `AGENT` principal receives 0 ERA rows (never inherits broad workspace member permissions). `app_principal_has_role` correctly validates `PROJECT_ADMIN` and `SERVER_ADMIN` while rejecting `WORKSPACE_MEMBER` or other-project admins. |
| `test_05_cross_workspace_and_check_constraints` | S3.2, S3.3 | Cross-workspace bindings/ACLs raise `ROLE_BINDING_WORKSPACE_MISMATCH` and `ACL_WORKSPACE_MISMATCH`. Invalid scope/role combinations or mask out of bounds raise check violation `23514`. Direct insertion into `effective_resource_access` raises permission denied `42501`. |
| `test_06_dynamic_reactivity_edge_removal` | S3.2, S3.3 | Deleting group edge `G1 -> G2` automatically drops inherited access for `U` in the exact same transaction without manual rebuild. |
| `test_07_access_control_migration_lifecycle` | Migration | Complete migration upgrade, downgrade, and re-upgrade lifecycle validation via `MigrationHarness`. Verifies table drops, enum drops, and clean state restoration. |

---

## 4. Verification Proof Artifacts

- `docs/qa/KANBA-44/git-diff.patch`: Clean unified diff against base.
- `docs/qa/KANBA-44/unit-test-results.txt`: Output of `uv run pytest database/tests/test_p1_13_access_control.py database/tests/migrations/test_p1_13_migration.py -q --cov=database --cov-branch --cov-report=term-missing` (7 passed in 0.90s, exit code 0).
- `docs/qa/KANBA-44/build-check.txt`: Output of ruff check, ruff format check, mypy strict check, and dash check (exit code 0).
- `docs/qa/KANBA-44/alembic-heads.txt`: Single linear head `p1_13_access_control (head)`.
- `docs/qa/KANBA-44/schema-dump.sql`: Complete pg_dump of `role_bindings`, `resource_acl_entries`, and `effective_resource_access` with function source for `app_effective_principal_set` and `app_principal_has_role`.
- `docs/qa/KANBA-44/deny-precedence-sample.txt`: Verbatim SQL execution results demonstrating explicit deny precedence and zero group rows in ERA.
- Screenshots: N/A (Backend Database & Migration Ticket).
