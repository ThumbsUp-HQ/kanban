---
id: KB-P3-10b
title: "[Phase 3 / API] Modules API with modules_enabled feature-flag 404 & issue module assignment"
epic: KB-E3
depends_on: [KB-P3-01a, KB-P3-02]
spec_sections: ["7.2", "11.4"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: second half of manifest row `KB-P3-10`. `KB-P3-02` added as a dependency for issue module assignment.

### User Story
As a **Project Administrator**, I need **module CRUD and per-issue module assignment that completely disappears (404-equivalent) when `modules_enabled = FALSE`** so that **projects that do not use modules have zero module clutter in the API or UI**.

**Requirement Traceability:** Spec S7.2 `8f`; S11.4 tool 6; requirement `#8f` | **Dependencies:** `KB-P3-01a`, `KB-P3-02`

### Scoped Technical Actions
1. **Target Files:** `kanban/api/v1/modules.py`, `kanban/api/v1/schemas/modules.py`, `kanban/services/modules.py`, `kanban/api/v1/deps.py` (add `require_modules_enabled` dependency), `kanban/services/activity.py` (append events).
2. **Feature flag dependency `require_modules_enabled(project)`:** when `projects.modules_enabled = FALSE`, every endpoint below returns:
   ```json
   {"type": "https://kanban/problems/not-found", "status": 404, "code": "MODULES_DISABLED", "title": "Not Found"}
   ```
   Order of checks: project unreadable -> plain `404 NOT_FOUND` (equalized, no `MODULES_DISABLED` code, so the code is only visible to callers who can already read the project) -> modules disabled -> `404 MODULES_DISABLED` -> capability check.
3. **Endpoints:**

   | Method + Path | Capability | Success | Errors |
   | :-- | :-- | :-- | :-- |
   | `GET /api/v1/projects/{project_ref}/modules` | `VIEW` | `200` | `404`, `404 MODULES_DISABLED` |
   | `POST /api/v1/projects/{project_ref}/modules` | project `ADMIN` | `201` | `404`, `403`, `409 MODULE_NAME_TAKEN`, `422` |
   | `GET /api/v1/modules/{module_id}` | `VIEW` | `200` | `404` |
   | `PATCH /api/v1/modules/{module_id}` | project `ADMIN` | `200` | `404`, `403`, `409`, `422` |
   | `DELETE /api/v1/modules/{module_id}` | project `ADMIN` | `204` (removes `issue_modules` and `project_module_defaults` rows) | `404`, `403` |
   | `PUT /api/v1/issues/{issue_ref}/modules` body `{"module_ids": [...]}` | `EDIT` on issue | `200` | `404`, `403`, `404 MODULES_DISABLED`, `422 MODULE_NOT_IN_PROJECT`, `422 MODULE_LIMIT` |

   - Module body: `{"name": "Auth Core", "description_markdown": "", "lead_principal_id": null, "status": "in_progress"}`; `name` `1..120`, unique per project case-insensitively; `description_markdown` through KB-P2-13 normalizer, max `65536` bytes; `status` in `backlog|planned|in_progress|paused|completed|cancelled`; `lead_principal_id` must hold project `VIEW` (`422 LEAD_NOT_ELIGIBLE`, identical body for nonexistent). Module create registers an `objects` row (`object_type='module'`).
   - `PUT .../modules` replaces the set; max `10` modules per issue, unique; modules from other projects return `422 MODULE_NOT_IN_PROJECT`.
   - Module serializer: `{"id", "name", "status", "lead": {...} | null, "issue_count", "completed_count"}`.
   - Issue serializer (KB-P3-02) omits the `module_ids` key entirely when `modules_enabled = FALSE` (S7.2 `8f`: row unmounted).
4. **Activity events emitted (category `HISTORY`):** `MODULE_CREATED`, `MODULE_UPDATED {changes}`, `MODULE_DELETED {removed_issue_links}` against the module object; `ISSUE_MODULES_CHANGED {added, removed}` against the issue.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_modules.py`
- **Required Test Cases:**
  1. Positive: with `modules_enabled=true`, create module `201`, assign to issue `200`, list shows `issue_count: 1`; `MODULE_CREATED` and `ISSUE_MODULES_CHANGED` rows written.
  2. Feature flag: with `modules_enabled=false`, each of the 6 endpoints returns `404` with `code: MODULES_DISABLED` for a project viewer; issue `GET` response has no `module_ids` key.
  3. Security: a non-viewer receives plain `404 NOT_FOUND` without `code: MODULES_DISABLED` (assert body identical to a nonexistent project); `EDIT` member module create `403`; non-viewer lead `422 LEAD_NOT_ELIGIBLE`.
  4. Boundary: 10 modules on one issue accepted, 11 returns `422 MODULE_LIMIT`; duplicate name `409`; 65537-byte description `422`.
  5. Delete cascade: deleting a module removes it from issues and from `project_module_defaults`; `MODULE_DELETED.removed_issue_links` equals the count.
- Clean-DB `SAVEPOINT` harness. Coverage `>= 95%`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** target files exist; 6 endpoints and `require_modules_enabled` implemented.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_modules.py -q --cov=kanban.api.v1.modules --cov=kanban.services.modules --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check kanban && uv run mypy --strict kanban && uv run lint-imports` exits `0`.
- [ ] **Contract Sample:** includes module create `201`, issue assign `200`, `404 MODULES_DISABLED`, non-viewer plain `404`, `422 MODULE_LIMIT`.
- [ ] **Specialist Reviews:** `api-specialist-review.md` and `ui-specialist-review.md` with `APPROVED`.
- [ ] **Forensic Proof Packet Complete.**

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/contract-sample.json` - via `KB_TICKET_ID=<TICKET_ID> KB_CONTRACT_OUT=docs/qa/<TICKET_ID>/contract-sample.json uv run pytest kanban/tests/api/test_modules.py -q`.
5. `docs/qa/<TICKET_ID>/api-specialist-review.md`
6. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - confirms `MODULES_DISABLED` and absent `module_ids` let the UI unmount the Modules row, tab and facet.
7. Screenshots: N/A - Non-UI Ticket.
