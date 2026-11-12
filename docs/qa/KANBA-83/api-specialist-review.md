# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-83 (KB-P3-03)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Worktree: `/tmp/kb-wt-KANBA-83` on branch `feat/KANBA-83`
- Ticket: `KANBA-83` (`KB-P3-03`: `[Phase 3 / API] Hybrid assignees API & access-filtered assignee autocomplete`)
- Target File: `docs/qa/KANBA-83/api-specialist-review.md`

---

### 1. Architectural Scope & Security Invariants Verification

A comprehensive forensic audit of the hybrid assignees subsystem, autocomplete search pipeline, permission-filtering boundaries, and anti-enumeration defenses was conducted in `/tmp/kb-wt-KANBA-83`:

1. **REST Endpoints & Permission Enforcement (`kanban/api/v1/assignees.py`):**
   - **Mounted Routes:**
     * `POST /api/v1/issues/{issue_ref}/assignees`: Requires `Capability.EDIT` on the target issue. Assigns either an eligible project viewer or a free-text external label; returns `201 Created`.
     * `DELETE /api/v1/issues/{issue_ref}/assignees/{assignee_id}`: Requires `Capability.EDIT` on the target issue. Removes the issue-assignee link; returns `204 No Content`.
     * `GET /api/v1/projects/{project_ref}/assignee-suggestions`: Requires `Capability.VIEW` on the target project. Returns eligible viewers matching prefix query `q`; returns `200 OK`.
   - **Cross-Issue Guard:** In `remove_assignee()`, if the target `assignee_id` exists in the database but belongs to a different issue, the service cleanly invokes `not_found()` (RFC 7807 404), completely preventing cross-issue manipulation.
   - **Anti-Enumeration Timing Floor:** All three endpoints execute inside `timing_floor(floor_ms=25.0)`, equalizing response latency and eliminating side-channel timing disclosures.

2. **Principal Eligibility & Zero-Enumeration Boundary (`kanban/services/assignees.py`):**
   - **Access-Filtering Mandate:** Before linking a principal assignee, the service queries `effective_resource_access` for the issue's project:
     ```sql
     SELECT 1 FROM effective_resource_access
     WHERE object_id = :project_id
       AND principal_id = :principal_id
       AND workspace_id = :workspace_id
       AND (allow_mask & 1) = 1
       AND (deny_mask & 1) = 0
     ```
     This strictly guarantees that assignments can never grant ambient permissions to outsiders.
   - **Indistinguishable Rejection:** Non-existent principals, cross-workspace principals, inactive principals, and principals lacking `VIEW` capability (or holding explicit `DENY`) on the project all fail with the byte-identical RFC 7807 `422 ASSIGNEE_NOT_ELIGIBLE` payload (`"The specified principal is not eligible for assignment in this project"`). An attacker cannot enumerate tenant membership or user existence via the assignment endpoint.

3. **Free-Text Label Normalization & Security Boundary (`kanban/services/assignees.py`):**
   - **Normalization & Sanitization:** Free-text labels undergo `normalize_plain_text()` (stripping zero-width characters, tag planes, and embedded HTML tags like `<b>x</b>` -> `x`).
   - **Length Constraints:** Validated between 1 and 120 UTF-8 characters (`MIN_FREE_TEXT_LENGTH = 1`, `MAX_FREE_TEXT_LENGTH = 120`). Out-of-bounds inputs raise RFC 7807 `422 FREE_TEXT_INVALID`.
   - **Non-Privileged Metadata:** Free-text assignees insert into `issue_assignees` without creating any `resource_acl_entries` or `effective_resource_access` records. They are flagged with `notify: false` and the explicit warning hint: `"External free-text label - grants zero access and sends zero notifications"`.

4. **Resource Bounds & Duplicate Detection (`kanban/services/assignees.py`):**
   - **Capacity Caps:**
     * Maximum total assignees per issue: `MAX_TOTAL_ASSIGNEES = 20` (exceeding returns RFC 7807 `422 ASSIGNEE_LIMIT`).
     * Maximum free-text assignees per issue: `MAX_FREE_TEXT_ASSIGNEES = 10` (exceeding returns RFC 7807 `422 ASSIGNEE_LIMIT`).
   - **Duplicate Prevention:**
     * Duplicate principal assignments fail with RFC 7807 `409 ASSIGNEE_EXISTS`.
     * Duplicate free-text assignments fail case-insensitively (`func.lower(free_text_assignee) == cleaned.lower()`) with RFC 7807 `409 ASSIGNEE_EXISTS`.

5. **Autocomplete Privacy & Indexed Execution (`kanban/services/assignees.py`):**
   - **Query Constraints:** Parameter `q` is validated between 1 and 64 characters (`422 INVALID_QUERY`). Limit is clamped between 1 and 20 (default 10).
   - **Wildcard Escaping:** `escape_like()` escapes `\`, `%`, and `_` characters to prevent wildcard injection attacks against the `ILIKE` pattern.
   - **Privacy Isolation:** Autocomplete strictly queries principals who hold active `VIEW` permissions on the target project via `effective_resource_access`. Users holding permissions only in other projects are never returned.
   - **Zero PII Exposure:** Output items expose strictly `id`, `handle`, `display_name`, and `type`. Private fields (such as `email`, OAuth provider card IDs, or LDAP distinguished names) are completely omitted.
   - **Query Performance:** Forensic execution plan in `suggestions-explain.txt` confirms an actual execution time of **0.114 ms** utilizing nested index scans across `effective_resource_access_pkey`, `objects_id_object_type_key`, and `principals_id_principal_type_key`.

6. **Activity Ledger Auditability (`kanban/services/assignees.py`):**
   - Adding an assignee records `ActivityEventType.ASSIGNEE_ADDED` with payload `{"kind": "principal", "principal_id": "..."}` or `{"kind": "free_text", "free_text": "..."}`.
   - Removing an assignee records `ActivityEventType.ASSIGNEE_REMOVED` with identical payload structure.
   - Events are categorized under `HISTORY` in compliance with Section 11.4.

---

### 2. Verification Matrix

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Endpoints** | POST / DELETE assignees, GET suggestions | All 3 mounted on `build_v1_router()` under `/api/v1` | PASS |
| **Permission Gates** | EDIT on issue for mutations, VIEW for suggestions | Enforced via `require_capability()`; unauthorized returns 403/404 | PASS |
| **Principal Eligibility** | Project VIEW required; zero cross-scope leakage | Checks `effective_resource_access`; outsiders return 422 | PASS |
| **Anti-Enumeration Uniformity** | Byte-identical 422 for all invalid principals | Non-existent, inactive, cross-workspace, and non-viewers return identical 422 | PASS |
| **Free-Text Normalization** | 1..120 chars, plain text, HTML/zero-width stripped | Sanitized via `normalize_plain_text()`; zero-width and HTML tags dropped | PASS |
| **Free-Text Semantics** | `notify: false`, hint string, zero ACL rows | Emits `notify: false` and exact `hint` string; no ACL entries created | PASS |
| **Capacity Caps** | Max 20 total, max 10 free-text | 21st assignee and 11th free-text return `422 ASSIGNEE_LIMIT` | PASS |
| **Duplicate Prevention** | Reject duplicate principal or duplicate free-text | Duplicate principal or case-insensitive text returns `409 ASSIGNEE_EXISTS` | PASS |
| **Autocomplete Privacy** | Project viewers only; no email/card/DN leaks | Joins `effective_resource_access`; returns only id, handle, display_name, type | PASS |
| **Autocomplete Query Speed** | Indexed search execution | Execution time **0.114 ms** verified in `suggestions-explain.txt` | PASS |
| **Cross-Issue Delete Guard** | Assignee from other issue returns 404 | Verified `not_found()` on mismatched `issue_id` / `workspace_id` | PASS |
| **Anti-Enumeration Timing** | 25.0ms timing floor across endpoints | Wrapped in `timing_floor(floor_ms=25.0)` | PASS |
| **Activity Ledger Logging** | `ASSIGNEE_ADDED` and `ASSIGNEE_REMOVED` | Both events appended to immutable ledger under category `HISTORY` | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 7/7 passed in 3.72s; 98.82% branch+line coverage across target modules | PASS |
| **Quality & Type Safety** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean, Mypy strict clean (126 files), Lint-imports clean | PASS |
| **Typography & Formatting** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 3. Forensic Test Suite & Coverage Verification

- **Test Suite Execution:**
  ```text
  kanban/tests/api/test_assignees.py: 7 passed in 3.72s
  ```
- **Coverage Breakdown:**
  * `kanban/api/v1/assignees.py`: 100% (25 statements, 0 branches)
  * `kanban/services/assignees.py`: 99% (113 statements, 32 branches, 1 missed line 302 defensive branch)
  * **Combined Coverage:** **98.82%** (exceeds `>=95%` mandatory threshold)

---

### 4. Gate Sign-Off

All technical requirements, data contracts, and security invariants defined in `docs/tickets/KB-P3-03.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 7.2 (8b) and Section 3.4 have been rigorously audited and proven. Both UI Specialist Gate (`docs/qa/KANBA-83/ui-specialist-review.md`) and API Specialist Gate reviews are complete and approved.

Verdict: APPROVED
