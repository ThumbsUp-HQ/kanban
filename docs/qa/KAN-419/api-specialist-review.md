# API Specialist Review: KAN-419 (Slice 3 Phase 4 Publish Verified MCP Access, Gemini/Claude OAuth & Workload OIDC Wiki + In-App Docs)

**Ticket:** KAN-419 (`[SLICE-3-P4][KB-MCP-OAUTH-DOCS]`)  
**Parent Epic:** KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan419-f31af3af`  
**Target Commit:** `7c40a3a7` (branch `docs/KAN-419-slice3-mcp-docs`, base `685b9edf`)  
**Wiki Commit:** `44545f4` (branch `docs/KAN-419-slice3-mcp-docs` inside `./thumbs-up-kanban.wiki`)  

---

## 1. Executive Summary & Verdict

This API Specialist Review evaluates the technical accuracy, schema fidelity, protocol specifications, API contracts, and security documentation delivered in **KAN-419: Phase 4 Publish Verified MCP Access, Gemini/Claude OAuth & Workload OIDC Wiki + In-App Docs**.

The documentation covers the entire Slice-3 subsystem across authoritative wiki chapters and the compiled offline in-app DocsCenter bundle (`wikiManifest.ts`, 599,201 bytes across 34 chapters, 102 images copied). Every documented contract was audited against the active API schemas, database models, and surface tool registries:
1. **Three-Surface MCP Protocol & Tool Catalog Parity**:
   - The authoritative documentation precisely enumerates all 25 MCP tools across their respective surfaces:
     * `/mcp/agent`: 10 execution and QA tools (`search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`, `update_workpad`).
     * `/mcp/docs`: 3 documentation tools (`search`, `create`, `update`).
     * `/mcp/admin`: exactly 12 governance and lifecycle tools matching `mcp/surfaces/admin/__init__.py` 1:1 (`configure_workspace`, `manage_auth_cards`, `manage_principals_and_groups`, `manage_access_policies`, `architect_project`, `manage_cycles_and_modules`, `manage_custom_fields_and_scripts`, `manage_workflow_interceptors`, `manage_ai_and_agent_runners`, `override_ticket_provenance`, `audit_and_purge_object_links`, and `destructive_lifecycle` with 2-stage confirmation).
   - In `audit_and_purge_object_links`, verified action enums match implementation: `run_audit`, `list_flagged`, `purge_audited`, and `help`.
2. **Capability Mask & Scoping Protocol Bounds**:
   - Granular capability bitmask matches `kanban/security/permissions.py` (`Capability`) 1:1: `NONE=0`, `VIEW=1`, `COMMENT=2`, `EDIT=4`, `TRANSITION=8`, `LINK=16`, `SHARE=32`, `ADMIN=64`, `DELETE=128`, `ALL=255`.
   - Deny-all capability mask `0` (Migration #84 / `p6_22_mcp_api_keys_capability_mask_boundary`) is accurately detailed as rejecting all tool calls with `INSUFFICIENT_CAPABILITY`.
   - MCP Key API fields match backend schemas across 9 settings in 3 groups: `label` (`max_length=120`), `owner_kind` (`personal_user` | `service_bot`), `scope_tier`, `expires_in_days` (`30`, `60`, `90`, `365`, `0`), `capability_mask` (`0..255`, UI default 31, API default 7), `allowed_tools`, `disabled_tools`, `allowed_cidrs`.
3. **OAuth 2.1 Governance & RFC 8628 Device Flow**:
   - RFC 8414 metadata discovery at `/.well-known/oauth-authorization-server` and RFC 9728 discovery at `/.well-known/oauth-protected-resource` documented with literal schemas.
   - Exact query parameter state limit `MAX_STATE_LEN = 4096` documented (guaranteeing Gemini 1,200+ char state compatibility).
   - OAuth 2.1 client properties (11 settings across 3 groups): `client_id` prefix `client_`, `auth_method` (`none`, `client_secret_post`, `client_secret_basic`, `private_key_jwt`), `pkce_enforce` (mandatory `S256`), `allowed_scopes` strictly matching `SURFACE_SCOPES` (`agent:read`, `agent:write`, `docs:read`, `docs:write`, `admin:read`, `admin:write`, `admin:destructive`), and `access_token_ttl` (`60..86400`, default 3600 client, 900 JWT).
   - RFC 8628 Device Flow user verification charset specified as canonical Base20 `BCDFGHJKLMNPQRSTVWXZ` (excluding vowels `A,E,I,O,U` and digits `0-9`).
4. **RFC 8693 Workload Identity Federation & DCR Governance**:
   - UI routes verified at `/settings/mcp` and `/admin/mcp` (13 settings across 3 groups).
   - Presets for GitHub Actions (`repo:org/repo:ref:refs/heads/*`), GitLab CI (`project_path:group/project:ref:*:ref_type:branch`), and Kubernetes (`system:serviceaccount:default:*`) documented with strict boundary `max_ttl_seconds <= 86400`.
   - Token exchange executed via standard RFC 8693 `POST /oauth/token` (`grant_type=urn:ietf:params:oauth:grant-type:token-exchange`).
   - Admin bulk DCR client purge (`POST /api/v1/admin/oauth-clients/bulk-delete`) documented with single-transaction guarantees.
5. **In-App Help Links & Heading Slug Anchors**:
   - Resolved heading anchors for all 8 UI help links across `McpAccessStudio.tsx`, `McpUnifiedStudio.tsx`, `ConnectOAuthAppModal.tsx`, `McpConfigSnippetModal.tsx`, `OAuthClientGovernanceStudio.tsx`, and `DeviceActivatePage.tsx`. All links resolve to actual `##` / `###` headings matching `slugifyAnchor()` output, with 0 broken links.
   - All 102 images in `thumbs-up-kanban.wiki/images/` match `kanban/web/public/docs-images/` byte-for-byte with 0 external image links and 0 orphan files.
   - Claude CLI command accurately documented: `claude mcp add --transport http kanban https://kanban.example.com/mcp/agent`.

**Verdict: APPROVED.** All API contracts, tool schemas, protocol runbooks, and security boundaries in KAN-419 are 100% verified and approved.

---

## 2. API Contract & Security Invariant Audit

### 2.1 Verified Endpoints & Wire Schemas
- **Discovery Endpoints:**
  - `GET /.well-known/oauth-authorization-server`
  - `GET /.well-known/oauth-protected-resource`
  - `GET /mcp/agent/.well-known/oauth-protected-resource`
- **MCP Surface Routes:**
  - `POST /mcp/agent` (Streamable JSON-RPC / SSE, `application/json, text/event-stream`)
  - `POST /mcp/docs`
  - `POST /mcp/admin`
- **OAuth 2.1 & Device Flow Routes:**
  - `POST /oauth/register` (DCR with `client_secret_post` / `client_secret_basic`)
  - `GET /oauth/authorize` (PKCE S256 with `state` up to 4,096 chars)
  - `POST /oauth/token` (including RFC 8693 Workload Identity Token Exchange)
  - `POST /oauth/device/authorize` (Base20 user code minting)
  - `POST /oauth/device/token`
- **Admin Governance & Federation Routes:**
  - `POST /api/v1/admin/oauth-clients/bulk-delete`
  - `POST /api/v1/admin/mcp-keys`
  - `POST /api/v1/admin/workload-identities/policies`

### 2.2 Security Invariants Verified
- **Cryptographic Zeroization:** Scoped API keys (`kb_agt_*`, `kb_doc_*`, `kb_adm_*`) displayed once at minting and never retrievable in plaintext.
- **Strict AAL2 Authorization:** All `/admin/oauth/*` and `/admin/mcp/*` endpoints require verified WebSudo AAL2.
- **Air-Gapped Offline Privacy:** All 34 compiled wiki chapters render without external network requests or third-party tracking CDNs.

---

## 3. Automated Test Verification & Quality Gates

1. **Pytest Parity Suite (`kanban/tests/test_wiki_bundle_sync.py`)**:
   - 7/7 tests passed in 0.14s.
   - Verified 100% SHA-256 image parity (102 images), zero duplicate numeric prefix collisions, zero external images, and zero unreferenced orphan images.

2. **Frontend Vitest Suite (`src/features/docs-center/`)**:
   - 71/71 tests passed across `DocsCenter.test.tsx` and `DocsCenterImages.test.tsx` in 6.50s.
   - Branch coverage: **96.74%** (Statements 99.6%, Functions 100%, Lines 100%).
   - 0 failures, 0 `act(...)` warnings.

3. **Static Analysis & Build Pipeline**:
   - `scripts/check_no_dashes.py`: 0 Unicode em/en-dashes found across repository and wiki chapters.
   - `tsc -b --noEmit`: 0 TypeScript errors.
   - `eslint . --max-warnings 0`: 0 warnings, 0 errors.
   - `vite build`: Production client built cleanly in 1.34s.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-419/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: Exit code 0 across sync, dashes, typecheck, lint, and build.
  - `unit-test-results.txt`: Documents 7 Pytest and 71 Vitest tests with 96.74% branch coverage.
  - `wiki-diff.patch`: Patch of commit `44545f4` across 4 wiki chapters.
  - `screenshots/`: 26 multi-viewport PNG captures visually verified, with `07-slice3-mermaid-diagrams-rendered-1440x900.png` confirming clean SVG rendering.

The documentation and API schemas for KAN-419 are fully verified, robust, and approved for production release.
