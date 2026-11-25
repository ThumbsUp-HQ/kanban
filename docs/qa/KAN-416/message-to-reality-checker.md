# Integration Reality-Checker Briefing: KAN-416 (Rev 2 - Forensic Correction)

- **Ticket**: KAN-416 (`[SLICE-3-P1][KB-MCP-OAUTH-AUDIT]` Phase 1: Read-Only Setting Inventory & Simplification Audit for Slice 3)
- **Parent Epic**: KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)
- **Branch**: `fix/p1-audits-rc2` (consolidated Round 2 on `main` at `71b847ba`, base branch `fix/KAN-416-rc1`)
- **Review Status**: Dual Specialist Review (`api-spec` and `ui-spec`) APPROVED; Reality Checker Gate: Pending Clean-Room Reality-Checker re-audit
- **Deliverable Path**: `docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md`

## Summary of Completed Technical Actions

1. **Comprehensive Setting-by-Setting Inventory Table**:
   - Inspected 100% of UI controls, labels, options, defaults, validation rules, and backend bindings across all Slice-3 files:
     - Frontend (6 files):
       - `kanban/web/src/features/settings/McpAccessStudio.tsx`
       - `kanban/web/src/features/settings/McpUnifiedStudio.tsx`
       - `kanban/web/src/features/settings/ConnectOAuthAppModal.tsx`
       - `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`
       - `kanban/web/src/features/oauth/OAuthClientGovernanceStudio.tsx`
       - `kanban/web/src/features/oauth/DeviceActivatePage.tsx`
     - Backend (6 files):
       - `kanban/api/v1/oauth.py`
       - `kanban/api/v1/mcp_keys.py`
       - `kanban/api/v1/auth_mcp_keys.py`
       - `kanban/api/v1/admin/mcp_keys.py`
       - `kanban/api/v1/admin/workload_identities.py`
       - `mcp/app.py`
   - Structured table with columns: `Screen/Drawer | Setting Label and Key | Options / Type | 1-Sentence Plain-English Meaning | Backend Wiring Status | Disposition`.
   - Exact Disposition Counts (1:1 Parity with `01-audit-and-cuts.md`):
     - Total Cataloged Settings: 77
     - KEEP: 62
     - SIMPLIFY: 6
     - MOVE_TO_ADVANCED: 9

2. **Forensic Source Parity Adjustments**:
   - `McpAccessStudio.tsx`:
     - Replaced hallucinated `/workspaces/{ws}/mcp-keys` routes with actual backend routes `/api/v1/mcp-keys` (`mcp_keys.py`) and `/api/v1/admin/mcp-keys` (`admin/mcp_keys.py`).
     - Corrected scope filter pills to `scope-pill-all`, `scope-pill-project`, `scope-pill-workspace`, `scope-pill-server` + `scope-project-select`.
     - Accurately noted that the Mint MCP Key modal already implements a 4-step question hierarchy (`mint-label-input`, `mint-key-scope-type-select` / `mint-project-input`, `mint-surface-select` / `mint-expiry-select` / `advanced-capability-restrictions`, and `mint-key-summary`).
     - Corrected `mint-project-input` (`list="mint-project-datalist"`), `capability-bits-grid` (`cap-bit-1` through `cap-bit-128`), and `mint-allowed-cidrs-input`.
     - Removed non-existent `copy-prefix-btn` and `inspect-key-btn` (only `revoke-btn-*` exists in `McpAccessStudio.tsx`).
     - Added Connected OAuth Apps controls (`disconnect-btn-*`, `enter-device-code-btn`) and `mcp-copy-llms-prompt-btn`.
   - `ConnectOAuthAppModal.tsx`:
     - Corrected admin surface scopes to fine-grained individual verbs (`admin:read`, `admin:write`, `admin:destructive`, NOT wildcard `admin:*`).
     - Added `copy-resource-url-btn`, `copy-rfc8414-url-btn`, `copy-snippet-btn`, and `modal-enter-device-code-btn`.
   - `McpUnifiedStudio.tsx`:
     - Added `edit-policy-btn-*` action.
     - Confirmed Workload Identity Federation lives in `McpUnifiedStudio.tsx` (`WorkloadFederationSection`), NOT in `OAuthClientGovernanceStudio.tsx`.
     - Noted that `create_workload_policy` in `admin/workload_identities.py` does not currently validate OIDC discovery or compile regex/glob patterns on `POST`.
   - `OAuthClientGovernanceStudio.tsx`:
     - Corrected exact `data-testid` attributes: `input-client-name`, `input-redirect-uris`, `select-client-type`, `select-auth-method`, `toggle-pkce-s256`, `input-access-token-ttl`, `input-grant-types`, `approve-btn-*`, `suspend-btn-*`, `revoke-btn-*`, `inspect-btn-*`, `edit-uris-btn-*`, `input-edit-redirect-uris`.
     - Accurately documented that `toggle-pkce-s256`, `input-access-token-ttl`, and `input-grant-types` are ALREADY inside `<AdvancedSection data-testid="advanced-oauth-parameters">` AND are currently dead/unwired UI controls (not sent by `handleRegisterSubmit` and rejected by `AdminOAuthClientCreateRequest` `extra="forbid"`), flagging them honestly for `KAN-417` backend and frontend wiring.
     - Removed already-implemented items (auto-selecting `none` for `public` client type, and one-time secret display drawer `registered-client-secret`) from `KAN-417` pending tasks.
   - `DeviceActivatePage.tsx` & `oauth.py`:
     - Corrected Base20 consonant character set definition (`BASE20_CHARS = 'BCDFGHJKLMNPQRSTVWXZ'`), noting it includes `L` and excludes vowels (`A, E, I, O, U`) and all digits (`0-9`).
     - Corrected device endpoint in `oauth.py` to `POST /oauth/device/authorize` (RFC 8628 Section 3.1), NOT `/oauth/device/code`.
     - Documented `POST /oauth/token` supported grant types (`authorization_code`, `refresh_token`, `device_code`, and `token-exchange`), with strictly NO `client_credentials`.

3. **Verification and Quality Gates**:
   - Zero Unicode em/en-dashes verified: `python3 scripts/check_no_dashes.py docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md` (EXIT 0) and `python3 scripts/check_no_dashes.py --all` (EXIT 0) recorded in `docs/qa/KAN-416/build-check.txt`.
   - 100% of cited repository file paths verified on disk (19/19 files) in `docs/qa/KAN-416/unit-test-results.txt`.
   - Regenerated `docs/qa/KAN-416/git-diff.patch` via `git diff e975ab96 -- docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md`.
   - Manifest updated in `docs/qa/KAN-416/changed-files-manifest.txt` including `01-audit-and-cuts.md` and verified with `sha256sum -c`.
   - Zero production source-code mutations (100% read-only Phase 1 boundary).
   - Zero `reality-checker-report.md` drafted (reserved exclusively for Clean-Room reality-checker).
