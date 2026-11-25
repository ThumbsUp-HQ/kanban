# Integration Reality-Checker Briefing: KAN-416

- **Ticket**: KAN-416 (`[SLICE-3-P1][KB-MCP-OAUTH-AUDIT]` Phase 1: Read-Only Setting Inventory & Simplification Audit for Slice 3)
- **Parent Epic**: KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)
- **Branch**: `docs/KAN-416-slice3-audit` (base `2673a4c9`)
- **Review Status**: Dual Specialist Review (`api-spec` and `ui-spec`) APPROVED; Reality-Checker Certified Grade-A READY
- **Deliverable Path**: `docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md`

## Summary of Completed Technical Actions

1. **Comprehensive Setting-by-Setting Inventory Table**:
   - Inspected 100% of UI controls, labels, options, defaults, validation rules, and backend bindings across all Slice-3 files:
     - Frontend (6 files): `kanban/web/src/features/settings/McpAccessStudio.tsx`, `kanban/web/src/features/settings/McpUnifiedStudio.tsx`, `kanban/web/src/features/settings/ConnectOAuthAppModal.tsx`, `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`, `kanban/web/src/features/admin-oauth/OAuthClientGovernanceStudio.tsx`, `kanban/web/src/features/auth/DeviceActivatePage.tsx`
     - Backend (6 files): `kanban/api/v1/oauth.py`, `kanban/api/v1/mcp_keys.py`, `kanban/api/v1/auth_mcp_keys.py`, `kanban/api/v1/admin/mcp_keys.py`, `kanban/api/v1/admin/workload_identities.py`, `mcp/app.py`
   - Structured table with columns: `Screen/Drawer | Setting Label & Key | Options / Type | 1-Sentence Plain-English Meaning | Backend Wiring Status | Disposition (KEEP | SIMPLIFY | MERGE | MOVE_TO_ADVANCED | CUT)`.
   - Total cataloged settings: 58 granular items covering key minting, OAuth client governance, workload identity federation (RFC 8693), and device authorization (RFC 8628).

2. **Simplification Proposals & Focus Areas**:
   - **4-Question Mint MCP Key Modal**: Eliminates confusing composite dropdowns by separating into 4 plain questions (Role/Target, Expiration, Capability Preset, Advanced Restrictions) with active workspace/project pre-selection.
   - **ConnectOAuthAppModal Ergonomics**: Responsive resource URL wrapping, auto-copy client IDs, and dynamic fallback when target projects are unselected.
   - **Workload Identity Federation 1-Click Presets**: Adds 1-click preset pills for GitHub Actions (`https://token.actions.githubusercontent.com`), GitLab CI (`https://gitlab.com`), and Kubernetes Service Accounts (`https://kubernetes.default.svc.cluster.local`).
   - **OAuth Client Governance Studio Ergonomics**: Adds quick-filter status pills (`All`, `Active`, `Revoked`, `Confidential`, `Public`) and a 1-click Public Client toggle that automatically sets `client_type = "public"` and configures PKCE S256 enforcement.
   - **Device Flow (/activate) Usability & Security**: Adds auto-hyphenation formatting (`XXXX-XXXX`), instant visual warning on ambiguous Base20 consonants (`I`, `L`, `O`, `U`), auto-focus submission, and clear step-up AAL2 requirements.

3. **Phase 2 (`KAN-417`) Action Checklist & Phase 3 (`KAN-418`) Staging Checklist**:
   - File-scoped implementation tasks for Phase 2, strictly deduplicated against `KAN-404` (WebSudo), `KAN-390` (Admin MCP subnav), `KAN-395` (Admin AAL2 routes), and `KAN-396` (OAuth client registration).
   - Local staging checklist for Phase 3 covering PostgreSQL 16+ RLS testbed, mock OIDC issuer (Keycloak/Dex), RFC 8693 token exchange tests, and RFC 8628 device flow client verification.
   - Reiteration of strict non-destructive policy protecting `https://k.hackedyour.info` / `192.168.1.101`.

4. **Forensic Verification**:
   - Zero Unicode em/en-dashes verified: `python3 scripts/check_no_dashes.py --all docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md` exits 0 (`docs/qa/KAN-416/build-check.txt`).
   - 100% of cited repository file paths verified to exist on disk (`docs/qa/KAN-416/unit-test-results.txt` verifies 19/19 files).
   - Zero source-code mutations made during Phase 1 (100% read-only audit).
   - Screenshots: `N/A - Read-Only Audit & Specification Handoff Ticket (UI screenshots captured in KAN-417 and KAN-418)`.
