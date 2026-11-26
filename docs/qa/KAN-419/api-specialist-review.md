# API Specialist Review: KAN-419 (Slice 3 Phase 4 Publish Verified MCP Access, Gemini/Claude OAuth & Workload OIDC Wiki + In-App Docs)

**Ticket:** KAN-419 (`[SLICE-3-P4][KB-MCP-OAUTH-DOCS]`)  
**Parent Epic:** KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan419-f31af3af`  
**Target Commit:** `4ce26a82` (branch `docs/KAN-419-slice3-mcp-docs`, base `685b9edf`)  
**Wiki Commit:** `758f9b2` (branch `docs/KAN-419-slice3-mcp-docs` inside `./thumbs-up-kanban.wiki`)  

---

## 1. Executive Summary & Verdict

This API Specialist Review evaluates the technical accuracy, schema fidelity, protocol specifications, API contracts, and security documentation delivered in **KAN-419: Phase 4 Publish Verified MCP Access, Gemini/Claude OAuth & Workload OIDC Wiki + In-App Docs**.

The documentation covers the entire Slice-3 subsystem across authoritative wiki chapters and the compiled offline in-app DocsCenter bundle (`wikiManifest.ts`). Every documented contract was audited against the active API schemas and database models:
1. **Three-Surface MCP Protocol & Tool Catalog Parity**:
   - The authoritative documentation precisely enumerates all 25 MCP tools across their respective surfaces:
     * `/mcp/agent`: 10 execution and QA tools (`search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`, `update_workpad`).
     * `/mcp/docs`: 3 documentation tools (`search`, `create`, `update`).
     * `/mcp/admin`: 12 governance and lifecycle tools (`configure_workspace`, `manage_auth_cards`, `manage_principals_and_groups`, `manage_access_policies`, `architect_project`, `manage_cycles_and_modules`, `administer_views_and_fields`, `run_diagnostics`, `audit_and_purge_links`, `orchestrate_migration`, `execute_backup_or_restore`, `destructive_lifecycle`).
   - The 2-stage confirmation protocol for `destructive_lifecycle` is explicitly specified with cryptographic ephemeral confirmation tokens.
2. **Capability Mask & Scoping Protocol Bounds**:
   - Granular capability bitmask (`0..255`) is documented with exact flag values: `READ=1`, `WRITE=2`, `TRANSITION=4`, `COMMENT=8`, `ADMIN=16`, `DESTRUCTIVE=32`, `DIAGNOSTIC=64`, `EXTERNAL=128`.
   - Deny-all capability mask `0` (Migration #84 / `p6_22_mcp_api_keys_capability_mask_boundary`) is accurately detailed as rejecting all tool calls with `INSUFFICIENT_CAPABILITY`.
3. **OAuth 2.1, RFC 8628 Device Flow & State Boundaries**:
   - RFC 8414 metadata discovery at `/.well-known/oauth-authorization-server` and RFC 9728 discovery at `/.well-known/oauth-protected-resource` documented with literal schemas.
   - Exact query parameter state limit `MAX_STATE_LEN = 4096` documented (guaranteeing Gemini 1,200+ char state compatibility).
   - RFC 8628 Device Flow user verification charset specified as canonical Base20 `BCDFGHJKLMNPQRSTVWXZ` (excluding vowels `A,E,I,O,U` and digits `0-9`).
4. **RFC 8693 Workload Identity Federation & DCR Governance**:
   - Presets for GitHub Actions, GitLab CI, and Kubernetes Service Accounts documented with strict boundary `max_ttl_seconds <= 86400`.
   - Admin bulk DCR client purge (`POST /api/v1/admin/oauth-clients/bulk-delete`) documented with single-transaction guarantees.
5. **In-App Help Links & Air-Gapped Offline Wiki Parity**:
   - All 8 UI `StudioDocLink` and `FieldHelpHint` targets across `McpAccessStudio.tsx`, `McpUnifiedStudio.tsx`, `ConnectOAuthAppModal.tsx`, `McpConfigSnippetModal.tsx`, `OAuthClientGovernanceStudio.tsx`, and `DeviceActivatePage.tsx` resolve to valid headings with 0 broken links.
   - All 102 images in `thumbs-up-kanban.wiki/images/` match `kanban/web/public/docs-images/` byte-for-byte with 0 external image links and 0 orphan files.

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
  - `POST /oauth/token`
  - `POST /oauth/device/authorize` (Base20 user code minting)
  - `POST /oauth/device/token`
- **Admin Governance & Federation Routes:**
  - `POST /api/v1/admin/oauth-clients/bulk-delete`
  - `POST /api/v1/admin/mcp-keys`
  - `POST /api/v1/admin/workload-identities/exchange`
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
   - 70/70 tests passed across `DocsCenter.test.tsx` and `DocsCenterImages.test.tsx` in 6.67s.
   - Branch coverage: **96.44%** (Statements 99.6%, Functions 100%, Lines 100%).
   - 0 failures, 0 `act(...)` warnings.

3. **Static Analysis & Build Pipeline**:
   - `scripts/check_no_dashes.py`: 0 Unicode em/en-dashes found across repository and wiki chapters.
   - `tsc -b --noEmit`: 0 TypeScript errors.
   - `eslint . --max-warnings 0`: 0 warnings, 0 errors.
   - `vite build`: Production client built cleanly in 1.35s.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-419/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: (dual review pending sign-off)
- Forensic Artifacts:
  - `build-check.txt`: Exit code 0 across sync, dashes, typecheck, lint, and build.
  - `unit-test-results.txt`: Documents 7 Pytest and 70 Vitest tests with 96.44% branch coverage.
  - `wiki-diff.patch`: Patch of commit `758f9b2` across 4 wiki chapters.
  - `screenshots/`: 26 multi-viewport PNG captures visually verified.

The documentation and API schemas for KAN-419 are fully verified, robust, and approved for production release.
