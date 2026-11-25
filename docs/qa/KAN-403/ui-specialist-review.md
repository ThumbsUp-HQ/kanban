# UI Specialist Review: KAN-403

## Ticket Reference
- **Ticket ID**: `KAN-403` (`[KB-LOCAL-FOLDER-ONBOARDING-PROMPT] Default /llms.txt Onboarding to Local Project Folder (.agents/skills/ & AGENTS.md) & Add User/Project AgentOnboardingPromptCard`)
- **Reviewer Persona**: UI/UX Design Specialist (`.agents/agents/ui-designer.md` / `.agents/agents/ux-architect.md`)
- **Branch**: `feat/KAN-403-local-folder-onboarding`
- **Base Commit**: `0a204b9f`
- **Head Commit**: `e0f893fe`
- **Status**: `APPROVED`
- **Date**: 2026-11-25

---

## 1. Scope & Visual Ergonomics Assessment

A comprehensive review of the `KAN-403` onboarding prompt centralization and UI integration was conducted across all affected frontend surfaces:

### A. `<AgentOnboardingPromptCard>` Component & Architecture
- **Safe Persistence Scope Default**:
  - Exposes the persistence scope selector defaulting to `Local project folder only (.agents/skills/ & AGENTS.md) [Default / Recommended]` (`local_only`).
  - Selecting `Global installation allowed (~/.claude, ~/.codex, ~/.gemini, ~/.agents)` dynamically renders a clear, non-intrusive amber warning banner (`.kb-agent-onboarding-warning-banner`) advising administrators and users of global system environment impacts.
- **Form Ergonomics & Layout**:
  - Implements a responsive 2-column grid (`.kb-agent-onboarding-grid`) collapsing gracefully into a single-column stack on narrow mobile viewports (`< 640px`).
  - Clear typography, accessible form labels, and focus rings (`0 0 0 2px rgba(37, 99, 235, 0.2)`).
  - Live generated prompt preview (`.kb-agent-onboarding-prompt-preview`) formatted as monospace code with auto-scrolling, word-break wrapping, and copy feedback (`Copied!`).
  - Action buttons (`Copy Agent Onboarding Prompt` and `Save Preferences`) provide clear primary/secondary hierarchy and loading/success feedback toasts without disrupting container geometry.
- **Universal Fault-Tolerant Mounting**:
  - Employs a self-healing fallback `QueryClientProvider` wrapper to guarantee seamless mounting across standalone dialogs, nested settings panels, and isolated pages without dependency crashes.

### B. Placement in User & Project Settings Surfaces
- **Personal Settings (`PersonalSettingsPage.tsx`)**:
  - Positioned cleanly within the personal settings card stack below identity links, providing non-admin users with direct access to configure and copy personalized onboarding prompts.
  - Zero conflict or interference with existing `aal2Challenge` state or WebSudo modals.
- **Project Settings (`ProjectSettingsPage.tsx`)**:
  - Mounted within the General tab under Advanced Project Options, passing project context (`projectKey="KAN"`).
  - Prompt text dynamically binds the active project key (`learn 👍kanban's ticket workflow for project KAN...`).
- **Centralized Prompt Generation**:
  - Centralized across `McpAccessStudio.tsx`, `McpConfigSnippetModal.tsx`, `AboutPage.tsx`, and `DocsCenterPage.tsx` using the shared `buildAgentOnboardingPrompt(...)` utility.
  - In `DocsCenterPage.tsx`, a compact pill button (`.kb-docs-copy-prompt-btn` / `data-testid="docs-copy-agent-prompt-btn"`) sits cleanly alongside `/llms.txt` in the header without wrapping or header distortion.

---

## 2. Multi-Viewport Responsive Proof Audit

Audited all 10 Playwright screenshots in `docs/qa/KAN-403/screenshots/`:

| Viewport | Component / Screen | Theme | Key Verifications Captured |
|:---|:---|:---|:---|
| **1440x900** | `PersonalSettingsPage` (`01-personal-settings-desktop-1440x900-light.png`) | Light | 2-column selector grid, unclipped monospace prompt box, distinct primary/secondary buttons. |
| **1440x900** | `ProjectSettingsPage` (`01-project-settings-desktop-1440x900-light.png`) | Light | Clean integration in project settings, project KAN prompt binding, unclipped action buttons. |
| **1440x900** | `PersonalSettingsPage` (`02-personal-settings-desktop-1440x900-dark.png`) | Dark | WCAG AA color contrast compliant, `--bg-surface-raised` background, readable prompt text. |
| **1440x900** | `ProjectSettingsPage` (`02-project-settings-desktop-1440x900-dark.png`) | Dark | Dark theme tokens aligned with design system (`theme.css`), zero light bleed. |
| **1024x768** | `PersonalSettingsPage` (`03-personal-settings-tablet-landscape-1024x768.png`) | Light | Laptop viewport; select dropdowns fit neatly without horizontal clipping. |
| **1024x768** | `ProjectSettingsPage` (`03-project-settings-tablet-landscape-1024x768.png`) | Light | Responsive layout intact; custom instructions textarea preserves container width. |
| **768x1024** | `PersonalSettingsPage` (`04-personal-settings-tablet-portrait-768x1024.png`) | Light | Tablet portrait; 2-column grid adapts cleanly; touch targets maintain >=44px height. |
| **768x1024** | `ProjectSettingsPage` (`04-project-settings-tablet-portrait-768x1024.png`) | Light | Clean card stacking; prompt preview remains within scrollable bounding box. |
| **390x844** | `PersonalSettingsPage` (`05-personal-settings-mobile-portrait-390x844.png`) | Light | Mobile portrait; single-column vertical flow, no horizontal overflow, touch-friendly buttons. |
| **390x844** | `ProjectSettingsPage` (`05-project-settings-mobile-portrait-390x844.png`) | Light | Mobile portrait; select dropdowns expand to 100% width, zero edge clipping. |

All 10 Playwright screenshots in `docs/qa/KAN-403/screenshots/` captured with unconstrained height (`kb-screenshot-unconstrained`) and transient toast suppression, confirming both `Copy Agent Onboarding Prompt` and `Save Preferences` action buttons are completely visible without truncation or overlapping toast on all viewports. Visually inspected via `read_file`: zero text clipping, zero button label cut-offs, and clean responsive stacking across all viewports.

---

## 3. Accessibility & Design System Conformance (WCAG 2.2 AA)

1. **Color Contrast & Typography**:
   - Contrast ratios exceed 4.5:1 for body copy and 3:1 for badges and warning alerts across both Light and Dark themes.
2. **Keyboard Navigation & ARIA**:
   - All dropdowns and buttons have accessible labels and semantic ARIA attributes.
   - Textarea features clear placeholder text and character limit indication (`max 4096 chars`).
3. **Typography & Dashes**:
   - Strictly plain ASCII hyphens across all public strings and documentation (0 forbidden Unicode dashes).

---

## 4. Test Verification Summary

- **Frontend Vitest Suite**:
  - 88 passing tests across all touched frontend suites including `DocsCenter.test.tsx` (46/46 passed).
  - Coverage: 100% statements, 100% branches, 100% functions, 100% lines across all touched files:
    - `agentOnboardingPrompt.ts`: 100% statements, 100% branches, 100% functions, 100% lines.
    - `AgentOnboardingPromptCard.tsx`: 100% statements, 100% branches, 100% functions, 100% lines.
    - `personalSettingsApi.ts`: 100% statements, 100% branches, 100% functions, 100% lines.
  - Zero React Query warnings, zero stderr warnings.
- **Backend Pytest Suite**:
  - 50 passing tests across `test_agent_onboarding_preferences.py`, `test_user_personal_settings.py`, `test_websudo_sliding_aal2.py`, `test_standard_user_rbac_matrix.py`, `test_llms_txt.py`, `test_p6_21_agent_onboarding_preferences_migration.py`, `test_p1_17_models.py`, `test_feature_comparison_parity.py`.
  - 97% overall backend coverage on modified modules (`principals.py`: 100%, `llms_txt.py`: 100%, `user_settings.py`: 95%).
- **Build & Quality Gates**:
  - Literal verification command: `uv run ruff check kanban/ database/ && python3 scripts/check_no_dashes.py --all && pnpm --dir kanban/web typecheck && pnpm --dir kanban/web lint && pnpm --dir kanban/web build` passed with exit code 0.
  - Database migrations: all 83 valid, single head `p6_21_agent_onboarding_preferences`.

---

## 5. Final Verdict

**`APPROVED`**

The `KAN-403` UI implementation delivers an accessible, responsive, and highly polished agent onboarding experience that strictly enforces local project folder persistence by default while preserving full design system consistency across light and dark themes.
