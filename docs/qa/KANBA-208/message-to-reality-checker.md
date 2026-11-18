# Verification Proof & Reality-Checker Submission: KANBA-208

## Metadata
- **Ticket ID:** `KANBA-208`
- **Ticket Title:** [KB-AUDIT-02] Fix Standalone Backup & Schedule 500s (pg_dump Permissions), Restore kanban-ctl to Container PATH, and Fix Studio Modal/Tab Accessibility
- **Assignee:** `w1-ops`
- **Worktree Branch:** `feat/w1-ops`
- **Submission Date:** 2026-11-18

---

## 1. Scope & Verification Packet Inventory

The forensic QA proof packet is organized inside `docs/qa/KANBA-208/`:
- `git-diff.patch`: Unified diff of all modifications across `Dockerfile`, `deploy/standalone/entrypoint.py`, `kanban/api/v1/system_status.py`, `kanban/jobs/scheduled_backup.py`, `kanban/web/src/features/standalone/`, and test suites.
- `unit-test-results.txt`: Raw execution output from `uv run pytest` (41 passed) and `vitest run --coverage` (29 passed, statements: 99.41%, branch: 95.29%, lines: 99.69%).
- `build-check.txt`: Static analysis and formatting logs (`typecheck`, `eslint --max-warnings 0`, `ruff check`, `mypy`, `check_no_dashes --all`).
- `ui-specialist-review.md`: Verbatim UI/UX specialist audit with `APPROVED` verdict.
- `api-specialist-review.md`: Verbatim API specialist audit with `APPROVED` verdict.
- `screenshots/`: 24 full-resolution PNG artifacts covering Light, Dark, Desktop (1440x900), Tablet (1024x768), and Mobile (390x844) viewports.

---

## 2. Requirement Verification Matrix

| Requirement | Implementation Artifacts | Verification Method & Output | Status |
| :--- | :--- | :--- | :---: |
| 1. Fix `pg_dump` Permissions (`500`) | `deploy/standalone/entrypoint.py:ensure_backup_grants` | `tests/deploy/test_standalone_entrypoint.py` (20 passed), `kanban/tests/api/test_system_status.py` (11 passed) | PASS |
| 2. Fix Backup Schedule 500 & Error Alerts | `kanban/api/v1/system_status.py`, `StandaloneStatusPanel.tsx` | `StandaloneStatusPanel.test.tsx` (cases asserting inline alert & correlation ID), 29 passed | PASS |
| 3. Restore `kanban-ctl` & `kanban-agent` in PATH | `Dockerfile` (wrapper scripts, ENV PATH) | `tests/deploy/test_dockerfile.py:test_kanban_ctl_and_agent_in_container_path` | PASS |
| 4. Modal Height & Scroll Accessibility | `StandaloneStatusPanel.css`, `StandaloneStatusPanel.tsx` | Playwright screenshots in `docs/qa/KANBA-208/screenshots/`, roving tabindex tests | PASS |
| 5. WAI-ARIA Tab Navigation | `StandaloneStatusPanel.tsx:handleTabKeyDown` | `ArrowRight`, `ArrowLeft`, `Home`, `End` unit tests | PASS |
| 6. Mobile 390x844 Tab Bar Layout | `StandaloneStatusPanel.css` (`overflow-x: auto`) | Playwright mobile screenshots (zero tab clipping/crushing) | PASS |
| 7. >=95% Unit/Branch Coverage | Touched backend and frontend files | Coverage report: statements 99.41%, branches 95.29%, lines 99.69% | PASS |
| 8. Dual Specialist Gate Sign-Off | `docs/qa/KANBA-208/ui-specialist-review.md`, `api-specialist-review.md` | Both specialists issued independent `APPROVED` verdicts | PASS |

---

## 3. Request for Reality-Checker Forensic Audit

Please audit this verification packet against the requirements of `KANBA-208` and the project invariants defined in `GEMINI.md`.
