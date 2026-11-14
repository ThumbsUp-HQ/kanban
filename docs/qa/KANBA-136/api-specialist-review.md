# API Specialist Gate Review: KANBA-136 (KB-P4-09b)

- **Ticket**: `KANBA-136` (`KB-P4-09b`: `[Phase 4 / MCP] /mcp/admin tools 3-4: manage_principals_and_groups & manage_access_policies (+ admin REST)`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-136`
- **Worktree**: `/tmp/kb-wt-KANBA-136`
- **Scope**:
  - `kanban/api/v1/admin/principals.py`
  - `kanban/api/v1/admin/acl.py`
  - `kanban/admin/principal_service.py`
  - `kanban/admin/acl_service.py`
  - `mcp/surfaces/admin/manage_principals_and_groups.py`
  - `mcp/surfaces/admin/manage_access_policies.py`
  - `mcp/auth.py`
  - `mcp/errors.py`
  - `mcp/internal_client.py`

---

### 1. Architectural & Security Evaluation

#### A. Administrative REST Endpoints (Spec S11.4, S3.1, S3.2)
- Mounted under `/api/v1/admin/principals` and `/api/v1/admin/acl-entries`.
- Protection:
  - `POST /api/v1/admin/principals`, `PATCH /api/v1/admin/principals/{id}`, `POST/DELETE /api/v1/admin/groups/{id}/members/{principal_id}`, `POST/DELETE /api/v1/admin/role-bindings`, `POST/DELETE /api/v1/admin/acl-entries`: All declare `Depends(require_admin_aal2)` and `Depends(require_workspace_or_server_admin)` at the route dependency layer. MFA AAL2 is strictly enforced (`403 AAL2_REQUIRED` on AAL1 tokens).
  - Anti-lockout defense: Removing or deactivating the last active `SERVER_ADMIN` role binding raises HTTP 409 `lockout-prevented` (`LOCKOUT_PREVENTED`), backed by database trigger and service-layer validation.
  - Principal lifecycle: Deactivation atomically revokes active server sessions and marks all user MCP API keys (`revoked_at = now()`) in the same transaction.
  - Hierarchy controls: Group membership enforces `max_depth <= 8` (`GROUP_DEPTH_EXCEEDED`) and cycle rejection (`GROUP_CYCLE_REJECTED`) via closure triggers.
  - SCRIPT_EPHEMERAL isolation: Transient execution identities are strictly filtered from administrative listing and manual provisioning.

#### B. Access Control & ACL Engine (Spec S3.2, S3.4)
- 8-Capability Bitmask:
  - Canonical enumeration: `VIEW` (1), `COMMENT` (2), `EDIT` (4), `TRANSITION` (8), `LINK` (16), `SHARE` (32), `ADMIN` (64), `DELETE` (128).
  - Validation: Requires 1 to 8 distinct valid capability names; empty lists or unrecognized values fail with HTTP 422 `VALIDATION_FAILED`.
- Explicit Deny Precedence:
  - Direct `DENY` entries override group-inherited `ALLOW` permissions. Recomputed effective capabilities after a `DENY [VIEW]` grant immediately strip access and return 404 on target entities.
- Manifest Endpoint:
  - `GET /api/v1/admin/acl-entries/{object_id}/manifest` requires caller `ADMIN` capability on the target object. Non-admin callers receive byte-identical 404 (if not VIEW-able) or 403 `INSUFFICIENT_PERMISSION`.
  - Privacy and Anti-Enumeration: External collaborators and out-of-boundary guest principals are redacted into `1 External Collaborator` without exposing user handles, IDs, or email addresses.

#### C. MCP Admin Tools (Spec S11.4 Tools 3-4)
- `manage_principals_and_groups`:
  - Actions: `list`, `get`, `provision_user`, `provision_group`, `provision_agent`, `deactivate`, `reactivate`, `add_member`, `remove_member`, `bind_role`, `unbind_role`, `help`.
  - Scopes: `list`/`get`/`help` require `admin:read`; all mutation actions require `admin:write`.
  - Emits compact Spec S11.4 summary YAML output.
- `manage_access_policies`:
  - Actions: `inspect`, `grant`, `revoke`, `help`.
  - Scopes: `inspect`/`help` require `admin:read`; `grant`/`revoke` require `admin:write`.
  - Returns recomputed effective capabilities on mutations and formats the 6 Section 3.4 inspection groupings.

---

### 2. Verification & Test Coverage Audit
- **Unit Test Suite**: 27 unit tests pass in 21.63s with **97% combined test coverage** across all touched modules:
  - `kanban/admin/acl_service.py`: 100%
  - `kanban/admin/principal_service.py`: 95%
  - `kanban/api/v1/admin/acl.py`: 100%
  - `kanban/api/v1/admin/principals.py`: 100%
  - `mcp/surfaces/admin/manage_access_policies.py`: 96%
  - `mcp/surfaces/admin/manage_principals_and_groups.py`: 97%
- **Static Quality**:
  - `uv run ruff check .` passes with 0 errors.
  - `uv run ruff format --check .` passes (1224 files clean).
  - `uv run mypy --strict mcp kanban database` passes with 0 errors across 644 source files.
  - `uv run lint-imports` passes (2/2 contracts kept).
  - `python scripts/license_gate.py` passes (0 violations).
  - `python scripts/check_no_dashes.py --all` passes (0 dash violations).

**Verdict: APPROVED**
