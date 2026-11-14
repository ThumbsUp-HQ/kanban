# API Specialist Gate Review: KANBA-138 (KB-P4-11)

- **Ticket**: `KANBA-138` (`KB-P4-11`: `/mcp/admin` tools 10-11: `override_ticket_provenance` & `audit_and_purge_object_links` (+ link auditor admin REST))
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-138`
- **Worktree**: `/tmp/kb-wt-KANBA-138`
- **Scope**:
  - `kanban/api/v1/admin/link_auditor.py`
  - `kanban/api/v1/schemas/link_auditor.py`
  - `kanban/services/link_auditor_admin.py`
  - `kanban/api/v1/issue_archive.py`
  - `kanban/api/v1/schemas/issue_move.py`
  - `kanban/services/issue_archive.py`
  - `kanban/services/issue_move.py`
  - `mcp/surfaces/admin/override_ticket_provenance.py`
  - `mcp/surfaces/admin/audit_and_purge_object_links.py`
  - `mcp/surfaces/admin/__init__.py`
  - `mcp/auth.py`
  - `mcp/errors.py`
  - `mcp/internal_client.py`

---

### 1. Architectural & Security Evaluation

#### A. Admin Link Auditor REST Endpoints (Spec S11.4, S12.3)
- Mounted under `/api/v1/admin/object-links:*` and `/api/v1/admin/object-links/audits`.
- Protection:
  - `POST /api/v1/admin/object-links:audit`: Requires `Depends(require_admin_aal2)` and `require_workspace_or_server_admin`. Enforces caller MFA AAL2 (`403 AAL2_REQUIRED` on AAL1 tokens) and workspace or server administrator authorization (`403 INSUFFICIENT_CAPABILITY` on project-only admins). Invokes `audit_object_links(:workspace_id)` inside the admin RLS session.
  - `GET /api/v1/admin/object-links/audits`: Requires workspace or server admin authorization. Supports filtering by `reason_code` (all 6 invalidity classes) and `status` (`unpurged`, `purged`, `resolved`, `all`), keyset cursor pagination (`_encode_cursor`/`_decode_cursor`), and bounds checking (`limit` 1..100).
  - `POST /api/v1/admin/object-links:purge`: Requires `Depends(require_admin_aal2)` and `require_workspace_or_server_admin`. Validates `audit_ids` (1..200 items) and mandatory audit `reason` (10..500 characters). Performs pre-check verification confirming all audit IDs are flagged as unpurged, returning HTTP 409 `LINK_NOT_FLAGGED` on non-existent or active links. Calls `purge_invalid_object_links(audit_ids, actor_id, reason)` which removes links and logs immutable `INVALID_OBJECT_LINK_PURGED` activity rows.

#### B. Issue Archive & Hard WIP Limit Enhancements (Spec S7.2 8p, S6.4)
- `kanban/api/v1/issue_archive.py` & `kanban/services/issue_archive.py`:
  - `IssueUnarchiveRequest` accepts optional `reason` (required during admin overrides) and optional `admin_override: bool = False`.
  - When unarchived with admin override, the activity ledger payload records `{reason, admin_override: true}`.
- `kanban/api/v1/schemas/issue_move.py` & `kanban/services/issue_move.py`:
  - `IssueMoveResponse` exposes `hard_limit: int | None` and `resulting_count: int` so MCP callers and UI clients receive exact WIP state after hard-limit overrides.

#### C. Tool 10: `override_ticket_provenance` (Spec S11.4 Tool 10, S7.2 8d)
- Schema strictly enforces `additionalProperties: false`.
- Actions:
  - `override_creator`: Dispatches `PATCH /api/v1/issues/{id}/created-by`, preserving `original_created_by`, setting new creator, and returning compact summary YAML. Correctly formats and redacts external guest collaborator identities.
  - `override_hard_wip_move`: Resolves issue project and target state, checks target state WIP configuration, dispatches `POST /api/v1/issues/{id}/move` with `wip_override_reason=reason`, and returns `{status: wip_overridden_moved, issue, state, resulting_count, hard_limit}`.
  - `unarchive_issue`: Dispatches `POST /api/v1/issues/{id}/unarchive` with `{"reason": reason, "admin_override": true}`. Returns conflict `NOT_ARCHIVED` if ticket is active.
  - `help`: Returns tool documentation and schema guidance without dispatching upstream requests.
- Security: Enforces `admin:write` scope, caller AAL2 step-up verification, and project or server admin role.

#### D. Tool 11: `audit_and_purge_object_links` (Spec S11.4 Tool 11, S12.3)
- Schema strictly enforces `additionalProperties: false`.
- Actions:
  - `run_audit`: Dispatches `POST /api/v1/admin/object-links:audit`, returning compact grouped counts across all 6 S12.3 invalidity reasons.
  - `list_flagged`: Dispatches `GET /api/v1/admin/object-links/audits`, supporting LOD tiers (`summary`, `standard`, `full`), `reason_filter`, `limit`, and `cursor`.
  - `purge_audited`: Enforces `admin:destructive` scope tier (`INSUFFICIENT_SCOPE` otherwise). Requires `audit_ids` (1..200) and `reason` (10..500 chars). Returns `{status: purged, purged_count, activity_ids}`.
  - `help`: Returns tool action documentation.

#### E. Error Handling & Surface Isolation (Spec S2.4, S11.2)
- Rejection of agent keys (`kb_agt_*`) on `/mcp/admin` with HTTP 403 `SURFACE_KEY_MISMATCH`.
- Rejection of write-only keys on `purge_audited` with `INSUFFICIENT_SCOPE`.
- Registered error codes in `mcp/errors.py`: `LINK_NOT_FLAGGED`, `CREATOR_NOT_ELIGIBLE`, `CREATOR_UNCHANGED`, `NOT_ARCHIVED`.
- RFC 9457 problem detail mapping verified in `mcp/internal_client.py`.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 23/23 pytest passed in 3.48s:
  - `kanban/tests/api/test_admin_link_auditor.py`: 4/4 passed (100% API and service coverage).
  - `mcp/tests/admin/test_override_ticket_provenance.py`: 10/10 passed (97% coverage).
  - `mcp/tests/admin/test_audit_and_purge_links.py`: 9/9 passed (96% coverage).
- **Coverage**: 97.81% total module coverage across all 4 touched modules (exceeds >= 95% threshold).
- **Static Analysis**: Ruff check clean, Ruff format clean, Mypy strict clean (665 files), ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.
- **Proof Bundle**: Complete forensic proof bundle (`unit-test-results.txt`, `build-check.txt`, `mcp-transcript.txt`, `contract-sample.json`, `git-diff.patch`).

---

### 3. Gate Verdict

The admin REST endpoints and MCP admin tools 10-11 comply with all architectural specifications, role hierarchy constraints, AAL2 security requirements, and test coverage standards.

**Verdict: APPROVED**
