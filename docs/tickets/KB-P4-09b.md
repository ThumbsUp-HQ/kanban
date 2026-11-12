---
id: KB-P4-09b
title: "[Phase 4 / MCP] /mcp/admin tools 3-4: manage_principals_and_groups & manage_access_policies (+ admin REST)"
epic: KB-E4
depends_on: [KB-P4-09a, KB-P2-11, KB-P1-13, KB-P1-03]
spec_sections: ["11.4", "3.1", "3.2", "3.4"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

### User Story
As a **Workspace Admin**, I need **`manage_principals_and_groups` to provision and deactivate users, groups, and service agents, manage memberships and role bindings, and `manage_access_policies` to inspect an object's `access_manifest` and grant or revoke `ALLOW`/`DENY` capabilities** so that **all identity and sharing administration is possible via MCP with explicit-deny precedence, no cross-workspace enumeration, and no way to remove the last Server Admin.**

**Requirement Traceability:** `S11.4` tools 3-4, `S3.1` (principal types, closure `max_depth <= 8`), `S3.2` (capabilities, explicit deny precedence), `S3.4` (redaction), requirement `#1`, `#12` | **Dependencies:** `KB-P4-09a`, `KB-P2-11`, `KB-P1-13`, `KB-P1-03`

> Split note: second half of manifest row KB-P4-09 (see `KB-P4-09a`).

### Scoped Technical Actions
1. **Target Files:** `kanban/api/v1/admin/principals.py`, `kanban/api/v1/admin/acl.py`, `kanban/admin/principal_service.py`, `kanban/admin/acl_service.py`, `mcp/surfaces/admin/manage_principals_and_groups.py`, `mcp/surfaces/admin/manage_access_policies.py`, `mcp/auth.py`.
2. **REST endpoints (Workspace Admin, AAL2 for writes; all write `activity_records`):**
   - `GET/POST /api/v1/admin/principals`, `PATCH /api/v1/admin/principals/{id}` (`status: active|deactivated`, `display_name`).
   - `POST/DELETE /api/v1/admin/groups/{id}/members/{principal_id}`.
   - `POST/DELETE /api/v1/admin/role-bindings` `{principal_id, role, scope_type: server|workspace|project, scope_id}` (roles = the enum defined by KB-P1-13).
   - `POST/DELETE /api/v1/admin/acl-entries` `{object_id, principal_id, effect: ALLOW|DENY, capabilities: [..]}`.
   - Deactivation revokes the principal's sessions (KB-P2-02) and MCP API keys (`revoked_at = now()`, KB-P4-02a) in the same transaction.
   - Removing/deactivating the last active `SERVER_ADMIN` binding -> `409` problem `lockout-prevented`.
3. **`manage_principals_and_groups`** input:
   ```yaml
   action: {enum: [list, get, provision_user, provision_group, provision_agent, deactivate, reactivate, add_member, remove_member, bind_role, unbind_role, help]}  # required
   principal: {type: string}        # "@handle" | group name | agent slug | uuid
   group: {type: string}            # add_member/remove_member target group
   handle: {type: string, pattern: "^[a-z0-9][a-z0-9._-]{1,38}$"}
   display_name: {type: string, maxLength: 120}
   email: {type: string, format: email}
   role: {type: string}             # KB-P1-13 role enum
   scope: {type: string}            # "server" | "workspace" | project key
   filter: {enum: [USER, GROUP, AGENT, SERVICE_PRINCIPAL]}   # list
   limit: {type: integer, minimum: 1, maximum: 100, default: 50}
   ```
   `list`/`get` -> `admin:read`; all other actions -> `admin:write`. `SCRIPT_EPHEMERAL` principals are never listed or provisioned through this tool. `summary` response for `get`:
   ```yaml
   principal: "@maya"
   type: USER
   status: active
   groups: [Core Backend]
   roles: [{role: MEMBER, scope: KAN}]
   ```
4. **`manage_access_policies`** input:
   ```yaml
   action: {enum: [inspect, grant, revoke, help]}   # required
   object: {type: string}          # any object ref: KAN, KAN-142, page path, uuid
   principal: {type: string}
   effect: {enum: [ALLOW, DENY]}
   capabilities: {type: array, items: {enum: [VIEW, COMMENT, EDIT, TRANSITION, LINK, SHARE, ADMIN, DELETE]}, minItems: 1, maxItems: 8}
   ```
   `inspect` -> `admin:read`, returns the KB-P2-11 `access_manifest` (redaction preserved). `grant`/`revoke` -> `admin:write`; caller must hold `ADMIN` on the object (else `NOT_FOUND` if not VIEW-able, `INSUFFICIENT_PERMISSION` if VIEW-able). Response includes recomputed effective capabilities for the target principal. `summary` response for `inspect`:
   ```yaml
   object: KAN-142
   inherited_scope: "Project: KAN"
   users: [{who: "@adam", caps: ADMIN}, {who: "@maya", caps: EDIT}]
   groups: [{who: SecOps Reviewers, members: 4, caps: COMMENT}]
   agents: [{who: forensic-code-check, caps: VIEW}]
   restricted: [{who: Contractors, effect: DENY}]
   external: "1 External Collaborator"
   ```
5. **Error codes appended:** `INSUFFICIENT_PERMISSION`, `GROUP_CYCLE_REJECTED` (closure trigger cycle), `GROUP_DEPTH_EXCEEDED` (`> 8`); reuses `LOCKOUT_PREVENTED`.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_admin_principals.py`, `kanban/tests/api/test_admin_acl.py` (clean-DB harness), `mcp/tests/admin/test_manage_principals.py`, `mcp/tests/admin/test_manage_access_policies.py`
- **Required Test Cases:**
  1. Positive: provision user `maya`, group `Core Backend`, agent `forensic-code-check`; add maya to the group; bind `MEMBER` on `KAN`; `grant ALLOW [VIEW, COMMENT]` to the group on `KAN-142`; `inspect` shows the group with `COMMENT`.
  2. Deny precedence/security: `grant DENY [VIEW]` to maya on `KAN-142` while her group has ALLOW -> recomputed effective caps exclude VIEW and maya's `read_ticket KAN-142` (via KB-P4-04 if merged, else `GET /api/v1/issues/{id}`) returns 404; `inspect` by a non-admin -> `INSUFFICIENT_SCOPE`/`INSUFFICIENT_PERMISSION`; referencing a principal from another workspace -> `NOT_FOUND`.
  3. Lockout: deactivating or unbinding the last `SERVER_ADMIN` -> `LOCKOUT_PREVENTED`; deactivating a user revokes that user's MCP keys (introspection returns inactive) in the same transaction.
  4. Boundary: group A contains B, adding A into B -> `GROUP_CYCLE_REJECTED`; nesting depth 9 -> `GROUP_DEPTH_EXCEEDED`; `capabilities: []` -> `VALIDATION_FAILED`; handle `-bad` -> `VALIDATION_FAILED`; `limit=101` -> `VALIDATION_FAILED`.
  5. Redaction: `inspect` output for an object shared with an out-of-boundary principal contains `external: "1 External Collaborator"` and no email or handle of that principal.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** target files exist; REST endpoints in Action 2 and 2 MCP tools implemented.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_admin_principals.py kanban/tests/api/test_admin_acl.py mcp/tests/admin/test_manage_principals.py mcp/tests/admin/test_manage_access_policies.py -q --cov=mcp --cov=kanban.admin --cov-branch --cov-report=term-missing` exits `0`, `0` failures, coverage `>= 95%`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict mcp kanban && uv run lint-imports` exits `0`.
- [ ] **Transcript Captured:** `docs/qa/<TICKET_ID>/mcp-transcript.txt` includes provisioning, a DENY grant with recomputed caps, `LOCKOUT_PREVENTED`, and a redacted `inspect`.
- [ ] **Forensic Proof Packet Complete:** all files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/mcp-transcript.txt` - captured via `KB_MCP_TRANSCRIPT_PATH`.
5. `docs/qa/<TICKET_ID>/contract-sample.json` - raw REST request/response pairs for each new admin endpoint.
6. `docs/qa/<TICKET_ID>/api-specialist-review.md`
7. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - review that `inspect` YAML mirrors the `🛡️` Effective Access Inspector groupings (S3.4).
8. Screenshots: N/A - Non-UI Ticket.
