# Message to Reality-Checker for Ticket KANBA-51 (KB-P1-14)

## Executive Summary

Ticket `KANBA-51` (`KB-P1-14`: `[Phase 1 / Database] FORCE ROW LEVEL SECURITY policies, session context helpers & schema-wide RLS catalog gate`) is fully implemented, verified, and ready for forensic audit.

This ticket delivers complete schema-wide row-level security enforcement across PostgreSQL in strict compliance with Section 3.3, Section 3.2, Section 2.2, and Core Architecture Requirement #1.

---

## 1. Lineage & Single Head Verification

- **Alembic Down Revision:** `p1_07_creator_provenance` (the current linear head on `main`).
- **Single Head Confirmation:**
  ```bash
  $ uv run alembic -c database/alembic.ini heads
  p1_14_force_rls (head)
  ```
  Verified in `docs/qa/KANBA-51/alembic-heads.txt`.

---

## 2. Core Implementation Deliverables

1. **Alembic Version Migration:**
   - `database/migrations/versions/p1_14_force_rls.py`: Linearly chained to `p1_07_creator_provenance`.
2. **Upgrade SQL (`database/migrations/sql/p1_14_force_rls.up.sql`):**
   - **Session Helpers:**
     - `app_current_token_scopes() RETURNS text[]` (`STABLE PARALLEL SAFE`, granted to `kanban_app, app_rls_reader, kanban_migrator`).
     - `app_current_aal_level() RETURNS integer` (`STABLE PARALLEL SAFE`, granted to `kanban_app, app_rls_reader, kanban_migrator`).
     - `app_has_object_capability(uuid, integer) RETURNS boolean` (`STABLE PARALLEL SAFE SECURITY INVOKER`, granted to `kanban_app, app_rls_reader, kanban_migrator`).
   - **Dynamic Partition RLS Update:**
     - `ensure_activity_partitions()` updated to apply `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` with 0 direct partition policies on newly created monthly partitions.
   - **Trigger Constraint Integrity:**
     - Configured `issues_validate_biu()`, `issues_parent_dag_biu()`, and `docs_spine_match_biu()` as `SECURITY DEFINER SET search_path = pg_catalog, public` so cross-table constraint checks succeed under RLS.
   - **ENABLE & FORCE RLS:**
     - Applied `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` across all 31 tenant tables in `public` and all existing `activity_records_y*` partitions.
     - Exempt tables: `alembic_version` and `link_type_matrix` only.
   - **Comprehensive RLS Policies:**
     - `workspaces`: SELECT scoped to `app_current_workspace_id()`, UPDATE requires `SERVER_ADMIN` or `WORKSPACE_ADMIN`.
     - `principals`, `users`, `groups`, `principal_group_edges`, `principal_group_closure`: SELECT scoped to workspace and non-empty principal set; writes require `SERVER_ADMIN` or `WORKSPACE_ADMIN`.
     - `objects`: `objects_select_rls` verbatim from S3.3; INSERT requires EDIT (4) on project; UPDATE requires EDIT (4); DELETE requires DELETE (128).
     - `projects`: SELECT requires VIEW (1); INSERT requires `SERVER_ADMIN` or `WORKSPACE_ADMIN`; UPDATE requires ADMIN (64); DELETE requires DELETE (128).
     - Object-spine entities (`issues`, `cycles`, `modules`, `docs`, `pages`, `stickies`, `views`): SELECT requires VIEW (1); INSERT requires EDIT (4); UPDATE requires EDIT (4) or TRANSITION (8) for issues; DELETE requires DELETE (128).
     - Child/join entities (`workflow_states`, `project_priorities`, `project_labels`, `project_module_defaults`, `issue_modules`, `issue_assignees`, `issue_labels`, `issue_subscriptions`, `issue_comments`, `page_versions`): Capability-gated against parent issue/project/page.
     - `object_links`: SELECT permits viewing link when caller has VIEW on either endpoint (`source_id` or `target_id`); INSERT requires LINK (16) on source and VIEW (1) on target; DELETE requires LINK (16) on source.
     - `activity_records`: SELECT requires VIEW (1) on target object or workspace/server admin; INSERT requires actor matching current principal.
     - `activity_chain_heads`: ENABLE + FORCE RLS with 0 direct policies (accessed solely via SECURITY DEFINER ledger functions).
     - `effective_resource_access`: Non-recursive RLS policy `workspace_id = app_current_workspace_id() AND cardinality(app_effective_principal_set()) > 0`.
3. **Downgrade SQL (`database/migrations/sql/p1_14_force_rls.down.sql`):**
   - Cleanly drops all 108 created policies, disables FORCE and ROW LEVEL SECURITY on all tenant tables, reverts triggers to `SECURITY INVOKER`, restores `ensure_activity_partitions` without RLS calls, and drops the 3 helper functions.

---

## 3. Scoped Definition of Done Traceability

| DoD Requirement | Status | Evidence |
| :--- | :---: | :--- |
| File existence & implementation (`p1_14_force_rls.{py,up.sql,down.sql}`) | **PASS** | Files present in worktree, 100% statement coverage |
| Single Head (`uv run alembic heads`) | **PASS** | `p1_14_force_rls (head)` (`docs/qa/KANBA-51/alembic-heads.txt`) |
| Mandatory unit tests pass (`test_p1_14_rls_policies.py`, `test_p1_14_rls_catalog.py`, `test_p1_14_migration.py`) | **PASS** | 7/7 tests passed in 1.48s, 100% statement/branch coverage (`docs/qa/KANBA-51/unit-test-results.txt`) |
| Full migration lifecycle pass | **PASS** | 15/15 migration tests pass (`test_p1_01` through `test_p1_14`) |
| Lint, format, and static typing clean (`ruff check`, `ruff format`, `mypy --strict`) | **PASS** | 0 warnings, 0 errors across 63 database source files (`docs/qa/KANBA-51/build-check.txt`) |
| Dash check (`check_no_dashes --all`) | **PASS** | Clean exit 0, zero `U+2014` or `U+2013` unicode dashes |
| License gate check (`make license`) | **PASS** | Clean exit 0, 0 license violations |
| Forensic verification proof packet complete | **PASS** | All artifacts populated under `docs/qa/KANBA-51/` |

---

## 4. Verification Proof Artifact Manifest

1. `docs/qa/KANBA-51/git-diff.patch` - Unified git diff against `main`.
2. `docs/qa/KANBA-51/unit-test-results.txt` - Pytest output verifying 7/7 tests pass with 100% coverage on touched modules.
3. `docs/qa/KANBA-51/build-check.txt` - Output of ruff check, ruff format --check, and mypy --strict.
4. `docs/qa/KANBA-51/alembic-heads.txt` - Output of `alembic heads` showing single head `p1_14_force_rls (head)`.
5. `docs/qa/KANBA-51/rls-catalog.txt` - Relrowsecurity / relforcerowsecurity scan of all 41 public tables/partitions and 108 pg_policies.
6. `docs/qa/KANBA-51/zero-context-check.txt` - Empirical verification showing 0 rows returned across all 39 tenant tables under `kanban_app` and `app_rls_reader`.
7. `docs/qa/KANBA-51/message-to-reality-checker.md` - This document.
