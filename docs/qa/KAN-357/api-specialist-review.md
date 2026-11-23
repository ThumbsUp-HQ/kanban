# API Specialist Review (KAN-357 / KB-A11Y-FORM-INPUTS)

## Overview & Architecture Verification

- **Ticket**: KAN-357 (`[KB-A11Y-FORM-INPUTS] Accessible Names, Associated Form Labels, and Error Announcements Across Issue Creation, Custom Fields, and Settings Studios`)
- **Modules**: `kanban/web/src/features/views/`, `kanban/web/src/features/settings/`, `kanban/web/src/features/admin-auth/`, `kanban/web/src/features/custom-fields/`, `kanban/web/src/features/a11y/`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The programmatic label associations and accessible error announcements implemented across issue creation, settings, admin auth, MCP studio, and custom fields adhere strictly to Priority #0 Security-First and Priority #1 Agent-First architecture.

### 1. Form Payload Serialization & Parameter Integrity
- **`QuickCreateIssueModal.tsx`**:
  - Binding `htmlFor="quick-create-summary"`, `htmlFor="quick-create-description"`, `htmlFor="quick-create-state"`, `htmlFor="quick-create-priority"`, `htmlFor="quick-create-module"`, and `htmlFor="quick-create-draft"` maintains 100% two-way data-binding fidelity with backend issue creation contracts (`POST /api/v1/projects/{project_key}/issues`).
  - Added `aria-invalid={Boolean(submitError)}` and `aria-describedby={submitError ? 'quick-create-error-msg' : undefined}` without altering request payload schemas or execution flow.
- **`ProjectSettingsPage.tsx`**:
  - Workflow state parameters (`name`, `group`, `color_hex`, `sort_order`, `is_default`, `wip_soft_limit`, `wip_hard_limit`), priority definitions (`slug`, `label`, `emoji`, `sort_order`, `color_hex`, `is_default`), label creations, and module toggles continue to serialize with complete fidelity to backend REST endpoints.
  - Soft WIP vs. hard WIP client-side validation (`wip_soft_limit <= wip_hard_limit`) prevents malformed concurrency limits from reaching Postgres.
- **`WorkspaceSettingsPage.tsx`**:
  - Export role permissions (`issueExportAllowedRoles`), principal creation (`newHandle`, `newDisplayName`, `newEmail`, `newPassword`, `newRole`), and group governance mutations serialize cleanly to `/api/v1/admin/*` endpoints with CSRF token protection intact.
- **`AuthCardEditorDrawer.tsx`**:
  - Preserves write-only secret contract (omitting `secret_input` on existing cards unless explicitly replaced).
  - Validates OIDC, OAuth2, and LDAP configuration fields (`slug`, `display_name`, `client_id`, `issuer_url`, `server_url`, `bind_dn`, `base_dn`, `spki_pin`), rendering dynamic error announcements while keeping submission payloads strictly typed.
- **`McpAccessStudio.tsx`**:
  - Key minting payload (`label`, `surface`, `scopes`, `scope_tier`, `allowed_cidrs`, `expiry_days`) preserves full compatibility with MCP server endpoints (`POST /api/v1/mcp/keys`).
  - Downward capability narrowing and CIDR parsing enforce security boundaries without privilege escalation.
- **`CustomFieldDefinitionEditor.tsx`**:
  - Format configuration metadata JSON and sandbox script source code serialize accurately to `/api/v1/projects/{project_key}/custom-fields`.

### 2. State Synchronization & Error Recovery Contracts
- **Error Announcement Linking**: When validation fails, inputs dynamically receive `aria-invalid="true"` and `aria-describedby` pointing to the alert element's ID (`quick-create-error-msg`, `wip-limit-error`, `card-*-error`, `cidr-error-message`, `format-metadata-error`).
- **Dynamic Recovery**: Correcting input values immediately clears `aria-invalid` back to `"false"` or removes the attribute, and detaches `aria-describedby`, guaranteeing assistive technology announces state restoration without stale warnings.

### 3. Specialist Verdict
The accessibility bindings preserve complete API contract fidelity, input sanitization invariants, and submission payload integrity across all studios.
**STATUS: APPROVED**
