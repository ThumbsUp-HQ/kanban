# KANBA-223: Forensic Verification Proof Packet for reality-checker

## Ticket Overview
- **Ticket ID:** KANBA-223
- **Title:** [KB-AUDIT-17] Build Automated Multi-Role Missing-Control RBAC, Zero-Mock-Data, and Light/Dark/Mobile Visual Regression Gate in Playwright CI
- **Owner / Builder:** w7-e2e
- **Branch:** feat/w7-e2e
- **Target Repository:** thumbs-up-kanban
- **Verification Gate Standard:** reality-checker Forensic QA Gate (Grade A - READY)

---

## Deliverables Summary

1. **Production Container Cold-Boot Smoke Gate:**
   - Spec file: `kanban/web/e2e/qa/kanba-223-smoke-coldboot.spec.ts`
   - Automated CI harness: `scripts/ci/cold_boot_smoke_gate.sh`
   - Validates that `kanban-ctl --help` exits `0` and exposes complete operational commands (`backup`, `restore`, `promote`, `jobs`, `auth`, `import`, `cutover`, `db`).
   - Validates `/setup` cold-boot bootstrap, TOTP emergency recovery code enrollment, and `/confirm` transition to `AAL2`.
   - Validates stale-cookie `/login` recovery redirects cleanly to login form without 500 crashes.
   - Validates `POST /api/v1/admin/standalone/backup` returns `200` with encrypted archive metadata without unexpected network errors (`500`, `404`, `422`, `428`).

2. **6-Role Missing-Control DOM and Route-Guard Gate:**
   - Spec file: `kanban/web/e2e/qa/kanba-223-rbac-missing-controls.spec.ts`
   - Audits DOM controls across all 6 roles: `@guest`, `@viewer`, `@member`, `@projadmin`, `@wsadmin`, and `@admin`.
   - Asserts exact `count() === 0` for disallowed buttons/links:
     - `@guest`: exact 0 write controls, 0 synthetic KAN dummy cards, "No accessible projects".
     - `@viewer`: exact 0 create buttons (`+ New work item`, `+ New`, `+ Create Cycle`), 0 inline edit triggers, 0 row checkboxes.
     - `@member`: exact 0 `+ Create Project` buttons in home or sidebar, 0 Workflow admin buttons.
     - `@projadmin`: exact `Not found or no access` route-guard on unauthorized `/projects/PRJSECRET` and `/admin/standalone`.
     - `@wsadmin`: exact `Not found or no access` route-guard on `/admin/standalone` server administration.
     - `@admin` + `AAL2`: full authorized access to `/admin/standalone` panels.

3. **Closed-Loop Persist + Zero-Mock-Data + ETag/Timezone Gate:**
   - Spec file: `kanban/web/e2e/qa/kanba-223-closed-loop-persist.spec.ts`
   - Asserts created Cycles, Modules, Issues, Stickies, Docs, and MCP keys appear immediately and persist across `F5` browser reloads.
   - Verifies non-description ETag updates and strict ISO date timezone handling (`UTC-5` and `UTC+9`).
   - `assertZeroMockData` fails immediately if any forbidden mock tokens appear in DOM or API traffic (`Alice Cooper`, `Adam Outler`, `Cycle 1`, `Kanban Board`, `state-todo`, `mod-1`, `QAADM-NEW`, `/undefined/`).

4. **Light/Dark Contrast and 390x844 Mobile Overflow Gate:**
   - Spec file: `kanban/web/e2e/qa/kanba-223-visual-contrast-overflow.spec.ts`
   - Sweeps User and Admin studios at `1440x900` (desktop) and `390x844` (mobile) across Light and Dark themes.
   - Asserts 0 contrast failures (<4.5:1 for regular text, <3.0:1 for large text).
   - Asserts responsive layout invariant: `document.documentElement.scrollWidth <= window.innerWidth` (no horizontal viewport blowout).
   - Asserts modal footer action buttons are fully visible and clamped within viewport bounds.

5. **Meta-Assertion Unit Harness:**
   - Files: `kanban/web/e2e/support/gateAuditor.ts` and `kanban/web/e2e/support/gateAuditor.unit.test.ts`
   - 9 Vitest unit tests verifying that `gateAuditor` correctly flags forbidden mock token leaks, validates WCAG 2.1 contrast math, and catches injected violations.

---

## Verification Matrix

| Requirement | Test Implementation | Project / Viewport | Result | Proof Artifact |
| :--- | :--- | :--- | :--- | :--- |
| kanban-ctl --help exits 0 | `kanba-223-smoke-coldboot.spec.ts:87` | Desktop (1440x900) | PASS (1.3s) | `unit-test-results.txt` |
| /setup + TOTP enroll -> AAL2 | `kanba-223-smoke-coldboot.spec.ts:110` | Desktop (1440x900) | PASS (990ms) | `01-coldboot-setup-step3-*.png` |
| Stale cookie /login recovery | `kanba-223-smoke-coldboot.spec.ts:201` | Desktop (1440x900) | PASS (706ms) | `02-stale-cookie-login-recovery-*.png` |
| POST /api/v1/admin/standalone/backup (200) | `kanba-223-smoke-coldboot.spec.ts:272` | Desktop (1440x900) | PASS (1.1s) | `03-admin-standalone-backup-200-*.png` |
| @guest 0 dummy objects & 0 controls | `kanba-223-rbac-missing-controls.spec.ts:194` | Desktop (1440x900) | PASS (1.0s) | `01-guest-rbac-empty-home-*.png` |
| @viewer exact count() === 0 write controls | `kanba-223-rbac-missing-controls.spec.ts:239` | Desktop (1440x900) | PASS (1.6s) | `02-viewer-readonly-board-*.png` |
| @member 0 Create Project buttons | `kanba-223-rbac-missing-controls.spec.ts:342` | Desktop (1440x900) | PASS (1.1s) | `04-member-restricted-home-*.png` |
| @projadmin unauthorized route guard | `kanba-223-rbac-missing-controls.spec.ts:391` | Desktop (1440x900) | PASS (749ms) | `05-unauthorized-project-guard-*.png` |
| @wsadmin standalone admin guard | `kanba-223-rbac-missing-controls.spec.ts:432` | Desktop (1440x900) | PASS (795ms) | `06-admin-standalone-guard-*.png` |
| @admin + AAL2 standalone admin verified | `kanba-223-rbac-missing-controls.spec.ts:464` | Desktop (1440x900) | PASS (986ms) | `07-admin-standalone-verified-*.png` |
| Cycle & Module F5 persist + UTC-5/UTC+9 | `kanba-223-closed-loop-persist.spec.ts:80` | Desktop (1440x900) | PASS (1.3s) | `01-closed-loop-cycles-persist-*.png` |
| Issue F5 persist + ETag concurrency | `kanba-223-closed-loop-persist.spec.ts:213` | Desktop (1440x900) | PASS (1.4s) | `02-closed-loop-issue-board-persist-*.png` |
| Stickies, Docs, MCP Keys F5 persist | `kanba-223-closed-loop-persist.spec.ts:345` | Desktop (1440x900) | PASS (1.9s) | `03-closed-loop-mcp-stickies-persist-*.png` |
| Zero mock data leak assertion | `gateAuditor.ts:assertZeroMockData` | All tests | PASS (0 leaks) | `unit-test-results.txt` |
| User Studios Contrast & 390x844 Overflow | `kanba-223-visual-contrast-overflow.spec.ts:264` | Desktop + Mobile | PASS (2.1s / 2.4s) | `01-user-*-desktop.png`, `01-user-*-mobile.png` |
| Admin Studios Contrast & 390x844 Overflow | `kanba-223-visual-contrast-overflow.spec.ts:311` | Desktop + Mobile | PASS (2.2s / 2.6s) | `02-admin-*-desktop.png`, `02-admin-*-mobile.png` |
| Gate Auditor Meta-Assertion Tests | `gateAuditor.unit.test.ts` | Vitest | PASS (9/9 passed) | `unit-test-results.txt` |
| Production Container Smoke Gate Script | `scripts/ci/cold_boot_smoke_gate.sh` | CLI + Web | PASS (Exit 0) | `build-or-typecheck.txt` |
| TypeScript Compiler Verification | `pnpm tsc -b --noEmit` | Web workspace | PASS (0 errors) | `build-or-typecheck.txt` |
| ESLint Verification | `pnpm eslint ...` | Web workspace | PASS (0 errors) | `build-or-typecheck.txt` |
| Plain ASCII Hyphens Validation | `scripts.check_no_dashes --all` | Repository-wide | PASS (0 violations) | `build-or-typecheck.txt` |

---

## Screenshot Evidence Manifest

All screenshots are stored in `docs/qa/KANBA-223/screenshots/` and have been verified with annotated legends and bounding boxes:

### 1. Production Container Cold-Boot & Authentication Smoke
- `01-coldboot-setup-step3-dark-desktop.png` / `01-coldboot-setup-step3-light-desktop.png`: Step 3 emergency recovery codes and AAL2 session transition.
- `02-stale-cookie-login-recovery-dark-desktop.png` / `02-stale-cookie-login-recovery-light-desktop.png`: Stale cookie session cleared gracefully with login form displayed.
- `03-admin-standalone-backup-200-dark-desktop.png` / `03-admin-standalone-backup-200-light-desktop.png`: Admin standalone studio backup modal returning 200 with encrypted archive metadata.

### 2. 6-Role Missing-Control DOM & Route-Guard Gate
- `01-guest-rbac-empty-home-dark-desktop.png` / `01-guest-rbac-empty-home-light-desktop.png`: Guest home view with 0 write controls and 0 dummy KAN objects.
- `02-viewer-readonly-board-dark-desktop.png` / `02-viewer-readonly-board-light-desktop.png`: Read-only issue board with 0 create buttons, 0 inline edit triggers, and 0 checkboxes.
- `03-viewer-readonly-cycles-dark-desktop.png` / `03-viewer-readonly-cycles-light-desktop.png`: Read-only cycles view with Create Cycle form completely hidden from DOM.
- `04-member-restricted-home-dark-desktop.png` / `04-member-restricted-home-light-desktop.png`: Member home view with 0 Create Project buttons and 0 Add Project in sidebar.
- `05-unauthorized-project-guard-dark-desktop.png` / `05-unauthorized-project-guard-light-desktop.png`: Unauthorized project route returning 404 "Not found or no access" with 0 leaked project sidebar items.
- `06-admin-standalone-guard-dark-desktop.png` / `06-admin-standalone-guard-light-desktop.png`: Workspace admin attempting /admin/standalone blocked with 404 "Not found or no access".
- `07-admin-standalone-verified-dark-desktop.png` / `07-admin-standalone-verified-light-desktop.png`: Full server admin with AAL2 accessing standalone management panel.

### 3. Closed-Loop Persist & Zero-Mock Gate
- `01-closed-loop-cycles-persist-dark-desktop.png` / `01-closed-loop-cycles-persist-light-desktop.png`: Persisted sprint cycle with UTC-5 / UTC+9 dates after F5 reload.
- `02-closed-loop-issue-board-persist-dark-desktop.png` / `02-closed-loop-issue-board-persist-light-desktop.png`: Persisted work item on board with valid ETag concurrency after reload.
- `03-closed-loop-mcp-stickies-persist-dark-desktop.png` / `03-closed-loop-mcp-stickies-persist-light-desktop.png`: Persisted MCP token and stickies note after F5 reload with zero forbidden tokens.

### 4. Light/Dark Contrast & 390x844 Mobile Overflow Gate
- `01-user-cycles-view-dark-desktop.png` / `01-user-cycles-view-light-desktop.png`
- `01-user-cycles-view-dark-mobile.png` / `01-user-cycles-view-light-mobile.png`
- `01-user-issues-board-dark-desktop.png` / `01-user-issues-board-light-desktop.png`
- `01-user-issues-board-dark-mobile.png` / `01-user-issues-board-light-mobile.png`
- `01-user-stickies-canvas-dark-desktop.png` / `01-user-stickies-canvas-light-desktop.png`
- `01-user-stickies-canvas-dark-mobile.png` / `01-user-stickies-canvas-light-mobile.png`
- `02-admin-mcp-access-studio-dark-desktop.png` / `02-admin-mcp-access-studio-light-desktop.png`
- `02-admin-mcp-access-studio-dark-mobile.png` / `02-admin-mcp-access-studio-light-mobile.png`
- `02-admin-standalone-panel-dark-desktop.png` / `02-admin-standalone-panel-light-desktop.png`
- `02-admin-standalone-panel-dark-mobile.png` / `02-admin-standalone-panel-light-mobile.png`
- `02-admin-workspace-settings-dark-desktop.png` / `02-admin-workspace-settings-light-desktop.png`
- `02-admin-workspace-settings-dark-mobile.png` / `02-admin-workspace-settings-light-mobile.png`

---

## Clean-Code and CI Invariants
- Zero forbidden mock tokens in DOM, mocks, or API payloads.
- Strictly plain ASCII hyphens (`-`) used throughout docs and code comments.
- Zero TypeScript compiler errors (`tsc -b --noEmit`).
- Zero ESLint warnings or errors (`eslint`).
- All tests automated in repeatable script: `scripts/ci/cold_boot_smoke_gate.sh`.
