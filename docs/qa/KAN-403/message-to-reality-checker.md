# Message to Reality-Checker: KAN-403 Forensic QA Packet

## Ticket Details
- **Ticket ID**: KAN-403 (`[KB-LOCAL-FOLDER-ONBOARDING-PROMPT] Default /llms.txt Onboarding to Local Project Folder (.agents/skills/ & AGENTS.md) & Add User/Project AgentOnboardingPromptCard`)
- **Branch**: `feat/KAN-403-local-folder-onboarding`
- **Base Commit**: `0a204b9f` (from `main`, linear Alembic head #82 `p6_20_oauth_clients_status_check`)
- **Head Commit**: `34cef65c`

## Forensic Verification Summary

### 1. Default Strictly to Local Project Folder in `/llms.txt` (`kanban/ops/llms_txt.py`)
- Updated `ONBOARDING_PROMPT_TEMPLATE`:
  ```text
  Read {origin}/llms.txt, learn 👍kanban's ticket workflow, interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), and QA Rigor, and save my preferences strictly to the local project folder (.agents/skills/ and AGENTS.md) - do NOT modify global home/system directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents) unless I explicitly request global installation.
  ```
- Updated `_SKILL_WORKFLOW_SETUP_MD` Phase 1 and Axis 4:
  - Phase 1 restricted to read-only inspection of the local repository (`AGENTS.md` and `.agents/skills/`).
  - Axis 4 marks `[4A] Local Project Folder Only (.agents/skills/ and AGENTS.md) [Default / Recommended]` as mandatory default.
- Updated `_LLMS_TXT_TEMPLATE` Phase 1 and Axis 4 identically.
- Expanded `kanban/tests/api/test_llms_txt.py` to assert strict local-folder prompt invariants.

### 2. Per-User Saved Onboarding Preferences (`database/` & `kanban/api/v1/user_settings.py`)
- Generated linear migration #83 `p6_21_agent_onboarding_preferences` (`ALTER TABLE public.user_preferences ADD COLUMN IF NOT EXISTS agent_onboarding_prefs_json JSONB NOT NULL DEFAULT '{}'::jsonb;`).
- Added reversible `.down.sql` (`DROP COLUMN IF EXISTS agent_onboarding_prefs_json;`).
- Added migration lifecycle test `database/tests/migrations/test_p6_21_agent_onboarding_preferences_migration.py`.
- Updated `database/models/principals.py` `UserPreference` model with column-level ORM parity.
- Implemented `GET` and `PATCH /api/v1/users/me/preferences` in `kanban/api/v1/user_settings.py`:
  - Accessible to all authenticated users (`MEMBER`, etc.) for their own principal under `FORCE RLS`.
  - Pydantic models `AgentOnboardingPrefs`, `UserPreferencesResponse`, `UpdateUserPreferencesRequest`.
  - Enforced UTF-16 lone surrogate rejection: `0xD800 <= ord(c) <= 0xDFFF` -> `422 INVALID_UTF8_SURROGATE`.
  - Enforced byte-length limit on `custom_notes` (`<= 4096` bytes -> `422 PAYLOAD_TOO_LARGE`).
  - Validated enum constraints for `scope`, `execution_mode`, `model_strategy`, `qa_rigor`.
- Updated live OpenAPI paths/ops/schemas count in `README.md` and `kanban/tests/test_feature_comparison_parity.py` (`paths: 292`, `ops: 388`, `schemas: 390`).

### 3. Reusable `<AgentOnboardingPromptCard>` & UI Integration
- Created `kanban/web/src/features/settings/agentOnboardingPrompt.ts` with `buildAgentOnboardingPrompt(...)` helper.
- Created `kanban/web/src/features/settings/AgentOnboardingPromptCard.tsx` and `AgentOnboardingPromptCard.css`:
  - Persistence scope defaults to `Local project folder only (.agents/skills/ & AGENTS.md) [Default / Recommended]` (`local_only`).
  - Warning banner dynamically displays when `global_allowed` is selected.
  - Interactive controls for Execution Topology, Model & Quota Strategy, QA & Verification Rigor, and Custom Notes.
  - Live generated prompt preview with 1-click clipboard copy and feedback.
  - "Save Preferences" button mutations persisted via `PATCH /api/v1/users/me/preferences`.
  - Self-healing fallback `QueryClientProvider` to allow mounting safely anywhere.
  - Fully responsive, accessible semantic tokens with dark theme support (`theme.css`).
- Mounted `<AgentOnboardingPromptCard>` in `PersonalSettingsPage.tsx` and `ProjectSettingsPage.tsx` (in General tab with `projectKey="KAN"` context).
- Replaced prompt copy strings in `McpAccessStudio.tsx`, `McpConfigSnippetModal.tsx`, `AboutPage.tsx`, and `DocsCenterPage.tsx` with `buildAgentOnboardingPrompt(...)`, including dedicated `docs-copy-agent-prompt-btn` in DocsCenterPage. Zero changes made to `aal2Challenge` state/modal in `PersonalSettingsPage.tsx` or `McpAccessStudio.tsx` to prevent merge conflicts with parallel branch `b-kan404-rc1`.

## Overwhelming Evidence & Artifacts

1. **Unit Test & Coverage Report**:
   - `docs/qa/KAN-403/unit-test-results.txt`
   - Static Migration Check: `uv run kanban-ctl db check-migrations --static-only` (All 83 migrations valid, single head: `p6_21_agent_onboarding_preferences`).
   - Backend Pytest: 49 passed tests in 34.84s with 0 warnings.
     - `database/models/principals.py`: 100% coverage
     - `kanban/ops/llms_txt.py`: 100% coverage
     - `kanban/api/v1/user_settings.py`: 95% coverage (100% on new preferences endpoints)
     - Total Backend Coverage: 97% across changed modules
   - Frontend Vitest: 90 passed tests in 5.89s with 0 warnings.
     - `agentOnboardingPrompt.ts`: 100% statements, 100% branches, 100% funcs, 100% lines
     - `AgentOnboardingPromptCard.tsx`: 100% statements, 100% branches, 100% funcs, 100% lines
     - `personalSettingsApi.ts`: 100% statements, 100% branches, 100% funcs, 100% lines
     - `DocsCenter.test.tsx`: 46 passed tests
     - 0 stderr warnings, 0 React Query warnings
2. **Build, Static Migrations & Dashes Verification**:
   - `docs/qa/KAN-403/build-check.txt`
   - Literal verification command: `uv run ruff check kanban/ database/ && python3 scripts/check_no_dashes.py --all && pnpm --dir kanban/web typecheck && pnpm --dir kanban/web lint && pnpm --dir kanban/web build`
   - Exit code: 0, 765 modules transformed
   - `python3 scripts/check_no_dashes.py --all`: 0 Unicode dashes
3. **5-Viewport Visual Proof Artifacts** (`docs/qa/KAN-403/screenshots/`):
   - All 10 screenshots captured with unconstrained height (`kb-screenshot-unconstrained`) and transient toast suppression, confirming both `Copy Agent Onboarding Prompt` and `Save Preferences` buttons are completely visible without truncation across all viewports:
   - `01-personal-settings-desktop-1440x900-light.png`
   - `01-project-settings-desktop-1440x900-light.png`
   - `02-personal-settings-desktop-1440x900-dark.png`
   - `02-project-settings-desktop-1440x900-dark.png`
   - `03-personal-settings-tablet-landscape-1024x768.png`
   - `03-project-settings-tablet-landscape-1024x768.png`
   - `04-personal-settings-tablet-portrait-768x1024.png`
   - `04-project-settings-tablet-portrait-768x1024.png`
   - `05-personal-settings-mobile-portrait-390x844.png`
   - `05-project-settings-mobile-portrait-390x844.png`
4. **Code Differences & Manifest**:
   - `docs/qa/KAN-403/git-diff.patch`
   - `docs/qa/KAN-403/changed-files-manifest.txt`
