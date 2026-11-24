# UI Specialist Review: KAN-394

## Ticket Reference
- **Ticket ID**: `KAN-394` (`[KB-UX-SETTINGS-HELP-NORMALIZATION] Pin All Setting '?' Helpers Right, Replace Mixed EmojiHint Icons & Document Default Values on All User Input Settings`)
- **Reviewer Persona**: UI/UX Design Specialist (`ui-designer.md` / `ux-architect.md`)
- **Status**: `APPROVED`
- **Date**: 2026-11-24

---

## Ergonomic & Visual Architecture Audit

### 1. Unified '?' Iconography vs Heterogeneous Mixed Icons
- **Findings**: Previously, the settings surfaces had mixed iconography (e.g. `EmojiHint kind="agentSafeNumbering"` rendering `🔢` floating outside label structures while other settings used `FieldHelpHint` rendering `?` inline or unaligned).
- **Verification**: Replaced all instances of `EmojiHint kind="agentSafeNumbering"` across `WorkspaceSettingsPage.tsx`, `ProjectSettingsPage.tsx`, and `CreateProjectModal.tsx` with standard `<FieldHelpHint title="Agent-Safe Sequence Numbering" />` triggers.
- **Ergonomics**: Every setting helper is now uniform across the entire platform, utilizing the canonical 18x18px rounded circular `?` trigger button with 44x44px coarse hit target area on touch viewports.

### 2. Right-Pinned Helper Alignment
- **Findings**: Previous helper icons sat immediately adjacent to varying length text labels, creating jagged visual cadence down form columns.
- **Verification**:
  - Configured `.field-help-hint` with `margin: 0 0 0 auto;` (`margin-left: auto`).
  - Added global form label flex alignment rules targeting:
    - `label:has(> .field-help-hint)`
    - `.kb-label:has(> .field-help-hint)`
    - `.kb-form-label:has(> .field-help-hint)`
    - `.kb-toggle-label:has(> .field-help-hint)`
    - `.kb-checkbox-label:has(> .field-help-hint)`
    - `.kb-create-project-checkbox-row:has(> .field-help-hint)`
    - `.kb-mcp-form-label:has(> .field-help-hint)`
    - `.kb-oauth-form-label:has(> .field-help-hint)`
    - `.custom-field-form-label:has(> .field-help-hint)`
    - `.workflow-form-label:has(> .field-help-hint)`
    - `.auth-editor-label:has(> .field-help-hint)`
    - `.kb-personal-settings-label:has(> .field-help-hint)`
  - Ensured `.kb-toggle-text` has `flex: 1 1 auto;`, keeping checkboxes pinned left, label text centered/filling, and `?` triggers pinned right.

### 3. Popover Card Structure & Default Values
- **Findings**: Users lacked clear documentation on out-of-the-box defaults when configuring integer thresholds, timeout bounds, and quota policies.
- **Verification**:
  - `FieldHelpHintProps.defaultValue` is destructured and rendered inside `.field-help-hint-default` with subhead `Default:` and styled code block `.field-help-hint-code`.
  - Added comprehensive default documentation to all user input settings:
    - `Workspace Name`: `kanban`
    - `Workspace Slug`: `kanban`
    - `Display Name`: `Same as Workspace Name`
    - `Default Project Visibility`: `Workspace (All members can view)`
    - `Granular Field-Level Override Rules`: `Strict workspace inheritance enabled`
    - `Session Idle Timeout (Minutes)`: `30 minutes` (Valid values: 5 to 1440 minutes)
    - `Session Absolute Timeout (Minutes)`: `480 minutes (8 hours)` (Valid values: 60 to 43200 minutes)
    - `Trash Retention Days`: `30 days` (Valid values: 7 to 365 days)
    - `MCP Key Max TTL (Days)`: `90 days` (Valid values: 1 to 365 days)
    - `Air-Gap Mode`: `Disabled (false)`
    - `Agent-Safe Sequence Numbering`: `Enabled (true)` (Workspace/Project/CreateModal)
    - `Enable Issue Export`: `Enabled (true)`
    - `Enable Issue Import`: `Enabled (true)`
    - `Allowed Issue Export Roles`: `Workspace Admin, Project Admin, Member`
    - `Webhook Restrictions`: `HMAC SHA-256 payload signing required`
    - `Project Name`: `My Project`
    - `Description (Markdown)`: `None (blank)`
    - `Exclusive Group`: `None (unrestricted)`
    - `Auto-Archive Days`: `Disabled (blank; e.g. 30 days)`
    - `Cutoff Timeout (ms)`: `30000 ms (30 seconds)`
    - `Temperature`: `0.7` (0.0 to 2.0)
    - `Top-P (Nucleus)`: `1.0` (0.0 to 1.0)
    - `Max Tokens`: `4096 tokens` (1 to 128000 tokens)
    - `Maximum Token Cap`: `0 (Zero-allowance freeze) or positive quota`
    - `Agent Timeout`: `60000 ms (60 seconds)` (1000 to 300000 ms)
    - `Enrollment Token TTL`: `900 seconds (15 minutes)`
    - `Import Batch Size`: `100 items per batch` (10 to 1000 items)
    - `Conflict Resolution Strategy`: `Skip Existing`
    - `MCP Key Expiration`: `30 Days (Max: Workspace TTL)`
    - `Capability Ceiling / Mask`: `31 (Standard Developer Agent)`
    - `Max TTL Seconds`: `3600 seconds (1 hour)`
    - `Timezone`: `UTC`
    - `New Password`: `Minimum 12 characters (14 for Server Admins)`

### 4. Accessibility & Interaction Polish
- Strict zero-inline-style popover positioning conforming to CSP `style-src 'self'`.
- Keyboard navigation: 0ms focus opening, Escape dismissal with focus restoration to trigger, Tab cycling through popover focusables and back to trigger.
- Touch pointers: 44px hit bounds, 180ms hover delay with 120ms hover bridge preventing accidental closing.

## Final Verdict
`APPROVED` - The normalized help hints achieve exceptional UI polish, clean right-edge alignment across all screen sizes, and unambiguous default values for all configuration fields.
