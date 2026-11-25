# Forensic QA Reality-Checker Handover Packet

**Ticket:** KAN-417 (`[SLICE-3-P2][KB-MCP-OAUTH-SIMPLIFY]`)  
**Parent Epic:** KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)  
**Author:** b-kan417 (Security and UX Systems Architect)  
**Branch:** `feat/KAN-417-slice3-mcp-simplify`  
**Base Commit:** `8c6a77e2`  
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan417-b61a8c15`  

---

## 1. Executive Summary & Zero-Mutation Boundary

This packet provides forensic verification evidence for ticket **KAN-417 (Phase 2: Simplify MCP Access, Workload OIDC & OAuth 2.1 Governance UI + Backend Wiring)**.

- **Zero Database Migrations:** 100% of existing schema and Alembic revision chain on `main` is preserved without any new database migrations or DDL mutations.
- **Strict Quality Invariants:** Zero linter warnings, safe typing (Mypy 808 files, TypeScript 0 errors), zero act(...) warnings, `>=95%` branch coverage on all touched modules, and zero Unicode em-dash or en-dash characters.
- **No Test Modifications to Conceal Bugs:** All existing regression assertions and cryptographic boundaries (`MAX_STATE_LEN = 4096`, PKCE S256 requirement for public clients, rejection of `client_credentials`) remain strictly enforced.

---

## 2. Inventory of Implemented Changes

### 2.1 Frontend Changes
1. **`kanban/web/src/features/settings/McpAccessStudio.tsx`:**
   - Streamlined Question 2 with segmented role selector pills (`role-pill-personal`, `role-pill-service_bot`) and scope selector pills (`scope-tier-pill-project`, `scope-tier-pill-workspace`, `scope-tier-pill-global`).
   - Synced pills bidirectionally with the existing accessible select element (`mint-key-scope-type-select`), preserving all accessibility and form test contracts.
   - Added workspace maximum MCP key TTL policy clamping: when `maxKeyTtlDays` is set, displays `policy-ttl-badge` and omits "Unlimited" option.
   - Retained dynamic active overrides count indicator on `AdvancedSection`.
2. **`kanban/web/src/features/settings/ConnectOAuthAppModal.tsx` & `ConnectOAuthAppModal.css`:**
   - Enforced responsive word-wrapping (`overflow-wrap: anywhere; word-break: break-all;`) on `.kb-connect-oauth-url` so all 5 viewports display without clipping or horizontal overflow.
   - Provided dynamic fallback to workspace scope when target project is not selected.
   - Retained client snippet tabs for Gemini App, Claude Code, Cursor, Antigravity, and Codex.
3. **`kanban/web/src/features/settings/McpUnifiedStudio.tsx` (`WorkloadFederationSection`):**
   - Added 1-click Workload OIDC preset buttons (`preset-github-actions`, `preset-gitlab-ci`, `preset-kubernetes`) pre-populating canonical HTTPS issuer URLs, audiences, and subject glob patterns.
   - Wired `useAal2DirtyKeepalive(isDirty)` to keep WebSudo session elevated during policy authoring.
4. **`kanban/web/src/features/oauth/OAuthClientGovernanceStudio.tsx`:**
   - Added status filter pills (All, Active, Suspended, Revoked).
   - Wired dead controls in `AdvancedSection` (`toggle-pkce-s256`, `input-access-token-ttl`, `input-grant-types`) into `handleRegisterSubmit`.
5. **`kanban/web/src/features/oauth/DeviceActivatePage.tsx`:**
   - Auto-formatting and hyphen insertion at 4 characters (`XXXX-XXXX`) for Base20 consonant codes (`BCDFGHJKLMNPQRSTVWXZ`).
   - Real-time character guide warning banner and step-up confirmation gate.

### 2.2 Backend Changes
1. **`kanban/api/v1/oauth.py`:**
   - Extended `AdminOAuthClientCreateRequest` to accept `pkce_enforce: bool`, `access_token_ttl: int`, and `grant_types: list[str]`.
   - Rejects `client_credentials`, mandates PKCE S256 for public clients, and bounds token TTL (60-86400s).
2. **`kanban/api/v1/admin/workload_identities.py`:**
   - Added field validators requiring HTTPS scheme on `issuer`, compiled glob/regex validation on `subject_pattern`, and capped `max_ttl_seconds <= 86400`.
3. **`kanban/api/v1/mcp_keys.py` & `kanban/api/v1/admin/mcp_keys.py`:**
   - Added `validate_allowed_cidrs` using `ipaddress.ip_network(..., strict=False)`.
   - Allowed capability mask bounds `0 <= capability_mask <= 255`.
4. **`kanban/security/mcp_keys.py`:**
   - Updated capability mask bound check to `0 <= capability_mask <= MAX_CAPABILITY_MASK`.

---

## 3. Replication & Verification Instructions

Execute the following commands from the workspace root to reproduce all verification results:

```bash
# 1. Run backend unit test suites (118 tests: 53 core slice + 58 oauth flow + 7 parity; 95% on admin/mcp_keys.py, 98% on workload_identities.py, 97% on mcp_keys.py, 95% on oauth.py, 95% on mcp/app.py)
uv run python3 -c "import numpy, sys, pytest; sys.exit(pytest.main(['kanban/tests/oauth/test_device_flow.py', 'kanban/tests/oauth/test_oauth_coverage.py', 'kanban/tests/oauth/test_oauth_flow.py', 'kanban/tests/oauth/test_oauth_unit.py', 'kanban/tests/api/test_unified_mcp_keys_api.py', 'kanban/tests/api/test_admin_mcp_keys_api.py', 'kanban/tests/auth/test_workload_oidc_exchange.py', 'mcp/tests/test_workload_jwt_auth.py', 'mcp/tests/test_mcp_capability_mask_and_cidr.py', 'kanban/tests/test_feature_comparison_parity.py']))"

# 2. Run frontend Vitest test suites (133 tests with 95.96% branch coverage and 0 act(...) warnings)
COVERAGE_INCLUDE="src/features/settings/McpAccessStudio.tsx,src/features/settings/ConnectOAuthAppModal.tsx,src/features/settings/McpUnifiedStudio.tsx,src/features/oauth/OAuthClientGovernanceStudio.tsx,src/features/oauth/DeviceActivatePage.tsx" \
pnpm --dir kanban/web exec vitest run --coverage \
  src/features/settings/__tests__/McpAccessStudio.test.tsx \
  src/features/settings/__tests__/ConnectOAuthAppModal.test.tsx \
  src/features/oauth/__tests__/OAuthClientGovernanceStudio.test.tsx \
  src/features/oauth/__tests__/DeviceActivatePage.test.tsx \
  src/features/settings/__tests__/McpUnifiedStudio.test.tsx

# 3. Run static linters and build checks
uv run ruff check kanban/ mcp/
uv run mypy kanban/ mcp/
python3 scripts/check_no_dashes.py --all
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build

# 4. Verify integrity checksums
cd docs/qa/KAN-417 && sha256sum -c changed-files-manifest.txt
```

---

## 4. Visual Evidence & Screenshots

All 5 viewports were captured and verified via Playwright in `docs/qa/KAN-417/screenshots/`:
- `01-desktop-1440x900-light-mcp-mint-modal-segmented-selectors.png`
- `02-desktop-1440x900-dark-connect-oauth-modal.png`
- `03-desktop-1024x768-workload-oidc-presets.png`
- `04-tablet-portrait-768x1024-oauth-governance-advanced.png`
- `05-mobile-portrait-390x844-device-activate.png`

---

## 5. Specialist Audits

- **API Specialist Review:** `docs/qa/KAN-417/api-specialist-review.md` (APPROVED by `@api-spec`)
- **UI Specialist Review:** `docs/qa/KAN-417/ui-specialist-review.md` (APPROVED by `@ui-spec`)
