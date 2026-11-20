# API Specialist Security & Architecture Audit Review: KAN-31

## Audit Metadata
- Ticket ID: KAN-31 ([KB-P3-AUDIT-25])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan31-rcfix-6c02ef64`
- Target Branch: fix/KAN-31-rc2
- Base Commit: 036216b
- Head Commit: 4a24d1a
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the security architecture, RBAC boundaries, REST API contract schemas, and Clean-Room Reality-Checker Round 2 surgical remediations ([KB-P3-AUDIT-25]) implemented for ticket KAN-31. The delivery resolves four severe MCP key security vulnerabilities (cross-workspace global tier privilege escalation, admin surface role bypass, capability bitmask typo, and cross-project administrative information disclosure), establishes a canonical unified REST router at `/api/v1/mcp-keys`, decouples key ownership (`owner_kind`) from authorization tiers (`scope_tier`), and enforces read-after-write commit consistency.

All changes have been verified against authoritative security specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Global Tier Privilege Escalation Prevention
- Files: `kanban/security/mcp_keys.py` (lines 477-495)
- Invariant: Personal user tokens must not transcend tenant boundaries without explicit system administrator authorization.
- Audit Findings:
  - Previous vulnerability: Non-admin users could mint personal user tokens scoped to `"global"` because the personal user branch omitted global tier restrictions.
  - Fix verified: `mint_mcp_api_key` explicitly verifies that when `scope_tier == "global"` (or `"server"`), the caller must hold the `SERVER_ADMIN` role and possess fresh AAL2 authentication (`effective_aal >= 2`). Callers without `SERVER_ADMIN` or lacking fresh AAL2 are rejected with RFC 7807 403 `INSUFFICIENT_CAPABILITY` or `AAL2_REQUIRED`.

### 2. Admin Surface Role Bypass & Capability.DELETE Bitmask Fix
- Files: `kanban/security/mcp_keys.py` (lines 427-476)
- Invariant: Keys capable of destructive operations or bound to the admin surface must enforce tier-matched administrative roles and fresh AAL2.
- Audit Findings:
  - Bitmask typo correction: Previously evaluated `capability_mask & 8` (which is `Capability.TRANSITION`). It has been corrected to test `Capability.DELETE.value` (`128`).
  - Admin surface validation: When `surface == "admin"`, the implementation now requires:
    - Global tier: `SERVER_ADMIN` + fresh AAL2.
    - Workspace tier: `WORKSPACE_ADMIN` or `SERVER_ADMIN` + fresh AAL2.
    - Project tier: `PROJECT_ADMIN`, `WORKSPACE_ADMIN`, or `SERVER_ADMIN` on target project + fresh AAL2.
  - Destructive scope protection: Any key including `admin:destructive` strictly requires `SERVER_ADMIN` + fresh AAL2.

### 3. Cross-Project PROJECT_ADMIN Leak Prevention
- Files: `kanban/api/v1/admin/mcp_keys.py` (lines 284-310, 386-407)
- Invariant: A `PROJECT_ADMIN` in one project must never inspect or revoke MCP keys belonging to other projects or workspace-wide infrastructure.
- Audit Findings:
  - Listing (`GET /api/v1/admin/mcp-keys`): Callers with only `PROJECT_ADMIN` authority are strictly filtered to `scope_tier == "project"` keys targeting projects where the caller possesses `Capability.ADMIN` (`64`) or project admin roles. Any query requesting `workspace` or `global` tiers returns an empty list (`[]`).
  - Revocation (`DELETE /api/v1/admin/mcp-keys/{key_id}`): If a `PROJECT_ADMIN` attempts to revoke an MCP key outside their administered projects or in workspace/global scope, the endpoint returns 404 Not Found, preventing cross-project enumeration or revocation.

### 4. Canonical Unified Router (`/api/v1/mcp-keys`) & Commit Consistency
- Files: `kanban/api/v1/mcp_keys.py`, `kanban/api/v1/auth_mcp_keys.py`, `kanban/api/v1/__init__.py`
- Invariant: Single canonical REST endpoint supporting self-service (`view=mine`) and tier-matched governance (`view=governance`), returning safe metadata (prefixes and hints, never secret hashes).
- Audit Findings:
  - Endpoints:
    - `GET /api/v1/mcp-keys`: Supports `?view=mine|governance`, `?scope_tier=project|workspace|server`, `?project_ref=...`.
    - `POST /api/v1/mcp-keys`: Mints personal or service bot keys, returning one-time `token` and `Location` header.
    - `DELETE /api/v1/mcp-keys/{key_id}`: Allows self-service owner revocation, or governance revocation with AAL2 and tier-matched administrative authority.
  - Read-after-write commit consistency: Added `await session.commit()` before HTTP response in `mint_unified_mcp_key`, `revoke_unified_mcp_key`, `mint_personal_key`, and `revoke_personal_key`, eliminating race conditions between client redirect/refetch and database transaction commit.

---

## Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-25 Round 2)

- Target Branch: `fix/KAN-31-rc2`
- Remediation Head Commit: `4a24d1a`
- Remediations Verified:
  1. **Unified API Wiring Across McpAccessStudio.tsx:**
     - Migrated key operations across `/settings/mcp` to `fetchUnifiedMcpKeys`, `mintUnifiedMcpKey`, and `revokeUnifiedMcpKey` on `/api/v1/mcp-keys`.
     - Eliminates 404 errors in Governance view when revoking service bot or foreign user keys.
     - Surfaced non-AAL2 revocation/mint errors in accessible error banner (`role="alert"` / `data-testid="studio-error-banner"`) using dedicated CSS class `.kb-mcp-mint-error--banner` with zero inline styles.
  2. **Key Type (`owner_kind`) and Scope Tier (`scope_tier`) Decoupling:**
     - Separated `owner_kind` (`personal_user` vs `service_bot`) from `scope_tier` (`workspace`, `project`, `global`, `server`) in mint modal inputs.
     - Eliminates HTTP 422 `VALIDATION_FAILED` errors when minting personal user or service bot keys across scopes.
  3. **UI State & Accessibility Polish:**
     - Interpolated `currentWorkspaceSlug` dynamically into `getTierBadge` (`Workspace: ${currentWorkspaceSlug}`).
     - Passed target project into `McpConfigSnippetModal` (`newKeyProject.trim() || effectiveProjectKey`).
     - Replaced inline style with dedicated tokenized CSS class `.kb-mcp-mint-error--banner` in `McpAccessStudio.css`.
  4. **Quality Gates & Test Coverage:**
     - Vitest: 52 tests passing (98.55% statements, 96.35% branches) with 0 console or act warnings.
     - Pytest: 21 tests passing (97% coverage on `kanban/api/v1/mcp_keys.py`).
     - Static checks: `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings/errors), `vite build` (clean in 1.12s), `ruff check` (clean), `mypy` (clean), `cssTokensAudit.test.ts` (4/4 passed).
     - Strict punctuation: 0 em-dashes and 0 en-dashes across all code, tests, and documentation.
     - Clean evidence packet: `git-diff.patch` generated against `31aca8e` with zero `docs/qa/` files included.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: Mandatory `Depends(require_admin_aal2)` maintained across all `/api/v1/admin/*` routes.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend: `kanban/api/v1/mcp_keys.py` 97% line and branch coverage (21 pytest tests passing).
   - Frontend: 52 vitest tests passing across touched features with >= 95% coverage.
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy`, `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, and screenshots verified in `docs/qa/KAN-31/`.

---

## Verdict & Handoff
STATUS: APPROVED

The unified MCP key API contracts, security boundaries, and test evidence are verified clean. Ready for final coordinator merge into `main`.
