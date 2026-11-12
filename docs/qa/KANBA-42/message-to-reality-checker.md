# Forensic QA Packet: KANBA-42 (KB-P1-10)

- Ticket: KANBA-42
- Spec Reference: docs/tickets/KB-P1-10.md
- Specification Authority: docs/ARCHITECTURE_AND_PRODUCT_SPEC.md (S6.4, S12.1, S3.4)
- Author: builder-20
- Branch: feat/KANBA-42

## Summary of Implementation

Implemented Phase 1 database schema and migrations for views table, view_layout enum, and filter/WIP JSON validators:
1. Migration files:
   - database/migrations/versions/p1_10_views.py: down_revision = 'p1_11_object_links'
   - database/migrations/sql/p1_10_views.up.sql: DDL, triggers, and functions
   - database/migrations/sql/p1_10_views.down.sql: clean rollback
2. JSON Validator Functions:
   - validate_view_filters_json(p_doc jsonb): IMMUTABLE PARALLEL SAFE function enforcing object type, <= 16384 bytes, and allowlisted keys ('state_ids', 'state_groups', 'priority_ids', 'assignee_ids', 'label_ids', 'cycle_ids', 'module_ids', 'start_date', 'due_date', 'gate_status', 'search_query').
   - validate_view_wip_limits_json(p_doc jsonb): IMMUTABLE PARALLEL SAFE function enforcing object type, <= 8192 bytes, UUID string keys, subset of ('soft', 'hard') properties, integer values between 1 and 10000, and hard >= soft when both are non-null.
3. Enum and Table DDL:
   - view_layout: ENUM ('list', 'board', 'table', 'calendar', 'timeline')
   - views: id UUID PRIMARY KEY, object_type object_kind DEFAULT 'view', workspace_id, project_id, owner_principal_id, visibility ('private', 'project', 'workspace'), name (1-200 chars), summary_markdown (<= 65536 bytes), summary_sha256 STORED GENERATED digest, layout, group_by, sub_group_by, filters_json, display_props_json, wip_limits_json, sort_rank COLLATE "C", composite FK (id, object_type) to objects.
   - CHECK (visibility <> 'project' OR project_id IS NOT NULL).
   - CHECK (group_by IS NULL OR sub_group_by IS NULL OR group_by <> sub_group_by).
4. Integrity Trigger:
   - views_spine_match_biu: BEFORE INSERT OR UPDATE ON views enforcing objects spine match (workspace_id and project_id IS NOT DISTINCT FROM), owner principal validation (must belong to same workspace and be USER, AGENT, or SERVICE_PRINCIPAL), and project workspace match.

## Definition of Done Verification

| DoD Item | Requirement | Result | Evidence |
| :--- | :--- | :--- | :--- |
| File Existence | 3 migration files created | PASS | p1_10_views.py, .up.sql, .down.sql |
| Single Alembic Head | Exactly one head: p1_10_views (head) | PASS | alembic-heads.txt |
| Unit Tests Passing | All 7 tests pass with 0 failures | PASS | unit-test-results.txt |
| Coverage | >=95% branch+line coverage on touched modules | PASS (100%) | unit-test-results.txt |
| Lint / Type Check | ruff check, ruff format, mypy --strict pass | PASS | build-check.txt |
| Schema Dump | pg_dump -t views, \dT+ view_layout, \sf validate_view_wip_limits_json | PASS | schema-dump.sql |
| UI Changes | Non-UI Ticket | N/A | Non-UI Ticket |
| Unicode Dashes | Zero U+2014 or U+2013 characters | PASS | scripts.check_no_dashes |

## Test Traceability Matrix

1. Positive layouts and SHA-256 (all 5 layouts, 2D swimlanes, SHA-256 digest match): test_01_views_layouts_and_sha256 (PASSED)
2. Positive visibility and scope (workspace-scoped null project view and private project view): test_02_views_visibility_and_scope (PASSED)
3. Negative layout and filter checks (identical swimlanes, null project on project visibility, invalid filter keys, array filters): test_03_views_layout_and_filter_checks (PASSED)
4. Negative WIP limits checks (hard < soft, soft = 0, non-UUID key, extra key override): test_03_views_wip_limits_checks (PASSED)
5. Security trigger enforcements (group owner, cross-workspace owner, spine mismatch, cross-workspace project): test_04_views_security_and_spine_mismatches (PASSED)
6. Boundary conditions (16384 bytes filter accepted, 16385 rejected, WIP soft=hard, WIP null hard, catalog markdown-only check): test_05_views_boundary_conditions (PASSED)
7. Migration up/down/re-up lifecycle (views table and view_layout enum verified): test_06_views_migration_lifecycle (PASSED)
