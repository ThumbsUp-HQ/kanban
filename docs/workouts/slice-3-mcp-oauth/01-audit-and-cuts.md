# Slice 3: MCP Access Studio, Workload OIDC and OAuth 2.1 Governance Setting Inventory and Simplification Audit

**Ticket:** KAN-416 (`[SLICE-3-P1][KB-MCP-OAUTH-AUDIT]`)  
**Parent Epic:** KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)  
**Target Next Phase:** KAN-417 (`[SLICE-3-P2][KB-MCP-OAUTH-SIMPLIFY]`)  
**Status:** In Progress (Phase 1 Audit and Simplification Specification - Rev 2 Forensic Correction)  
**Author:** s3-p1 (Security and UX Auditor)  
**Traceability:** `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 11 (Three-Surface Intent-Driven MCP Server) and Section 4 (Zero-Trust Service Auth)  

---

## 1. Executive Summary and Scope Boundaries

### 1.1 Purpose
This document delivers the comprehensive Phase 1 setting-by-setting inventory, technical audit, simplification cut list, and Phase 3 staging checklist for **Slice 3 (MCP Access Studio, Connect OAuth App Modal, Config Snippet Modal, Workload Identity Federation OIDC RFC 8693, OAuth 2.1 Client Governance, and Headless RFC 8628 Device Flow Activation)**.

### 1.2 Zero-Mutation Phase 1 Boundary
Phase 1 (`KAN-416`) is strictly read-only reconnaissance, specification, and inter-phase handoff. No production or test source code is modified in Phase 1. All UI simplifications, layout refactorings, 1-click presets, and backend wiring adjustments are executed in Phase 2 (`KAN-417`).

### 1.3 Coordination with In-Flight Tickets
- **KAN-404 (Gate 0 WebSudo):** Owns administrative session step-up (AAL2 dirty keepalive, sudo re-auth prompt, and session elevation). Slice 3 references AAL2 step-up handlers (`require_admin_aal2`, `dispatchAal2StepUpIfRequired`, `isAal2StepUpCode`) as downstream consumers for administrative MCP key minting and `/admin/oauth` actions without re-implementing WebSudo primitives.
- **KAN-390 (CLI Flag Standardization):** Standardizes CLI parameter nomenclature across local agent utilities. Slice 3 aligns MCP configuration snippets with canonical flags.
- **KAN-395 (Gemini MCP OAuth 2.1 State and URL Parsing):** Raised `MAX_STATE_LEN` to 4096 bytes, resolved `?` vs `&` query separator handling on OAuth redirect assembly, bound issued OAuth tokens to target workspaces via RFC 8707 `resource`, and added the initial Gemini App connector tab to `ConnectOAuthAppModal.tsx`. Slice 3 builds upon these verified OAuth 2.1 foundations.
- **KAN-396 (OAuth PKCE S256 Boundaries):** Gated public clients strictly to PKCE S256 with confidential fallback. Slice 3 preserves these cryptographic boundaries.

---

## 2. Complete Setting-by-Setting Inventory Table

Below is the complete inventory of all UI controls, labels, options, defaults, validation rules, and backend bindings across Slice-3 files:
- `kanban/web/src/features/settings/McpAccessStudio.tsx`
- `kanban/web/src/features/settings/McpUnifiedStudio.tsx`
- `kanban/web/src/features/settings/ConnectOAuthAppModal.tsx`
- `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`
- `kanban/web/src/features/oauth/OAuthClientGovernanceStudio.tsx`
- `kanban/web/src/features/oauth/DeviceActivatePage.tsx`
- `kanban/api/v1/oauth.py`
- `kanban/api/v1/mcp_keys.py`
- `kanban/api/v1/auth_mcp_keys.py`
- `kanban/api/v1/admin/mcp_keys.py`
- `kanban/api/v1/admin/workload_identities.py`
- `mcp/app.py`

### Inventory Table

| Screen/Drawer | Setting Label and Key | Options / Type | 1-Sentence Plain-English Meaning | Backend Wiring Status | Disposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `McpAccessStudio.tsx` | Scope Filter Pills (`scope-pill-all`, `scope-pill-project`, `scope-pill-workspace`, `scope-pill-server`) | Pill Buttons: All, Project, Workspace, Server | Filters the active list of MCP API keys and token allowances by architectural scope boundary. | Client-side filter on `activeScope` wired to `GET /api/v1/mcp-keys?scope_tier=...`. | KEEP |
| `McpAccessStudio.tsx` | Target Project Filter Select (`scope-project-select`) | Select: List of workspace project identifiers | Filters MCP keys strictly to a single project when Project scope pill is selected. | Client-side filter on `effectiveProjectKey` wired to `GET /api/v1/mcp-keys?project_ref=...`. | KEEP |
| `McpAccessStudio.tsx` | View Toggle (`view-mine-btn`, `view-governance-btn`) | Segmented Toggle: My Keys vs Workspace Governance | Toggles between viewing personal keys issued by caller and audit governance across all workspace keys. | Client-side state `activeView` wired to `GET /api/v1/mcp-keys?view=mine|governance`. | KEEP |
| `McpAccessStudio.tsx` | Connect OAuth App Button (`connect-oauth-app-btn`) | Button (and empty state variant `empty-connect-oauth-app-btn`) | Opens the ConnectOAuthAppModal to configure external desktop or cloud MCP clients via OAuth 2.1. | Triggers `showConnectOAuthModal=true`. | KEEP |
| `McpAccessStudio.tsx` | Enter Device Code Link (`enter-device-code-btn`) | Link Button (and empty state variant `empty-enter-device-code-btn`) | Navigates to `/oauth/device` to authorize a headless CLI or remote device. | Navigates to `DeviceActivatePage.tsx`. | KEEP |
| `McpAccessStudio.tsx` | Connected OAuth Apps Disconnect (`disconnect-btn-*`) | Button | Initiates two-stage confirmation to deauthorize an external OAuth application grant. | Wired to `DELETE /api/v1/auth/oauth-grants/{grant_id}` via `confirm-disconnect-btn`. | KEEP |
| `McpAccessStudio.tsx` | Agent Onboarding Prompt Copy (`mcp-copy-llms-prompt-btn`) | Button | Copies ready-to-paste agent onboarding prompt referencing `/llms.txt` and interview preferences. | Client-side clipboard helper in `mcp-llms-txt-callout`. | KEEP |
| `McpAccessStudio.tsx` | Mint New Key Button (`mint-key-button`) | Button | Opens the 4-question Mint Key Modal to create a new scoped static `kb_*` API token. | Triggers `showMintModal=true`. | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Question 1: Key Name (`mint-label-input`) | Text Input (1-64 chars) | Human-readable identifier or application name describing the purpose of the key. | Wired to `label` in `POST /api/v1/mcp-keys` (and `/api/v1/admin/mcp-keys`). | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Question 2: Scope & Owner Kind (`mint-key-scope-type-select`) | Select: Personal (Workspace/Project), Service Bot (Workspace/Project/Server) | Defines token ownership (user vs automated service bot) and resource confinement boundary. | Wired to `owner_kind` and `scope_tier` in `POST /api/v1/mcp-keys`. | SIMPLIFY |
| `McpAccessStudio.tsx` | Mint Modal Question 2: Target Project (`mint-project-input`) | Text Input with datalist (`mint-project-datalist`) | Restricts token authorization strictly to items within a single chosen project. | Wired to `project_ref` in `POST /api/v1/mcp-keys`. | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Target Surface (`mint-surface-select`) | Select: `/mcp/agent` (Workflow & Issues), `/mcp/docs` (Knowledge), `/mcp/admin` (Server Admin) | Restricts token invocation to a single isolated MCP tool surface. | Wired to `surface` in `POST /api/v1/mcp-keys` (and `/api/v1/admin/mcp-keys`). | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Expiration (`mint-expiry-select`) | Select: 30 Days, 60 Days, 90 Days, 365 Days, Unlimited (`option-unlimited`) | Lifetime duration before the newly minted MCP token automatically expires and invalidates. | Wired to `expires_in_days` in `POST /api/v1/mcp-keys`. | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Confirm Unlimited Key (`confirm-unlimited-checkbox`) | Checkbox | Explicit security confirmation acknowledgement required before issuing a non-expiring token. | Client-side validation guard blocking submit if unconfirmed. | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Advanced Restrictions Accordion (`advanced-capability-restrictions`) | Collapsible Accordion | Houses granular bitmask permissions, tool-level exclusions, and network CIDR filters. | Expands progressive disclosure container. | SIMPLIFY |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Capability Preset (`capability-preset-select`) | Select: 1 (Read-Only), 3 (Read/Write), 31 (Standard Developer), 255 (Admin Superuser), Custom | Sets the maximum capability bitmask ceiling granted to the token. | Wired to `capability_mask` in `POST /api/v1/mcp-keys`. | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Granular Capability Bits Grid (`capability-bits-grid`, `cap-bit-*`) | Checkbox Grid (8 bits: 1, 2, 4, 8, 16, 32, 64, 128) | Granular manual bitmask override checkboxes for specialized agent capability policies. | Computes composite `capability_mask` in `POST /api/v1/mcp-keys`. | MOVE_TO_ADVANCED |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Allowed Ingress CIDRs (`mint-allowed-cidrs-input`) | Text Input (comma-separated IPv4/IPv6 CIDRs) | Restricts token authentication strictly to caller IP addresses matching network CIDR list. | Wired to `allowed_cidrs` in `POST /api/v1/mcp-keys`. | MOVE_TO_ADVANCED |
| `McpAccessStudio.tsx` | Mint Modal Question 3: Disabled Tools Selection Grid (`tools-selection-grid`, `disable-tool-*`) | Tool Checkbox Grid | Explicitly subtracts individual MCP tools from the client capability set. | Wired to `disabled_tools` in `POST /api/v1/mcp-keys`. | MOVE_TO_ADVANCED |
| `McpAccessStudio.tsx` | Mint Modal Question 4: Live Key Summary (`mint-key-summary`) | Plain-Language Summary Box | Displays dynamic real-time human-readable description of the token policy before creation. | Client-side summary computed from form state. | KEEP |
| `McpAccessStudio.tsx` | Mint Modal Submit Button (`mint-submit-btn`) | Button | Issues API request to create the configured MCP access token. | Wired to `POST /api/v1/mcp-keys` (or `POST /api/v1/admin/mcp-keys`). | KEEP |
| `McpAccessStudio.tsx` | Keys Table: Revoke Key Button (`revoke-btn-*`) | Button | Opens 2-stage confirm bar (`confirm-revoke-btn`) to immediately revoke and invalidate the MCP token. | Wired to `DELETE /api/v1/mcp-keys/{key_id}` (or `DELETE /api/v1/admin/mcp-keys/{key_id}`). | KEEP |
| `ConnectOAuthAppModal.tsx` | Target Scope Selector (`scope-tier-select`) | Select: Workspace, Single Project, Server (Global) | Selects the RFC 8707 resource scope target for external MCP client configuration. | Dynamically computes `data-testid="mcp-resource-url"`. | KEEP |
| `ConnectOAuthAppModal.tsx` | Target Project Dropdown (`project-select`) | Select: Dynamic project list | Chooses the project key for project-scoped OAuth resource URLs. | Dynamically appends `/p/{projectKey}` to resource URL. | KEEP |
| `ConnectOAuthAppModal.tsx` | Target Surface Selector (`surface-select`) | Select: Agent (`/mcp/agent`), Docs (`/mcp/docs`), Admin (`/mcp/admin`) | Sets the MCP surface endpoint in generated configuration URLs and snippets. | Dynamically adjusts URL and updates scope checkboxes. | KEEP |
| `ConnectOAuthAppModal.tsx` | Fine-Grained OAuth Scopes (`scope-picker`, `scope-check-*`) | Checkboxes: `agent:read`, `agent:write`, `docs:read`, `docs:write`, `admin:read`, `admin:write`, `admin:destructive` | Selects fine-grained OAuth scopes requested by client (Admin scopes: `admin:read`, `admin:write`, `admin:destructive`, NOT `admin:*`). | Binds to `selectedScopes` array in code snippets. | KEEP |
| `ConnectOAuthAppModal.tsx` | MCP Resource URL Display (`mcp-resource-url`) | Read-only Code Display | Fully resolved RFC 8707 MCP endpoint URL configured in client settings. | Dynamically rendered from current host, surface, and scope. | KEEP |
| `ConnectOAuthAppModal.tsx` | Copy Resource URL Button (`copy-resource-url-btn`) | Button | Copies the RFC 8707 MCP Resource URL to clipboard with 2-second visual feedback. | Client-side clipboard copy helper. | KEEP |
| `ConnectOAuthAppModal.tsx` | RFC 8414 Metadata URL (`rfc8414-url`) | Read-only Code Display | Standard authorization server metadata discovery endpoint (`/.well-known/oauth-authorization-server`). | Dynamically rendered discovery URL. | KEEP |
| `ConnectOAuthAppModal.tsx` | Copy RFC 8414 Metadata URL Button (`copy-rfc8414-url-btn`) | Button | Copies the RFC 8414 Metadata URL to clipboard with 2-second visual feedback. | Client-side clipboard copy helper. | KEEP |
| `ConnectOAuthAppModal.tsx` | Connector Tool Tabs (`tab-claude-code`, `tab-cursor`, `tab-antigravity`, `tab-codex`, `tab-gemini-app`) | Tabs: Claude Code, Cursor, Antigravity, Codex, Gemini App | Selects the target AI IDE or agent client to display exact copy-paste configuration instructions. | Renders tool-specific configuration snippet. | KEEP |
| `ConnectOAuthAppModal.tsx` | Tool Configuration Snippet Display (`command-snippet`) | Preformatted Code Box | Displays formatted JSON configuration block or CLI command tailored to selected client tool. | Formatted template based on active tab and scopes. | KEEP |
| `ConnectOAuthAppModal.tsx` | Copy Snippet Button (`copy-snippet-btn`) | Button | Copies the active tool configuration snippet to clipboard with 2-second visual feedback. | Client-side clipboard copy helper. | KEEP |
| `ConnectOAuthAppModal.tsx` | Modal Enter Device Code Link (`modal-enter-device-code-btn`) | Link Button | Provides navigation link directly to `/oauth/device` for headless device code entry. | Navigates to `DeviceActivatePage.tsx`. | KEEP |
| `McpConfigSnippetModal.tsx` | Raw Key One-Time Display (`raw-key-display`) | Code Display | Displays newly minted plaintext `kb_*` token immediately after creation before hashing. | Rendered only once when `rawKey` is present in modal props. | KEEP |
| `McpConfigSnippetModal.tsx` | Copy Raw Key Button (`copy-key-button`) | Button | Copies newly minted plaintext `kb_*` token to clipboard. | Client-side clipboard helper. | KEEP |
| `McpConfigSnippetModal.tsx` | URL Scope Selector (`url-scope-select`) | Select: Single Project, Entire Workspace, Global (Server) | Adjusts the target endpoint path in generated client JSON configurations. | Updates `endpointUrl` in snippets. | KEEP |
| `McpConfigSnippetModal.tsx` | Client Snippet Tabs (`tab-claude`, `tab-cursor`, `tab-gemini`, `tab-antigravity`, `tab-codex`, `tab-oauth`) | Tabs: Claude, Cursor, Gemini, Antigravity, Codex, OAuth | Selects client-specific configuration format (JSON block and CLI command). | Renders formatted client snippet with Authorization header. | KEEP |
| `McpConfigSnippetModal.tsx` | Snippet Code Box (`snippet-code-box`) | Preformatted Code Display | Preformatted client configuration block showing exact JSON or CLI syntax. | Formatted template with API token. | KEEP |
| `McpConfigSnippetModal.tsx` | Copy Snippet Button (`copy-snippet-button`) | Button | Copies generated configuration snippet to clipboard. | Client-side clipboard helper. | KEEP |
| `McpConfigSnippetModal.tsx` | Copy Prompt Button (`mcp-copy-llms-prompt-btn`) | Button | Copies ready-to-paste agent onboarding prompt referencing `/llms.txt`. | Client-side clipboard copy of standard system prompt. | KEEP |
| `McpUnifiedStudio.tsx` | Add Workload Policy Button (`add-workload-policy-btn`) | Button | Opens modal to configure a new headless RFC 8693 workload identity federation policy. | Triggers `showModal=true` in `WorkloadFederationSection`. | KEEP |
| `McpUnifiedStudio.tsx` | Workload Policy: Name (`policy-name-input`) | Text Input (1-128 chars) | Administrative name for the CI/CD workload policy. | Wired to `name` in `POST /api/v1/admin/workload-identities`. | KEEP |
| `McpUnifiedStudio.tsx` | Workload Policy: Description (`policy-description-input`) | Text Input | Optional summary of the workload identity purpose and repository mapping. | Wired to `description` in `POST /api/v1/admin/workload-identities`. | KEEP |
| `McpUnifiedStudio.tsx` | Workload Policy: Issuer URL (`policy-issuer-input`) | URL Input | HTTPS OIDC IdP token issuer URL (e.g. `https://token.actions.githubusercontent.com`). | Wired to `issuer` in `POST /api/v1/admin/workload-identities`. | SIMPLIFY |
| `McpUnifiedStudio.tsx` | Workload Policy: Client ID / Audience (`policy-client-id-input`) | Text Input | Expected audience claim (`aud`) contained in the inbound workload JWT. | Wired to `client_id` in `POST /api/v1/admin/workload-identities`. | SIMPLIFY |
| `McpUnifiedStudio.tsx` | Workload Policy: Surface (`policy-surface-select`) | Select: Agent (`/mcp/agent`), Docs (`/mcp/docs`) | Confines exchanged tokens strictly to the chosen MCP surface. | Wired to `surface` in `POST /api/v1/admin/workload-identities`. | KEEP |
| `McpUnifiedStudio.tsx` | Workload Policy: Subject Pattern (`policy-subject-pattern-input`) | Text Input (glob pattern) | Glob or exact pattern matched against inbound JWT `sub` claim (e.g. `repo:org/app:*`). | Wired to `subject_pattern` in `POST /api/v1/admin/workload-identities`. | SIMPLIFY |
| `McpUnifiedStudio.tsx` | Workload Policy: Capability Mask (`policy-cap-mask-input`) | Number Input (0-255) | Maximum capability bitmask granted to tokens exchanged under this policy. | Wired to `capability_mask` in `POST /api/v1/admin/workload-identities`. | MOVE_TO_ADVANCED |
| `McpUnifiedStudio.tsx` | Workload Policy: Allowed CIDRs (`policy-cidrs-input`) | Text Input (comma-separated CIDRs) | Ingress IP restriction for token exchange and subsequent MCP calls. | Wired to `allowed_cidrs` in `POST /api/v1/admin/workload-identities`. | MOVE_TO_ADVANCED |
| `McpUnifiedStudio.tsx` | Workload Policy: Max TTL (`policy-ttl-input`) | Number Input (seconds, 60-86400) | Maximum lifetime of ephemeral tokens issued via workload exchange. | Wired to `max_ttl_seconds` in `POST /api/v1/admin/workload-identities`. | MOVE_TO_ADVANCED |
| `McpUnifiedStudio.tsx` | Workload Policy Table: Status Toggle (`toggle-policy-btn-*`) | Button | Enables or disables an active workload federation policy. | Wired to `PATCH /api/v1/admin/workload-identities/{id}` (`is_enabled`). | KEEP |
| `McpUnifiedStudio.tsx` | Workload Policy Table: Edit Policy (`edit-policy-btn-*`) | Button | Opens policy modal pre-populated with policy attributes for editing. | Wired to `PATCH /api/v1/admin/workload-identities/{id}`. | KEEP |
| `McpUnifiedStudio.tsx` | Workload Policy Table: Delete (`delete-policy-btn-*`) | Button | Deletes a workload federation policy permanently. | Wired to `DELETE /api/v1/admin/workload-identities/{id}`. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Refresh Clients Button (`refresh-clients-btn`) | Button | Re-fetches all registered dynamic and administrative OAuth 2.1 clients. | Wired to `GET /api/v1/admin/oauth-clients` (AAL2). | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Register OAuth Client Button (`register-client-btn`) | Button | Opens modal to manually register a new confidential or public OAuth 2.1 client. | Triggers `showRegisterModal=true`. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: Name (`input-client-name`) | Text Input (1-128 chars) | Human-readable application name for the client. | Wired to `client_name` in `POST /api/v1/admin/oauth-clients`. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: Redirect URIs (`input-redirect-uris`) | Textarea (newline/comma-separated URIs) | Valid HTTPS or localhost callback URIs registered for authorization code redirects. | Wired to `redirect_uris` in `POST /api/v1/admin/oauth-clients`. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: Client Type (`select-client-type`) | Select: Public (SPA/CLI/Desktop), Confidential (Web Backend) | Security classification governing client secret issuance. Auto-selects auth method `none` when Public. | Wired to `client_type` in `POST /api/v1/admin/oauth-clients`. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: Auth Method (`select-auth-method`) | Select: None, Client Secret Basic, Client Secret Post, Private Key JWT | Authentication scheme used at `POST /oauth/token`. | Wired to `token_endpoint_auth_method` in `POST /api/v1/admin/oauth-clients`. | SIMPLIFY |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: PKCE Enforce (`toggle-pkce-s256`) | Checkbox | Mandates RFC 7636 PKCE S256. Already inside Advanced Section; currently dead UI control. | Unwired in `handleRegisterSubmit`; rejected by backend `extra="forbid"`. | MOVE_TO_ADVANCED |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: Token TTL (`input-access-token-ttl`) | Number Input (seconds, default 3600) | Lifetime of access tokens issued to this client application. Already inside Advanced Section; dead UI control. | Unwired in `handleRegisterSubmit`; rejected by backend `extra="forbid"`. | MOVE_TO_ADVANCED |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: Grant Types (`input-grant-types`) | Text Input (comma-separated grant types) | Allowed OAuth grant types. Already inside Advanced Section; dead UI control. | Unwired in `handleRegisterSubmit`; rejected by backend `extra="forbid"`. | MOVE_TO_ADVANCED |
| `OAuthClientGovernanceStudio.tsx` | Client Registration: Secret Reveal Drawer (`registered-client-secret`) | Read-only Code Display + Copy Button | Secure one-time reveal drawer displaying client ID and secret immediately after creation. | Already implemented via `register-success-view`. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Action: Inspect (`inspect-btn-*`) | Button | Opens modal card displaying secret prefix and client metadata. | Triggers `inspectingClient` modal state. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Action: Edit Redirect URIs (`edit-uris-btn-*`) | Button | Opens edit modal (`edit-uris-modal`) with `input-edit-redirect-uris` to modify URIs. | Wired to `PATCH /api/v1/admin/oauth-clients/{client_id}` with `redirect_uris`. | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Action: Approve / Activate (`approve-btn-*`) | Button | Approves a pending dynamic client registration or re-activates a suspended client. | Wired to `PATCH /api/v1/admin/oauth-clients/{client_id}` (`status='active'`). | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Action: Suspend (`suspend-btn-*`) | Button | Suspends an active OAuth client and revokes all active authorization grants. | Wired to `PATCH /api/v1/admin/oauth-clients/{client_id}` (`status='suspended'`). | KEEP |
| `OAuthClientGovernanceStudio.tsx` | Client Action: Revoke / Delete (`revoke-btn-*`) | Button | Opens 2-stage confirm bar (`confirm-revoke-*`) to permanently revoke and delete client registration. | Wired to `DELETE /api/v1/admin/oauth-clients/{client_id}`. | KEEP |
| `DeviceActivatePage.tsx` | User Code Input (`user-code-input`) | Text Input (8 Base20 consonants formatted `XXXX-XXXX`) | Input for 8-character user code displayed on headless device or CLI screen (`BASE20_CHARS = 'BCDFGHJKLMNPQRSTVWXZ'`). | Local state `userCode` auto-formatted via `formatUserCodeInput`. | KEEP |
| `DeviceActivatePage.tsx` | Character Validation Notice (`user-code-input-notice`) | Inline Warning Banner | Explains that vowels (A, E, I, O, U) and numbers (0-9) are excluded from Base20 device codes. | Real-time validation triggered on non-Base20 input. | KEEP |
| `DeviceActivatePage.tsx` | Lookup Code Button (`lookup-button`) | Button | Queries backend to verify device code and retrieve requested scopes and client info. | Wired to `GET /api/v1/oauth/device/info?user_code={code}`. | KEEP |
| `DeviceActivatePage.tsx` | Scope Selection Checkboxes (`scope-checkbox-*`) | Checkboxes | Grants or restricts individual requested scopes prior to device authorization. | Binds to `scopes` payload in `POST /api/v1/oauth/device/activate`. | KEEP |
| `DeviceActivatePage.tsx` | Project Selection Checkboxes (`project-checkbox-*`) | Checkboxes | Restricts device code access to specific authorized workspace projects. | Binds to `allowed_projects` payload in `POST /api/v1/oauth/device/activate`. | KEEP |
| `DeviceActivatePage.tsx` | Approve Button (`approve-button`) | Button | Approves device authorization request and authorizes external headless client. | Wired to `POST /api/v1/oauth/device/activate` (`approved=true`). | KEEP |
| `DeviceActivatePage.tsx` | Deny Button (`deny-button`) | Button | Denies device authorization request and rejects external headless client. | Wired to `POST /api/v1/oauth/device/activate` (`approved=false`). | KEEP |
| `DeviceActivatePage.tsx` | Admin AAL2 Step-Up Banner (`aal2-banner`) | Inline Elevation Banner | Displays AAL2 step-up requirement prompt when `/mcp/admin` scope is requested. | Triggered when `isAal2StepUpCode` returns true. | KEEP |

---

## 3. Simplification Proposals and Focus Areas

### 3.1 4-Question Mint MCP Key Modal Ergonomics
**Current Architectural State:**  
The Mint MCP Key modal in `McpAccessStudio.tsx` already implements a 4-step progressive disclosure question flow:
- **Question 1:** Key Name (`mint-label-input`) with auto-focus.
- **Question 2:** Who is this key for & what can it access? (`mint-key-scope-type-select` combining owner kind and scope tier, plus `mint-project-input` with `mint-project-datalist` for single project scoping).
- **Question 3:** What can it do? (`mint-surface-select` for surface isolation, `mint-expiry-select` with unlimited confirmation guard `confirm-unlimited-checkbox`, and `<AdvancedSection testId="advanced-capability-restrictions">` housing `capability-preset-select`, 8-bit granular grid `capability-bits-grid` (`cap-bit-1` through `cap-bit-128`), `mint-allowed-cidrs-input` with real-time IPv4/IPv6 validation, and tool exclusions in `tools-selection-grid`).
- **Question 4:** Live Plain-Language Key Summary (`mint-key-summary` rendering a dynamic preview of the configured key parameters).

**Proposed Simplifications for Phase 2:**
1. **Streamline Composite Question 2 Selector:**
   In `mint-key-scope-type-select`, separate owner kind (Personal User vs Service Bot) and target scope (Project vs Workspace vs Server) into two intuitive segmented pill groups to avoid long composite option labels.
2. **Active Override Indicators:**
   Add an active override count badge to `AdvancedSection` so users immediately see when non-default bitmasks or CIDRs are active.
3. **Workspace Policy Clamping:**
   When the workspace enforces a maximum key TTL (e.g. 90 days), automatically clamp the Expiry dropdown and hide the "Unlimited" option with an informative policy badge instead of failing upon submission.

### 3.2 `ConnectOAuthAppModal` Resource URL and Client Ergonomics
**Current Architectural State:**  
`ConnectOAuthAppModal.tsx` configures external desktop and cloud MCP clients (Claude Code, Cursor, Antigravity, Codex, Gemini App) using RFC 8707 resource parameters.
- Fine-grained scopes per surface are strictly defined:
  - Agent surface (`/mcp/agent`): `agent:read`, `agent:write`
  - Docs surface (`/mcp/docs`): `docs:read`, `docs:write`
  - Admin surface (`/mcp/admin`): `admin:read`, `admin:write`, `admin:destructive` (CRITICAL: admin scopes are explicitly individual verbs, NOT wildcard `admin:*`).
- Dedicated copy buttons provide 2-second visual feedback:
  - `copy-resource-url-btn` for the RFC 8707 MCP Resource URL (`mcp-resource-url`).
  - `copy-rfc8414-url-btn` for the RFC 8414 OAuth Authorization Server Metadata URL (`rfc8414-url`).
  - `copy-snippet-btn` for the active client JSON block or CLI command snippet (`command-snippet`).
- Direct navigation for headless clients is provided via `modal-enter-device-code-btn` linking to `/oauth/device`.

**Proposed Simplifications for Phase 2:**
1. **Responsive Viewport Word Wrapping:**
   Enforce `white-space: normal; word-break: break-all; overflow-wrap: anywhere;` on `.kb-connect-oauth-url` and tighten modal padding so the full snippet and guidance box remain visible without clipping on `1440x900` desktop, `768x1024` tablet, and `390x844` mobile portrait.
2. **Dynamic Project Key Fallback:**
   Ensure `effectiveProject` always resolves dynamically to the caller's active project key or first available project rather than displaying `<PROJECT_KEY>` when projects have loaded.

### 3.3 Workload Identity Federation (RFC 8693) 1-Click Presets
**Current Architectural State:**  
Workload Identity Federation lives in `McpUnifiedStudio.tsx` (`WorkloadFederationSection`), NOT in `OAuthClientGovernanceStudio.tsx`.
- Operators configure inbound OIDC token exchange policies matching CI/CD workloads (e.g. GitHub Actions, GitLab CI, Kubernetes).
- The table provides `toggle-policy-btn-*` (enable/disable), `edit-policy-btn-*` (open edit modal with pre-populated values), and `delete-policy-btn-*` (permanent deletion).
- **Backend Note:** In `kanban/api/v1/admin/workload_identities.py`, `create_workload_policy` currently accepts policy attributes without validating OIDC discovery endpoints (`/.well-known/openid-configuration`) or verifying that the subject pattern compiles as a valid glob/regex pattern on `POST`.

**Proposed Simplifications for Phase 2:**
1. **1-Click CI/CD IdP Presets:**
   Add a quick-select preset bar (`GitHub Actions`, `GitLab CI`, `Kubernetes Workload Identity`) above the form that pre-populates:
   - **GitHub Actions:**
     - Issuer: `https://token.actions.githubusercontent.com`
     - Client ID / Audience: Default to current `origin` or `https://kanban.example.com`
     - Subject Pattern Template: `repo:<org>/<repo>:ref:refs/heads/<branch>`
   - **GitLab CI:**
     - Issuer: `https://gitlab.com`
     - Client ID / Audience: Default to current `origin`
     - Subject Pattern Template: `project_path:<group>/<project>:ref:<branch>:ref_type:branch`
   - **Kubernetes:**
     - Issuer: `https://kubernetes.default.svc.cluster.local`
     - Client ID / Audience: `https://kanban.example.com`
     - Subject Pattern Template: `system:serviceaccount:<namespace>:<serviceaccount>`
2. **Subject Pattern Syntax Helper:**
   Provide inline syntax help explaining wildcard tokens (`*` for single segment, `**` for arbitrary sub-paths) and common claim keys (`ref`, `environment`, `job_workflow_ref`).

### 3.4 `/admin/oauth` Governance Studio Ergonomics
**Current Architectural State:**  
In `OAuthClientGovernanceStudio.tsx`:
- Precise UI control `data-testid` attributes are:
  - Form fields: `input-client-name`, `input-redirect-uris`, `select-client-type`, `select-auth-method`.
  - Advanced section: `<AdvancedSection title="Advanced OAuth Parameters" summary="PKCE S256 enforcement, token lifetimes, and grant type restrictions" testId="advanced-oauth-parameters">` housing `toggle-pkce-s256`, `input-access-token-ttl`, and `input-grant-types`.
  - Modal buttons: `register-client-btn`, `submit-register-btn`, `cancel-register-btn`, `close-register-modal-btn`.
  - Secret reveal view: `register-success-view` rendering `registered-client-id`, `registered-client-secret`, `copy-client-id-btn`, `copy-client-secret-btn`, `secret-warning`, and `done-register-btn`.
  - Client table actions: `approve-btn-*`, `suspend-btn-*`, `revoke-btn-*` (with 2-stage confirm bar `confirm-revoke-bar-*`), `inspect-btn-*` (displaying `inspect-client-secret-prefix`), and `edit-uris-btn-*` (opening edit URIs modal with `input-edit-redirect-uris` and `submit-edit-uris-btn`).
- **Critical Architectural Finding on Advanced Controls:**
  `toggle-pkce-s256`, `input-access-token-ttl`, and `input-grant-types` are ALREADY located inside `<AdvancedSection data-testid="advanced-oauth-parameters">`. However, they are currently dead and unwired UI controls: `AdminOAuthClientCreateRequest` (`oauth.py:241-275`) declares `client_name, redirect_uris, client_type, token_endpoint_auth_method, grant_types, response_types` with `ConfigDict(extra="forbid")` (though `admin_register_oauth_client` ignores `grant_types`/`response_types`, `handleRegisterSubmit` omits `grant_types`, `pkce_enforce`, and `access_token_ttl`, and `pkce_enforce`/`access_token_ttl` fail 422 `extra="forbid"`).
- **Already-Implemented Features:**
  - Auto-selecting `'none'` for client authentication when `client_type === 'public'` is ALREADY implemented in `select-client-type` `onChange`.
  - Secure one-time secret display drawer (`register-success-view`) is ALREADY implemented with copy buttons and one-time display warning.
  Both items are removed from the `KAN-417` pending list.

**Proposed Simplifications for Phase 2:**
1. **Instant Status Filter Bar:**
   Add quick-filter buttons (All, Active, Suspended, Revoked) above the clients table to filter large client catalogs.
2. **Wire Advanced Parameters in Frontend and Backend:**
   Extend `AdminOAuthClientCreateRequest` to accept `pkce_enforce: bool`, `access_token_ttl: int`, and `grant_types: list[str]`, and wire `handleRegisterSubmit` to send them.

### 3.5 `/activate` Device Flow Ergonomics and Base20 Consonant Guide
**Current Architectural State:**  
`DeviceActivatePage.tsx` and backend `kanban/api/v1/oauth.py` implement RFC 8628 OAuth 2.0 Device Authorization:
- **Base20 Character Set:**
  `BASE20_CHARS = 'BCDFGHJKLMNPQRSTVWXZ'` (defined in `DeviceActivatePage.tsx:17` and `kanban/oauth/device.py:38`).
  The character set consists of 20 uppercase consonants. It INCLUDES `L` and strictly EXCLUDES vowels (`A, E, I, O, U`) and all digits (`0-9`) to eliminate visual ambiguity and accidental word formation.
- **Backend Endpoint Contracts:**
  - Device authorization request: `POST /oauth/device/authorize` (RFC 8628 Section 3.1) - NOT `/oauth/device/code`.
  - Pending code lookup: `GET /api/v1/oauth/device/info?user_code={code}` (`fetchDeviceCodeInfo`).
  - Device activation decision: `POST /api/v1/oauth/device/activate` (`submitDeviceActivation`) accepting `{ user_code, approved, scopes, allowed_projects }`.
  - Token exchange: `POST /oauth/token` supporting grant types:
    - `authorization_code` (RFC 6749 / RFC 7636 PKCE S256)
    - `refresh_token` (RFC 6749)
    - `urn:ietf:params:oauth:grant-type:device_code` (RFC 8628 Device Code)
    - `urn:ietf:params:oauth:grant-type:token-exchange` (RFC 8693 Workload Identity Token Exchange)
    - Strictly NO `client_credentials` grant type is supported.

**Proposed Simplifications for Phase 2:**
1. **Auto-Formatting and Hyphen Insertion:**
   Automatically uppercase input and insert hyphen after 4 characters (`XXXX-XXXX`) as the user types.
2. **Educational Validation Notice:**
   Render immediate inline notice `user-code-input-notice` when forbidden vowels or digits are typed.
3. **Admin AAL2 Step-Up Elevation:**
   Verify `isAal2StepUpCode` triggers clean AAL2 elevation prompt (`aal2-banner`) whenever `/mcp/admin` scope is requested.

---

## 4. Phase 2 (`KAN-417`) File-Scoped Action Checklist

This checklist defines the exact implementation boundaries for Phase 2 (`KAN-417`), deduplicated against `KAN-404`, `KAN-390`, `KAN-395`, and `KAN-396`:

### 4.1 Frontend Tasks (`kanban/web/src/features/`)
- [ ] **`McpAccessStudio.tsx`:**
  - Streamline Question 2 composite dropdown (`mint-key-scope-type-select`) into distinct segmented role and scope selectors.
  - Add active override indicators to `AdvancedSection` (`advanced-capability-restrictions`).
  - Clamp expiration options to workspace maximum TTL policy.
- [ ] **`ConnectOAuthAppModal.tsx` & `ConnectOAuthAppModal.css`:**
  - Verify mobile word-wrapping on `.kb-connect-oauth-url` (`overflow-wrap: anywhere; word-break: break-all;`).
  - Ensure modal max height allows full content visibility on `1440x900` desktop, `768x1024` tablet, and `390x844` mobile portrait without clipping.
  - Guarantee `effectiveProject` dynamically resolves to the first available project instead of generic placeholders.
- [ ] **`McpUnifiedStudio.tsx`:**
  - Add 1-click IdP preset buttons (GitHub Actions, GitLab CI, Kubernetes) to `WorkloadFederationSection` modal.
  - Pre-populate valid issuer URLs, audience templates, and subject pattern examples upon clicking preset buttons.
- [ ] **`OAuthClientGovernanceStudio.tsx`:**
  - Add status filter buttons (All, Active, Suspended, Revoked) above the clients table.
  - Wire dead controls in `AdvancedSection` (`toggle-pkce-s256`, `input-access-token-ttl`, `input-grant-types`) into `handleRegisterSubmit`.
- [ ] **`DeviceActivatePage.tsx`:**
  - Enhance auto-formatting to automatically uppercase and insert hyphen at 4 characters.
  - Verify Base20 consonant warning banner triggers immediately upon entering vowels or digits.
  - Ensure AAL2 step-up prompt triggers cleanly when `/mcp/admin` scope is requested.

### 4.2 Backend Tasks (`kanban/api/v1/` and `mcp/`)
- [ ] **`kanban/api/v1/admin/workload_identities.py`:**
  - Validate issuer HTTPS scheme and compile subject pattern glob/regex during policy creation on `POST`.
  - Enforce maximum TTL boundary (`max_ttl_seconds <= 86400`).
- [ ] **`kanban/api/v1/oauth.py`:**
  - Extend `AdminOAuthClientCreateRequest` to accept `pkce_enforce: bool`, `access_token_ttl: int`, and `grant_types: list[str]`.
  - Verify DCR client auto-activation behavior for verified redirect URI patterns.
  - Ensure `GET /api/v1/oauth/device/info` returns rich client metadata and surface scope for `/activate` screen rendering.
  - Verify `MAX_STATE_LEN = 4096` boundary enforcement and RFC 8707 workspace binding on token issuance.
- [ ] **`kanban/api/v1/mcp_keys.py` & `kanban/api/v1/admin/mcp_keys.py`:**
  - Validate CIDR block parsing with strict IPv4/IPv6 validation.
  - Enforce capability bitmask bounds (`0 <= capability_mask <= 255`).
- [ ] **`mcp/app.py`:**
  - Ensure RFC 9728 protected resource metadata endpoints return valid absolute URLs matching `KANBAN_PUBLIC_ORIGIN`.

---

## 5. Phase 3 (`KAN-418`) Credential and Container Checklist

The Phase 3 live workout (`KAN-418`) must execute end-to-end integration tests and capture zero-mock screenshots across all viewports. Below are the staging requirements:

### 5.1 Local Companion Containers & Test Fixtures
- **Hermetic Database State:** Fast clean-DB harness using PostgreSQL template database with sub-millisecond `SAVEPOINT` rollback isolation.
- **Local TLS Staging Stack:** Running via standalone container or local Vite dev server on an ephemeral high port (e.g. `18921` or `8080`) configured with:
  - `KANBAN_PUBLIC_ORIGIN="https://localhost:18921"` (or staging FQDN)
  - `KANBAN_TRUSTED_PROXIES="*"`
  - `KB_FORWARDED_ALLOW_IPS="*"`
- **Mock OIDC Identity Provider:** For headless RFC 8693 workload token exchange tests, utilize local RSA-signed JWT test fixtures with valid JWKS endpoints without requiring external internet egress.

### 5.2 External Provider Staging (Optional / User-Supplied Only)
- **Google Gemini Connected Apps:** Optional live validation against `gemini.google.com/devmode` using an external reverse proxy (e.g. Nginx Proxy Manager with Let's Encrypt TLS) configured with `KANBAN_PUBLIC_ORIGIN`. If external credentials are required, store strictly in `~/.config/kanban/workout.env` (`0600`), never committed to git.
- **Third-Party CI Workloads:** GitHub Actions / GitLab CI workload federation tests can execute against mock OIDC issuers locally unless external user-supplied repository federations are explicitly requested.

### 5.3 Non-Destructive Live Protection Invariant
Under zero circumstances may any workout, script, or automated test perform mutating or destructive operations against the pre-production `👍kanban` instance at `192.168.1.101` (`k.hackedyour.info`). All live validation is confined strictly to local hermetic test containers.

---

## 6. Audit Verification and Sign-Off

### 6.1 Cited File Existence Verification
The following 19 repository paths cited in this audit document have been verified to exist on disk:
- `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`
- `kanban/web/src/features/settings/McpAccessStudio.tsx`
- `kanban/web/src/features/settings/McpUnifiedStudio.tsx`
- `kanban/web/src/features/settings/ConnectOAuthAppModal.tsx`
- `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`
- `kanban/web/src/features/oauth/OAuthClientGovernanceStudio.tsx`
- `kanban/web/src/features/oauth/DeviceActivatePage.tsx`
- `kanban/api/v1/oauth.py`
- `kanban/api/v1/mcp_keys.py`
- `kanban/api/v1/auth_mcp_keys.py`
- `kanban/api/v1/admin/mcp_keys.py`
- `kanban/api/v1/admin/workload_identities.py`
- `kanban/ops/llms_txt.py`
- `mcp/app.py`
- `mcp/protocol.py`
- `mcp/metadata.py`
- `mcp/auth.py`
- `kanban/oauth/server.py`
- `kanban/security/push_protection.py`

### 6.2 Writing Style & Dash Policy Compliance
Verified with `python3 scripts/check_no_dashes.py docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md` and `python3 scripts/check_no_dashes.py --all`. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) are present.

### 6.3 Disposition Count Parity Summary
- **Total Cataloged Settings:** 77
- **KEEP:** 62
- **SIMPLIFY:** 6
- **MOVE_TO_ADVANCED:** 9
