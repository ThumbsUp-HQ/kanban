# API Specialist Security & Architecture Audit Review: KAN-31

## Audit Metadata
- Ticket ID: KAN-31 ([KB-P3-AUDIT-25])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan31-394cc1ee`
- Target Branch: feat/KAN-31
- Base Commit: 31aca8e
- Head Commit: 724ec7c
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the security architecture, RBAC boundaries, and REST API contract schemas implemented for ticket KAN-31. The delivery resolves four severe MCP key security vulnerabilities (cross-workspace global tier privilege escalation, admin surface role bypass, capability bitmask typo, and cross-project administrative information disclosure) while establishing a canonical, unified REST router at `/api/v1/mcp-keys` and consolidating redundant user interfaces.

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

### 4. Canonical Unified Router (`/api/v1/mcp-keys`)
- Files: `kanban/api/v1/mcp_keys.py`, `kanban/api/v1/__init__.py`
- Invariant: Single canonical REST endpoint supporting self-service (`view=mine`) and tier-matched governance (`view=governance`), returning safe metadata (prefixes and hints, never secret hashes).
- Audit Findings:
  - Endpoints:
    - `GET /api/v1/mcp-keys`: Supports `?view=mine|governance`, `?scope_tier=project|workspace|server`, `?project_ref=...`.
    - `POST /api/v1/mcp-keys`: Mints personal or service bot keys, returning one-time `token` and `Location` header.
    - `DELETE /api/v1/mcp-keys/{key_id}`: Allows self-service owner revocation, or governance revocation with AAL2 and tier-matched administrative authority.
  - Backward compatibility: Legacy routes `/api/v1/auth/mcp-keys` and `/api/v1/admin/mcp-keys` remain functional delegates.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` routes maintain mandatory `Depends(require_admin_aal2)`. Verified via `test_aal2_policy.py::test_case_10_assert_admin_routes_protected`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend touched router: `kanban/api/v1/mcp_keys.py` achieved 97% line coverage and 95% branch coverage (9 of 9 tests passing).
   - Security unit and integration tests: 31 passed in 11.55s.
   - Frontend studio: `McpAccessStudio.tsx` achieved 99.61% line coverage and 97.91% branch coverage (31 tests passing).
5. [x] Static Analysis: `ruff check`, `ruff format --check`, and `mypy` (1078 files) pass with 0 errors.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `message-to-reality-checker.md`, and 16 Playwright screenshot PNGs verified in `docs/qa/KAN-31/`.

---

## 5. Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-25)

- Target Branch: `fix/KAN-31-liveqa`
- Remediation Head Commit: `50f0089`
- Remediation Scope:
  1. Dynamic Target Project Selection:
     - In `kanban/web/src/features/settings/McpAccessStudio.tsx` and `McpConfigSnippetModal.tsx`: Replaced hardcoded project choices with dynamic project fetching via `GET /api/v1/projects`.
     - Dynamic options populate `[data-testid="scope-project-select"]` and `<datalist id="mint-project-datalist">`, mapping directly to accessible workspace projects and propagating real project keys to snippet modals and OAuth connect flows.
     - Added cache invalidation (`queryClient.invalidateQueries`) ensuring freshly minted keys display immediately without race conditions.
  2. Parity for `scope_tier: "server"` on Personal Key Endpoint:
     - In `kanban/api/v1/auth_mcp_keys.py`: Expanded `PersonalMcpKeyMintRequest.scope_tier` to accept `"server"` alongside `"global"`, `"workspace"`, and `"project"`.
     - Properly evaluates `SERVER_ADMIN` role and fresh AAL2, returning RFC 7807 403 `AAL2_REQUIRED` or `INSUFFICIENT_CAPABILITY` on unauthorized requests instead of 422 `VALIDATION_FAILED`.
  3. Test and Quality Verification:
     - 39 Vitest tests passing with 99.18% statements and 97.32% branch coverage across `McpAccessStudio.tsx` and `McpConfigSnippetModal.tsx`.
     - 13 backend Pytest tests passing, with explicit assertions for 403 response on unauthorized `scope_tier='server'` minting.
     - Zero new external dependencies, zero em-dashes and en-dashes, clean `tsc`, `eslint`, `ruff`, `mypy`, and `cssTokensAudit`.

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, and test evidence are verified clean. Handoff to `@ui-spec-2` for visual, UX, and accessibility verification of `docs/qa/KAN-31/screenshots/`.

