# Forensic QA Verification Packet: KAN-31

**Ticket Summary:** [KB-P3-AUDIT-25] Consolidate 4 Duplicate MCP Key Screens Into One Unified Scoped MCP Studio (/settings/mcp) and Fix MCP Key RBAC Escalation Bugs (4 Problems)
**Branch:** feat/KAN-31
**Author:** b-kan31 (Security & Full-Stack Systems Engineer)

---

## 1. Executive Summary & Problems Resolved

This delivery unifies the fragmented Model Context Protocol (MCP) surface across both backend APIs and frontend web UI into a single, secure, tiered MCP Studio (`/settings/mcp`), eliminating duplicate screens and fixing four critical RBAC/security vulnerabilities.

### Problem 1: Global Tier Privilege Escalation Guard
- **File:** `kanban/security/mcp_keys.py`
- **Root Cause:** Personal user key minting previously checked workspace membership but lacked an `elif scope_tier in ("global", "server")` constraint, allowing non-admin users to mint cross-workspace global keys.
- **Remediation:** Enforced strict check requiring `SERVER_ADMIN` role and fresh `AAL2` (`effective_aal >= 2`) before minting global/server scoped personal keys. Normalizes `"server"` alias to `"global"`.

### Problem 2: Admin Surface Role Bypass and Bitmask Typo Fix
- **File:** `kanban/security/mcp_keys.py`
- **Root Cause:**
  1. The delete capability check improperly tested bitmask value `8` (which is `Capability.TRANSITION`) instead of `128` (`Capability.DELETE.value`).
  2. Minting keys on `surface == "admin"` lacked tier-matched role enforcement, permitting users without administrative authority to mint admin surface tokens.
- **Remediation:**
  - Corrected delete capability bitmask verification to `Capability.DELETE.value` (`128`).
  - Added tier-matched administrative role enforcement for `surface == "admin"`:
    - `scope_tier in ("global", "server")`: requires `SERVER_ADMIN` + fresh `AAL2`.
    - `scope_tier == "workspace"`: requires `WORKSPACE_ADMIN` or `SERVER_ADMIN` + fresh `AAL2`.
    - `scope_tier == "project"`: requires `PROJECT_ADMIN`, `WORKSPACE_ADMIN`, or `SERVER_ADMIN` on target project + fresh `AAL2`.
  - Scopes containing `admin:destructive` strictly require `SERVER_ADMIN` + fresh `AAL2`.

### Problem 3: Cross-Project PROJECT_ADMIN Leak Prevention
- **File:** `kanban/api/v1/admin/mcp_keys.py`
- **Root Cause:** `PROJECT_ADMIN` users querying `/api/v1/admin/mcp-keys` could inspect workspace-wide keys or keys associated with projects they did not administer.
- **Remediation:**
  - Restricted `PROJECT_ADMIN` callers to `scope_tier == "project"` keys targeting projects where the caller possesses `Capability.ADMIN` (`64`) or project admin roles.
  - Queries for workspace or global scopes by `PROJECT_ADMIN` return an empty list (`[]`).
  - Revocation by `PROJECT_ADMIN` via `DELETE /api/v1/admin/mcp-keys/{key_id}` strictly verifies target key belongs to an administered project in caller workspace; foreign or workspace keys return `404 Not Found`.

### Problem 4: Unified API Router, Single Studio UI, and Route Consolidation
- **Backend Router (`kanban/api/v1/mcp_keys.py`):**
  - Canonical endpoints mounted at `/api/v1/mcp-keys` (`GET ?view=mine|governance&scope_tier=...&project_ref=...`, `POST`, `DELETE /{key_id}`).
  - Standardized response schema returning `key_prefix`, `display_hint`, `allowed_projects`, `expires_at`, and one-time `token` on creation (raw keys/hashes are never exposed).
  - Preserved backward compatibility: legacy `/api/v1/auth/mcp-keys` and `/api/v1/admin/mcp-keys` remain functional delegates.
- **Frontend Studio (`kanban/web/src/features/settings/McpAccessStudio.tsx`):**
  - Single canonical destination at `/settings/mcp`.
  - Scope Filter Pills: `[All] [Project] [Workspace] [Server]` with contextual target project selector when `Project` is selected.
  - Architecture explainer card detailing Personal User vs Service Bot keys and Project vs Workspace vs Server scopes.
  - Segmented View Toggle: `[My Keys & Connected Apps | Governance (All Scoped Keys)]` visible to `PROJECT_ADMIN`, `WORKSPACE_ADMIN`, and `SERVER_ADMIN`.
  - Inline AAL2 Step-up Challenge: intercepting `403 AAL2_REQUIRED` or `403 AAL2_STALE` with embedded `SecondFactorStep` dialog, automatically retrying operations on factor confirmation.
- **Navigation & Deep Linking Consolidation:**
  - `Topbar.tsx`: Collapsed 3 right-menu entries into a single entry: `🔑 MCP Keys & OAuth Apps` -> `/settings/mcp`.
  - `WorkspaceSettingsPage.tsx`: Removed duplicate embedded tab `tab-mcp`, added contextual deep link card pointing to `/settings/mcp?scope=workspace`.
  - `ProjectSettingsPage.tsx`: Updated integration card to contextual deep link `/settings/mcp?scope=project&project=:projectKey`.
  - `routes.tsx`: Redirected legacy routes (`/workspaces/settings/mcp`, `/projects/:projectKey/settings/mcp`, `/admin/mcp`, `/admin/mcp-keys`) to `/settings/mcp` preserving search parameters.

---

## 2. Verification Proofs & Test Results

### Automated Quality Gates
All automated quality gates executed cleanly without errors or warnings:
- **Ruff Check:** Passed (0 errors)
- **Ruff Format Check:** 1,790 files already formatted
- **Import Architecture Contracts (lint-imports):** 2 contracts kept, 0 broken
- **Mypy Type Checking:** Success (0 issues across 1,078 source files)
- **TypeScript Typecheck (`tsc -b --noEmit`):** Clean (0 errors)
- **ESLint (`eslint . --max-warnings 0`):** Clean (0 warnings, 0 errors)
- **Dashes Audit (`python3 -m scripts.check_no_dashes --all`):** Clean (zero em-dashes or en-dashes)
- **Admin Routes Protected:** All `/api/v1/admin/*` routes maintain mandatory `Depends(require_admin_aal2)`

### Test Coverage Results
- **Backend Touched Unit & API Coverage:**
  - `kanban/api/v1/mcp_keys.py`: **97% Line Coverage**, **95% Branch Coverage**
  - `kanban/security/mcp_keys.py`: 100% of newly added guard lines (415-467) covered
  - `kanban/api/v1/admin/mcp_keys.py`: 100% of newly added PROJECT_ADMIN isolation lines (280-357) covered
  - Suite: 34 integration and security tests passed in 10.95s
- **Frontend Studio Coverage:**
  - `McpAccessStudio.tsx`: **99.61% Line Coverage**, **97.91% Branch Coverage**, **100% Function Coverage**
  - Suites: 31 tests passed in `McpAccessStudio.test.tsx` and `McpUnifiedStudio.test.tsx`
  - Integration: 71 tests passed across `Topbar.test.tsx`, `WorkspaceSettingsPage.test.tsx`, and `routes.test.tsx`

### Visual Proof Screenshots (Desktop 1440x900 & Mobile 390x844, Light & Dark)
Stored in `docs/qa/KAN-31/screenshots/`:
1. `01-settings-mcp-my-keys-light-desktop.png` / `01-settings-mcp-my-keys-dark-desktop.png`: My Keys view with scope pills and architecture guide.
2. `01-settings-mcp-my-keys-light-mobile.png` / `01-settings-mcp-my-keys-dark-mobile.png`: Mobile viewport responsiveness of My Keys view.
3. `02-settings-mcp-governance-light-desktop.png` / `02-settings-mcp-governance-dark-desktop.png`: Governance view displaying all scoped keys with revoke controls.
4. `02-settings-mcp-governance-light-mobile.png` / `02-settings-mcp-governance-dark-mobile.png`: Mobile viewport responsiveness of Governance view.
5. `03-settings-mcp-project-scope-light-desktop.png` / `03-settings-mcp-project-scope-dark-desktop.png`: Project scope pill active, showing target project dropdown filter.
6. `03-settings-mcp-project-scope-light-mobile.png` / `03-settings-mcp-project-scope-dark-mobile.png`: Mobile viewport responsiveness of Project scope selector.
7. `04-topbar-menu-mcp-studio-light-desktop.png` / `04-topbar-menu-mcp-studio-dark-desktop.png`: Topbar avatar menu showing consolidated single link: `🔑 MCP Keys & OAuth Apps`.
8. `04-topbar-menu-mcp-studio-light-mobile.png` / `04-topbar-menu-mcp-studio-dark-mobile.png`: Mobile Topbar avatar menu with single consolidated MCP link.

---

## 3. Forensic Artifact Manifest

- `docs/qa/KAN-31/unit-test-results.txt`: Full raw output of backend pytest and frontend vitest test suites.
- `docs/qa/KAN-31/build-or-typecheck.txt`: Full raw log of ruff, mypy, lint-imports, tsc, eslint, and check_no_dashes.
- `docs/qa/KAN-31/git-diff.patch`: Patch against origin/main containing all modifications and new files.
- `docs/qa/KAN-31/changed-files-manifest.txt`: List of 17 changed and new code/test files.
- `docs/qa/KAN-31/screenshots/`: 16 Playwright visual proof screenshot PNGs.
- `kanban/web/e2e/qa/kan-31-screenshots.spec.ts`: Hermetic Playwright test script generating the visual proofs.
