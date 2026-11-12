# Forensic QA Handoff: KANBA-31

- Ticket ID: KANBA-31 (`KB-P1-02`)
- Title: [Phase 1 / Database] workspaces + objects spine, object_kind enum & register_object()
- Wave: W02
- Author: builder-18

---

## 1. Architectural Implementation Summary

This ticket delivers the core universal object spine for the Kanban graph platform:

1. **Table `workspaces` (`p1_02_objects_spine.up.sql`):**
   - Implements UUID primary key defaulting to `uuidv7()`.
   - Enforces slug regex constraint `slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'`.
   - Enforces name length constraint `char_length(btrim(name)) BETWEEN 1 AND 200`.
   - Enforces trash retention constraint `trash_retention_days BETWEEN 1 AND 3650` (default 30 days per S7.2).
   - Configures automatic timestamp maintenance via `workspaces_set_updated_at` trigger calling `set_updated_at()`.

2. **Enum `object_kind` (`p1_02_objects_spine.up.sql`):**
   - Implements PostgreSQL ENUM with exactly 9 labels in authoritative specification order:
     `'issue', 'sticky', 'doc', 'user', 'project', 'cycle', 'module', 'view', 'page'`.

3. **Table `objects` Spine (`p1_02_objects_spine.up.sql`):**
   - Implements UUID primary key defaulting to `uuidv7()`.
   - References `workspaces(id)` with `ON DELETE RESTRICT`.
   - Declares dual unique constraints per S12.1:
     * `UNIQUE (id, object_type)` (type-pinned composite key for downstream entity table FKs).
     * `UNIQUE (workspace_id, object_type, canonical_key)` (scoped canonical key deduplication).
   - Enforces `canonical_key` length (1-200) and `display_title` length (1-500).
   - Partial indexes:
     * `objects_project_idx` ON objects (project_id) WHERE project_id IS NOT NULL.
     * `objects_ws_type_live_idx` ON objects (workspace_id, object_type) WHERE deleted_at IS NULL.
   - Configures automatic timestamp maintenance via `objects_set_updated_at` trigger.

4. **Immutability Guard Trigger (`objects_guard_bu`):**
   - BEFORE UPDATE trigger on `objects` rejecting changes to:
     * `object_type` (raises `OBJECT_TYPE_IMMUTABLE`).
     * `id` (raises `OBJECT_ID_IMMUTABLE`).
     * `created_at` (raises `OBJECT_CREATED_AT_IMMUTABLE`).

5. **Helper Function `register_object()` (`p1_02_objects_spine.up.sql`):**
   - Declared `SECURITY INVOKER` so caller session context and Row-Level Security policies apply.
   - Validates non-null `p_workspace_id`, `p_canonical_key`, `p_display_title`, `p_created_by_id` (`REGISTER_OBJECT_NULL_ARGUMENT`).
   - Forbids assigning `p_project_id` when `object_type` is `project` or `user` (`REGISTER_OBJECT_PROJECT_NOT_ALLOWED`).
   - Assigns `COALESCE(p_id, uuidv7())` and returns object UUID.
   - Granted execution permission to `kanban_app`.

6. **Reversible Down Migration (`p1_02_objects_spine.down.sql`):**
   - Drops function `register_object`, trigger `objects_guard_bu_trg`, function `objects_guard_bu`, triggers `objects_set_updated_at` and `workspaces_set_updated_at`, table `objects`, enum `object_kind`, and table `workspaces` in reverse order.

---

## 2. Test Execution & Coverage Evidence

- Mandatory feature unit tests in `database/tests/test_p1_02_objects.py` and `database/tests/migrations/test_p1_02_migration.py`:
  * 8 passed in 0.54s.
  * 100% statement and branch coverage on touched test and migration modules.
- Full test suite regression check: 233 passed in 11.80s.

---

## 3. Linter, Formatter, and Strict Type Safety

- Command: `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database`
- Status: Exit code 0, zero warnings, zero errors. All 22 source files checked with mypy strict mode.

---

## 4. UI Exemption Notice

This ticket is strictly a database infrastructure and schema migration ticket (`KB-P1-02`). There are no web UI components, frontend templates, or browser interactions modified; Playwright screenshot capture is not applicable.
