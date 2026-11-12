# Reality-Checker Verification Packet: KANBA-52 (KB-P1-15)

## Ticket Metadata
- Ticket ID: `KANBA-52`
- Spec Key: `KB-P1-15`
- Title: `[Phase 1 / Database] audit_object_links() 6-reason detector, invalid_object_link_audits & incremental triggers`
- Epic: `KB-E1` (Phase 1 Database Architecture)
- Spec Sections: `12.3` (All 6 Invalidity Classes, `FLAGGED_INVALID`, `invalid_object_link_audits` Snapshots), `12.1` (`object_links.link_state`), Requirement `#13j`
- Dependencies: `KB-P1-11` (`object_links`), `KB-P1-13` (`access_control`), `KB-P1-14` (`force_rls`)
- Gate: `reality-checker` (Passive Forensic Mode)

---

## User Story
As a platform administrator or security auditor, I need `audit_object_links(p_workspace_id)` and incremental database triggers that detect all 6 S12.3 invalidity classes, transition offending `object_links` rows to `FLAGGED_INVALID`, and capture full endpoint snapshots in `invalid_object_link_audits` so that broken, archived-blocking, soft-deleted, type-corrupted, cross-workspace, or ACL-severed links never fail silently or disappear without forensic proof.

---

## Scoped Definition of Done Checklist
- [x] **Enum & DDL Definition:** `invalid_link_reason` enum implemented with all 7 values covering the 6 classes (`'DANGLING_SOURCE'`, `'DANGLING_TARGET'`, `'SOFT_DELETED_ENDPOINT'`, `'ARCHIVED_POLICY_VIOLATION'`, `'TYPE_MATRIX_VIOLATION'`, `'CROSS_WORKSPACE_LEAK'`, `'PERMISSION_SEVERED'`).
- [x] **Audit Table & Security:** `invalid_object_link_audits` table created matching S12.3 specification with `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. INSERT, UPDATE, DELETE permissions revoked from `kanban_app` and `app_rls_reader`.
- [x] **RLS Policy:** `invalid_link_audits_select_rls` policy enforces workspace scoping and requires `SERVER_ADMIN` or `WORKSPACE_ADMIN` (or project admin on endpoint project snapshots).
- [x] **Immutability Guard:** Trigger `invalid_link_audits_guard_bud` rejects `DELETE` with `LINK_AUDIT_RECORD_IMMUTABLE` and rejects modifications to snapshot columns with `LINK_AUDIT_SNAPSHOT_IMMUTABLE` (permitting only `resolved_at`, `purged_at`, `purged_by_id`, `purge_reason`).
- [x] **Single-Link & Workspace Auditors:** `audit_single_object_link(p_link_id, p_as_of)` and `audit_object_links(p_workspace_id, p_as_of)` detect all 6 classes, flip `link_state = 'FLAGGED_INVALID'`, insert audit rows with full JSONB snapshots, and auto-heal resolved links back to `'ACTIVE'` when no open violations remain.
- [x] **Incremental Triggers:** Trigger function `audit_object_links_for_object(p_object_id)` attached `AFTER UPDATE OF archived_at, deleted_at, workspace_id ON objects` and `AFTER INSERT OR UPDATE OR DELETE ON resource_acl_entries, role_bindings`.
- [x] **Alembic Single Head:** Migration `p1_15_link_auditor.py` chains cleanly from `p1_14_force_rls`. `alembic heads` reports exactly `p1_15_link_auditor (head)`.
- [x] **Feature Unit Tests:** 9 test cases covering all 6 classes, incremental triggers, auto-healing, superuser replica simulation, security checks, and immutability guards in `database/tests/test_p1_15_link_auditor.py` passing in 0.24s with 100% statement and branch coverage.
- [x] **Migration Tests:** Upgrade, downgrade, and re-upgrade lifecycle test in `database/tests/migrations/test_p1_15_migration.py` passing in 0.30s with 100% coverage.
- [x] **Catalog Gate Passing:** `database/tests/test_p1_14_rls_catalog.py` confirms `invalid_object_link_audits` passes `FORCE RLS` catalog inspection.
- [x] **Static Analysis Clean:** `ruff check`, `ruff format --check`, and `mypy --strict` exit code 0 across 66 source files.
- [x] **Zero Forbidden Unicode Dashes:** Repository passes `scripts.check_no_dashes --all` with 0 violations.

---

## Six Invalidity Classes Implementation Matrix

| Class | Enum Value(s) | Detection Condition | Auto-Healing Trigger |
| :--- | :--- | :--- | :--- |
| **Class 1: Dangling Endpoints** | `DANGLING_SOURCE`, `DANGLING_TARGET` | Referenced row missing from `objects` or `objects.object_type != object_links.source/target_type`. | Repopulating missing endpoint object. |
| **Class 2: Soft-Deleted Endpoint** | `SOFT_DELETED_ENDPOINT` | `src.deleted_at` or `tgt.deleted_at <= p_as_of - ws.trash_retention_days` (default 30 days). | Un-deleting endpoint before retention window expires (`deleted_at = NULL`). |
| **Class 3: Archived Policy Violation** | `ARCHIVED_POLICY_VIOLATION` | `BLOCKS` link where source is archived while target is active/in-progress, or `BLOCKED_BY` where target is archived while source is active/in-progress. | Un-archiving source (`archived_at = NULL`) or completing blocked issue. Handled immediately via incremental trigger on `objects.archived_at`. |
| **Class 4: Type Matrix Violation** | `TYPE_MATRIX_VIOLATION` | Tuple `(source_type, link_type, target_type)` not present in `link_type_matrix`. | Re-registering allowed tuple in `link_type_matrix`. |
| **Class 5: Cross-Workspace Leak** | `CROSS_WORKSPACE_LEAK` | `src.workspace_id != tgt.workspace_id` or `src.workspace_id != object_links.workspace_id`. | Moving endpoint object to matching workspace. Handled via trigger on `objects.workspace_id`. |
| **Class 6: Permission Severed** | `PERMISSION_SEVERED` | Link creator lacks `VIEW` (capability mask `1`) on both source and target objects in `effective_resource_access`. | Restoring `VIEW` permission (e.g. removing `DENY` ACL or adding role binding). Handled immediately via trigger on `resource_acl_entries` and `role_bindings`. |

---

## Forensic Artifacts in `docs/qa/KANBA-52/`
1. `git-diff.patch`: Unified diff of all migration files, tests, and proof documentation.
2. `unit-test-results.txt`: Output of `pytest database/tests/test_p1_15_link_auditor.py database/tests/test_p1_14_rls_catalog.py database/tests/migrations/test_p1_15_migration.py -q --cov=database --cov-branch --cov-report=term-missing` (11 passed in 1.60s, 100% coverage on touched modules, EXIT_CODE=0).
3. `build-check.txt`: Output of `ruff check database && ruff format --check database && mypy --strict database` (all checks passed, 68 files formatted, no issues in 66 source files, EXIT_CODE=0).
4. `alembic-heads.txt`: Output of `alembic heads` showing single head `p1_15_link_auditor (head)`.
5. `schema-dump.sql`: Complete DDL dump of `invalid_object_link_audits` and function source `audit_object_links()`.
6. `six-reasons-sample.txt`: Verified query output demonstrating all 6 invalidity classes captured concurrently in `invalid_object_link_audits` with `link_state = 'FLAGGED_INVALID'`.
7. `message-to-reality-checker.md`: This forensic sign-off document.

---

## Note on Pre-existing KANBA-51 RLS Scope Gap
Running the full repository test suite (`pytest database/tests/`) reveals 28 failures in earlier test modules (`test_p1_04_projects.py`, `test_p1_09_prose.py`, `test_p1_10_views.py`, `test_p1_13_access_control.py`). These older tests connect via `app_session` without binding workspace context (`bind_ctx`), which conflicts with the `FORCE ROW LEVEL SECURITY` policies introduced in ticket `KANBA-51` (`p1_14_force_rls`). This is a known cross-ticket test fixture discrepancy outside `KANBA-52` scope. All ticket-specified test files for `KANBA-52` (`test_p1_15_link_auditor.py`, `test_p1_14_rls_catalog.py`, `test_p1_15_migration.py`) pass 100% cleanly under the `SAVEPOINT` test harness with full RLS compliance.
