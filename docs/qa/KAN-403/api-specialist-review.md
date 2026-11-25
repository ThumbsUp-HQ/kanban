# API Specialist & Security Review: KAN-403

## Ticket Reference
- **Ticket ID**: `KAN-403` (`[KB-LOCAL-FOLDER-ONBOARDING-PROMPT] Default /llms.txt Onboarding to Local Project Folder (.agents/skills/ & AGENTS.md) & Add User/Project AgentOnboardingPromptCard`)
- **Reviewer Persona**: API & Security Architect (`.agents/agents/backend-architect.md` / `.agents/agents/api-tester.md`)
- **Branch**: `feat/KAN-403-local-folder-onboarding`
- **Base Commit**: `0a204b9f`
- **Head Commit**: `2ec6204a`
- **Status**: `APPROVED`
- **Date**: 2026-11-25

---

## 1. Executive Summary & Verification Objective

Ticket `KAN-403` implements strict local-project-folder default onboarding in `/llms.txt` and introduces user preferences persistence for AI coding agent configurations along with the reusable `AgentOnboardingPromptCard`.

This review specifically audits:
1. **Local Project Boundary in `/llms.txt`**: Confirms `ONBOARDING_PROMPT_TEMPLATE`, `_SKILL_WORKFLOW_SETUP_MD`, and `_LLMS_TXT_TEMPLATE` strictly default to `.agents/skills/` and `AGENTS.md` in the local repository, prohibiting inspection or modification of global home/system dot-directories (`~/.claude`, `~/.codex`, `~/.gemini`, `~/.agents`) unless explicitly requested by the user.
2. **Linear Migration #83 (`p6_21_agent_onboarding_preferences`) & ORM Parity**: Verifies single-head migration chain, reversible `.down.sql`, and ORM model parity in `database/models/principals.py`.
3. **Preferences API Endpoints & Input Hardening**: Audits `GET /api/v1/users/me/preferences` and `PATCH /api/v1/users/me/preferences` in `kanban/api/v1/user_settings.py` for `FORCE RLS` session context enforcement, strict UTF-16 surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF` -> `422 INVALID_UTF8_SURROGATE`), control character stripping, and `<= 4096` byte bounds checking.
4. **DocsCenter Integration**: Verifies addition of `docs-copy-agent-prompt-btn` in `DocsCenterPage.tsx` wired to `buildAgentOnboardingPrompt(...)`.
5. **Unit Test Coverage & Hygiene**: Verifies `>=95%` test coverage on modified backend modules (`database/models/principals.py`: 100%, `kanban/ops/llms_txt.py`: 100%, `kanban/api/v1/user_settings.py`: 95%), 0 warnings, clean migrations check, clean `pnpm typecheck`, clean `pnpm lint`, and 0 Unicode em/en-dashes.

---

## 2. API Architecture & Security Audit

### A. Strict Local Project Folder Boundary
- In `kanban/ops/llms_txt.py`:
  - `ONBOARDING_PROMPT_TEMPLATE`: Explicitly instructs:
    ```
    "Read {origin}/llms.txt, learn 👍kanban's ticket workflow, interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), and QA Rigor, and save my preferences strictly to the local project folder (.agents/skills/ and AGENTS.md) - do NOT modify global home/system directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents) unless I explicitly request global installation."
    ```
  - Phase 1 read-only discovery is confined to local project configuration (`AGENTS.md` and `.agents/skills/`).
  - Axis 4 is defaulted to `[4A] Local Project Folder Only (.agents/skills/ and AGENTS.md) [Default / Recommended]`.
  - All existing `/llms.txt` and full text tests updated and passing (`kanban/tests/api/test_llms_txt.py`).

### B. Linear Database Migration #83
- Migration: `p6_21_agent_onboarding_preferences` revising single head `p6_20_oauth_clients_status_check`.
- Adds `agent_onboarding_prefs_json JSONB NOT NULL DEFAULT '{}'::jsonb` to `public.user_preferences`.
- Reversible `.down.sql`: drops column safely.
- Verified single-head chain: `check-migrations --static-only` (83 valid migrations, 1 head).
- Migration lifecycle verified: `test_p6_21_agent_onboarding_preferences_migration.py` passed.
- Model parity in `database/models/principals.py`: `UserPreference.agent_onboarding_prefs_json` mapped with `JSONB` and tested via `test_p1_17_models.py` (100% coverage).

### C. Preferences API Endpoints & Input Hardening
- In `kanban/api/v1/user_settings.py`:
  - `GET /api/v1/users/me/preferences`: Returns user onboarding preferences merged with defaults. Accessible to any authenticated user under `FORCE RLS` for their own `principal_id`.
  - `PATCH /api/v1/users/me/preferences`: Validates payload with Pydantic `AgentOnboardingPrefsPatch`:
    - `scope`: `Literal["local_only", "global_allowed"]`
    - `execution_mode`: `Literal["single_thread", "teamwork", "swarm"]`
    - `model_strategy`: `Literal["quota_sipping_flash", "hybrid", "unconstrained_max"]`
    - `qa_rigor`: `Literal["standard", "strict_forensic"]`
    - `custom_notes`: Validated via `_validate_custom_notes`:
      - Rejects UTF-16 surrogates (`422 INVALID_UTF8_SURROGATE`)
      - Checks byte length `<= 4096` (`422 PAYLOAD_TOO_LARGE`)
      - Strips invisible and dangerous control characters via `strip_invisible_and_control_chars`
  - Records activity record with `USER_PREFERENCES_UPDATED`.

### D. Zero Privilege Escalation or Conflict
- Operates under caller's authenticated session context (`get_principal`), preventing cross-tenant or cross-user preference tampering.
- Clean separation from WebSudo step-up state: zero edits to `aal2Challenge` state or handlers in `PersonalSettingsPage.tsx` or `McpAccessStudio.tsx`, avoiding conflicts with parallel workers.

---

## 3. Test Suite & Coverage Verification

### A. Python Backend Test Suite
Executed backend tests:
```bash
pytest kanban/tests/api/test_user_personal_settings.py \
  database/tests/migrations/test_p6_21_agent_onboarding_preferences_migration.py \
  database/tests/test_p1_17_models.py \
  kanban/tests/api/test_llms_txt.py \
  kanban/tests/security/test_admin_routes_protected.py -v \
  --cov=database/models/principals --cov=kanban/ops/llms_txt --cov=kanban/api/v1/user_settings --cov-report=term-missing
```
**Results**:
- 43/43 passed in 31.45s with **0 warnings**.
- Coverage:
  - `database/models/principals.py`: **100%**
  - `kanban/ops/llms_txt.py`: **100%**
  - `kanban/api/v1/user_settings.py`: **95%** (100% on new preferences routes)
  - Combined Total: **97%** (exceeds `>=95%` gate).

### B. Frontend Vitest Suite
Executed web test suite:
```bash
pnpm vitest run src/features/settings/__tests__/AgentOnboardingPromptCard.test.tsx \
  src/features/settings/__tests__/agentOnboardingPrompt.test.ts \
  src/features/docs-center/__tests__/DocsCenter.test.tsx --coverage
```
**Results**:
- 65/65 passed across all targeted test suites.
- Coverage on `agentOnboardingPrompt.ts`: **100% Statements, 100% Branches, 100% Functions, 100% Lines**.
- Coverage on `AgentOnboardingPromptCard.tsx`: **100% Statements, 97.05% Branches, 100% Functions, 100% Lines**.

### C. Build & Hygiene
- Migration audit: Clean exit code 0, 83 migrations, single head `p6_21_agent_onboarding_preferences`.
- `ruff check .`: All checks passed.
- `mypy`: 0 errors.
- `scripts/check_no_dashes.py --all`: 0 violations across all files.
- `pnpm typecheck`: Clean compilation.
- `pnpm lint`: 0 warnings.
- `pnpm build`: Clean production bundle (1.21s).

---

## 4. Final Verdict & Sign-Off

**`APPROVED`**

The implementation of `KAN-403` enforces strict local folder onboarding constraints, provides robust per-user preference persistence with hostile input sanitization, and achieves `>=95%` coverage with zero warnings across all modified components.
