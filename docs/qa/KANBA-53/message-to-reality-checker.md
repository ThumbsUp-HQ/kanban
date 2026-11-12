# Reality-Checker Verification Packet: KANBA-53 (KB-P1-16)

## Ticket Metadata
- Ticket ID: `KANBA-53`
- Spec Key: `KB-P1-16`
- Title: `[Phase 1 / Database] purge_invalid_object_links() admin-only audited purge & INVALID_OBJECT_LINK_PURGED ledger entry`
- Epic: `KB-E1` (Phase 1 Database Architecture)
- Spec Sections: `12.3` (`purge_invalid_object_links(p_audit_ids UUID[], p_actor_id UUID, p_reason TEXT)`, `INVALID_OBJECT_LINK_PURGED` activity event), `11.4` (tool 11 `audit_and_purge_object_links`), Requirement `#13j`
- Dependencies: `KB-P1-15` (`link_auditor`), `KB-P1-12` (`activity_ledger`)
- Gate: `reality-checker` (Passive Forensic Mode)

---

## User Story
As a **Workspace or Server Administrator**, I need **`purge_invalid_object_links(p_audit_ids, p_actor_id, p_reason)` that verifies admin privileges, deletes ONLY `FLAGGED_INVALID` links backed by open audit snapshots, stamps the audit rows as purged, blocks raw un-audited `DELETE`s of flagged links, and appends `INVALID_OBJECT_LINK_PURGED` to `activity_records`** so that **invalid graph edges can be cleaned up with a permanent cryptographic audit trail while `ACTIVE` links can never be accidentally purged**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `p1_16_link_purger.py`, `p1_16_link_purger.up.sql`, `p1_16_link_purger.down.sql` exist and define `purge_invalid_object_links`, `object_links_flagged_delete_guard_bd`, `PURGE_FORBIDDEN`, `PURGE_ACTIVE_LINK_REFUSED`, `FLAGGED_LINK_REQUIRES_AUDITED_PURGE`, and `INVALID_OBJECT_LINK_PURGED`.
- [x] **Direct-Delete Guard:** Trigger `object_links_flagged_delete_guard_bd_trg` on `BEFORE DELETE ON object_links` raises `FLAGGED_LINK_REQUIRES_AUDITED_PURGE` if `link_state = 'FLAGGED_INVALID'` and `kb.in_audited_purge` is not `'on'`. `ACTIVE` links remain deletable through standard operations.
- [x] **Fail-Closed Validation:** Validates `p_audit_ids` (1-1000 items, non-null, deduplicated preserving UUID sort order), `p_reason` (3-1000 characters post-trim), session RLS context (`RLS_CONTEXT_REQUIRED`), actor identity match (`PURGE_ACTOR_MISMATCH`), and role authorization (`SERVER_ADMIN` or `WORKSPACE_ADMIN`, else `PURGE_FORBIDDEN`).
- [x] **Audit and Link Locking:** Acquires deterministic `FOR UPDATE` row locks on `invalid_object_link_audits` and `object_links`. Aborts with `PURGE_AUDIT_NOT_FOUND` if count mismatches or workspace differs, `PURGE_ALREADY_EXECUTED` if already purged, `PURGE_AUDIT_RESOLVED` if resolved, `PURGE_LINK_MISSING` if missing from links table, and `PURGE_ACTIVE_LINK_REFUSED` if `link_state <> 'FLAGGED_INVALID'`.
- [x] **Audited Deletion and Ledger:** Executes `DELETE FROM object_links` under session GUC `kb.in_audited_purge = 'on'`, stamps all open audit rows on deleted links with `purged_at`, `purged_by_id`, `purge_reason` (including sibling open audit reasons), determines activity anchor from surviving endpoints, and calls `append_activity` with `INVALID_OBJECT_LINK_PURGED`.
- [x] **Single Head:** `uv run alembic -c database/alembic.ini heads` prints exactly one head: `p1_16_link_purger (head)`.
- [x] **Unit Tests Passing:** `uv run pytest database/tests/test_p1_16_link_purger.py database/tests/migrations/test_p1_16_migration.py -q --cov=database --cov-branch --cov-report=term-missing` passes 7/7 tests with 100% coverage on touched modules (`p1_16_link_purger.py: 100%`, `test_p1_16_link_purger.py: 100%`, `test_p1_16_migration.py: 100%`).
- [x] **Static Analysis Clean:** `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database` exits code 0 across 69 source files.
- [x] **No Forbidden Unicode Dashes:** Repository passes `scripts.check_no_dashes --all` with zero violations.
- [x] **License Gate Clean:** `make license` passes with 0 violations.

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Alembic Migration** | `database/migrations/versions/p1_16_link_purger.py` | Migration revision chaining from `p1_15_link_auditor` to `p1_16_link_purger`. |
| **Delete Guard Trigger** | `database/migrations/sql/p1_16_link_purger.up.sql` | `object_links_flagged_delete_guard_bd` before-delete trigger rejecting raw deletion of `FLAGGED_INVALID` links without `kb.in_audited_purge = 'on'`. |
| **Purge Function** | `database/migrations/sql/p1_16_link_purger.up.sql` | `purge_invalid_object_links(uuid[], uuid, text)` volatile security definer function returning table of `(purged_audit_id, purged_link_id, activity_id)`. |
| **Down Migration** | `database/migrations/sql/p1_16_link_purger.down.sql` | Drops function, trigger, and trigger function cleanly. |
| **Feature Unit Tests** | `database/tests/test_p1_16_link_purger.py` | 6 comprehensive test cases covering positive two-link purge, sibling closure, service principal authorization, direct delete guard, active link refusal, replay protection, boundary conditions, and catalog integrity. |
| **Migration Lifecycle Tests** | `database/tests/migrations/test_p1_16_migration.py` | Upgrade, downgrade, and re-upgrade lifecycle verification via `MigrationHarness`. |

---

## Forensic Artifacts in `docs/qa/KANBA-53/`
1. `git-diff.patch`: Complete unified `git diff` for this ticket.
2. `unit-test-results.txt`: Full output and exit code of `pytest database/tests/test_p1_16_link_purger.py database/tests/migrations/test_p1_16_migration.py -q --cov=database --cov-branch --cov-report=term-missing` (7 passed in 1.55s, 100% coverage on touched modules, EXIT_CODE=0).
3. `build-check.txt`: Full output of `ruff check database && ruff format --check database && mypy --strict database` (all checks passed, 71 files checked, 69 source files clean, EXIT_CODE=0).
4. `alembic-heads.txt`: Output of `alembic heads` showing single head `p1_16_link_purger (head)`.
5. `schema-dump.sql`: Complete PostgreSQL `\sf` definitions of `purge_invalid_object_links` and `object_links_flagged_delete_guard_bd`.
6. `purge-ledger-sample.txt`: Verified execution output showing return rows from `purge_invalid_object_links`, surviving stamped audit rows, `INVALID_OBJECT_LINK_PURGED` records in `activity_records`, and valid cryptographic activity chain verification.
7. `message-to-reality-checker.md`: This forensic sign-off document.
