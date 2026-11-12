# Forensic QA Handoff: KANBA-35

- Ticket ID: KANBA-35 (`KB-P1-03`)
- Title: [Phase 1 / Database] principals, users, groups & cycle-safe principal_group_closure
- Wave: W02
- Author: builder-18

---

## 1. Architectural Implementation Summary

This ticket delivers the unified principals model and cycle-safe recursive group closure for the Kanban platform:

1. **Table `principals` (`p1_03_principals.up.sql`):**
   - Declares UUID primary key defaulting to `uuidv7()`.
   - Restricts `principal_type` to `('USER', 'GROUP', 'AGENT', 'SCRIPT_EPHEMERAL', 'SERVICE_PRINCIPAL')`.
   - References `workspaces(id)` with `ON DELETE RESTRICT`.
   - Enforces `status IN ('ACTIVE', 'DISABLED')` defaulting to `'ACTIVE'`.
   - Validates `display_name` non-empty between 1 and 200 characters.
   - Enforces composite unique constraint `UNIQUE (id, principal_type)` for typed subtype references.

2. **Table `users` (`p1_03_principals.up.sql`):**
   - Declares UUID primary key matching `principals.id` and `objects.id`.
   - Pins `object_type = 'user'` and `principal_type = 'USER'`.
   - Enforces composite foreign keys:
     * `(id, principal_type) REFERENCES principals(id, principal_type) ON DELETE RESTRICT`.
     * `(id, object_type) REFERENCES objects(id, object_type) ON DELETE RESTRICT`.
   - Enforces email address syntax and length (3 to 320 characters).
   - Creates unique index `users_ws_email_uq` on `(workspace_id, lower(email))`.

3. **Table `groups` (`p1_03_principals.up.sql`):**
   - Declares UUID primary key matching `principals.id`.
   - Pins `principal_type = 'GROUP'`.
   - References `workspaces(id)` with `ON DELETE RESTRICT`.
   - Enforces unique constraint `UNIQUE (workspace_id, name)`.
   - Validates `external_source IN ('LDAP', 'OIDC')` and `external_id <= 1024` chars when provided.
   - Enforces composite foreign key `(id, principal_type) REFERENCES principals(id, principal_type) ON DELETE RESTRICT`.

4. **Table `principal_group_edges` (`p1_03_principals.up.sql`):**
   - Stores direct membership edges between a principal (`member_id`) and a group (`group_id`).
   - Declares composite primary key `(member_id, group_id)`.
   - Enforces check constraint `CHECK (member_id <> group_id)` (raising 23514 on self-edges).
   - References `workspaces(id)` with `ON DELETE RESTRICT`.
   - Indexes `pge_workspace_group_idx` on `(workspace_id, group_id)` for high-speed recursive CTE joins.

5. **Table `principal_group_closure` (`p1_03_principals.up.sql`):**
   - Stores computed transitive closure pairs `(member_id, ancestor_group_id)`.
   - Enforces `depth SMALLINT NOT NULL CHECK (depth BETWEEN 1 AND 8)` representing shortest path length.
   - Declares primary key `(member_id, ancestor_group_id)`.
   - Creates indexes `pgc_ancestor_idx` on `(ancestor_group_id, member_id)` and `pgc_workspace_idx` on `(workspace_id)`.
   - Permissions: `REVOKE INSERT, UPDATE, DELETE ON TABLE principal_group_closure FROM kanban_app;` ensures table is only writable via `rebuild_group_closure()`.

6. **Triggers and Closure Maintenance Function:**
   - `users_workspace_match_biu` / `groups_workspace_match_biu`: Verifies `NEW.workspace_id` matches `principals.workspace_id` and `objects.workspace_id`, raising `PRINCIPAL_WORKSPACE_MISMATCH` on deviation.
   - `principal_group_edges_guard_biu`: BEFORE INSERT OR UPDATE trigger verifying member and group workspaces match `NEW.workspace_id` (raising `GROUP_EDGE_WORKSPACE_MISMATCH`), and verifying no path exists from `NEW.group_id` to `NEW.member_id` (raising `GROUP_CYCLE_REJECTED`).
   - `rebuild_group_closure(p_workspace_id)`: Declared `SECURITY DEFINER SET search_path = public, pg_temp`. Acquires advisory transaction lock `pg_advisory_xact_lock(hashtextextended('group_closure:' || p_workspace_id::text, 0))`. Executes recursive CTE with `CYCLE member_id SET is_cycle USING path`. Aborts with `GROUP_CYCLE_REJECTED` if a cycle is detected, aborts with `GROUP_DEPTH_EXCEEDED` if any path exceeds 8 levels, and atomically repopulates closure rows with `min(depth)`.
   - `principal_group_edges_closure_aiud`: AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW trigger invoking `rebuild_group_closure()`.

7. **Reversible Down Migration (`p1_03_principals.down.sql`):**
   - Cleanly drops triggers, trigger functions, definer function, and all 5 tables in reverse dependency order.

---

## 2. Test Execution & Coverage Evidence

- Mandatory feature unit tests in `database/tests/test_p1_03_principals.py` and `database/tests/migrations/test_p1_03_migration.py`:
  * 9 passed in 0.73s.
  * 100% statement and branch coverage on touched test and migration modules.
- Full test suite regression check: 242 passed in 12.23s.
- Performance budget: rebuild on 500 edges completed in < 50ms (measured at ~2ms, well within the 500ms test assertion bound).

---

## 3. Linter, Formatter, and Strict Type Safety

- Command: `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database`
- Status: Exit code 0, zero warnings, zero errors. All 25 source files verified under mypy strict typing.

---

## 4. UI Exemption Notice

This ticket is strictly a database infrastructure and schema migration ticket (`KB-P1-03`). There are no web UI components, frontend templates, or browser interactions modified; Playwright screenshot capture is not applicable.
