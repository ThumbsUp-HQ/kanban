# Forensic QA Reality-Checker Audit Report: KANBA-208

## Metadata
- **Ticket ID:** `KANBA-208`
- **Title:** [KB-AUDIT-02] Fix Standalone Backup & Schedule 500s (pg_dump Permissions), Restore kanban-ctl to Container PATH, and Fix Studio Modal/Tab Accessibility
- **Module:** `deploy.standalone`, `kanban.api.v1.system_status`, `kanban.standalone`, `kanban.web.features.standalone`
- **Evaluated Branch:** `feat/w1-ops`
- **Auditor:** reality-checker (Passive Forensic QA Gate)
- **Date:** 2026-11-18
- **Overall Grade:** A
- **Verdict:** READY

---

## 1. Reality Check & Scope Validation

### 1.1 UI & Visual Proof Audit
- **Classification:** Standalone System Status Modal, Accessibility Navigation, Backup/Schedule APIs, and Docker Deployment Configuration.
- **UI Modifications:** Modifies modal CSS layout (`max-height: calc(100vh - 64px)`, scroll body containment, mobile tab bar horizontal scrolling) and React component logic (`StandaloneStatusPanel.tsx`).
- **Visual Artifacts:** 24 full-resolution Playwright screenshot files captured in `docs/qa/KANBA-208/screenshots/`.
  - Desktop (`1440x900`): Light and Dark modes for Health, Backup, Compose tabs, and tall error banner scrolling.
  - Tablet (`1024x768`): Light and Dark modes for all three tabs and error banner scrolling.
  - Mobile (`390x844`): Light and Dark modes for all three tabs and error banner scrolling.
  - Forensic Inspection: Directly inspected via `read_file`. Confirmed zero occlusion of modal tabs or close button, zero text clipping on mobile tab bar, proper high-contrast error banners with visible correlation IDs, and flawless dark mode styling.

### 1.2 Specialist Gates Cross-Validation
- **Dual Specialist Mandate:** Both UI and API specialists must audit and approve changes modifying API endpoints and frontend presentation.
- **UI Specialist Review:** `docs/qa/KANBA-208/ui-specialist-review.md` present and audited.
  - Reviewer: `ui-specialist` (ArchitectUX & UI Designer Persona).
  - Assessment: Verified modal body scrolling, WAI-ARIA roving keyboard navigation (`ArrowRight`, `ArrowLeft`, `Home`, `End`), mobile viewport stability on `390x844`, design token compliance, and Playwright screenshot inspection.
  - Verdict: **APPROVED**.
- **API Specialist Review:** `docs/qa/KANBA-208/api-specialist-review.md` present and audited.
  - Reviewer: `api-specialist` (Backend Architect & API Tester Persona).
  - Assessment: Verified `ensure_backup_grants` executes `GRANT SELECT ON TABLE alembic_version TO kanban_app, app_rls_reader`, typed `ProblemException` handling with correlation tracking on backup schedule and run-now endpoints, and container `$PATH` restoration in Dockerfile.
  - Verdict: **APPROVED**.

---

## 2. Forensic Proof Packet Inspection (`docs/qa/KANBA-208/`)

1. **`git-diff.patch`**:
   - Accurately captures all modifications on branch `feat/w1-ops`.
   - Modifies `Dockerfile`: adds wrapper scripts `/usr/local/bin/kanban-ctl` and `/usr/local/bin/kanban-agent`, updates `ENV PATH=/opt/kanban/.venv/bin:/usr/local/bin:$PATH`, and sets `0775` permissions on `/var/lib/kanban/data/backups`.
   - Modifies `deploy/standalone/entrypoint.py`: adds `ensure_backup_grants` and directory ownership validation.
   - Modifies `kanban/api/v1/system_status.py`: typed problem responses for backup schedule and immediate snapshot endpoints.
   - Modifies `kanban/web/src/features/standalone/StandaloneStatusPanel.tsx` & `.css`: modal viewport containment, body scroll, WAI-ARIA keyboard navigation, dismissible alert with correlation ID.
   - Comprehensive unit and E2E screenshot test additions.

2. **`unit-test-results.txt`**:
   - Backend pytest suite: 41 passed in 3.97s with 0 failures (`tests/deploy/test_dockerfile.py`, `tests/deploy/test_standalone_entrypoint.py`, `kanban/tests/api/test_system_status.py`).
   - Frontend unit test suite: 29 passed in 3.67s with 0 failures (`StandaloneStatusPanel.test.tsx`).
   - Code Coverage:
     - Statements: 99.41% (threshold >=95%).
     - Branches: 95.29% (threshold >=95%).
     - Functions: 98.11% (threshold >=95%).
     - Lines: 99.69% (threshold >=95%).

3. **`build-check.txt`**:
   - TypeScript Typecheck (`tsc -b --noEmit`): Exit 0, 0 errors.
   - Frontend ESLint (`eslint src/features/standalone --max-warnings 0`): Exit 0, 0 warnings.
   - Python Ruff Lint (`ruff check`): All checks passed.
   - Python MyPy (`mypy deploy/ kanban/`): Success in 516 source files.
   - Plain ASCII Dash Check (`scripts.check_no_dashes --all`): Passed with 0 em/en-dash violations.

4. **`screenshots/`**:
   - Complete set of 24 PNG screenshot files documenting Light, Dark, Desktop, Tablet, and Mobile viewports.

---

## 3. Definition of Done Compliance Matrix

| Requirement | Implementation Evidence | Status |
| :--- | :--- | :---: |
| Fix `pg_dump` Permission Denied (`500`) | `ensure_backup_grants()` grants SELECT on `alembic_version` to `kanban_app, app_rls_reader` | PASS |
| Fix Backup Schedule 500 & Error Alerts | Typed problem responses, dismissible inline alert card with correlation ID in UI | PASS |
| Restore `kanban-ctl` & `kanban-agent` to PATH | Wrapper scripts in `/usr/local/bin` and virtualenv PATH in `Dockerfile` (6 stages intact) | PASS |
| Modal Viewport Containment & Body Scroll | `.standalone-panel` enforces `max-height: calc(100vh - 64px)` with internal scroll | PASS |
| WAI-ARIA Tab Keyboard Navigation | Tablist handles `ArrowRight`, `ArrowLeft`, `Home`, and `End` with roving tabindex | PASS |
| Mobile 390x844 Layout Stability | `overflow-x: auto`, `white-space: nowrap`, and `flex-shrink: 0` prevent tab crushing | PASS |
| >=95% Unit/Branch Coverage | Frontend coverage: 99.69% lines, 95.29% branches; Backend: 41 tests passing | PASS |
| Dual Specialist Reviews | Verbatim UI Specialist and API Specialist `APPROVED` reviews logged | PASS |
| Comprehensive Proof Packet | Complete unified diff, test outputs, build checks, and 24 visual artifacts | PASS |

---

## 4. Certification

The forensic proof submitted in `docs/qa/KANBA-208/` provides indisputable, comprehensive evidence of correctness, architectural isolation, security hardening, accessibility compliance, and visual quality.

- **Grade:** A
- **Verdict:** READY
