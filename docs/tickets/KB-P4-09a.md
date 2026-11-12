---
id: KB-P4-09a
title: "[Phase 4 / MCP] /mcp/admin tools 1-2: configure_workspace & manage_auth_cards (+ workspace settings API)"
epic: KB-E4
depends_on: [KB-P4-03, KB-P4-02b, KB-P2-10, KB-P2-09]
spec_sections: ["11.4", "4.1", "4.3", "10.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

### User Story
As a **Server or Workspace Admin operating through an admin agent**, I need **`configure_workspace` to read and change workspace branding, security defaults, retention windows, and `air_gap_mode`, and `manage_auth_cards` to create, test, toggle, and reorder authentication cards** so that **I can administer identity and workspace policy via MCP while the `LOCKOUT_PREVENTED` invariant and write-only secret handling still hold.**

**Requirement Traceability:** `S11.4` tools 1-2, `S4.1` (card schema, encrypted secrets never returned), `S4.3` (`LOCKOUT_PREVENTED` 3 layers), `S10.2` (`air_gap_mode`), requirement `#6`, `#12` | **Dependencies:** `KB-P4-03`, `KB-P4-02b`, `KB-P2-10`, `KB-P2-09`

> Split note: manifest row KB-P4-09 (admin tools 1-4) is split into `KB-P4-09a` (tools 1-2, this ticket) and `KB-P4-09b` (tools 3-4) because no prior ticket provides workspace-settings, principal-provisioning, or ACL-grant REST endpoints; each half adds its own backend endpoints.

### Scoped Technical Actions
1. **Target Files:** `database/migrations/versions/<rev>_workspace_settings.py`, `database/models/workspace_settings.py`, `kanban/api/v1/admin/workspace_settings.py` (`GET/PATCH /api/v1/admin/workspace-settings`), `mcp/surfaces/admin/__init__.py` (registry; removes `ping_admin`), `mcp/surfaces/admin/configure_workspace.py`, `mcp/surfaces/admin/manage_auth_cards.py`, `mcp/auth.py`.
2. **DDL `workspace_settings`** (one row per workspace, FORCE RLS):
   ```sql
   CREATE TABLE workspace_settings (
       workspace_id                  UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
       display_name                  TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
       default_project_visibility    TEXT NOT NULL DEFAULT 'private' CHECK (default_project_visibility IN ('private','workspace')),
       session_idle_timeout_min      INTEGER NOT NULL DEFAULT 60 CHECK (session_idle_timeout_min BETWEEN 5 AND 720),
       session_absolute_timeout_min  INTEGER NOT NULL DEFAULT 720 CHECK (session_absolute_timeout_min BETWEEN 60 AND 10080),
       trash_retention_days          INTEGER NOT NULL DEFAULT 30 CHECK (trash_retention_days BETWEEN 1 AND 365),
       mcp_key_max_ttl_days          INTEGER NOT NULL DEFAULT 90 CHECK (mcp_key_max_ttl_days BETWEEN 1 AND 365),
       air_gap_mode                  BOOLEAN NOT NULL DEFAULT FALSE,
       updated_at                    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
       CHECK (session_absolute_timeout_min >= session_idle_timeout_min)
   );
   ```
   Every PATCH writes `WORKSPACE_SETTINGS_CHANGED` activity with the before/after diff; toggling `air_gap_mode` writes `AIR_GAP_MODE_CHANGED` and requires session/token AAL2. KB-P4-02a minting reads `mcp_key_max_ttl_days` as the cap (one-line change in `kanban/security/mcp_keys.py`).
3. **`configure_workspace`** input: `{action: enum [get, update, help] (required), settings: {display_name, default_project_visibility, session_idle_timeout_min, session_absolute_timeout_min, trash_retention_days, mcp_key_max_ttl_days, air_gap_mode}}`. `get` -> `admin:read`; `update` -> `admin:write`. Unknown setting key -> `VALIDATION_FAILED`. `summary` response:
   ```yaml
   workspace: Engineering
   air_gap_mode: false
   trash_retention_days: 30
   session: {idle_min: 60, absolute_min: 720}
   mcp_key_max_ttl_days: 90
   ```
4. **`manage_auth_cards`** input:
   ```yaml
   action: {enum: [list, get, create, update, enable, disable, reorder, test_handshake, delete, help]}   # required
   card: {type: string}                    # slug or uuid (all except list/create/help)
   provider_kind: {enum: [OIDC, OAUTH2, LDAP, LOCAL_ADMIN]}   # create
   display_name / button_subtext / icon_preset: {type: string}
   public_config: {type: object}           # validated by KB-P2-10 per provider_kind
   secret: {type: object, writeOnly: true} # client_secret | bind_dn_password; never echoed
   allowed_email_domains: {type: array, items: string, maxItems: 50}
   auto_provision_users: {type: boolean}
   after: {type: string}                   # reorder: place after this card slug ("" = first)
   confirm_slug: {type: string}            # delete: must equal the card slug
   ```
   - Maps 1:1 onto KB-P2-10 endpoints. `list`/`get`/`test_handshake` -> `admin:read`; `create`/`update`/`enable`/`disable`/`reorder` -> `admin:write`; `delete` -> `admin:destructive` and `confirm_slug` equal to slug (`CONFIRM_PHRASE_MISMATCH` otherwise).
   - `secret` values are redacted by the transcript fixture and by `mcp/yaml_out.py` (any key named `secret`, `client_secret`, `bind_dn_password` is replaced with `"***"` if it ever appears in a response, plus a test asserting kanban-api never returns them).
   - Upstream `P0001 LOCKOUT_PREVENTED` (surfaced by KB-P2-09/10 as `409` problem type `lockout-prevented`) -> MCP `LOCKOUT_PREVENTED` with hint naming the layer (`db_trigger` or `handshake_probe_15m`).
   - `summary` response for `list`:
   ```yaml
   cards:
     - {slug: okta-sso, kind: OIDC, enabled: true, rank: 1, health: OK}
     - {slug: local-admin, kind: LOCAL_ADMIN, enabled: true, rank: 2, health: OK}
   ```
5. **Error codes appended:** `LOCKOUT_PREVENTED`, `CONFIRM_PHRASE_MISMATCH`, `AAL2_REQUIRED`.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_workspace_settings.py` (clean-DB harness), `mcp/tests/admin/test_configure_workspace.py`, `mcp/tests/admin/test_manage_auth_cards.py`
- **Required Test Cases:**
  1. Positive: `configure_workspace(get)` returns the defaults; `update` `trash_retention_days=45` persists and writes `WORKSPACE_SETTINGS_CHANGED`; `manage_auth_cards` creates an OIDC card with a secret, lists it without any secret field, reorders it first, toggles enable.
  2. Lockout/security: disabling the only card that authenticates a `SERVER_ADMIN` -> `LOCKOUT_PREVENTED` (layer `db_trigger`); disabling `LOCAL_ADMIN` without a successful external admin handshake in the last 15 minutes -> `LOCKOUT_PREVENTED` (layer `handshake_probe_15m`); `delete` with wrong `confirm_slug` -> `CONFIRM_PHRASE_MISMATCH`; `admin:write` key calling `delete` -> `INSUFFICIENT_SCOPE`; `kb_agt_` key on `/mcp/admin` -> `403`.
  3. Secret non-disclosure: grep of the full captured transcript for the test secret value `s3cr3t-canary-91` returns `0` matches; every `get`/`list` response lacks `encrypted_secret_blob`, `wrapped_dek`, `client_secret`.
  4. Boundary: `trash_retention_days` 0 and 366 -> `VALIDATION_FAILED`; idle 721 -> `VALIDATION_FAILED`; absolute < idle -> `VALIDATION_FAILED`; `air_gap_mode=true` via an AAL1 OAuth token -> `AAL2_REQUIRED`; 51 email domains -> `VALIDATION_FAILED`.
  5. RLS: workspace B admin `get` returns workspace B row only.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** target files exist; DDL matches Action 2; 2 admin tools registered on `/mcp/admin` only.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_workspace_settings.py mcp/tests/admin/test_configure_workspace.py mcp/tests/admin/test_manage_auth_cards.py -q --cov=mcp --cov=kanban.api --cov-branch --cov-report=term-missing` exits `0`, `0` failures, touched-module coverage `>= 95%`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict mcp kanban database && uv run lint-imports` exits `0`.
- [ ] **Secret Canary:** `docs/qa/<TICKET_ID>/secret-canary-grep.txt` shows `grep -c 's3cr3t-canary-91' docs/qa/<TICKET_ID>/mcp-transcript.txt` output `0`.
- [ ] **Transcript Captured:** `docs/qa/<TICKET_ID>/mcp-transcript.txt` includes both `LOCKOUT_PREVENTED` variants and a successful reorder.
- [ ] **Forensic Proof Packet Complete:** all files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - `workspace_settings` schema + policies.
5. `docs/qa/<TICKET_ID>/mcp-transcript.txt` - captured via `KB_MCP_TRANSCRIPT_PATH`.
6. `docs/qa/<TICKET_ID>/secret-canary-grep.txt`
7. `docs/qa/<TICKET_ID>/api-specialist-review.md`
8. `docs/qa/<TICKET_ID>/ui-specialist-review.md`
9. Screenshots: N/A - Non-UI Ticket.
