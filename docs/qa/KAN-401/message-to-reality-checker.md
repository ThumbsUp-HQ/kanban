# Message to Reality-Checker: KAN-401 Epic Rollup Forensic QA Packet

## Epic Details
- **Epic Ticket ID**: KAN-401 (`[EPIC][KB-WORKSPACE-AI-AGENTS-AND-USER-PROMPT] Workspace & Project AI Agents Management Studio + Default /llms.txt Local Project Folder Prompt`)
- **Child Tasks & Sub-Tickets**:
  - **KAN-402**: `[KB-WORKSPACE-PROJECT-AI-AGENTS-SETTINGS] Workspace & Project AI Studio & Autonomous Agent Settings Tabs`
    - Commit: `1e509ba4` / `45db6e87`
    - Reality-Checker Certification: **Grade-A `READY`** (`docs/qa/KAN-402/reality-checker-report.md`)
    - Specialist Sign-Offs: API Specialist (`APPROVED`), UI Specialist (`APPROVED`)
  - **KAN-403**: `[KB-LOCAL-FOLDER-ONBOARDING-PROMPT] Default /llms.txt Onboarding to Local Project Folder (.agents/skills/ & AGENTS.md) & Add User/Project AgentOnboardingPromptCard`
    - Commit: `34cef65c`
    - Reality-Checker Certification: **Grade-A `READY`** (`docs/qa/KAN-403/reality-checker-report.md`)
    - Specialist Sign-Offs: API Specialist (`APPROVED`), UI Specialist (`APPROVED`)
- **Branch**: `feat/KAN-403-local-folder-onboarding`
- **Base Commit**: `0a204b9f` (from `main`, linear Alembic head #82 `p6_20_oauth_clients_status_check`)
- **Rollup Target**: Combined verification and merge candidate for Epic KAN-401 covering both KAN-402 and KAN-403 deliverables.

---

## Executive Summary & System Architecture

Epic KAN-401 delivers end-to-end workspace and project level autonomous AI agent and LLM provider management, paired with strict local-folder isolation for agent onboarding across `👍kanban`.

### 1. Scoped AI Provider & Agent Studio Management (KAN-402)
- **Multi-Tier Scoping**: Allows Workspace Admins and Project Admins to configure LLM providers (`OPENAI`, `ANTHROPIC`, `GEMINI`, `OLLAMA`), failover priority stacks (#1..#N), model allowlists, monthly token caps, and zero-egress boundaries without leaking server admin privileges.
- **Autonomous Agent Definitions**: Supports configuring, testing, and managing in-app SDK agents and CLI pipe agents (`agy -p`, `codex exec -s read-only -`) under strict CLI execution policies with project/workspace authorization boundaries.
- **Seamless Settings Integration**: Embedded into Workspace Settings (`/settings/workspaces/{slug}`) and Project Settings (`/settings/projects/{key}`) with dedicated tabs (`AI & Agents`), clean responsive layouts, and zero Sudo or server-admin subnav leakage.

### 2. Local Project Folder Onboarding Prompt & User Preferences (KAN-403)
- **Local Project Folder Invariant**: Updated `ONBOARDING_PROMPT_TEMPLATE`, `_SKILL_WORKFLOW_SETUP_MD`, and `_LLMS_TXT_TEMPLATE` in `kanban/ops/llms_txt.py` to default strictly to the local repository folder (`.agents/skills/` and `AGENTS.md`) without mutating global system directories (`~/.claude`, `~/.codex`, `~/.gemini`, `~/.agents`).
- **User Onboarding Preferences Migration & API**: Linear migration #83 `p6_21_agent_onboarding_preferences` adding `agent_onboarding_prefs_json JSONB NOT NULL DEFAULT '{}'::jsonb` to `user_preferences`. Backed by `GET` and `PATCH /api/v1/users/me/preferences` under `FORCE RLS` with strict Pydantic validation, UTF-16 lone surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF` -> `422 INVALID_UTF8_SURROGATE`), byte-budget enforcement (`<= 4096` bytes), and multi-tenant isolation.
- **Reusable `<AgentOnboardingPromptCard>` UI Component**: Reusable settings card defaulting to `Local project folder only (.agents/skills/ & AGENTS.md)` (`local_only`), interactive configuration controls, copy-to-clipboard functionality, dynamic warning banners when global scope is selected, and seamless mounting in both Personal Settings and Project Settings. Shared prompt generator integrated across McpAccessStudio, McpConfigSnippetModal, AboutPage, and DocsCenterPage.

---

## Complete Forensic Verification & Evidence

### 1. Child Reality-Checker Certifications
Both child deliverables underwent independent clean-room forensic QA audits and received Grade-A `READY` certifications:
- **KAN-402 Reality-Checker Report**: `docs/qa/KAN-402/reality-checker-report.md`
  - Rating: **Grade-A `READY`**
  - All 12 Playwright screenshots inspected and verified across 5 viewports.
  - Zero critical issues, zero medium issues, 100% compliance with scoped requirements.
- **KAN-403 Reality-Checker Report**: `docs/qa/KAN-403/reality-checker-report.md`
  - Rating: **Grade-A `READY`**
  - All 10 Playwright screenshots inspected and verified across 5 viewports.
  - Linear migration #83 verified, unit test coverage >= 95%, zero Unicode dashes.

### 2. Specialist Sign-Offs
- `docs/qa/KAN-402/api-specialist-review.md`: **APPROVED**
- `docs/qa/KAN-402/ui-specialist-review.md`: **APPROVED**
- `docs/qa/KAN-403/api-specialist-review.md`: **APPROVED**
- `docs/qa/KAN-403/ui-specialist-review.md`: **APPROVED**

### 3. Comprehensive Visual Evidence (22 Screenshots across 5 Viewports)
All 22 distinct screenshots from KAN-402 and KAN-403 are preserved in `docs/qa/KAN-401/screenshots/`:
- **KAN-402 Workspace & Project AI Studio (12 PNGs)**:
  - `01-workspace-ai-desktop-1440x900-light.png`: Workspace AI Studio in desktop light theme
  - `01-workspace-agents-desktop-1440x900-light.png`: Workspace Autonomous Agents Studio in desktop light theme
  - `01-project-ai-agents-desktop-1440x900-light.png`: Project Settings AI & Agents tab in desktop light theme
  - `02-workspace-ai-desktop-1440x900-dark.png`: Workspace AI Studio in desktop dark theme
  - `02-workspace-agents-desktop-1440x900-dark.png`: Workspace Autonomous Agents Studio in desktop dark theme
  - `02-project-ai-agents-desktop-1440x900-dark.png`: Project Settings AI & Agents tab in desktop dark theme
  - `03-workspace-ai-tablet-landscape-1024x768.png`: Workspace AI Studio tablet landscape
  - `03-project-ai-agents-tablet-landscape-1024x768.png`: Project Settings tablet landscape
  - `04-workspace-ai-tablet-portrait-768x1024.png`: Workspace AI Studio tablet portrait
  - `04-project-ai-agents-tablet-portrait-768x1024.png`: Project Settings tablet portrait
  - `05-workspace-ai-mobile-390x844.png`: Workspace AI Studio mobile portrait
  - `05-project-ai-agents-mobile-390x844.png`: Project Settings mobile portrait
- **KAN-403 Local-Folder Onboarding & Settings (10 PNGs)**:
  - `01-personal-settings-desktop-1440x900-light.png`: Personal Settings Agent Onboarding Card desktop light theme
  - `01-project-settings-desktop-1440x900-light.png`: Project Settings Agent Onboarding Card desktop light theme
  - `02-personal-settings-desktop-1440x900-dark.png`: Personal Settings desktop dark theme
  - `02-project-settings-desktop-1440x900-dark.png`: Project Settings desktop dark theme
  - `03-personal-settings-tablet-landscape-1024x768.png`: Personal Settings tablet landscape
  - `03-project-settings-tablet-landscape-1024x768.png`: Project Settings tablet landscape
  - `04-personal-settings-tablet-portrait-768x1024.png`: Personal Settings tablet portrait
  - `04-project-settings-tablet-portrait-768x1024.png`: Project Settings tablet portrait
  - `05-personal-settings-mobile-portrait-390x844.png`: Personal Settings mobile portrait
  - `05-project-settings-mobile-portrait-390x844.png`: Project Settings mobile portrait

### 4. Automated Testing & Code Coverage
Recorded in `docs/qa/KAN-401/unit-test-results.txt`:
- **Static Database Migration Lifecycle Check**:
  - `uv run kanban-ctl db check-migrations --static-only`: Passed. All 83 migrations valid, single linear head `p6_21_agent_onboarding_preferences`.
- **Backend Pytest Suite**:
  - **101 passed in 64.98s, 0 warnings**.
  - Total backend coverage across all modified modules: **96%** (>= 95% across 100% of rows).
    - `database/models/principals.py`: **100%**
    - `kanban/ops/llms_txt.py`: **100%**
    - `kanban/api/v1/agent_definitions.py`: **100%**
    - `kanban/agents/service.py`: **97%**
    - `kanban/ai_config/service.py`: **95%**
    - `kanban/api/v1/admin/ai_providers.py`: **95%**
    - `kanban/api/v1/user_settings.py`: **95%** (100% on new preferences endpoints)
- **Frontend Vitest Suite**:
  - **300 passed across 12 test files in 7.37s, 0 warnings**.
  - Enforced `--coverage.thresholds.branches=95`.
  - Overall coverage: **99.59% Statements, 95.88% Branch, 99.34% Functions, 100% Lines**.
  - Every modified component satisfies >= 95.0% branch coverage threshold.

### 5. Build, Static Analysis & Zero Dash Verification
Recorded in `docs/qa/KAN-401/build-check.txt`:
- Database static migrations check: OK (83 migrations, 1 single head)
- Python linter: `uv run ruff check kanban/ database/`: All checks passed.
- Plain ASCII dash gate: `python3 scripts/check_no_dashes.py --all`: Clean exit 0, 0 non-ASCII dashes found.
- TypeScript compiler: `pnpm --dir kanban/web typecheck`: Clean exit 0.
- Frontend linter: `pnpm --dir kanban/web lint`: Clean exit 0, max-warnings 0.
- Production build: `pnpm --dir kanban/web build`: Clean bundle generated in 1.25s.

---

## Rollup Artifact Inventory in `docs/qa/KAN-401/`
1. `git-diff.patch`: Unified commit and diff manifest for Epic KAN-401 referencing KAN-402 and KAN-403 commits.
2. `unit-test-results.txt`: Raw output of migrations check, 96 backend Pytests with coverage report, and 300 frontend Vitests with v8 branch coverage table.
3. `build-check.txt`: Raw output of migrations check, ruff, no-dashes verification, typecheck, lint, and production vite build.
4. `message-to-reality-checker.md`: This comprehensive Epic audit summary document.
5. `screenshots/`: 22 verified screenshots covering all 5 standard viewports for both KAN-402 and KAN-403 surfaces.
6. `changed-files-manifest.txt` & `SHA256SUMS.txt`: Cryptographic SHA-256 manifest of all QA bundle files with 100% verification pass.
