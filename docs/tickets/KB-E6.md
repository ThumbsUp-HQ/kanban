---
id: KB-E6
title: "[Phase 6 / Epic] Cutover, Hardening & Release"
type: epic
children: [KB-P6-01, KB-P6-02, KB-P6-03, KB-P6-04, KB-P6-05]
spec_sections: ["1.3", "2.2", "3.5", "9", "14", "15.1", "15.5"]
gates: [reality-checker]
state: Backlog
---

### Goal
Import the bootstrap board at `https://kanban.hackedyour.info/kanban/` losslessly with `KANBA-*` key continuity, verify zero invalid object links, lock in STRIDE security regression and performance budget suites in CI, and ship backup/restore plus standalone-to-production promotion.

### Scope Summary
- Importer and cutover: KB-P6-01, KB-P6-02.
- Hardening: KB-P6-03 (STRIDE suite), KB-P6-04 (performance budgets).
- Operations: KB-P6-05 (backup/restore, promotion).

### Child Tickets
| ID | Title | Deps |
| :-- | :-- | :-- |
| KB-P6-01 | Plane importer (`kanban-ctl import plane`) | KB-P3-* backend complete, KB-P2-13 |
| KB-P6-02 | Cutover runbook & zero-invalid-link verification | KB-P6-01, KB-P1-15 |
| KB-P6-03 | STRIDE security regression suite | KB-P4-07, KB-P5-21, KB-P2-15 |
| KB-P6-04 | Performance budget suite | KB-P5-09, KB-P5-17, KB-P0-08 |
| KB-P6-05 | Backup/restore & standalone -> production promotion | KB-P0-08, KB-P0-11 |

### Epic Definition of Done
- [ ] All 5 child tickets (KB-P6-01 .. KB-P6-05) are in state `Done`, each closed only after a local `reality-checker` grade-A `READY` certification recorded in its `docs/qa/<TICKET_ID>/` bundle.
- [ ] Every child ticket tagged `[UI]` has `docs/qa/<TICKET_ID>/ui-specialist-review.md`; every child tagged `[API]` has both `api-specialist-review.md` and `ui-specialist-review.md`; every child tagged `[DEP]` has `dependency-evaluation.md`.
- [ ] Phase-level CI is green via Dash (`status` / `wait` / `logs`) on the `main` commit that closes the last child ticket, with all CI jobs passing and `--cov-fail-under=95` / `vitest` `95%` thresholds enforced.
- [ ] Zero open tickets labeled as gaps discovered during this phase remain unlinked to a follow-up ticket.

### Exit Criteria (Spec S15.5)
- Spec S15.5 item 7 (Phase 6): Lossless `KANBA-*` migration, Link Auditor zero-invalid check, and full self-hosted dogfooding.
