# Reality-Checker Verification Packet: KANBA-114 (KB-P3-49)

- **Ticket:** `KANBA-114` (`KB-P3-49`: `[Phase 3 / Frontend] Effective Access Inspector popover: Users, Groups, Agents kill-switch, Deny overrides & redaction`)
- **Branch:** `feat/KANBA-114`
- **Worktree:** `/tmp/kb-wt-KANBA-114`
- **Unit Test Coverage:** 100% Statements, 96.57% Branches, 100% Functions, 100% Lines (exceeds mandatory >=95% threshold)
- **Static Analysis & Builds:** All clean (TypeScript typecheck exit 0, ESLint exit 0 with 0 warnings, Vite build exit 0, Check-no-dashes 0 violations)
- **E2E Tests:** 9/9 passing across desktop, tablet, and mobile projects in Playwright

---

### 1. Verification Matrix & Scoped DoD Criteria

| Requirement / Criterion | Status | Evidence File / Command |
| :--- | :--- | :--- |
| **Component Files:** `AccessInspectorPopover.tsx`, `.css`, `AgentKillSwitchControl.tsx`, `useAccessInspector.tsx`, `index.ts`, `types.ts` | PASS | `kanban/web/src/features/access/` |
| **AppShell Integration:** `<AccessInspectorHost />` wired inside shell | PASS | `kanban/web/src/app/AppShell.tsx` |
| **Unit Test Coverage (>=95%):** 22 tests passing with 100% stmts, 96.57% branch, 100% funcs, 100% lines | PASS | `docs/qa/KANBA-114/unit-test-results.txt` |
| **Build / Type / Lint Clean:** `typecheck`, `lint`, and `build` exit 0 with 0 errors | PASS | `docs/qa/KANBA-114/build-check.txt` |
| **Playwright E2E:** 9/9 tests passed across desktop, tablet, and mobile | PASS | `docs/qa/KANBA-114/e2e-results.txt` |
| **Computed Whitespace Proof:** `min-height: 38px`, `24px x 24px` emoji hints, `8.6:1` contrast | PASS | `docs/qa/KANBA-114/computed-styles-*.json` |
| **Annotated Screenshots:** 9 responsive screenshots (3 scenarios x 3 viewports) | PASS | `docs/qa/KANBA-114/screenshots/` |
| **Contract Sample:** Raw `access_manifest` and `POST .../agent-kill-switch` exchange | PASS | `docs/qa/KANBA-114/contract-sample.json` |
| **Specialist Gates:** UI and API specialist reviews | PENDING | `docs/qa/KANBA-114/ui-specialist-review.md`<br>`docs/qa/KANBA-114/api-specialist-review.md` |

---

### 2. Core Invariants Preserved

1. **Wireframe Parity (Spec S3.4):**
   - Header with object type, mono canonical key (e.g. `EFFECTIVE ACCESS FOR ISSUE KAN-142`), and `[Manage Access...]` button rendered strictly when caller has `ADMIN` or `SHARE` capability.
   - Inherited Scope banner (`📂 Project "kanban" (Workspace: Default)`).
   - 4 ordered sections: `👤 USERS (<N> Direct)`, `👥 GROUPS (<N>)`, `🤖 AGENTS & WORKFLOW RUNNERS (<N> Active)`, and `🔒 RESTRICTED OVERRIDES (<N>)`. Empty sections render calm `None` line.
2. **Anti-Enumeration Redaction & Sanitization (Spec S3.4 item 2, S5.4):**
   - Redacted entries render strictly as neutral summary rows: `<N> External Collaborator(s) - outside your visibility boundary` (singular for 1). Leaked fields (like email or handle) on redacted objects are strictly ignored.
   - Hostile principal names (e.g. `<img src=x onerror=alert(1)>`) render as literal text without DOM script execution or `<img>` injection.
3. **Indistinguishable 403 / 404 (Spec S3.4):**
   - Both HTTP 403 and 404 render byte-identical message: `Object was not found or you do not have access.` (zero existence oracle).
4. **Agent Kill Switch Safety & Focus Trapping (Spec S3.4, S6.3):**
   - 2-step inline confirmation banner (`Revoke all active agent grants on <KEY>?`).
   - Default focus is placed on `[Cancel]` button to prevent accidental Enter activation.
   - Optimistic revocation with CSRF protection (`X-CSRF-Token` header) and automatic rollback announcement on failure.
5. **Responsive Spatial Rhythm (Spec S6.1, S6.2):**
   - Principal rows enforce `min-height: var(--prop-row-h)` (38px).
   - Emoji hints sized at 24px x 24px with tooltip metadata.
   - High-contrast Explicit DENY pill (`8.6:1` contrast ratio, exceeding 4.5:1 requirement).
   - Mobile viewport renders full-width bottom sheet (100vw, max-height 88dvh) with rounded top corners.
