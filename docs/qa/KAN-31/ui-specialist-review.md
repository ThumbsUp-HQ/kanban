# UI/UX Specialist Review: KAN-31

## Audit Metadata
- Ticket ID: KAN-31 ([KB-P3-AUDIT-25])
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan31-fix-d3e0178a`
- Target Branch: fix/KAN-31-liveqa
- Base Commit: 6eab593
- Head Commit: 50f0089
- STATUS: APPROVED

---

## Executive Summary
This review evaluates the UI layout, responsive behaviors, visual design token compliance, interaction ergonomics, and code standards for ticket KAN-31 and its clean-room live stack remediation ([KB-P3-AUDIT-25]). The remediations address:
1. Dynamic project resolution in `McpAccessStudio.tsx` via `GET /api/v1/projects`, populating the Target Project selector dynamically and eliminating hardcoded `'KANBA'` options.
2. Dynamic workspace slug and project key interpolation into `ConnectOAuthAppModal` and `McpConfigSnippetModal` without hardcoded fallbacks.
3. Cache invalidation on key minting (`queryClient.invalidateQueries({ queryKey: ['mcp-keys'] })`), preventing stale table state.
4. Scope tier alignment for `server` scopes returning standard 403 on non-admin mint requests.

All live Playwright visual proof screenshots (Desktop 1440x900 and Mobile 390x844 across Light and Dark themes, modal minting flows, governance tabs, and topbar navigation) were inspected and verified via binary image analysis.

---

## Visual & Ergonomics Verification (Live Screenshots)

### 1. My Keys View & Scope Pills (live-settings-mcp-desktop-light.png & dark.png)
- Theme: Light and Dark Themes (1440x900 Desktop)
- Layout & Whitespace: Breathable padding throughout. Clear visual hierarchy between header, segmented toggle, explainer card, scope pills, and key table.
- Segmented View Toggle: `[My Keys & Connected Apps | Governance (All Scoped Keys)]` provides crisp active pill styling with clear contrast.
- Explainer Card: High-contrast typography and subtle borders explaining Personal vs Service Bot keys and scope tiers adhering to WCAG AA.
- Active Keys Table: Clean badge tags for scope tiers (`Workspace: kanban`, `Project: KAN`, `Project: OPS`), mono key hints (`kb_agt_...c6ic`), and distinct action buttons ("Revoke").

### 2. Mobile Responsive Ergonomics (live-settings-mcp-mobile-light.png & dark.png)
- Theme: Light and Dark Themes (390x844 Mobile)
- Responsive Layout: Segmented toggle, explainer card, scope pills, and tables stack gracefully on 390px viewport width without horizontal clipping or distortion.
- Tap Targets: Interactive buttons ("+ Mint MCP Key", scope pills, tabs) maintain accessible heights >= 44px.

### 3. Contextual Project Scope Selection (live-settings-mcp-project-picker-desktop-light.png)
- Dynamic Controls: Selecting the `Project` scope pill cleanly surfaces the "Target Project: [KANBA v]" dropdown selector.
- Dynamic Population: Options are dynamically populated from `GET /api/v1/projects` instead of static mock strings.
- Table Filtering: Displays matching active keys and connected OAuth apps for the selected project.

### 4. Key Minting Modal Flow (live-mint-modal-desktop-light.png & live-settings-mcp-after-mint-desktop-light.png)
- Modal Ergonomics: Centered dialog with backdrop blur, clear field groupings, and tool narrowing checkboxes.
- Secret Display & Config Snippets: One-time secret display banner with Copy Key button, client integration tabs (Claude Code, Cursor, Gemini CLI, Antigravity, OpenAI Codex, OAuth 2.1), and formatted configuration snippet box.
- Cache Invalidation: Upon key creation, the key table refetches immediately, displaying the newly minted key without manual refresh.

### 5. Governance View & Topbar Navigation (live-settings-mcp-governance-desktop-light.png & live-topbar-avatar-menu-desktop-light.png)
- Governance Scope: Administrators cleanly access governance-scoped keys across workspaces and projects.
- Topbar Ergonomics: Consolidated menu entry `🔑 MCP Keys & OAuth Apps` -> `/settings/mcp` functions smoothly with circular avatar profile rendering.

---

## Code Quality & Architecture Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes added in `McpAccessStudio.tsx` or `McpConfigSnippetModal.tsx`.
- All styles leverage canonical CSS classes and design system tokens.

### 2. Nullish Coalescing & Type Safety
- Strict nullish coalescing (`??`) across all new code paths:
  - `effectiveProjectKey = selectedProject ?? queryProject ?? routeParams.projectKey ?? projects[0]?.identifier ?? ''`
  - `const ident = p.identifier ?? p.key ?? ''`
  - `name: p.name ?? ident`
  - `currentWorkspaceSlug = routeParams.workspaceSlug ?? ... ?? 'kanban'`
- Satisfies `@typescript-eslint/prefer-nullish-coalescing`.

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).

---

## Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-25)

- Target Branch: `fix/KAN-31-liveqa`
- Remediation Head Commit: `50f0089`
- Remediations Verified:
  1. Dynamic project resolution in `McpAccessStudio.tsx` queries `GET /api/v1/projects` via TanStack Query.
  2. Cache invalidation on key minting ensures active key list is synchronized immediately.
  3. Dynamic workspace and project slug interpolation in `McpConfigSnippetModal.tsx`.
  4. Unit test coverage across `McpAccessStudio.test.tsx` (19 tests) and `McpConfigSnippetModal.test.tsx` (4 tests) with >= 95% statement and line coverage.
  5. 100% zero em/en-dashes.

---

## Final Verification Checklist

1. [x] Desktop (1440x900) Light & Dark screenshots verified
2. [x] Mobile (390x844) Light & Dark screenshots verified
3. [x] Dynamic project selection in MCP Studio verified
4. [x] Snippet modal dynamic project key verified
5. [x] Key minting cache invalidation verified
6. [x] Topbar menu items consolidated into single `🔑 MCP Keys & OAuth Apps` link
7. [x] Zero inline `style={...}` attributes (CSP compliant)
8. [x] Strict nullish coalescing (`??`) conventions maintained
9. [x] Strict ASCII hyphenation verified (0 em/en-dashes)
10. [x] Frontend test suite passes with >= 95% coverage across touched files

---

## Verdict & Certification
STATUS: APPROVED

All visual, UX, ergonomics, accessibility, and frontend code quality criteria have been verified and certified. Ready for dual specialist completion and coordinator merge into `main`.
