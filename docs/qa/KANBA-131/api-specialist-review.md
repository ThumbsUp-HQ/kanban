# API Specialist Gate Review: KANBA-131 (KB-P4-09a)

- **Ticket**: `KANBA-131` (`KB-P4-09a`: `[Phase 4 / MCP] /mcp/admin tools 1-2: configure_workspace & manage_auth_cards (+ workspace settings API)`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-131`
- **Branch**: `feat/KANBA-131`
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Verification Matrix

As Systems/Backend Architect & API Specialist, I have performed an exhaustive architectural and API wire contract review of the implementation for `KANBA-131` (`KB-P4-09a`), implementing `/mcp/admin` tools 1-2 (`configure_workspace` and `manage_auth_cards`) and the underlying workspace settings REST API according to `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 11.4, 4.1, 4.3, 10.2), `AGENTS.md`, and `docs/tickets/KB-P4-09a.md`.

The implementation satisfies all architectural, cryptographic, and security invariant requirements:
- **Workspace Settings Schema & RLS**: The `workspace_settings` table implements Row-Level Security (`FORCE ROW LEVEL SECURITY`), strict CHECK constraints on string bounds and numeric ranges (`session_idle_timeout_min BETWEEN 5 AND 720`, `session_absolute_timeout_min BETWEEN 60 AND 10080`, `trash_retention_days BETWEEN 1 AND 365`, `mcp_key_max_ttl_days BETWEEN 1 AND 365`, `session_absolute_timeout_min >= session_idle_timeout_min`), automatic initialization via trigger `initialize_workspace_settings()` on `workspaces` insert, and synchronizes `trash_retention_days` to `workspaces.trash_retention_days`.
- **AAL2 & Admin Route Protection**: `GET` and `PATCH /api/v1/admin/workspace-settings` enforce `Depends(require_admin_aal2)` and restrict access to `SERVER_ADMIN` or `WORKSPACE_ADMIN`. Changing `air_gap_mode` requires an authenticated session/token with `AAL2` authorization (`403 AAL2_REQUIRED` on AAL1 tokens).
- **Activity Ledger Audit Invariants**: Every settings mutation logs `WORKSPACE_SETTINGS_CHANGED` with before/after diffs in the immutable activity ledger. Modifying `air_gap_mode` additionally records `AIR_GAP_MODE_CHANGED`.
- **MCP Admin Surface Isolation & Scopes**: `/mcp/admin` is mounted cleanly in `mcp/app.py` using `create_admin_registry()`. Tool access strictly enforces scoped permissions:
  - `configure_workspace`: `get` requires `admin:read`; `update` requires `admin:write`.
  - `manage_auth_cards`: `list`, `get`, `test_handshake` require `admin:read`; `create`, `update`, `enable`, `disable`, `reorder` require `admin:write`; `delete` requires `admin:destructive` plus matching `confirm_slug` (`CONFIRM_PHRASE_MISMATCH` on mismatch).
  - General agent keys (`kb_agt_*`) are rejected with `403 SURFACE_KEY_MISMATCH` before network dispatch.
- **Write-Only Secrets & Zero-Leakage**: Auth card secrets (`client_secret`, `bind_dn_password`, `encrypted_secret_blob`, `wrapped_dek`) are write-only. They are never returned by the REST API, never echoed in MCP responses, and are systematically redacted with `'***'` by `mcp/yaml_out.py` and test fixtures. Canary audit for `s3cr3t-canary-91` confirmed zero hits in transcripts.
- **Triple-Layer Anti-Lockout Invariants**: Enforces `LOCKOUT_PREVENTED` error propagation mapping upstream stored procedure errors from `kb_auth.*` with layer hints indicating either `db_trigger` (disabling only card for active server admin) or `handshake_probe_15m` (disabling local admin without external admin handshake within 15 minutes).
- **Dynamic Key TTL Capping**: `kanban/security/mcp_keys.py` dynamically queries `workspace_settings.mcp_key_max_ttl_days` when minting MCP API keys.
- **Zero Unicode Dashes**: All documentation and code use standard ASCII hyphens `-` with zero `U+2014` or `U+2013` characters.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Workspace Settings DDL & RLS** | Dedicated table, FORCE RLS, sync triggers | Verified in `schema-dump.sql` | PASS |
| **REST API Boundaries** | GET/PATCH /api/v1/admin/workspace-settings | Verified in `test_workspace_settings.py` (10/10 pass) | PASS |
| **AAL2 & Role Security** | require_admin_aal2, AAL2 on air_gap_mode | Verified: 403 AAL2_REQUIRED on AAL1 | PASS |
| **Activity Ledger** | WORKSPACE_SETTINGS_CHANGED & AIR_GAP_MODE_CHANGED | Verified in activity assertions | PASS |
| **MCP Admin Registry** | Exactly configure_workspace & manage_auth_cards | Verified in `mcp/surfaces/admin/__init__.py` | PASS |
| **Scope Enforcement** | admin:read, admin:write, admin:destructive | Verified in test_manage_auth_cards_scope_enforcement | PASS |
| **Secret Redaction** | Zero secret fields in get/list; transcript canary 0 hits | Verified in `secret-canary-grep.txt` (0 hits) | PASS |
| **Lockout Protection** | LOCKOUT_PREVENTED with db_trigger & handshake_probe_15m hints | Verified in `test_manage_auth_cards_lockout_layers` | PASS |
| **Unit Test Coverage** | >= 95% line and branch coverage across touched modules | Total Coverage: **97%** (24/24 tests pass) | PASS |
| **Static Analysis** | Ruff clean, Mypy strict clean, Lint-Imports clean | Verified in `build-check.txt` | PASS |

---

## 2. Architectural Audit Findings

### 2.1 Schema & Security Isolation (`workspace_settings`)
The migration `database/migrations/sql/p4_09a_workspace_settings.up.sql` creates the table with `FORCE ROW LEVEL SECURITY`. Default policies ensure tenant isolation: workspace members can only view settings for their active workspace, while mutations require admin authority. An insert trigger ensures every workspace is automatically provisioned with a default row.

### 2.2 Auth Card Protection & Access Invariants
The implementation respects the strict security boundary on `auth_provider_cards` (where direct SELECT is revoked from `kanban_app`). By routing card queries and administrative actions through `kb_auth.*` SECURITY DEFINER stored procedures (`card_admin_get`, `card_admin_list`, etc.), the architecture maintains least-privilege database access without compromising RLS or leaking credential blobs.

### 2.3 Anti-Lockout Invariants
Both layers of lockout prevention specified in S4.3 are operational:
1. `db_trigger`: Database trigger `auth_cards_prevent_lockout` blocks disabling the only enabled card associated with an active `SERVER_ADMIN`.
2. `handshake_probe_15m`: Disabling the `LOCAL_ADMIN` card is rejected unless an external provider card has successfully verified a handshake within the past 15 minutes.
Both conditions map cleanly to `LOCKOUT_PREVENTED` with descriptive diagnostic hints.

---

## 3. Verdict

The implementation of `KANBA-131` (`KB-P4-09a`) adheres strictly to all architectural specifications, security boundaries, and wire contract requirements.

**Verdict: APPROVED**
