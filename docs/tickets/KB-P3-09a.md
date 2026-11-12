---
id: KB-P3-09a
title: "[Phase 3 / API] Archive / unarchive with Plane rule & periodic auto-archive job"
epic: KB-E3
depends_on: [KB-P3-02]
spec_sections: ["7.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P3-09` is split into `KB-P3-09a` (archive + auto-archive) and `KB-P3-09b` (delete preview, soft trash, restore, purge).

### User Story
As a **project member**, I need **to archive only completed or cancelled issues (with the exact explanatory error otherwise) and have a job auto-archive them after the project's configured days** so that **boards stay clean using Plane's exact archive rule**.

**Requirement Traceability:** Spec S7.2 `8p`; requirement `#8p` | **Dependencies:** `KB-P3-02`

### Scoped Technical Actions
1. **Target Files:** `kanban/api/v1/issue_archive.py`, `kanban/services/issue_archive.py`, `kanban/jobs/auto_archive.py`, `kanban/jobs/__init__.py` (job registry + lifespan scheduler), `kanban/cli/jobs.py` (`kanban-ctl jobs run auto-archive`), `kanban/services/activity.py` (append events).
2. **Endpoints:**

   | Method + Path | Capability | Success | Errors |
   | :-- | :-- | :-- | :-- |
   | `POST /api/v1/issues/{issue_ref}/archive` | `EDIT` | `200` issue with `archived_at` | `404`, `403`, `409 ARCHIVE_NOT_ALLOWED`, `409 ALREADY_ARCHIVED` |
   | `POST /api/v1/issues/{issue_ref}/unarchive` | `EDIT` | `200` | `404`, `403`, `409 NOT_ARCHIVED` |
   | `GET /api/v1/projects/{project_ref}/issues?include_archived=true` | `VIEW` | `200` (extends KB-P3-02 list) | `404` |

   - Rule: archive allowed only when the issue's `workflow_states.group IN ('completed', 'cancelled')`. Otherwise:
     ```json
     {"status": 409, "code": "ARCHIVE_NOT_ALLOWED", "title": "Archive not allowed",
      "detail": "Only completed or canceled work items can be archived", "state_group": "started"}
     ```
     The `detail` string is exactly `Only completed or canceled work items can be archived` (S7.2 `8p`).
   - Archive sets `objects.archived_at = clock_timestamp()`; unarchive sets it to `NULL`. Archived issues are read-only: KB-P3-02 `PATCH` on an archived issue returns `409 ISSUE_ARCHIVED` (add this check in `kanban/services/issues.py`).
   - Issue serializer adds `"archived_at"` and `"archive_eligibility": {"allowed": false, "reason": "Only completed or canceled work items can be archived"}` so the UI disables the menu item with the inline reason.
3. **Auto-archive job (`kanban/jobs/auto_archive.py`):** `async def run_auto_archive(now: datetime, *, batch_size: int = 500) -> AutoArchiveReport`.
   - For each project with `auto_archive_days IS NOT NULL`, archive issues whose state group is `completed`/`cancelled`, `archived_at IS NULL`, `deleted_at IS NULL`, and whose latest `ISSUE_STATE_CHANGED` activity (fallback `objects.created_at`) is `<= now - auto_archive_days`.
   - Runs under a dedicated `SERVICE_PRINCIPAL` (`system:auto-archive`) with RLS context bound per project; processes at most `batch_size` issues per transaction; returns `{"projects_scanned", "issues_archived", "batches"}`.
   - Scheduling: registered in the lifespan job registry with interval `3600s` (single-runner guarded by `pg_try_advisory_lock(hashtext('kanban.auto_archive'))`); also invocable via `kanban-ctl jobs run auto-archive [--now ISO8601]`, exit code `0` on success, `1` on error.
4. **Activity events emitted (category `HISTORY`):** `ISSUE_ARCHIVED {mode: "manual" | "auto", auto_archive_days?}`, `ISSUE_UNARCHIVED {}`.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_issue_archive.py`, `kanban/tests/jobs/test_auto_archive.py`
- **Required Test Cases:**
  1. Positive: archiving a `Done` issue returns `200`, sets `archived_at`, writes `ISSUE_ARCHIVED {mode: "manual"}`; default list excludes it, `include_archived=true` includes it.
  2. Rule: archiving an `In Progress` issue returns `409` with the exact `detail` string; serializer shows `archive_eligibility.allowed == false` with the same reason.
  3. Security: non-viewer `404`; `VIEW`-only user `403`; `PATCH` on archived issue returns `409 ISSUE_ARCHIVED`.
  4. Job boundary: `auto_archive_days=7`; issue completed exactly 7 days ago is archived, 6 days 23 hours ago is not; project with `NULL` days is skipped; cancelled issue is archived; `batch_size=2` with 5 eligible issues yields `batches == 3`.
  5. Job concurrency: second concurrent run that fails to get the advisory lock returns `issues_archived == 0` (`@pytest.mark.committed_db`).
  6. CLI: `kanban-ctl jobs run auto-archive --now 2026-11-11T00:00:00Z` exits `0` and prints the JSON report.
- Clean-DB `SAVEPOINT` harness. Coverage `>= 95%`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** target files exist; 2 endpoints, list flag, `run_auto_archive`, scheduler registration and CLI implemented.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_issue_archive.py kanban/tests/jobs/test_auto_archive.py -q --cov=kanban.api.v1.issue_archive --cov=kanban.services.issue_archive --cov=kanban.jobs.auto_archive --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check kanban && uv run mypy --strict kanban && uv run lint-imports` exits `0`.
- [ ] **Contract Sample:** includes archive `200`, `409 ARCHIVE_NOT_ALLOWED` with exact detail, unarchive `200`, `404`.
- [ ] **Specialist Reviews:** `api-specialist-review.md` and `ui-specialist-review.md` with `APPROVED`.
- [ ] **Forensic Proof Packet Complete.**

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/contract-sample.json` - via `KB_TICKET_ID=<TICKET_ID> KB_CONTRACT_OUT=docs/qa/<TICKET_ID>/contract-sample.json uv run pytest kanban/tests/api/test_issue_archive.py -q`.
5. `docs/qa/<TICKET_ID>/cli-run.txt` - raw output of `uv run kanban-ctl jobs run auto-archive --now 2026-11-11T00:00:00Z` against the test fixture DB.
6. `docs/qa/<TICKET_ID>/api-specialist-review.md`
7. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - confirms `archive_eligibility` drives the disabled `🗄️ Archive` menu item and reason text.
8. Screenshots: N/A - Non-UI Ticket.
