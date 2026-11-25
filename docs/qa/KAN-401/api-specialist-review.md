# API Specialist Review & Verification: KAN-401 (Epic Rollup)

- **Epic Ticket ID:** KAN-401 (`[EPIC][KB-WORKSPACE-AI-AGENTS-AND-USER-PROMPT] Workspace & Project AI Providers, Autonomous Agents Studio & User Agent Onboarding Prompt`)
- **Child Tickets:**
  - KAN-402 (`feat/KAN-402-workspace-project-ai-agents` - commit `1e509ba4` / `45db6e87`, Grade-A `READY`)
  - KAN-403 (`feat/KAN-403-local-folder-onboarding` - commit `34cef65c` / `41740948`, Grade-A `READY`)
- **Reviewer Persona:** Senior Backend & API Security Architect (`@api-spec`)
- **Status:** APPROVED
- **Date:** 2026-11-25

---

## 1. Executive Summary & Verification Objective

Epic `KAN-401` coordinates the promotion of AI model provider configurations and autonomous agent registries to workspace and project tiers (KAN-402) and pairs it with the local-folder project onboarding prompt in `/llms.txt` and user preferences persistence (KAN-403).

This review verifies the combined security invariants, data isolation, and API surface across the entire epic:
1. **Multi-Tenant Scope Isolation & Air-Gap Separation (KAN-402)**:
   - AI provider listings, configurations, and provider reorder operations are strictly partitioned by `project_id IS NULL` (workspace-level) versus `project_id == body.project_id` (project-level), resolving scope collisions.
   - Cross-scope budget mutations are rejected with HTTP 422 `SCOPE_MISMATCH`.
   - Dedicated unauthenticated/non-server-admin runtime settings route `GET /api/v1/workspaces/{workspace}/ai-providers/settings` exposes air-gap status safely without leaking server admin settings.
2. **Local Project Boundary & Input Hardening (KAN-403)**:
   - `/llms.txt` and `AgentOnboardingPromptCard` default strictly to local repository folder (`.agents/skills/` and `AGENTS.md`) without mutating global user directories.
   - Linear migration #83 `p6_21_agent_onboarding_preferences` adds `agent_onboarding_prefs_json JSONB NOT NULL DEFAULT '{}'::jsonb` to `user_preferences`.
   - `GET` and `PATCH /api/v1/users/me/preferences` operate under `FORCE RLS` with strict UTF-16 lone-surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF` -> HTTP 422 `INVALID_UTF8_SURROGATE`), control character stripping, and `<= 4096` byte payload bounds checking. Partial nested updates safely preserve untouched preference fields via `AgentOnboardingPrefsPatch`.
3. **Database Migration Linearity & ORM Parity**:
   - Single-head linear migration chain (83 migrations total, single head `p6_21_agent_onboarding_preferences`).
   - Clean column-level ORM parity across `principals.py`, `ai_config.py`, and `agents.py`.

---

## 2. Automated Test Results & Code Quality

- **Backend Pytest Suite**: 96 tests passed in 63.87s with 0 warnings.
  - Overall coverage across modified modules: **96%** (`database/models/principals.py`: 100%, `kanban/ops/llms_txt.py`: 100%, `kanban/api/v1/agent_definitions.py`: 100%, `kanban/agents/service.py`: 97%, `kanban/ai_config/service.py`: 95%, `kanban/api/v1/admin/ai_providers.py`: 95%, `kanban/api/v1/user_settings.py`: 94% / 100% on preferences routes).
- **Frontend Vitest Suite**: 300 tests passed across 12 files in 7.37s with 0 warnings.
  - Line coverage: **100%**, Branch coverage: **95.88%** (`AgentOnboardingPromptCard.tsx`: 100%, `agentOnboardingPrompt.ts`: 100%, `personalSettingsApi.ts`: 100%).
- **Static Analysis & Linters**:
  - `uv run kanban-ctl db check-migrations --static-only`: Exit code 0 (83 migrations valid).
  - `uv run ruff check kanban/ database/`: Clean (0 errors, 0 warnings).
  - `python3 scripts/check_no_dashes.py --all`: Clean (0 Unicode dashes).
  - `pnpm --dir kanban/web typecheck`: Clean (0 errors).
  - `pnpm --dir kanban/web lint`: Clean (0 warnings).
  - `pnpm --dir kanban/web build`: Clean production build in 1.22s.

---

## 3. Forensic Bundle & Conclusion

- All child verification packets (`docs/qa/KAN-402/` and `docs/qa/KAN-403/`) are certified Grade-A `READY`.
- 22 zero-mock multi-viewport screenshots verified across 5 screen sizes.
- Cryptographic manifests (`changed-files-manifest.txt` and `SHA256SUMS.txt`) verified 100% OK.

The combined API surface and security implementation for Epic `KAN-401` is **APPROVED**.
