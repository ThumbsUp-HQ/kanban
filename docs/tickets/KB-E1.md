---
id: KB-E1
title: "[Phase 1 / Epic] Universal Object Graph, Markdown DDL, RLS & Link Auditor"
type: epic
children: [KB-P1-01, KB-P1-02, KB-P1-03, KB-P1-04, KB-P1-05, KB-P1-06, KB-P1-07, KB-P1-08, KB-P1-09, KB-P1-10, KB-P1-11, KB-P1-12, KB-P1-13, KB-P1-14, KB-P1-15, KB-P1-16, KB-P1-17, KB-P1-18]
spec_sections: ["3.1", "3.2", "3.3", "5.1", "6.4", "7.2", "8", "12.1", "12.2", "12.3", "15.5"]
gates: [reality-checker]
state: Backlog
---

### Goal
Deliver the complete `database/` module: Alembic baseline, roles and extensions, the shared-PK `objects` spine, all 9 object classes stored as canonical Markdown with `STORED` `sha256` and `tsvector`, principals and group closure, `effective_resource_access`, `FORCE ROW LEVEL SECURITY` on every tenant table, the hash-chained `activity_records` ledger, typed `object_links`, the Invalid Object Link Auditor and audited purger, SQLAlchemy 2.0 async models, and the transactional outbox with `RealtimeBroker`.

### Scope Summary
- DDL and migrations for workspaces, objects, principals, projects, issues, cycles, modules, comments, stickies, docs, pages, views, object links, activity records, ACLs.
- Triggers: parent DAG with `ltree`, created-by provenance, group-closure cycle rejection, link-type matrix, exclusive label groups.
- Security: `kanban_app` `NOSUPERUSER NOBYPASSRLS`, `FORCE RLS` policies bound to `app.principal_id` / `app.workspace_id`, catalog tests.
- Integrity: `audit_object_links()` (6 reasons), `purge_invalid_object_links()`, `verify_activity_chain()`.
- Python access layer: `database/models/*`, `database/session.py`, outbox relay and `PgNotifyBroker`.

### Child Tickets
| ID | Title | Deps |
| :-- | :-- | :-- |
| KB-P1-01 | Alembic baseline, roles & extensions | KB-P0-05 |
| KB-P1-02 | `workspaces` + `objects` spine + `object_kind` enum | KB-P1-01 |
| KB-P1-03 | Principals, users, groups & cycle-safe group closure | KB-P1-02 |
| KB-P1-04 | Projects, workflow states, priorities & labels | KB-P1-02 |
| KB-P1-05 | `issues` table, sequence allocation & `build_markdown_tsvector()` | KB-P1-04 |
| KB-P1-06 | Parent DAG trigger with `ltree` ancestry | KB-P1-05 |
| KB-P1-07 | Created-by provenance trigger | KB-P1-05, KB-P1-12 |
| KB-P1-08 | Cycles, modules, assignees, labels & subscriptions join tables | KB-P1-05 |
| KB-P1-09 | Comments, stickies, docs & pages (Markdown-only) | KB-P1-05 |
| KB-P1-10 | Views table | KB-P1-04 |
| KB-P1-11 | `object_links` + link-type matrix | KB-P1-02 |
| KB-P1-12 | Partitioned hash-chained `activity_records` | KB-P1-02 |
| KB-P1-13 | Resource ACLs & `effective_resource_access` materialization | KB-P1-03, KB-P1-04 |
| KB-P1-14 | `FORCE RLS` policies & session context binding | KB-P1-13, KB-P1-09, KB-P1-08, KB-P1-11 |
| KB-P1-15 | `audit_object_links()` 6-reason detector | KB-P1-11, KB-P1-13 |
| KB-P1-16 | `purge_invalid_object_links()` audited purge | KB-P1-15, KB-P1-12 |
| KB-P1-17 | SQLAlchemy 2.0 async models & RLS session context | KB-P1-14 |
| KB-P1-18 | Transactional outbox & `RealtimeBroker` (PG `LISTEN/NOTIFY` impl) | KB-P1-17 |

### Epic Definition of Done
- [ ] All 18 child tickets (KB-P1-01 .. KB-P1-18) are in state `Done`, each closed only after a local `reality-checker` grade-A `READY` certification recorded in its `docs/qa/<TICKET_ID>/` bundle.
- [ ] Every child ticket tagged `[UI]` has `docs/qa/<TICKET_ID>/ui-specialist-review.md`; every child tagged `[API]` has both `api-specialist-review.md` and `ui-specialist-review.md`; every child tagged `[DEP]` has `dependency-evaluation.md`.
- [ ] Phase-level CI is green via Dash (`status` / `wait` / `logs`) on the `main` commit that closes the last child ticket, with all CI jobs passing and `--cov-fail-under=95` / `vitest` `95%` thresholds enforced.
- [ ] Zero open tickets labeled as gaps discovered during this phase remain unlinked to a follow-up ticket.

### Exit Criteria (Spec S15.5)
- Spec S15.5 item 2 (Phase 1): All 9 object classes (`*_markdown` + `STORED` `sha256` + `tsvector`), `principals`, `effective_resource_access`, `activity_records` hash chain, and `audit_object_links()` / `purge_invalid_object_links()`.
- Catalog test proves every tenant table has `FORCE ROW LEVEL SECURITY` and zero `*_html` / `*_ast` columns exist (KB-P1-09, KB-P1-14 proof).
