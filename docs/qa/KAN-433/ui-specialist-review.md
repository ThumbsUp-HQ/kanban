# Independent UI Specialist Review: KAN-433

**Ticket:** KAN-433 (`[BUG][AGENTS] Persist system_instructions_md in Agent Definitions API and Stop Infinite /api/v1/auth/session Request Storm on /workspaces/settings/agents`)
**Auditor:** `ui-designer` (Independent UI Specialist Audit)
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan433-943bd920`
**Branch:** `fix/KAN-433-agent-instructions-and-session-storm` (base `7c5d632c`)

---

## 1. Code & Interaction Audit

### A. Request Storm Elimination (`AdminStudioSubnav.tsx` + `client.ts`)
- **Verified in `kanban/web/src/features/admin/AdminStudioSubnav.tsx`:**
  - `load()` calls `apiFetch('GET', '/api/v1/auth/session')` only on initial mount, on the 10-second `setInterval`, on the `'kb:aal2-stepup-success'` event, and inside `handleDrop` after dropping AAL2 elevation.
  - The `'kb:aal2-expires-at'` listener (`onExpiresAt`) no longer calls `void load()`. Instead, it reads `custom.detail?.expiresAt` and updates `sessionData` in place via `setSessionData((prev) => ...)`, returning `prev` unchanged when `prev?.aal2_active && prev.aal2_expires_at === expiresAt` to prevent redundant state updates and re-renders.
- **Verified defense-in-depth in `kanban/web/src/api/client.ts`:**
  - `executeRequest` checks `isAuthSession = path === '/api/v1/auth/session' || resolved.startsWith('/api/v1/auth/session')` on both initial and replayed responses, suppressing `'kb:aal2-expires-at'` dispatch on session endpoint responses.
- **Verified test coverage in `kanban/web/src/features/admin-agents/__tests__/AgentStudioPage.test.tsx`:**
  - The `request-storm guard` test mounts `AgentStudioPage` with `isServerAdmin={true}`, returns `x-kb-aal2-expires-at` headers from mocked `/api/v1/auth/session` and list fetches, opens the Edit drawer, waits 300ms, and asserts `sessionCallCount <= 2`.

### B. Custom `system_instructions_md` Persistence & React 19 Input Sync (`AgentDefinitionEditorDrawer.tsx` + `AgentStudioPage.tsx`)
- **Verified in `kanban/web/src/features/admin-agents/AgentDefinitionEditorDrawer.tsx`:**
  - `instructionsTextareaRef` (`useRef<HTMLTextAreaElement | null>(null)`) is bound to `<textarea id="agent-instructions-textarea" data-testid="agent-instructions-textarea">`.
  - A mount `useEffect` registers native DOM `'input'` and `'change'` event listeners on `instructionsTextareaRef.current` (with cleanup on unmount) that mark `hasUserEditedInstructions.current = true` and call `setSystemInstructions(el.value)`, ensuring programmatic or DevTools DOM mutations are captured alongside React `onChange` / `onInput` handlers.
  - `systemInstructions` state initializes from `agent ? agent.system_instructions_md : 'You are an autonomous Kanban specialist agent.'`, `AgentDefinitionEditorContent` is keyed by `agent?.id ?? 'new'`, and a detail-hydration `useEffect` calls `fetchAgentDefinition(agent.id || agent.slug)` to populate `detail.system_instructions_md` if `!hasUserEditedInstructions.current`.
  - `handleSubmit` reads `instructionsTextareaRef.current ? instructionsTextareaRef.current.value : systemInstructions` into `liveInstructions` for both `updateAgentDefinition` (Edit) and `createAgentDefinition` (Create), ensuring saved custom prompts are submitted and never replaced by the new-agent default string.
- **Verified in `kanban/web/src/features/admin-agents/AgentStudioPage.tsx`:**
  - `handleAgentSaved(savedAgent)` immediately upserts `savedAgent` into the `agents` array before calling `refreshAgents()`, preventing stale list state when reopening the Edit drawer immediately after save.
- **Verified test coverage:**
  - `AgentStudioPage.test.tsx` tests creating an agent via native DOM `textarea.value = customPrompt` + `dispatchEvent(new Event('input', { bubbles: true }))`, saving, clicking Edit, and verifying the textarea displays `customPrompt` rather than `'You are an autonomous Kanban specialist agent.'`.
  - `AgentDefinitionEditorDrawer.test.tsx` tests preserving saved `system_instructions_md` on Edit when changing `timeout_ms`, hydrating instructions via `fetchAgentDefinition` when the prop string is empty, and submitting custom instructions via native DOM `input` events on Create.

### C. Spurious `isDirty` Guard on Edit Mount (`AgentDefinitionEditorDrawer.tsx`)
- **Verified in `AgentDefinitionEditorDrawer.tsx`:**
  - `providerOrModelChanged` is guarded by `harnessKind === 'in_app_sdk' && (providerKind !== agent.provider_kind || modelId !== agent.model_id)`.
  - Editing `cli_pipe` or `remote_runner` agents (where `agent.provider_kind` and `agent.model_id` are `null`) no longer triggers `isDirty === true` on mount, preventing spurious `POST /api/v1/auth/aal2/touch` calls from `useAal2DirtyKeepalive(isDirty)`.
  - Verified by `cli_pipe agent in edit mode is not treated as dirty on mount` in `AgentDefinitionEditorDrawer.test.tsx`.

---

## 2. Visual Inspection of All Screenshots (`docs/qa/KAN-433/screenshots/`)

1. **`docs/qa/KAN-433/screenshots/desktop-light-1440x900.png` (1440x900 Desktop Light):**
   - **Pass criteria met:** Zero error banners on the page or inside the drawer. Background `AdminStudioSubnav` displays tabs and active green `Sudo 127:57 | Lock` pill cleanly behind the scrim. Inside the expanded `Advanced Model & Harness Configuration` disclosure, the `System Instructions (Markdown)` textarea displays the custom saved prompt (`# Reality Checker Directives`, `- Passive forensic audits only.`, `- Strict verification proof packets.`, `- Zero-tolerance quality gate.`) rather than the default string. `Cancel` and `Save Agent` footer buttons are crisp with strong contrast and generous bottom padding.
   - **Non-blocking layout note:** With `Advanced Model & Harness Configuration` expanded, the modal card is taller than the 900px viewport height, so in this scrolled capture the modal title bar (`Edit @reality-checker` + close button) and `Agent Slug (Permanent Handle)` label sit above the top edge of the viewport, and the 5th line in the 4-row textarea sits at the scrollable bottom edge of the textarea.

2. **`docs/qa/KAN-433/screenshots/desktop-dark-1440x900.png` (1440x900 Desktop Dark):**
   - **Pass criteria met:** Dark theme tokens apply cleanly across the scrim, modal surface, inputs, select controls, `Allowed MCP Agent Tools` checkboxes, `Advanced Model & Harness Configuration` focus/open border, and `Cancel` / `Save Agent` buttons with high text contrast. Zero error banners and zero light-mode bleed-through. Custom `system_instructions_md` (`# Reality Checker Directives` ...) is clearly legible inside the textarea.
   - **Non-blocking layout note:** Same modal height behavior as the 1440x900 light capture when `AdvancedSection` is expanded (modal header scrolled above the top viewport edge).

3. **`docs/qa/KAN-433/screenshots/tablet-768x1024.png` (768x1024 Tablet Portrait):**
   - **Pass criteria met:** Full modal fits vertically from `Edit @reality-checker` and `X` close button down to the full-width stacked `Cancel` and `Save Agent` buttons. Breathable spacing between form groups, clean 2-column tool checkbox alignment (`search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`), zero error banners, zero horizontal overflow, and custom `system_instructions_md` clearly visible in the textarea.
   - **Non-blocking layout note:** Top edge of the modal header sits flush near `y=0` due to the expanded modal height (~990px) within the 1024px viewport.

4. **`docs/qa/KAN-433/screenshots/mobile-390x844.png` (390x844 Mobile Portrait, full-page capture):**
   - **Pass criteria met:** Clean single-column responsive layout with zero horizontal overflow, full modal header (`Edit @reality-checker` and `X` button) framed with balanced top spacing, full-width `Cancel` and `Save Agent` buttons, zero error banners, and custom `system_instructions_md` visible in the textarea.
   - **Non-blocking layout note (pre-existing shared styles):** At 390px width, the 2-column `.kb-agent-tools-grid` places `read_ticket` close to the right inner border of the Advanced box, and the long `In-App SDK (Direct Provider / Cloud or Local)` select text slightly truncates near the select dropdown chevron.

---

## 3. Non-Blocking Follow-Up Recommendations
- Consider adding `max-height: calc(100vh - 48px); overflow-y: auto;` (or `margin: auto;` on `.kb-modal-card` with `align-items: flex-start` on `.kb-modal-backdrop`) in a future shared modal polish ticket so tall modals with expanded `AdvancedSection` keep their header and close button reachable on 900px-tall desktop viewports.
- Consider switching `.kb-agent-tools-grid` to `grid-template-columns: 1fr;` below `480px` to give MCP tool labels extra breathing room on narrow mobile viewports.

---

Verdict: APPROVED
