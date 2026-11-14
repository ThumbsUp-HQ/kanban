# Reality-Checker Audit Note: KANBA-138 (KB-P4-11)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-138` / `KB-P4-11`: `[Phase 4 / MCP] /mcp/admin tools 10-11: override_ticket_provenance & audit_and_purge_object_links (+ link auditor admin REST)`) implements the administrative link auditor REST endpoints and the corresponding MCP admin tools for provenance overrides, Hard WIP limit overrides, unarchivals, and universal object graph audit/purge.

1. **Target Files & Components**:
   - `kanban/api/v1/admin/link_auditor.py`: Three admin REST endpoints mounted under `/api/v1/admin`:
     * `POST /api/v1/admin/object-links:audit` (`require_admin_aal2`, `require_workspace_or_server_admin`)
     * `GET /api/v1/admin/object-links/audits` (`require_workspace_or_server_admin`, keyset cursor pagination, reason and status filters)
     * `POST /api/v1/admin/object-links:purge` (`require_admin_aal2`, `require_workspace_or_server_admin`, pre-check verifying unpurged audit records, 409 `LINK_NOT_FLAGGED`)
   - `kanban/api/v1/schemas/link_auditor.py`: Pydantic models for link audit scan reports, audit listing with keyset cursor, and audited purge payloads.
   - `kanban/services/link_auditor_admin.py`: Database operations calling PostgreSQL `audit_object_links()` and `purge_invalid_object_links()`, enforcing status/reason filters, keyset cursor pagination (`_encode_cursor`/`_decode_cursor`), and 409 `LINK_NOT_FLAGGED` pre-checks.
   - `kanban/api/v1/issue_archive.py` & `kanban/services/issue_archive.py`: `IssueUnarchiveRequest(reason, admin_override)` with activity payload recording `{reason, admin_override: true}`.
   - `kanban/api/v1/schemas/issue_move.py` & `kanban/services/issue_move.py`: Added `hard_limit` and `resulting_count` to `IssueMoveResponse`.
   - `mcp/errors.py`: Registered error codes `LINK_NOT_FLAGGED`, `CREATOR_NOT_ELIGIBLE`, `CREATOR_UNCHANGED`, `NOT_ARCHIVED`, `AAL2_REQUIRED`, `INSUFFICIENT_PERMISSION`.
   - `mcp/internal_client.py`: Mapped HTTP problem types and codes to MCP error codes with zero branch/cyclomatic warnings.
   - `mcp/surfaces/admin/override_ticket_provenance.py`: MCP Tool 10 handling `override_creator`, `override_hard_wip_move`, `unarchive_issue`, and `help`. Supports both full `IssueResponse` and summary dicts.
   - `mcp/surfaces/admin/audit_and_purge_object_links.py`: MCP Tool 11 handling `run_audit`, `list_flagged` (LODs summary, standard, full), `purge_audited` (enforcing `admin:destructive`), and `help`.
   - `mcp/surfaces/admin/__init__.py`: Registry factory exporting `build_admin_registry` and `create_admin_registry`.
   - `mcp/auth.py`: Scope map configured with `"audit_and_purge_object_links": frozenset({"admin:read"})` for middleware entry, action-level checks inside tool handler.
   - `mcp/app.py`: Constructed with `build_admin_registry(active_internal_client)` by default.

2. **Security & Redaction Invariants**:
   - **MFA AAL2 Gate**: Caller AAL2 verification is enforced on `override_creator`, `purge_audited`, and the underlying `/admin/object-links:*` REST endpoints.
   - **Role Hierarchy**: Project admins are rejected with `403 INSUFFICIENT_CAPABILITY` on workspace-wide link audit/purge operations.
   - **Scope Tier Separation**: `purge_audited` strictly requires `admin:destructive` scope. Keys with `admin:write` or `admin:read` only reject with `INSUFFICIENT_SCOPE`.
   - **Surface Key Isolation**: Agent keys (`kb_agt_*`) are rejected with `403 SURFACE_KEY_MISMATCH` on `/mcp/admin`.
   - **Active Link Protection**: Passing non-existent or active link IDs to purge rejects with `LINK_NOT_FLAGGED` without deleting records.
   - **Zero Secret Leaks**: Transcripts and wire exchanges redact all tokens and session secrets.
   - **Typography Standards**: Zero Unicode em/en-dashes (`U+2014`, `U+2013`); ASCII hyphens `-` only.

3. **Verification & Quality Metrics**:
   - **Unit Tests**: 23/23 pytest passed in 3.48s:
     * `kanban/api/v1/admin/link_auditor.py`: 100%
     * `kanban/services/link_auditor_admin.py`: 100%
     * `mcp/surfaces/admin/override_ticket_provenance.py`: 97%
     * `mcp/surfaces/admin/audit_and_purge_object_links.py`: 96%
     * **Total Coverage: 97.81%** (threshold: >=95%).
   - **Static Analysis**: Clean across `ruff check .`, `ruff format --check .`, `mypy --strict`, `lint-imports` (2 kept, 0 broken), `license_gate.py` (0 violations), and `check_no_dashes.py --all` (0 violations).
   - **MCP Transcript**: `docs/qa/KANBA-138/mcp-transcript.txt` records all 3 `override_ticket_provenance` actions, `run_audit`, `list_flagged`, `purge_audited`, `INSUFFICIENT_SCOPE`, and `LINK_NOT_FLAGGED`.
   - **REST Contract**: `docs/qa/KANBA-138/contract-sample.json` captures all 3 REST endpoints with success and error wire exchanges.
   - **Specialist Reviews**: Signed `api-specialist-review.md` and `ui-specialist-review.md` both certifying `Verdict: APPROVED`.
   - **Screenshots**: `Screenshots: N/A - Non-UI Ticket`.
