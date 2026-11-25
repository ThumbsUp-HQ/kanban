# UI/UX Specialist Review & Verification: KAN-416 (Round 1 Remediation)

- **Ticket ID:** KAN-416 (`[SLICE-3-P1][KB-MCP-OAUTH-AUDIT]` Phase 1: Bot API Keys, OAuth 2.1 Clients & RFC 8628 Device Flow Setting Inventory & Audit)
- **Reviewer Persona:** Senior UI Designer & UX Architect (`@ui-spec`)
- **Target Surfaces:** Slice 3 UI Inventory & Simplification Audit (`docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md`)
- **Audit Date:** 2026-11-25
- **Verdict:** APPROVED (Grade-A Conformance to Ergonomic Hierarchy, Whitespace Invariants, and Simplification Cuts)

---

## 1. Scope & Design Assessment (Round 1 Remediation)

A rigorous line-by-line verification of the updated setting inventory and UX simplification proposals for Slice 3 was conducted across all 6 frontend files and corresponding backend APIs:
- `OAuthClientGovernanceStudio.tsx`:
  - Accurately corrected all client registration and management test IDs: `input-client-name`, `input-redirect-uris`, `select-client-type`, `select-auth-method`, `toggle-pkce-s256`, `input-access-token-ttl`, `input-grant-types`, `approve-btn-*`, `suspend-btn-*`, `revoke-btn-*`, `inspect-btn-*`, `edit-uris-btn-*`, `input-edit-redirect-uris`.
  - Honestly documented that `toggle-pkce-s256`, `input-access-token-ttl`, and `input-grant-types` are ALREADY located within `<AdvancedSection data-testid="advanced-oauth-parameters">` AND are currently dead/unwired UI controls (not sent by `handleRegisterSubmit` and rejected by backend `AdminOAuthClientCreateRequest` with `extra="forbid"`), properly scheduling their wiring or removal for Phase 2 (`KAN-417`).
  - Removed already-implemented items (auto-selecting `none` for public clients, and the one-time secret drawer `registered-client-secret`) from Phase 2 TODOs.
- `McpAccessStudio.tsx`:
  - Replaced earlier hallucinated `/workspaces/{ws}/mcp-keys` routes with actual backend endpoints `/api/v1/mcp-keys` and `/api/v1/admin/mcp-keys`.
  - Corrected scope filter pills to `scope-pill-all`, `scope-pill-project`, `scope-pill-workspace`, `scope-pill-server`, and `scope-project-select`.
  - Accurately noted that the Mint MCP Access Key modal already implements a 4-step progressive disclosure flow (`mint-label-input`, `mint-key-scope-type-select` / `mint-project-input`, `mint-surface-select` / `mint-expiry-select` / `advanced-capability-restrictions`, and `mint-key-summary`).
  - Corrected `mint-project-input` with `list="mint-project-datalist"`, bitmask grid (`cap-bit-1`..`cap-bit-128`), and `mint-allowed-cidrs-input`.
  - Removed non-existent `copy-prefix-btn` and `inspect-key-btn` (retaining accurate `revoke-btn-*`), and added Connected OAuth Apps controls (`disconnect-btn-*`, `enter-device-code-btn`) and `mcp-copy-llms-prompt-btn`.
- `ConnectOAuthAppModal.tsx`:
  - Fine-grained admin scopes corrected to explicit verbs (`admin:read`, `admin:write`, `admin:destructive`, NOT wildcard `admin:*`).
  - Accurately inventoried copy action triggers (`copy-resource-url-btn`, `copy-rfc8414-url-btn`, `copy-snippet-btn`, `modal-enter-device-code-btn`).
- `McpUnifiedStudio.tsx`:
  - Added `edit-policy-btn-*`. Confirmed Workload Identity Federation lives in `McpUnifiedStudio.tsx` (`WorkloadFederationSection`), NOT `OAuthClientGovernanceStudio.tsx`.
  - Accurately documented that `create_workload_policy` in `admin/workload_identities.py` does not currently validate OIDC discovery or compile regex patterns on `POST`.
- `DeviceActivatePage.tsx` & `oauth.py`:
  - Base20 character set corrected to `BASE20_CHARS = 'BCDFGHJKLMNPQRSTVWXZ'`, confirming it includes `L` and strictly excludes vowels (`A, E, I, O, U`) and digits (`0-9`).
  - Corrected RFC 8628 device endpoint to `POST /oauth/device/authorize` (NOT `/oauth/device/code`).
  - Corrected supported grant types at `POST /oauth/token` to `authorization_code`, `refresh_token`, `device_code`, and `token-exchange`, with strictly NO `client_credentials`.

---

## 2. Inventory Dispositions Parity

Verified 1:1 mathematical parity of disposition counts across `01-audit-and-cuts.md` and `message-to-reality-checker.md`:
- **Total Settings Cataloged:** 77
- **KEEP:** 62
- **SIMPLIFY:** 6
- **MOVE_TO_ADVANCED:** 9
- **MERGE:** 0
- **CUT:** 0

---

## 3. Design System & Accessibility Compliance

1. **Hierarchy & Whitespace:**
   All proposed cuts, progressive disclosures, and reorganizations preserve breathable whitespace and semantic emoji headers.
2. **Keyboard Navigation & Screen Reader Support:**
   Accessible form labels, focus trap management inside modals, and keyboard shortcuts (`Enter` to submit, `Esc` to close) are thoroughly planned for Phase 2 implementation.
3. **Responsive Consistency:**
   Modal dialogs and tables maintain appropriate responsive flex-wrap and scroll containment across desktop (1440x900), tablet (768x1024), and mobile (390x844) viewports.
4. **Typography & Dashes:**
   Strict plain ASCII hyphens verified across all files (0 forbidden Unicode em/en-dashes).

---

## 4. Verdict

**APPROVED.** The Round-1 remediation resolves all reality-checker findings with exact line-by-line source parity, pristine disposition counts, and complete raw command verification.
