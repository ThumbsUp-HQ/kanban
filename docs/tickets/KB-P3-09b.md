---
id: KB-P3-09b
title: "[Phase 3 / API] Delete with blast-radius preview, soft trash, restore & retention purge job"
epic: KB-E3
depends_on: [KB-P3-09a, KB-P1-16]
spec_sections: ["7.2", "12.3", "11.4"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: second half of manifest row `KB-P3-09`.

### User Story
As a **project member with delete rights**, I need **a delete preview showing the exact blast radius, a delete bound to that preview, a trash with restore, and an automatic purge after the retention window** so that **deletions are deliberate, reversible for 30 days by default, and never silently drop graph links**.

**Requirement Traceability:** Spec S7.2 `8q`; S12.3 (links never silently cascade-dropped, `purge_invalid_object_links`); S11.4 tool 12 (blast hash concept); requirements `#8q`, `#13j` | **Dependencies:** `KB-P3-09a`, `KB-P1-16`

### Scoped Technical Actions
1. **Target Files:** `kanban/api/v1/issue_delete.py`, `kanban/api/v1/schemas/issue_delete.py`, `kanban/services/issue_delete.py` (`compute_blast_radius()`), `kanban/jobs/trash_purge.py`, `kanban/settings.py` (add `trash_retention_days`), `kanban/services/activity.py` (append events).
2. **Blast radius (`compute_blast_radius(session, issue_id) -> BlastRadius`):** counts `sub_issues_unparented` (direct children), `inbound_links_flagged` (ACTIVE `object_links` with `target_id = issue_id`), `outbound_links`, `comments`, `attachments`; `blast_hash` = lowercase hex SHA-256 of canonical JSON `{issue_id, description_sha256, sorted child ids, sorted inbound link ids, sorted outbound link ids, comment count, attachment count}`. Counts include rows the caller cannot read (as numbers only, never ids/keys), so the preview is exact.
3. **Endpoints:**

   | Method + Path | Capability | Success | Errors |
   | :-- | :-- | :-- | :-- |
   | `GET /api/v1/issues/{issue_ref}/delete-preview` | `DELETE` | `200` | `404`, `403` |
   | `DELETE /api/v1/issues/{issue_ref}` header `Kb-Blast-Hash: <hex>` | `DELETE` | `200` | `404`, `403`, `428 BLAST_HASH_REQUIRED`, `412 BLAST_RADIUS_CHANGED` |
   | `GET /api/v1/projects/{project_ref}/trash?cursor=&limit=` | project `VIEW`; items filtered to those with `DELETE` | `200` | `404` |
   | `POST /api/v1/issues/{issue_ref}/restore` | `DELETE` | `200` | `404`, `403`, `409 NOT_IN_TRASH`, `409 RETENTION_EXPIRED` |

   - Preview response:
     ```json
     {"issue_key": "KAN-142", "sub_issues_unparented": 2, "inbound_links_flagged": 3,
      "outbound_links": 1, "comments": 4, "attachments": 1,
      "summary_text": "2 sub-issues unparented, 3 inbound object_links flagged",
      "blast_hash": "5e1c...", "retention_days": 30}
     ```
   - `DELETE` recomputes the blast radius inside the transaction (`SELECT ... FOR UPDATE` on the issue); mismatch returns `412 BLAST_RADIUS_CHANGED` with the fresh preview in member `current_preview`. On success: `objects.deleted_at = clock_timestamp()`; direct children get `parent_issue_id = NULL` (child ids recorded in activity payload); links are not deleted (the KB-P1-15 auditor flags them per its grace policy). Response: `{"issue_key", "deleted_at", "purge_after": "<deleted_at + retention_days>"}`.
   - Deleted issues return `404` from every KB-P3-02 read path except `trash` and `restore`.
   - `Settings.trash_retention_days`: env `KANBAN_TRASH_RETENTION_DAYS`, default `30`, valid `1..365` (startup fails closed on invalid value).
   - Restore clears `deleted_at`; children are not re-parented (documented in response `"note": "sub-issues remain unparented"`).
4. **Purge job (`kanban/jobs/trash_purge.py`):** `async def run_trash_purge(now: datetime, *, batch_size: int = 100) -> PurgeReport`. For issues with `deleted_at <= now - retention_days`: run `audit_object_links(workspace_id)` (KB-P1-15) so all links touching the issue become `FLAGGED_INVALID` with audit rows, call `purge_invalid_object_links(audit_ids, system_actor, 'TRASH_RETENTION_EXPIRED')` (KB-P1-16), then delete dependent rows (comments, reactions, assignees, labels, modules, subscriptions, notifications) and the `issues` + `objects` rows. Uses `SERVICE_PRINCIPAL system:trash-purge`, advisory lock `hashtext('kanban.trash_purge')`, interval `3600s`, CLI `kanban-ctl jobs run trash-purge [--now]`.
5. **Activity events emitted (category `HISTORY`):** `ISSUE_DELETE_PREVIEWED` is NOT recorded (read-only); `ISSUE_TRASHED {blast_hash, unparented_child_ids, inbound_links_flagged}`, `ISSUE_RESTORED {}`, `ISSUE_PURGED {issue_key, purged_link_count}` (written against the project object, because the issue row is gone).

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_issue_delete.py`, `kanban/tests/jobs/test_trash_purge.py`
- **Required Test Cases:**
  1. Positive: issue with 2 children, 3 inbound links: preview returns those counts and `summary_text`; `DELETE` with that hash returns `200`; children unparented; `ISSUE_TRASHED` row; issue appears in `trash`.
  2. Concurrency: add a new inbound link after preview; `DELETE` with old hash returns `412` with `current_preview.inbound_links_flagged == 4`; missing header returns `428`.
  3. Security: non-viewer preview `404`; `EDIT`-only user `DELETE` `403`; preview counts a child in an unreadable project as a number without exposing its key (assert no key strings in body).
  4. Restore: restore within retention returns `200`; restore after `retention_days` elapsed returns `409 RETENTION_EXPIRED`.
  5. Purge: issue trashed 31 days ago with `retention_days=30` is purged, its links removed only via `purge_invalid_object_links` (assert `INVALID_OBJECT_LINK_PURGED` activity rows exist), `ISSUE_PURGED` row exists; issue trashed 29 days ago remains.
  6. Settings boundary: `KANBAN_TRASH_RETENTION_DAYS=0` and `366` raise at settings load; `1` and `365` accepted.
- Clean-DB `SAVEPOINT` harness. Coverage `>= 95%`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** target files exist; 4 endpoints, `compute_blast_radius`, `run_trash_purge`, CLI subcommand implemented.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_issue_delete.py kanban/tests/jobs/test_trash_purge.py -q --cov=kanban.api.v1.issue_delete --cov=kanban.services.issue_delete --cov=kanban.jobs.trash_purge --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check kanban && uv run mypy --strict kanban && uv run lint-imports` exits `0`.
- [ ] **Contract Sample:** includes preview `200`, delete `200`, `428`, `412` with `current_preview`, trash list `200`, restore `200`, `409 RETENTION_EXPIRED`.
- [ ] **Specialist Reviews:** `api-specialist-review.md` and `ui-specialist-review.md` with `APPROVED`.
- [ ] **Forensic Proof Packet Complete.**

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/contract-sample.json` - via `KB_TICKET_ID=<TICKET_ID> KB_CONTRACT_OUT=docs/qa/<TICKET_ID>/contract-sample.json uv run pytest kanban/tests/api/test_issue_delete.py -q`.
5. `docs/qa/<TICKET_ID>/cli-run.txt` - raw output of `uv run kanban-ctl jobs run trash-purge --now <ISO8601>` against the fixture DB.
6. `docs/qa/<TICKET_ID>/api-specialist-review.md`
7. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - confirms preview payload drives the confirmation modal text.
8. Screenshots: N/A - Non-UI Ticket.
