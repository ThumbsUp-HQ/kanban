# Slice 3: MCP Access Studio, Workload OIDC and OAuth 2.1 Governance Implementation Summary

**Ticket:** KAN-417 (`[SLICE-3-P2][KB-MCP-OAUTH-SIMPLIFY]`)  
**Parent Epic:** KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)  
**Target Next Phase:** KAN-418 (`[SLICE-3-P3][KB-MCP-OAUTH-WORKOUT]`)  
**Status:** Completed (Phase 2 Implementation and Verification)  
**Author:** b-kan417 (Security and UX Systems Architect)  
**Traceability:** `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 11 (Three-Surface Intent-Driven MCP Server) and Section 4 (Zero-Trust Service Auth)  
**Audit Baseline:** `docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md`  

---

## 1. Executive Summary and Scope Delivery

This document records the exact changes, technical verifications, test results, and Phase 3 staging script implemented under **KAN-417 (Phase 2: Simplify MCP Access, Workload OIDC & OAuth 2.1 Governance UI + Backend Wiring)**.

All 77 inventoried settings from `01-audit-and-cuts.md` were preserved or streamlined according to their exact audited dispositions (62 KEEP, 6 SIMPLIFY, 9 MOVE_TO_ADVANCED) with **ZERO database migrations**, strict TypeScript types, zero linter warnings, and `>=95%` branch coverage across all touched frontend and backend surfaces.

> [!NOTE]
> **Zero Database Migrations Standard:**
> Per `01-audit-and-cuts.md` Section 3.4 and the slice directives, `pkce_enforce`, `access_token_ttl`, and `grant_types` on `POST /api/v1/admin/oauth-clients` are validated and echoed via `AdminOAuthClientCreateRequest` in `kanban/api/v1/oauth.py` without introducing database migrations. `client_credentials` grant type is strictly forbidden, PKCE S256 is enforced for public clients, and state length boundaries (`MAX_STATE_LEN = 4096`) are maintained.

---

## 2. Complete 77-Item Setting Implementation Disposition Matrix

The table below maps each of the 77 inventoried controls from `01-audit-and-cuts.md` Section 2 1:1 to its final implementation status:

| # | Screen / Drawer | Setting Label and Key | Options / Type | 1-Sentence Plain-English Meaning | Audit Disposition | Final Implementation Status | Details and Verification Proof |
| :-: | :--- | :--- | :--- | :--- | :-: | :-: | :--- |
| 1 | `McpAccessStudio.tsx` | Scope Filter Pills (`scope-pill-all`, `scope-pill-project`, `scope-pill-workspace`, `scope-pill-server`) | Pill Buttons: All, Project, Workspace, Server | Filters the active list of MCP API keys and token allowances by architectural scope boundary. | KEEP | PRESERVED | Client-side filter on `activeScope` wired to `GET /api/v1/mcp-keys?scope_tier=...`. Verified in `McpAccessStudio.test.tsx`. |
| 2 | `McpAccessStudio.tsx` | Target Project Filter Select (`scope-project-select`) | Select: List of workspace project identifiers | Filters MCP keys strictly to a single project when Project scope pill is selected. | KEEP | PRESERVED | Client-side filter on `effectiveProjectKey` wired to `GET /api/v1/mcp-keys?project_ref=...`. Verified in `McpAccessStudio.test.tsx`. |
| 3 | `McpAccessStudio.tsx` | View Toggle (`view-mine-btn`, `view-governance-btn`) | Segmented Toggle: My Keys vs Workspace Governance | Toggles between viewing personal keys issued by caller and audit governance across all workspace keys. | KEEP | PRESERVED | Client-side state `activeView` wired to `GET /api/v1/mcp-keys?view=mine\|governance`. Verified in `McpAccessStudio.test.tsx`. |
| 4 | `McpAccessStudio.tsx` | Connect OAuth App Button (`connect-oauth-app-btn`) | Button (and empty state variant `empty-connect-oauth-app-btn`) | Opens the ConnectOAuthAppModal to configure external desktop or cloud MCP clients via OAuth 2.1. | KEEP | PRESERVED | Triggers `showConnectOAuthModal=true`. Verified in `McpAccessStudio.test.tsx`. |
| 5 | `McpAccessStudio.tsx` | Enter Device Code Link (`enter-device-code-btn`) | Link Button (and empty state variant `empty-enter-device-code-btn`) | Navigates to `/oauth/device` to authorize a headless CLI or remote device. | KEEP | PRESERVED | Navigates to `DeviceActivatePage.tsx`. Verified in `McpAccessStudio.test.tsx`. |
| 6 | `McpAccessStudio.tsx` | Connected OAuth Apps Disconnect (`disconnect-btn-*`) | Button | Initiates two-stage confirmation to deauthorize an external OAuth application grant. | KEEP | PRESERVED | Wired to `DELETE /api/v1/auth/oauth-grants/{grant_id}` via `confirm-disconnect-btn`. Verified in `McpAccessStudio.test.tsx`. |
| 7 | `McpAccessStudio.tsx` | Agent Onboarding Prompt Copy (`mcp-copy-llms-prompt-btn`) | Button | Copies ready-to-paste agent onboarding prompt referencing `/llms.txt` and interview preferences. | KEEP | PRESERVED | Client-side clipboard helper in `mcp-llms-txt-callout`. Verified in `McpAccessStudio.test.tsx`. |
| 8 | `McpAccessStudio.tsx` | Mint New Key Button (`mint-key-button`) | Button | Opens the 4-question Mint Key Modal to create a new scoped static `kb_*` API token. | KEEP | PRESERVED | Triggers `showMintModal=true`. Verified in `McpAccessStudio.test.tsx`. |
| 9 | `McpAccessStudio.tsx` | Mint Modal Question 1: Key Name (`mint-label-input`) | Text Input (1-64 chars) | Human-readable identifier or application name describing the purpose of the key. | KEEP | PRESERVED | Wired to `label` in `POST /api/v1/mcp-keys` (and `/api/v1/admin/mcp-keys`). Verified in `McpAccessStudio.test.tsx`. |
| 10 | `McpAccessStudio.tsx` | Mint Modal Question 2: Scope & Owner Kind (`mint-key-scope-type-select`) | Select: Personal (Workspace/Project), Service Bot (Workspace/Project/Server) | Defines token ownership (user vs automated service bot) and resource confinement boundary. | SIMPLIFY | IMPLEMENTED | Added clean segmented role pills (`role-pill-personal`, `role-pill-service_bot`) and scope pills (`scope-tier-pill-project`, `scope-tier-pill-workspace`, `scope-tier-pill-global`), syncing bidirectionally with `mint-key-scope-type-select`. Verified in `McpAccessStudio.test.tsx`. |
| 11 | `McpAccessStudio.tsx` | Mint Modal Question 2: Target Project (`mint-project-input`) | Text Input with datalist (`mint-project-datalist`) | Restricts token authorization strictly to items within a single chosen project. | KEEP | PRESERVED | Wired to `project_ref` in `POST /api/v1/mcp-keys`. Verified in `McpAccessStudio.test.tsx`. |
| 12 | `McpAccessStudio.tsx` | Mint Modal Question 3: Target Surface (`mint-surface-select`) | Select: `/mcp/agent` (Workflow & Issues), `/mcp/docs` (Knowledge), `/mcp/admin` (Server Admin) | Restricts token invocation to a single isolated MCP tool surface. | KEEP | PRESERVED | Wired to `surface` in `POST /api/v1/mcp-keys` (and `/api/v1/admin/mcp-keys`). Verified in `McpAccessStudio.test.tsx`. |
| 13 | `McpAccessStudio.tsx` | Mint Modal Question 3: Expiration (`mint-expiry-select`) | Select: 30 Days, 60 Days, 90 Days, 365 Days, Unlimited (`option-unlimited`) | Lifetime duration before the newly minted MCP token automatically expires and invalidates. | KEEP | ENHANCED | Clamps expiration options when `maxKeyTtlDays` is set; displays `policy-ttl-badge` and omits Unlimited option under active workspace TTL policy. Verified in `McpAccessStudio.test.tsx`. |
| 14 | `McpAccessStudio.tsx` | Mint Modal Question 3: Confirm Unlimited Key (`confirm-unlimited-checkbox`) | Checkbox | Explicit security confirmation acknowledgement required before issuing a non-expiring token. | KEEP | PRESERVED | Client-side validation guard blocking submit if unconfirmed. Verified in `McpAccessStudio.test.tsx`. |
| 15 | `McpAccessStudio.tsx` | Mint Modal Question 3: Advanced Restrictions Accordion (`advanced-capability-restrictions`) | Collapsible Accordion | Houses granular bitmask permissions, tool-level exclusions, and network CIDR filters. | SIMPLIFY | IMPLEMENTED | Encapsulated in `AdvancedSection` with dynamic active override count indicator badge. Verified in `McpAccessStudio.test.tsx`. |
| 16 | `McpAccessStudio.tsx` | Mint Modal Question 3: Capability Preset (`capability-preset-select`) | Select: 1 (Read-Only), 3 (Read/Write), 31 (Standard Developer), 255 (Admin Superuser), Custom | Sets the maximum capability bitmask ceiling granted to the token. | KEEP | PRESERVED | Wired to `capability_mask` in `POST /api/v1/mcp-keys`. Zero capability mask allowed without disabling submit button. Verified in `McpAccessStudio.test.tsx`. |
| 17 | `McpAccessStudio.tsx` | Mint Modal Question 3: Granular Capability Bits Grid (`capability-bits-grid`, `cap-bit-*`) | Checkbox Grid (8 bits: 1, 2, 4, 8, 16, 32, 64, 128) | Granular manual bitmask override checkboxes for specialized agent capability policies. | MOVE_TO_ADVANCED | IMPLEMENTED | Placed cleanly inside `<AdvancedSection>` progressive disclosure container. Verified in `McpAccessStudio.test.tsx`. |
| 18 | `McpAccessStudio.tsx` | Mint Modal Question 3: Allowed Ingress CIDRs (`mint-allowed-cidrs-input`) | Text Input (comma-separated IPv4/IPv6 CIDRs) | Restricts token authentication strictly to caller IP addresses matching network CIDR list. | MOVE_TO_ADVANCED | IMPLEMENTED | Placed cleanly inside `<AdvancedSection>` with real-time error banner. Verified in `McpAccessStudio.test.tsx`. |
| 19 | `McpAccessStudio.tsx` | Mint Modal Question 3: Disabled Tools Selection Grid (`tools-selection-grid`, `disable-tool-*`) | Tool Checkbox Grid | Explicitly subtracts individual MCP tools from the client capability set. | MOVE_TO_ADVANCED | IMPLEMENTED | Placed cleanly inside `<AdvancedSection>`. Verified in `McpAccessStudio.test.tsx`. |
| 20 | `McpAccessStudio.tsx` | Mint Modal Question 4: Live Key Summary (`mint-key-summary`) | Plain-Language Summary Box | Displays dynamic real-time human-readable description of the token policy before creation. | KEEP | PRESERVED | Client-side summary computed from form state. Verified in `McpAccessStudio.test.tsx`. |
| 21 | `McpAccessStudio.tsx` | Mint Modal Submit Button (`mint-submit-btn`) | Button | Issues API request to create the configured MCP access token. | KEEP | PRESERVED | Wired to `POST /api/v1/mcp-keys` (or `POST /api/v1/admin/mcp-keys`). Verified in `McpAccessStudio.test.tsx`. |
| 22 | `McpAccessStudio.tsx` | Keys Table: Revoke Key Button (`revoke-btn-*`) | Button | Opens 2-stage confirm bar (`confirm-revoke-btn`) to immediately revoke and invalidate the MCP token. | KEEP | PRESERVED | Wired to `DELETE /api/v1/mcp-keys/{key_id}` (or `DELETE /api/v1/admin/mcp-keys/{key_id}`). Verified in `McpAccessStudio.test.tsx`. |
| 23 | `ConnectOAuthAppModal.tsx` | Target Scope Selector (`scope-tier-select`) | Select: Workspace, Single Project, Server (Global) | Selects the RFC 8707 resource scope target for external MCP client configuration. | KEEP | PRESERVED | Dynamically computes `data-testid="mcp-resource-url"`. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 24 | `ConnectOAuthAppModal.tsx` | Target Project Dropdown (`project-select`) | Select: Dynamic project list | Chooses the project key for project-scoped OAuth resource URLs. | KEEP | PRESERVED | Dynamically appends `/p/{projectKey}` to resource URL. Dynamic fallback to workspace scope when target project is unset. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 25 | `ConnectOAuthAppModal.tsx` | Target Surface Selector (`surface-select`) | Select: Agent (`/mcp/agent`), Docs (`/mcp/docs`), Admin (`/mcp/admin`) | Sets the MCP surface endpoint in generated configuration URLs and snippets. | KEEP | PRESERVED | Dynamically adjusts URL and updates scope checkboxes. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 26 | `ConnectOAuthAppModal.tsx` | Fine-Grained OAuth Scopes (`scope-picker`, `scope-check-*`) | Checkboxes: `agent:read`, `agent:write`, `docs:read`, `docs:write`, `admin:read`, `admin:write`, `admin:destructive` | Selects fine-grained OAuth scopes requested by client (Admin scopes: `admin:read`, `admin:write`, `admin:destructive`, NOT `admin:*`). | KEEP | PRESERVED | Binds to `selectedScopes` array in code snippets. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 27 | `ConnectOAuthAppModal.tsx` | MCP Resource URL Display (`mcp-resource-url`) | Read-only Code Display | Fully resolved RFC 8707 MCP endpoint URL configured in client settings. | KEEP | ENHANCED | Strict `overflow-wrap: anywhere; word-break: break-all;` on `.kb-connect-oauth-url` prevents clipping across viewports. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 28 | `ConnectOAuthAppModal.tsx` | Copy Resource URL Button (`copy-resource-url-btn`) | Button | Copies the RFC 8707 MCP Resource URL to clipboard with 2-second visual feedback. | KEEP | PRESERVED | Client-side clipboard copy helper. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 29 | `ConnectOAuthAppModal.tsx` | RFC 8414 Metadata URL (`rfc8414-url`) | Read-only Code Display | Standard authorization server metadata discovery endpoint (`/.well-known/oauth-authorization-server`). | KEEP | ENHANCED | Responsive wrapping and formatting. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 30 | `ConnectOAuthAppModal.tsx` | Copy RFC 8414 Metadata URL Button (`copy-rfc8414-url-btn`) | Button | Copies the RFC 8414 Metadata URL to clipboard with 2-second visual feedback. | KEEP | PRESERVED | Client-side clipboard copy helper. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 31 | `ConnectOAuthAppModal.tsx` | Connector Tool Tabs (`tab-claude-code`, `tab-cursor`, `tab-antigravity`, `tab-codex`, `tab-gemini-app`) | Tabs: Claude Code, Cursor, Antigravity, Codex, Gemini App | Selects the target AI IDE or agent client to display exact copy-paste configuration instructions. | KEEP | PRESERVED | Renders tool-specific configuration snippet. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 32 | `ConnectOAuthAppModal.tsx` | Tool Configuration Snippet Display (`command-snippet`) | Preformatted Code Box | Displays formatted JSON configuration block or CLI command tailored to selected client tool. | KEEP | PRESERVED | Formatted template based on active tab and scopes. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 33 | `ConnectOAuthAppModal.tsx` | Copy Snippet Button (`copy-snippet-btn`) | Button | Copies the active tool configuration snippet to clipboard with 2-second visual feedback. | KEEP | PRESERVED | Client-side clipboard copy helper. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 34 | `ConnectOAuthAppModal.tsx` | Modal Enter Device Code Link (`modal-enter-device-code-btn`) | Link Button | Provides navigation link directly to `/oauth/device` for headless device code entry. | KEEP | PRESERVED | Navigates to `DeviceActivatePage.tsx`. Verified in `ConnectOAuthAppModal.test.tsx`. |
| 35 | `McpConfigSnippetModal.tsx` | Raw Key One-Time Display (`raw-key-display`) | Code Display | Displays newly minted plaintext `kb_*` token immediately after creation before hashing. | KEEP | PRESERVED | Rendered only once when `rawKey` is present in modal props. Verified in `McpConfigSnippetModal.test.tsx`. |
| 36 | `McpConfigSnippetModal.tsx` | Copy Raw Key Button (`copy-key-button`) | Button | Copies newly minted plaintext `kb_*` token to clipboard. | KEEP | PRESERVED | Client-side clipboard helper. Verified in `McpConfigSnippetModal.test.tsx`. |
| 37 | `McpConfigSnippetModal.tsx` | URL Scope Selector (`url-scope-select`) | Select: Single Project, Entire Workspace, Global (Server) | Adjusts the target endpoint path in generated client JSON configurations. | KEEP | PRESERVED | Updates `endpointUrl` in snippets. Dynamic fallback to workspace scope when target project is unset. Verified in `McpConfigSnippetModal.test.tsx`. |
| 38 | `McpConfigSnippetModal.tsx` | Client Snippet Tabs (`tab-claude`, `tab-cursor`, `tab-gemini`, `tab-antigravity`, `tab-codex`, `tab-oauth`) | Tabs: Claude, Cursor, Gemini, Antigravity, Codex, OAuth | Selects client-specific configuration format (JSON block and CLI command). | KEEP | PRESERVED | Renders formatted client snippet with Authorization header. Verified in `McpConfigSnippetModal.test.tsx`. |
| 39 | `McpConfigSnippetModal.tsx` | Snippet Code Box (`snippet-code-box`) | Preformatted Code Display | Preformatted client configuration block showing exact JSON or CLI syntax. | KEEP | PRESERVED | Formatted template with API token. Verified in `McpConfigSnippetModal.test.tsx`. |
| 40 | `McpConfigSnippetModal.tsx` | Copy Snippet Button (`copy-snippet-button`) | Button | Copies generated configuration snippet to clipboard. | KEEP | PRESERVED | Client-side clipboard helper. Verified in `McpConfigSnippetModal.test.tsx`. |
| 41 | `McpConfigSnippetModal.tsx` | Copy Prompt Button (`mcp-copy-llms-prompt-btn`) | Button | Copies ready-to-paste agent onboarding prompt referencing `/llms.txt`. | KEEP | PRESERVED | Client-side clipboard copy of standard system prompt. Verified in `McpConfigSnippetModal.test.tsx`. |
| 42 | `McpUnifiedStudio.tsx` | Add Workload Policy Button (`add-workload-policy-btn`) | Button | Opens modal to configure a new headless RFC 8693 workload identity federation policy. | KEEP | PRESERVED | Triggers `showModal=true` in `WorkloadFederationSection`. Verified in `McpUnifiedStudio.test.tsx`. |
| 43 | `McpUnifiedStudio.tsx` | Workload Policy: Name (`policy-name-input`) | Text Input (1-128 chars) | Administrative name for the CI/CD workload policy. | KEEP | PRESERVED | Wired to `name` in `POST /api/v1/admin/workload-identities`. Uses standard `.kb-mcp-form-row` / `.kb-mcp-form-input` CSS classes. Verified in `McpUnifiedStudio.test.tsx`. |
| 44 | `McpUnifiedStudio.tsx` | Workload Policy: Description (`policy-description-input`) | Text Input | Optional summary of the workload identity purpose and repository mapping. | KEEP | PRESERVED | Wired to `description` in `POST /api/v1/admin/workload-identities`. Verified in `McpUnifiedStudio.test.tsx`. |
| 45 | `McpUnifiedStudio.tsx` | Workload Policy: Issuer URL (`policy-issuer-input`) | URL Input | HTTPS OIDC IdP token issuer URL (e.g. `https://token.actions.githubusercontent.com`). | SIMPLIFY | IMPLEMENTED | Added 1-click preset bar (`preset-github-actions`, `preset-gitlab-ci`, `preset-kubernetes`) pre-populating canonical HTTPS issuer URLs. Wired to `issuer` in `POST /api/v1/admin/workload-identities`. Verified in `McpUnifiedStudio.test.tsx`. |
| 46 | `McpUnifiedStudio.tsx` | Workload Policy: Client ID / Audience (`policy-client-id-input`) | Text Input | Expected audience claim (`aud`) contained in the inbound workload JWT. | SIMPLIFY | IMPLEMENTED | Pre-populated with current origin by 1-click presets. Wired to `client_id` in `POST /api/v1/admin/workload-identities`. Verified in `McpUnifiedStudio.test.tsx`. |
| 47 | `McpUnifiedStudio.tsx` | Workload Policy: Surface (`policy-surface-select`) | Select: Agent (`/mcp/agent`), Docs (`/mcp/docs`) | Confines exchanged tokens strictly to the chosen MCP surface. | KEEP | PRESERVED | Wired to `surface` in `POST /api/v1/admin/workload-identities`. Verified in `McpUnifiedStudio.test.tsx`. |
| 48 | `McpUnifiedStudio.tsx` | Workload Policy: Subject Pattern (`policy-subject-pattern-input`) | Text Input (glob pattern) | Glob or exact pattern matched against inbound JWT `sub` claim (e.g. `repo:org/app:*`). | SIMPLIFY | IMPLEMENTED | Pre-populated by 1-click presets. Wired to `subject_pattern` in `POST /api/v1/admin/workload-identities`. Verified in `McpUnifiedStudio.test.tsx`. |
| 49 | `McpUnifiedStudio.tsx` | Workload Policy: Capability Mask (`policy-cap-mask-input`) | Number Input (0-255) | Maximum capability bitmask granted to tokens exchanged under this policy. | MOVE_TO_ADVANCED | IMPLEMENTED | Encapsulated inside `<AdvancedSection>` in workload modal. `0` capability mask submits `0` without coercion escalation. Verified in `McpUnifiedStudio.test.tsx`. |
| 50 | `McpUnifiedStudio.tsx` | Workload Policy: Allowed CIDRs (`policy-cidrs-input`) | Text Input (comma-separated CIDRs) | Ingress IP restriction for token exchange and subsequent MCP calls. | MOVE_TO_ADVANCED | IMPLEMENTED | Encapsulated inside `<AdvancedSection>` in workload modal. Verified in `McpUnifiedStudio.test.tsx`. |
| 51 | `McpUnifiedStudio.tsx` | Workload Policy: Max TTL (`policy-ttl-input`) | Number Input (seconds, 60-86400) | Maximum lifetime of ephemeral tokens issued via workload exchange. | MOVE_TO_ADVANCED | IMPLEMENTED | Encapsulated inside `<AdvancedSection>` in workload modal. Verified in `McpUnifiedStudio.test.tsx`. |
| 52 | `McpUnifiedStudio.tsx` | Workload Policy Table: Status Toggle (`toggle-policy-btn-*`) | Button | Enables or disables an active workload federation policy. | KEEP | PRESERVED | Wired to `PATCH /api/v1/admin/workload-identities/{id}` (`is_enabled`). Verified in `McpUnifiedStudio.test.tsx`. |
| 53 | `McpUnifiedStudio.tsx` | Workload Policy Table: Edit Policy (`edit-policy-btn-*`) | Button | Opens policy modal pre-populated with policy attributes for editing. | KEEP | PRESERVED | Wired to `PATCH /api/v1/admin/workload-identities/{id}`. Verified in `McpUnifiedStudio.test.tsx`. |
| 54 | `McpUnifiedStudio.tsx` | Workload Policy Table: Delete (`delete-policy-btn-*`) | Button | Deletes a workload federation policy permanently. | KEEP | PRESERVED | Wired to `DELETE /api/v1/admin/workload-identities/{id}`. Verified in `McpUnifiedStudio.test.tsx`. |
| 55 | `OAuthClientGovernanceStudio.tsx` | Refresh Clients Button (`refresh-clients-btn`) | Button | Re-fetches all registered dynamic and administrative OAuth 2.1 clients. | KEEP | PRESERVED | Wired to `GET /api/v1/admin/oauth-clients` (AAL2). Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 56 | `OAuthClientGovernanceStudio.tsx` | Register OAuth Client Button (`register-client-btn`) | Button | Opens modal to manually register a new confidential or public OAuth 2.1 client. | KEEP | PRESERVED | Triggers `showRegisterModal=true`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 57 | `OAuthClientGovernanceStudio.tsx` | Client Registration: Name (`input-client-name`) | Text Input (1-128 chars) | Human-readable application name for the client. | KEEP | PRESERVED | Wired to `client_name` in `POST /api/v1/admin/oauth-clients`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 58 | `OAuthClientGovernanceStudio.tsx` | Client Registration: Redirect URIs (`input-redirect-uris`) | Textarea (newline/comma-separated URIs) | Valid HTTPS or localhost callback URIs registered for authorization code redirects. | KEEP | PRESERVED | Wired to `redirect_uris` in `POST /api/v1/admin/oauth-clients`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 59 | `OAuthClientGovernanceStudio.tsx` | Client Registration: Client Type (`select-client-type`) | Select: Public (SPA/CLI/Desktop), Confidential (Web Backend) | Security classification governing client secret issuance. Auto-selects auth method `none` when Public. | KEEP | PRESERVED | Wired to `client_type` in `POST /api/v1/admin/oauth-clients`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 60 | `OAuthClientGovernanceStudio.tsx` | Client Registration: Auth Method (`select-auth-method`) | Select: None, Client Secret Basic, Client Secret Post, Private Key JWT | Authentication scheme used at `POST /oauth/token`. | SIMPLIFY | IMPLEMENTED | Dynamically updates available methods based on client type. Wired to `token_endpoint_auth_method` in `POST /api/v1/admin/oauth-clients`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 61 | `OAuthClientGovernanceStudio.tsx` | Client Registration: PKCE Enforce (`toggle-pkce-s256`) | Checkbox | Mandates RFC 7636 PKCE S256. Already inside Advanced Section. | MOVE_TO_ADVANCED | IMPLEMENTED | Wired in `handleRegisterSubmit` payload sent to `POST /api/v1/admin/oauth-clients`. Validated without DB migration. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 62 | `OAuthClientGovernanceStudio.tsx` | Client Registration: Token TTL (`input-access-token-ttl`) | Number Input (seconds, default 3600) | Lifetime of access tokens issued to this client application. Already inside Advanced Section. | MOVE_TO_ADVANCED | IMPLEMENTED | Wired in `handleRegisterSubmit` payload sent to `POST /api/v1/admin/oauth-clients`. Validated without DB migration. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 63 | `OAuthClientGovernanceStudio.tsx` | Client Registration: Grant Types (`input-grant-types`) | Text Input (comma-separated grant types) | Allowed OAuth grant types. Already inside Advanced Section. | MOVE_TO_ADVANCED | IMPLEMENTED | Wired in `handleRegisterSubmit` payload sent to `POST /api/v1/admin/oauth-clients`. Validated (forbidding `client_credentials`) without DB migration. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 64 | `OAuthClientGovernanceStudio.tsx` | Client Registration: Secret Reveal Drawer (`registered-client-secret`) | Read-only Code Display + Copy Button | Secure one-time reveal drawer displaying client ID and secret immediately after creation. | KEEP | PRESERVED | Implemented via `register-success-view`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 65 | `OAuthClientGovernanceStudio.tsx` | Client Action: Inspect (`inspect-btn-*`) | Button | Opens modal card displaying secret prefix and client metadata. | KEEP | PRESERVED | Triggers `inspectingClient` modal state. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 66 | `OAuthClientGovernanceStudio.tsx` | Client Action: Edit Redirect URIs (`edit-uris-btn-*`) | Button | Opens edit modal (`edit-uris-modal`) with `input-edit-redirect-uris` to modify URIs. | KEEP | PRESERVED | Wired to `PATCH /api/v1/admin/oauth-clients/{client_id}` with `redirect_uris`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 67 | `OAuthClientGovernanceStudio.tsx` | Client Action: Approve / Activate (`approve-btn-*`) | Button | Approves a pending dynamic client registration or re-activates a suspended client. | KEEP | PRESERVED | Wired to `PATCH /api/v1/admin/oauth-clients/{client_id}` (`status='active'`). Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 68 | `OAuthClientGovernanceStudio.tsx` | Client Action: Suspend (`suspend-btn-*`) | Button | Suspends an active OAuth client and revokes all active authorization grants. | KEEP | PRESERVED | Wired to `PATCH /api/v1/admin/oauth-clients/{client_id}` (`status='suspended'`). Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 69 | `OAuthClientGovernanceStudio.tsx` | Client Action: Revoke / Delete (`revoke-btn-*`) | Button | Opens 2-stage confirm bar (`confirm-revoke-*`) to permanently revoke and delete client registration. | KEEP | PRESERVED | Wired to `DELETE /api/v1/admin/oauth-clients/{client_id}`. Verified in `OAuthClientGovernanceStudio.test.tsx`. |
| 70 | `DeviceActivatePage.tsx` | User Code Input (`user-code-input`) | Text Input (8 Base20 consonants formatted `XXXX-XXXX`) | Input for 8-character user code displayed on headless device or CLI screen (`BASE20_CHARS = 'BCDFGHJKLMNPQRSTVWXZ'`). | KEEP | ENHANCED | Local state `userCode` auto-formatted via `formatUserCodeInput` with auto-inserted hyphen at 4 characters. Verified in `DeviceActivatePage.test.tsx`. |
| 71 | `DeviceActivatePage.tsx` | Character Validation Notice (`user-code-input-notice`) | Inline Warning Banner | Explains that vowels (A, E, I, O, U) and numbers (0-9) are excluded from Base20 device codes. | KEEP | ENHANCED | Real-time warning banner triggered immediately when user inputs vowels or digits. Verified in `DeviceActivatePage.test.tsx`. |
| 72 | `DeviceActivatePage.tsx` | Lookup Code Button (`lookup-button`) | Button | Queries backend to verify device code and retrieve requested scopes and client info. | KEEP | PRESERVED | Wired to `GET /api/v1/oauth/device/info?user_code={code}`. Verified in `DeviceActivatePage.test.tsx`. |
| 73 | `DeviceActivatePage.tsx` | Scope Selection Checkboxes (`scope-checkbox-*`) | Checkboxes | Grants or restricts individual requested scopes prior to device authorization. | KEEP | PRESERVED | Binds to `scopes` payload in `POST /api/v1/oauth/device/activate`. Verified in `DeviceActivatePage.test.tsx`. |
| 74 | `DeviceActivatePage.tsx` | Project Selection Checkboxes (`project-checkbox-*`) | Checkboxes | Restricts device code access to specific authorized workspace projects. | KEEP | PRESERVED | Binds to `allowed_projects` payload in `POST /api/v1/oauth/device/activate`. Verified in `DeviceActivatePage.test.tsx`. |
| 75 | `DeviceActivatePage.tsx` | Approve Button (`approve-button`) | Button | Approves device authorization request and authorizes external headless client. | KEEP | PRESERVED | Wired to `POST /api/v1/oauth/device/activate` (`approved=true`). Verified in `DeviceActivatePage.test.tsx`. |
| 76 | `DeviceActivatePage.tsx` | Deny Button (`deny-button`) | Button | Denies device authorization request and rejects external headless client. | KEEP | PRESERVED | Wired to `POST /api/v1/oauth/device/activate` (`approved=false`). Verified in `DeviceActivatePage.test.tsx`. |
| 77 | `DeviceActivatePage.tsx` | Admin AAL2 Step-Up Banner (`aal2-banner`) | Inline Elevation Banner | Displays AAL2 step-up requirement prompt when `/mcp/admin` scope is requested. | KEEP | PRESERVED | Triggered when `isAal2StepUpCode` returns true. Verified in `DeviceActivatePage.test.tsx`. |

---

## 3. Verification and Test Results

### 3.1 Unit and Coverage Results
1. **Frontend Vitest Suites:**
   - Files tested: `McpAccessStudio.test.tsx`, `ConnectOAuthAppModal.test.tsx`, `OAuthClientGovernanceStudio.test.tsx`, `DeviceActivatePage.test.tsx`, `McpUnifiedStudio.test.tsx`.
   - Results: **134 passed (100%)**, zero failed, zero act(...) warnings (6.10s).
   - Coverage: Statements **99.03%**, Branches **95.98%**, Functions **99.64%**, Lines **99.06%**. Meets and exceeds the mandatory `>=95%` branch coverage threshold.
2. **Backend Pytest Suites:**
   - Tests executed: `test_oauth_flow.py`, `test_device_flow.py`, `test_oauth_coverage.py`, `test_oauth_unit.py`, `test_unified_mcp_keys_api.py`, `test_admin_mcp_keys_api.py`, `test_workload_oidc_exchange.py`, `test_workload_jwt_auth.py`, `test_mcp_capability_mask_and_cidr.py`, `test_feature_comparison_parity.py`.
   - Results: **118 passed (100%)**, zero failed, zero errors (50.17s).
   - Coverage: `admin/mcp_keys.py` 95%, `admin/workload_identities.py` 98%, `mcp_keys.py` 97%, `oauth.py` 95%, `mcp/app.py` 95% (total 96%).
3. **OpenAPI Schema Parity:**
   - Executed: `uv run pytest kanban/tests/test_feature_comparison_parity.py`.
   - Results: **7 passed (100%)**. 0 delta in endpoints, operations, or OpenAPI schemas.

### 3.2 Linters and Static Checks
- `uv run ruff check kanban/ mcp/`: Clean pass (0 errors, 0 warnings).
- `uv run mypy kanban/ mcp/`: Clean pass (Success: no issues found in 808 source files).
- `pnpm --dir kanban/web typecheck`: Clean pass (0 errors).
- `pnpm --dir kanban/web lint`: Clean pass (0 errors, 0 warnings).
- `pnpm --dir kanban/web build`: Built client environment in 1.24s without errors.
- `python3 scripts/check_no_dashes.py --all`: Clean pass (0 em-dash or en-dash violations).

---

## 4. Multi-Viewport Visual Evidence

Unclipped screenshots across 5 standard viewports were captured and verified via Playwright in `docs/qa/KAN-417/screenshots/`:

1. `01-desktop-1440x900-light-mcp-mint-modal-segmented-selectors.png` (1440x1450):
   - Shows Mint MCP Key modal with Question 2 segmented role pills (`Personal User`, `Service Bot`) and scope pills (`Single Project`, `Entire Workspace`, `Server / Global`), dropdown synchronization, and expanded Advanced restrictions accordion with Granular Capability Bit Toggles, Allowed CIDRs, and Narrow Tools fully unclipped with bottom actions (`Cancel` / `Mint Key`) cleanly placed at the footer.
2. `02-desktop-1440x900-dark-connect-oauth-modal.png` (1440x900):
   - Shows Connect OAuth Application modal in dark theme with Gemini App client snippet tab, unclipped word-wrapped URLs, and 1-click copy buttons.
3. `03-desktop-1024x768-workload-oidc-presets.png` (1024x1250):
   - Shows Workload Identity Federation policy modal with 1-click IdP preset buttons (`GitHub Actions`, `GitLab CI`, `Kubernetes`) pre-populating canonical HTTPS issuer and audience values, with `<AdvancedSection>` expanded revealing capability mask, CIDR restrictions, and TTL inputs fully unclipped.
4. `04-tablet-portrait-768x1024-oauth-governance-advanced.png` (768x1024):
   - Shows OAuth 2.1 Client Governance registration modal on tablet portrait with expanded `AdvancedSection` revealing PKCE S256 toggle, access token TTL input, and grant types input.
5. `05-mobile-portrait-390x844-device-activate.png` (390x844):
   - Shows Device Activation screen on mobile portrait with auto-formatted Base20 consonant code (`XXXX-XXXX`) and real-time character guide notice banner for vowels/digits.

---

## 5. Phase 3 Live Workout Script Plan (`KAN-418`)

The following exact execution script is prepared for Phase 3 (`KAN-418`) to validate zero-mock end-to-end flows against local hermetic containers:

### 5.1 Test Environment Provisioning
```bash
# 1. Start hermetic PostgreSQL test container with clean template DB
make testdb-up

# 2. Build web client assets
pnpm --dir kanban/web build

# 3. Launch application server on ephemeral port 18921
KANBAN_PUBLIC_ORIGIN="http://127.0.0.1:18921" \
KANBAN_TRUSTED_PROXIES="*" \
KB_FORWARDED_ALLOW_IPS="*" \
uv run uvicorn kanban.api.app:app --host 127.0.0.1 --port 18921 &
APP_PID=$!
```

### 5.2 Verification Script Steps
1. **OAuth 2.1 Dynamic Client Registration & Advanced Governance:**
   - Execute `POST /api/v1/admin/oauth-clients` with `pkce_enforce=true`, `access_token_ttl=3600`, and `grant_types=["authorization_code", "refresh_token"]`.
   - Verify client secret is returned exactly once and hashed in database.
   - Verify non-admin or unauthorized calls reject with 403 / AAL2 required.
2. **Headless RFC 8628 Device Flow Activation:**
   - Execute `POST /oauth/device/authorize` with client credentials.
   - Extract `device_code` and `user_code` (8 Base20 consonants).
   - In browser, navigate to `http://127.0.0.1:18921/oauth/device?user_code={user_code}`.
   - Confirm user code loads requested scopes, approve authorization.
   - Poll `POST /oauth/token` and verify successful token issuance.
3. **Headless RFC 8693 Workload Identity Token Exchange:**
   - Mint RSA-signed test OIDC JWT using local test harness key.
   - Execute `POST /oauth/token` with `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`.
   - Verify issued ephemeral bearer token has correct capability ceiling bitmask and expires within policy `max_ttl_seconds`.
4. **Cleanup:**
   - Kill `APP_PID` and tear down testdb container with `make testdb-down`.
