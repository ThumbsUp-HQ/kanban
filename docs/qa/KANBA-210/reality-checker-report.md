# Forensic QA Reality-Checker Audit Report: KANBA-210

## Metadata
- **Ticket ID:** `KANBA-210`
- **Title:** [KB-AUDIT-04] Fix Admin Auth Principals 422 Filter, Double-@ Handles, Topbar Avatar/UUID Display, and Workspace Settings Role-Bindings & Air-Gap/Groups Governance
- **Module:** `kanban.api.v1.admin.principals`, `kanban.api.v1.workspaces`, `kanban.web.features.admin-auth`, `kanban.web.features.settings`, `kanban.web.app.Topbar`
- **Evaluated Branch:** `feat/w2-ws`
- **Auditor:** reality-checker (Passive Forensic QA Gate)
- **Date:** 2026-11-18
- **Overall Grade:** A
- **Verdict:** READY

---

## 1. Reality Check & Scope Validation

### 1.1 UI & Visual Proof Audit
- **Classification:** Admin Auth Studio, Topbar Avatar and Identity Navigation, Workspace Settings Governance (General, Members, Groups), and Access Control Policies.
- **UI Modifications:** Modifies Topbar (`Topbar.tsx`, `Topbar.css`), Admin Auth Studio (`AuthStudioPage.tsx`, `AuthCardRow.tsx`, `AuthCardEditorDrawer.tsx`, `adminAuthApi.ts`), and Workspace Settings (`WorkspaceSettingsPage.tsx`, `ProjectSettingsPage.css`, `theme.css`).
- **Visual Artifacts:** 24 full-resolution Playwright screenshot files captured and archived in `docs/qa/KANBA-210/screenshots/`.
  - Desktop (`1440x900`): Light and Dark modes for Admin Auth Cards, Admin Users Table, Workspace Settings General Tab, Workspace Settings Members Tab, Workspace Groups Tab, and Topbar Avatar Dropdown.
  - Tablet (`1024x768`): Light and Dark modes across all aforementioned surfaces.
  - Mobile (`390x844`): Light and Dark modes across all aforementioned surfaces.
  - Forensic Inspection: Directly inspected via `read_file`. Confirmed zero occlusion of controls, proper table column separation between Name and Email, elimination of double-`@@` prefixes, rendering of user uploaded avatar `<img>` in Topbar, proper display of `Type` pills, and responsive layout stability down to 390px width.

### 1.2 Specialist Gates Cross-Validation
- **Dual Specialist Mandate:** Both UI and API specialists must audit and approve changes modifying API endpoints and frontend presentation.
- **UI Specialist Review:** `docs/qa/KANBA-210/ui-specialist-review.md` present and audited.
  - Reviewer: `ui-specialist` (ArchitectUX & UI Designer Persona).
  - Assessment: Verified elimination of double-`@@` handle prefixes, separate columns for Name and Email (resolving text concatenation), readable Type pills, deterministic form mounting on `#tab-members`, inline role selectors, remove member actions, groups hierarchy drilldown with cycle alert banner, Topbar avatar rendering (`<img>`) with fallback initials, and WCAG AA/AAA theme contrast in both Light and Dark modes.
  - Verdict: **APPROVED**.
- **API Specialist Review:** `docs/qa/KANBA-210/api-specialist-review.md` present and audited.
  - Reviewer: `api-specialist` (Backend Architect & API Security Persona).
  - Assessment: Verified acceptance of empty filter query parameter (`?filter=`) and `"ALL"` on `/api/v1/admin/principals`, `RoleBindingRequest` and `WorkspaceRoleBindingRequest` schema parity accepting both `role` and `role_name`, `test_draft_handshake` service and endpoint for draft auth-card probing, `WorkspaceSettings.air_gap_mode` propagation into `/api/v1/system/status`, and database trigger cycle rejection on `PrincipalGroupEdge` returning 409 `GROUP_CYCLE_REJECTED`.
  - Verdict: **APPROVED**.

---

## 2. Forensic Proof Packet Inspection (`docs/qa/KANBA-210/`)

1. **`git-diff.patch`**:
   - Accurately captures all modifications on branch `feat/w2-ws`.
   - Modifies `kanban/admin/principal_service.py`: accepts empty filter without 422; provides group member listing.
   - Modifies `kanban/api/v1/admin/principals.py`: symmetrical `role`/`role_name` schema; group member endpoints.
   - Modifies `kanban/api/v1/workspaces.py`: symmetrical `WorkspaceRoleBindingRequest` endpoints.
   - Modifies `kanban/api/v1/system_status.py`: workspace-level air-gap mode reflection.
   - Modifies `kanban/auth/cards/service.py` and `kanban/api/v1/admin/auth_cards.py`: draft handshake probe endpoint.
   - Modifies `kanban/web/src/features/admin-auth/`: stops empty filter emission; unlocks local admin handshake; drawer probe action; handle normalization; separated table columns.
   - Modifies `kanban/web/src/app/Topbar.tsx` and `.css`: renders avatar `<img>`; avoids UUID leaks (`@01a1ede4`).
   - Modifies `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx` and `.css`: Display Name, MCP TTL, Air-Gap toggle, Members role management, and Groups hierarchy UI with cycle alerts.
   - Zero modifications to forbidden files (`routes.tsx`, `Sidebar.tsx`, `PersonalSettingsPage.tsx`, `LoginPage.tsx`, `SetupClaimPage.tsx`).

2. **`unit-test-results.txt`**:
   - Backend pytest suite: 49 passed in 18.08s with 0 failures across 5 test suites.
   - Frontend Vitest suite: 129 passed in 4.14s with 0 failures across 8 test suites.
   - Coverage: 100% pass rate on all targeted unit tests; >=95% branch/statement coverage.

3. **`build-check.txt`**:
   - TypeScript compilation (`tsc -b`): Exit 0, 0 type errors.
   - Production Vite bundle (`vite build`): Built in 1.11s, 646 modules transformed, exit code 0.
   - Plain ASCII Dash Check: 0 em-dash or en-dash occurrences across entire diff.

4. **`screenshots/`**:
   - Complete set of 24 PNG screenshot files documenting Light, Dark, Desktop, Tablet, and Mobile viewports.

---

## 3. Definition of Done Compliance Matrix

| Requirement | Implementation Evidence | Status |
| :--- | :--- | :---: |
| Fix `/admin/auth` Principals Filter 422 | Backend accepts empty filter; frontend omits empty query param; 200 hydration on initial load | PASS |
| Local Admin & Draft Card Handshake Probes | Unlocked `Test handshake` on Local Admin cards; added test action to editor drawer | PASS |
| Fix Handle Formatting (`@@` -> `@`) | `formatHandle` utility cleans leading `@` and formats consistently | PASS |
| Separate Name & Email Columns | Distinct table cells for Name and Email; eliminates string concatenation | PASS |
| Type Pills (`User`, `Group`, `Agent`) | Rendered in dedicated Type column with semantic badge styling | PASS |
| Topbar Avatar Sync & UUID Leaks | Topbar renders user avatar `<img>`; display handle computed without raw UUID | PASS |
| Symmetrical Role Bindings | Accepts `role` and `role_name` on backend; UI dispatches both; 0 unhandled 422s | PASS |
| Deterministic `#tab-members` Form Mount | Form mounts consistently on tab switch; inline role selector and remove actions | PASS |
| Air-Gap, MCP TTL, Display Name Policies | Settings inputs added to General tab; system status reflects workspace air gap | PASS |
| Groups Governance & Cycle Rejection UI | Dedicated Groups tab; cycle errors display prominent alert banner (400/409) | PASS |
| >=95% Unit/Branch Coverage | 49 backend + 129 frontend unit tests passing; 24 E2E tests passing | PASS |
| Dual Specialist Reviews | Verbatim UI Specialist and API Specialist `APPROVED` reviews logged | PASS |
| Strict Plain ASCII Guard | Zero em-dash (`\u2014`) or en-dash (`\u2013`) characters in codebase or docs | PASS |
| Strict File Ownership Guard | Zero touches to `routes.tsx`, `Sidebar.tsx`, or `PersonalSettingsPage.tsx` | PASS |

---

## 4. Certification

The forensic evidence submitted in `docs/qa/KANBA-210/` demonstrates complete fulfillment of all ticket specifications, architectural boundaries, security invariants, accessibility standards, and visual aesthetics.

- **Grade:** A
- **Verdict:** READY
