# UI Specialist Gate Review: KANBA-138 (KB-P4-11)

- **Ticket**: `KANBA-138` (`KB-P4-11`: `/mcp/admin` tools 10-11: `override_ticket_provenance` & `audit_and_purge_object_links` (+ link auditor admin REST))
- **Reviewer**: `@ui-specialist` (UI Designer & UX Architect)
- **Branch**: `feat/KANBA-138`
- **Worktree**: `/tmp/kb-wt-KANBA-138`
- **Scope**:
  - `kanban/api/v1/admin/link_auditor.py`
  - `kanban/api/v1/schemas/link_auditor.py`
  - `kanban/services/link_auditor_admin.py`
  - `mcp/surfaces/admin/override_ticket_provenance.py`
  - `mcp/surfaces/admin/audit_and_purge_object_links.py`

---

### 1. Executive Summary & Verification Matrix

A comprehensive UI/UX architecture and consumer contract audit was performed for `KANBA-138`. While `KANBA-138` primarily implements admin REST and MCP endpoints, these endpoints provide the foundational contracts and data payloads directly driving:
1. The **Admin Object Link Auditor** inspection drawer and modal views (`🕸️⚠️` flagged-link audit snapshots).
2. The **Ticket Detail Provenance** inspector and override flows (`🔄` creator provenance badge, audit tooltip, and Hard WIP limit override notifications).

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Flagged-Link Audit Snapshots (`🕸️⚠️`)** | S12.3 6 invalidity classes with endpoint snapshots | Clean snapshot records (`source_id`, `target_id`, `link_type`, `detected_at`) | PASS |
| **Provenance Override Payloads (`🔄`)** | S7.2 8d creator override with original attribution | Exposes `original_created_by`, `created_by`, `reason`, and privacy masking | PASS |
| **Hard WIP Limit Override Ergonomics** | S6.4 item 3 WIP limit bypass feedback | Returns `hard_limit` and `resulting_count` for UI badge display | PASS |
| **LOD Output Tiers** | `summary`, `standard`, `full` LOD support | Standardized YAML and JSON output structures matching client drawer expectations | PASS |
| **Screenshots Compliance** | N/A - Non-UI Ticket | Confirmed non-UI ticket (API & MCP layer); verified in `contract-sample.json` | PASS |
| **Typography Compliance** | Plain ASCII hyphens `-` only | Strictly plain ASCII hyphens used throughout code, comments, and documentation | PASS |

---

### 2. UI & UX Consumer Contract Analysis

#### A. Flagged-Link Audit Snapshots (`🕸️⚠️`) & Admin Inspection Views (S12.3)
- The admin link auditor inspection views display broken, orphaned, or policy-invalid links across the workspace object graph.
- The `POST /api/v1/admin/object-links:audit` endpoint provides grouped counts across all 6 invalidity classes:
  - `DANGLING_SOURCE` / `DANGLING_TARGET`
  - `SOFT_DELETED_ENDPOINT`
  - `ARCHIVED_POLICY_VIOLATION`
  - `TYPE_MATRIX_VIOLATION`
  - `CROSS_WORKSPACE_LEAK`
  - `PERMISSION_SEVERED`
- In `GET /api/v1/admin/object-links/audits`, each item returns a complete `link_snapshot` containing `{source_id, target_id, link_type, workspace_id, detected_at, purged_at, resolved_at}`:
  - Flagged links render with `🕸️⚠️` status badges in the inspection drawer.
  - Snapshot details allow administrators to review the exact relationship that became severed before approving an audited purge.
  - Keyset cursor pagination (`next_cursor`, `has_more`) ensures large audit catalogs browse smoothly without pagination lag.

#### B. Ticket Detail Provenance Payloads (`🔄`) & Admin Overrides (S7.2 8d, S7.2 8p)
- In the ticket drawer properties rail, creator provenance displays an immutable handle. When modified by an administrator, the `🔄` indicator elaborates the full audit trail:
  - `original_created_by`: Displays original author (e.g. `@bot-import` or initial creator).
  - `created_by`: Displays current attributed owner (e.g. `@maya`).
  - `reason`: Surfaces the justification text entered during the override flow.
  - Privacy boundary: Out-of-scope external collaborators serialize safely as `1 External Collaborator`, preventing cross-workspace identity leakage in UI tooltips.
- The unarchive action records `{reason, admin_override: true}` in the activity ledger, rendering an accessible audit badge in the activity stream.

#### C. Hard WIP Limit Move Response Ergonomics (S6.4)
- When moving an issue into a column at or above its Hard WIP limit with an administrative override, `IssueMoveResponse` now returns:
  - `hard_limit`: e.g. `5`
  - `resulting_count`: e.g. `6`
- This allows the frontend board to immediately update the column header badge (e.g. `6/5 ⚠️ WIP Overridden`) and animate the card drop without requiring a full board refresh.

---

### 3. Screenshots Verification
- Status: N/A - Non-UI Ticket (verified per Ticket Spec: `Screenshots: N/A - Non-UI Ticket`).
- Verified wire exchanges in `contract-sample.json`:
  * `admin_link_auditor_scan_200`: Grouped counts across invalidity classes.
  * `admin_link_auditor_list_200`: Paginated snapshot items with `link_snapshot`.
  * `admin_link_auditor_purge_200`: Purged count and activity ids.
  * `admin_link_auditor_conflict_409`: Conflict error mapping for unflagged/purged links.
  * `admin_link_auditor_aal2_required_403`: AAL2 step-up challenge.
  * `admin_link_auditor_insufficient_capability_403`: Role hierarchy enforcement.

---

### 4. Gate Verdict

The REST contracts and MCP tool output schemas align with the frontend inspection views, provenance badges, and board WIP indicators.

**Verdict: APPROVED**
