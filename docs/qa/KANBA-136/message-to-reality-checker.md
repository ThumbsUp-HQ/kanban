# Reality-Checker Audit Note: KANBA-136 (KB-P4-09b)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-136` / `KB-P4-09b`: `[Phase 4 / MCP] /mcp/admin tools 3-4: manage_principals_and_groups & manage_access_policies (+ admin REST)`) implements the administrative principal, group, role binding, and access policy REST endpoints and the corresponding MCP admin tools.

1. **Target Files & Components**:
   - `kanban/api/v1/admin/principals.py`: Administrative REST endpoints for identity management:
     * `GET /api/v1/admin/principals` (`require_workspace_or_server_admin`, filter by USER/GROUP/AGENT/SERVICE_PRINCIPAL, limit 1..100)
     * `POST /api/v1/admin/principals` (`require_admin_aal2`, `require_workspace_or_server_admin`, provision user/group/agent)
     * `GET /api/v1/admin/principals/{id}` (`require_workspace_or_server_admin`, retrieve principal detail)
     * `PATCH /api/v1/admin/principals/{id}` (`require_admin_aal2`, `require_workspace_or_server_admin`, deactivate/reactivate principal)
     * `POST /api/v1/admin/groups/{id}/members/{principal_id}` (`require_admin_aal2`, `require_workspace_or_server_admin`, add member)
     * `DELETE /api/v1/admin/groups/{id}/members/{principal_id}` (`require_admin_aal2`, `require_workspace_or_server_admin`, remove member)
     * `POST /api/v1/admin/role-bindings` (`require_admin_aal2`, `require_workspace_or_server_admin`, bind role)
     * `DELETE /api/v1/admin/role-bindings` (`require_admin_aal2`, `require_workspace_or_server_admin`, unbind role)
   - `kanban/api/v1/admin/acl.py`: Administrative REST endpoints for access policy management:
     * `POST /api/v1/admin/acl-entries` (`require_admin_aal2`, `require_workspace_or_server_admin`, grant ALLOW/DENY entry)
     * `DELETE /api/v1/admin/acl-entries` (`require_admin_aal2`, `require_workspace_or_server_admin`, revoke ALLOW/DENY entry)
     * `GET /api/v1/admin/acl-entries/{object_id}/manifest` (`require_workspace_or_server_admin`, inspect access manifest)
   - `kanban/admin/principal_service.py`: Service layer managing principal lifecycle, session invalidation, MCP API key revocation, anti-lockout protection for `SERVER_ADMIN`, group depth limits (max depth 8), and cycle detection.
   - `kanban/admin/acl_service.py`: Service layer managing 8-capability bitmasks, object resolution, direct ALLOW/DENY upsert/delete, and access manifest inspection with anti-enumeration redaction.
   - `mcp/surfaces/admin/manage_principals_and_groups.py`: MCP Tool 3 handling `list`, `get`, `provision_user`, `provision_group`, `provision_agent`, `deactivate`, `reactivate`, `add_member`, `remove_member`, `bind_role`, `unbind_role`, and `help`. Emits Spec S11.4 summary YAML.
   - `mcp/surfaces/admin/manage_access_policies.py`: MCP Tool 4 handling `inspect`, `grant`, `revoke`, and `help`. Returns recomputed effective capabilities and maps the 6 Section 3.4 inspection groupings.
   - `mcp/surfaces/admin/__init__.py`: Registry factory exporting `build_admin_registry` and `create_admin_registry`.
   - `mcp/auth.py`: Scope map configured with `"manage_principals_and_groups": frozenset({"admin:read"})` and `"manage_access_policies": frozenset({"admin:read"})` for protocol dispatcher, with `admin:write` enforced for mutations.
   - `mcp/errors.py`: Registered error codes `GROUP_CYCLE_REJECTED`, `GROUP_DEPTH_EXCEEDED`, `LOCKOUT_PREVENTED`, `AAL2_REQUIRED`, `INSUFFICIENT_PERMISSION`.
   - `mcp/internal_client.py`: Error code mapping and conflict resolution for MCP client invocations.

2. **Security & Redaction Invariants**:
   - **MFA AAL2 Gate**: All mutating operations (`POST`, `PATCH`, `DELETE`) require `Depends(require_admin_aal2)` and reject AAL1 callers with `403 AAL2_REQUIRED`.
   - **Server Admin Anti-Lockout**: Deactivating or unbinding the last active `SERVER_ADMIN` raises HTTP 409 `lockout-prevented` (`LOCKOUT_PREVENTED`).
   - **Atomic Invalidation on Deactivation**: Deactivating a principal revokes active web sessions and marks all user MCP API keys (`revoked_at = now()`) in the same database transaction.
   - **Group Hierarchy Safeguards**: Group cycles trigger `GROUP_CYCLE_REJECTED`, and nesting beyond 8 levels triggers `GROUP_DEPTH_EXCEEDED`.
   - **Anti-Enumeration Redaction**: Out-of-boundary guest principals in access manifests are masked as `1 External Collaborator` with zero handle or email leakage.
   - **Script Identity Isolation**: `SCRIPT_EPHEMERAL` principals are filtered from administrative listings and cannot be provisioned via MCP tools.
   - **Typography Standards**: Strictly plain ASCII hyphens `-` used across all code, comments, reviews, and proof files (zero `U+2014` or `U+2013` unicode dashes).

3. **Verification & Quality Metrics**:
   - **Unit Tests**: 27/27 unit tests pass in 21.63s on dedicated socket `KB_TEST_PGHOST=/tmp/kb-pgsock-21`:
     * `kanban/admin/acl_service.py`: 100%
     * `kanban/admin/principal_service.py`: 95%
     * `kanban/api/v1/admin/acl.py`: 100%
     * `kanban/api/v1/admin/principals.py`: 100%
     * `mcp/surfaces/admin/manage_access_policies.py`: 96%
     * `mcp/surfaces/admin/manage_principals_and_groups.py`: 97%
     * **Combined Total Coverage: 97%** (threshold: >=95%).
   - **Static Analysis**: Clean across `ruff check .`, `ruff format --check .` (1224 files clean), `mypy --strict` (0 errors across 644 source files), `lint-imports` (2 contracts kept, 0 broken), `license_gate.py` (0 violations), and `check_no_dashes.py --all` (0 violations).
   - **MCP Transcript**: `docs/qa/KANBA-136/mcp-transcript.txt` captured via `KB_MCP_TRANSCRIPT_PATH`, demonstrating user/group/agent provisioning, a DENY grant with recomputed effective capabilities, `LOCKOUT_PREVENTED` on last server admin deactivation, and redacted `inspect` output with `external: 1 External Collaborator`.
   - **REST Contract**: `docs/qa/KANBA-136/contract-sample.json` captures all 10 new admin REST endpoints and security error wire exchanges.
   - **Specialist Reviews**: Signed `api-specialist-review.md` and `ui-specialist-review.md` both certifying `Verdict: APPROVED`.
   - **Screenshots**: `Screenshots: N/A - Non-UI Ticket`.
