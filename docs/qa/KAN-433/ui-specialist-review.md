# UI Specialist Review: KAN-433 (Agent Definition Instructions Persistence and Request Storm Elimination)

**Ticket:** KAN-433 (`[BUG][AGENTS] Persist system_instructions_md in Agent Definitions API and Stop Infinite /api/v1/auth/session Request Storm on /workspaces/settings/agents`)  
**Parent Project:** `👍kanban`  
**Auditor:** `ui-designer` (UI Designer & UX Architect)  
**Status:** **APPROVED**  
**Date:** 2026-11-26  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan433-943bd920`  
**Target Branch:** `fix/KAN-433-agent-instructions-and-session-storm`  
**Base Commit:** `7c5d632c`  

---

## 1. Executive Summary & Verdict

This UI Specialist Review audits the user interface components, form ergonomics, state synchronization, responsive layouts, and visual artifacts for **KAN-433**.

Key Findings & Architectural Fixes:
1. **Elimination of Infinite Request Storm on AdminStudioSubnav**:
   - In `AdminStudioSubnav.tsx`, the `onExpiresAt` listener was executing `void load();` on every `kb:aal2-expires-at` event. Combined with middleware emitting the header on all responses, this caused a runaway loop (>64,000 requests).
   - Removed `void load();` from inside `onExpiresAt` since `onExpiresAt` already updates `sessionData` with `expiresAt` directly from event details.
   - Added an equality guard in `setSessionData` so identical `expiresAt` timestamps return `prev` unmodified, preventing cascading re-renders.
2. **Agent Definition Drawer Instructions Synchronization (React 19 Compatibility)**:
   - React 19's `_valueTracker` can swallow synthetic `onChange` events when inputs are populated programmatically or via DevTools scripts.
   - Attached `instructionsTextareaRef` to `<textarea id="agent-instructions-textarea">` with native DOM `addEventListener('input', ...)` and `'change'` hooks to reliably track user edits.
   - In `handleSubmit` for both create and edit modes, the live textarea value is extracted directly from the ref, ensuring custom prompts are never replaced by fallback defaults.
   - In `AgentStudioPage.tsx`, the `onSaved` callback immediately upserts the newly saved agent into component state, guaranteeing that opening the Edit drawer immediately displays the updated prompt even while background list refreshes remain in flight.
3. **Drawer Dirty State Accuracy**:
   - In `AgentDefinitionEditorDrawer.tsx`, the `isDirty` calculation was comparing provider and model values unconditionally, falsely marking `cli_pipe` and `remote_runner` agents as dirty upon drawer open.
   - Guarded provider and model dirty checks with `harnessKind === 'in_app_sdk'`.
   - Prevented spurious immediate `POST /api/v1/auth/aal2/touch` requests on drawer open.

**Verdict: APPROVED.** Form behaviors, responsive reflow, and visual hierarchy strictly follow 👍kanban design principles.

---

## 2. Multi-Viewport Visual Evidence Audit

Visual evidence captured via Playwright in `docs/qa/KAN-433/screenshots/` was audited across standard responsive breakpoints:

| Screenshot Artifact | Viewport / Theme | Verification Findings | Status |
| :--- | :--- | :--- | :--- |
| `desktop-light-1440x900.png` | 1440x900 Light Desktop | Edit Agent drawer open with custom system instructions textarea visible, displaying custom instructions cleanly without clipping. | PASS (WCAG AA > 4.5:1) |
| `desktop-dark-1440x900.png` | 1440x900 Dark Desktop | Dark theme active; high-contrast tokens applied to inputs, textarea, subnav tabs, and action buttons. | PASS (WCAG AA > 7.5:1) |
| `tablet-768x1024.png` | 768x1024 Tablet Portrait | Drawer adapts responsively to medium screen width; scrollable container maintains form alignment. | PASS (Touch targets >= 44px) |
| `mobile-390x844.png` | 390x844 Mobile Portrait | Mobile portrait view; drawer fills viewport width cleanly with zero horizontal overflow; sticky footer actions remain accessible. | PASS (Zero overflow) |

---

## 3. Automated Test Verification & Quality Metrics

- **Unit Tests**:
  - `AgentDefinitionEditorDrawer.test.tsx`: 14/14 tests passing. Verified native DOM input tracking and clean dirty-state checks.
  - `AgentStudioPage.test.tsx`: 32/32 tests passing. Verified custom instructions persistence on create/edit and confirmed session requests remain `<= 2` over 300ms.
- **Linting and Typing**:
  - `pnpm --dir kanban/web typecheck`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 warnings, 0 errors.
  - `pnpm --dir kanban/web build`: Clean production build (1.27s).
- **Zero Dash Invariant**: Verified zero Unicode em-dashes and en-dashes.

---

## 4. Final Sign-Off

- **Responsive & Visual Ergonomics:** APPROVED
- **Interaction & State Persistence:** APPROVED
- **Request Loop Prevention:** APPROVED
