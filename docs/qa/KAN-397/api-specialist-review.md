# API Specialist Review (KAN-397)

## Overview and Architecture Verification

- **Ticket**: KAN-397 (`[KB-MIGRATION-STUDIO-RENAME] Rename "Plane Migration Import Studio" and "Plane Migration" to "Migration Import Studio" and "Migration"`)
- **Module**: `kanban/web/src/features/admin-imports/`, `kanban/web/src/features/admin/`, `kanban/web/src/app/`
- **Reviewed By**: API Specialist (`@api-spec`)
- **Branch**: `fix/KAN-397-rc1`
- **Status**: STATUS: APPROVED
- **Verdict**: APPROVED

---

## Dual Specialist Verification Audit

### 1. Classification and Scope
- **Classification**: N/A - Pure Frontend Copy and Title Update.
- **Contract Integrity**: Zero backend API contracts, schema models, database tables, or MCP tool definitions are modified in this change.
- **Scope Verification**:
  - `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx`: Title rendered as exact literal `Migration Import Studio` across all 4 sources (`plane`, `jira`, `github`, `linear`). Source pills remain labeled `Plane`, `Jira`, `GitHub Issues`, `Linear`.
  - `kanban/web/src/features/admin/AdminStudioSubnav.tsx`: Label on `tab-admin-imports` updated to exact literal `'Migration'` pointing to `/admin/imports`.
  - `kanban/web/src/app/Topbar.tsx`: Navigation link text on `topbar-admin-imports-link` updated to exact literal `Migration Import Studio`.
  - `kanban/web/src/app/AppShell.tsx`: Section mapper `computeCurrentSection` maps `/admin/imports` to `'Migration Import Studio'`, `/admin/auth` to `'Auth Cards'`, `/admin/oauth` to `'OAuth Clients'`, `/admin/agent-runners` to `'Agent Runners'`, `/admin/ai` to `'AI Providers'`, and `/admin/agents` to `'Autonomous Agents'`.

### 2. API Contracts and Invariance Verification
- **Endpoint Contracts**:
  - The API routes (`/api/v1/imports/plane`, `/api/v1/imports/{source}`, `/api/v1/workspaces/{slug}/export/portable`) are unchanged.
  - The payload structures, parameters, and return types remain identical.
  - The offline and online MCP tools are unaffected.
- **Security Invariants**:
  - Zero bypass of authentication or AAL2 permission checks.
  - Zero modifications to backend database access, permissions, or RLS policies.

### 3. Automated Test Verification
- All 86 unit tests pass with 99.31% statement, 95.30% branch, 99.01% function, and 99.76% line coverage across the 4 modified source files.
- Verified explicit negative assertions in `MenuConsolidation_KAN362.test.tsx` verifying that `tab-admin-imports` and `topbar-admin-imports-link` do NOT contain `'Plane Migration'` or `'Plane Migration Import Studio'`.
- Positive and negative cases verified across positive input, source switching, dry-run simulation, and live import execution.

### 4. Specialist Verdict
The update cleanly aligns user-facing labels and navigation copy across all entry points without altering backend API contracts.
**STATUS: APPROVED**
