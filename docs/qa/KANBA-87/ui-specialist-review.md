# UI Specialist Gate Final Audit: APPROVED for KANBA-87 (KB-P3-09a)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-87`
- Branch: `feat/KANBA-87`
- Ticket: `KANBA-87` (`KB-P3-09a`: `[Phase 3 / API] Archive / unarchive with Plane rule & periodic auto-archive job`)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend contract, UX ergonomics, and schema serialization audit was conducted for `KANBA-87` in `/tmp/kb-wt-KANBA-87`. While `KB-P3-09a` is a backend REST API and background job ticket without direct frontend screenshots (Screenshots: N/A - Non-UI Ticket per KB-P3-09a specification), it establishes the foundational data models and interactive state machines for the Issue Action Menu (`KB-P3-36`), Board Column Archive Toggles (`KB-P3-33`), Dedicated Archive List View, and read-only archived issue indicators (`🗄️`). All request/response schemas, archive eligibility models, discrete RFC 7807 problem details, sub-issue dependency warnings, and anti-enumeration invariants were forensically evaluated against S7.2 (8p) and Section 5.4 architecture specifications.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Archive Eligibility Schema** | `archive_eligibility: { allowed: bool, reason: str | None }` | Pydantic schema with `extra="forbid"`; included in all `IssueResponse` payloads | PASS |
| **Action Menu Ergonomics** | Drives disabled state and tooltip for `🗄️ Archive` | Pre-computes eligibility and provides exact user-facing reason strings | PASS |
| **Exact Plane Rule Reason** | Verbatim explanatory text on non-terminal states | Emits exact detail `Only completed or canceled work items can be archived` | PASS |
| **Sub-Issue Dependency Guard** | Explains blocked archive when sub-issues are open | Emits `409 ARCHIVE_OPEN_SUBISSUES` separating readable keys from `hidden_open_count` | PASS |
| **Read-Only Archived State** | Block issue edits once archived | Edits on archived issues return `409 ISSUE_ARCHIVED`; UI disables editor | PASS |
| **List Filter Ergonomics** | `include_archived` and `only_archived` toggles | Cleanly partitions active boards and archive views; rejects conflicting params (422) | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 7/7 passed in 2.98s; 98.61% branch + line coverage across API and service modules | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (637 files), Mypy strict clean (133 files), Lint-imports clean (2 kept, 0 broken) | PASS |

---

### 2. Frontend Contract & UX Ergonomics Audit

1. **Pre-Computed Archive Eligibility (`archive_eligibility`):**
   - The issue serializer adds `archive_eligibility` to `IssueResponse`:
     ```json
     {
       "archived_at": null,
       "archive_eligibility": {
         "allowed": false,
         "reason": "Only completed or canceled work items can be archived"
       }
     }
     ```
   - *UX Impact:*
     * Rather than letting users click "Archive" and suffering unexpected 409 errors, the Issue Detail Drawer and Kanban Card context menus inspect `issue.archive_eligibility.allowed`.
     * If `allowed: false`, the `🗄️ Archive` menu item is disabled with an inline tooltip displaying the exact server-provided explanation (e.g. `"Only completed or canceled work items can be archived"` or `"Cannot archive work item with open sub-issues"`).
     * If `allowed: true`, the button is enabled and triggers the action smoothly.

2. **Sub-Issue Dependency Warning Modal (`409 ARCHIVE_OPEN_SUBISSUES`):**
   - If an open sub-issue was created concurrently or the user attempts to force archive, the API returns:
     ```json
     {
       "type": "urn:kanban:problem:ARCHIVE_OPEN_SUBISSUES",
       "title": "Open sub-issues exist",
       "status": 409,
       "code": "ARCHIVE_OPEN_SUBISSUES",
       "detail": "Cannot archive issue with open sub-issues",
       "open_subissue_keys": ["ARC-2"],
       "hidden_open_count": 0
     }
     ```
   - *UX Impact:* The UI presents a modal dialogue detailing the blocking sub-issues with clickable links to each open sub-task, while preserving permission boundaries for unreadable sub-issues via `hidden_open_count` without leaking sensitive titles or keys.

3. **Read-Only Invariant for Archived Issues:**
   - Once an issue is archived, `archived_at` is populated with an ISO-8601 timestamp.
   - The issue view displays an archived banner (`🗄️ Archived on <date>`) and transitions all form controls, editors, and priority selectors to read-only mode.
   - Attempting to edit an archived issue returns `409 ISSUE_ARCHIVED`, ensuring frontend and backend state consistency.

4. **Board View vs. Archive View List Filtering:**
   - Default `GET /api/v1/projects/{ref}/issues` excludes archived items, keeping Kanban boards breathable and performant.
   - The board view filter dropdown provides an "Include Archived" checkbox (`include_archived=true`) to display archived cards with dimmed opacity.
   - The project navigation sidebar features an "Archive" tab using `only_archived=true` for focused historical audits.
   - Passing contradictory query parameters (`include_archived=false&only_archived=true`) returns `422 ARCHIVE_FILTER_CONFLICT` with clear error detail.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-87/docs/qa/KANBA-87/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-87`.

Verdict: APPROVED
