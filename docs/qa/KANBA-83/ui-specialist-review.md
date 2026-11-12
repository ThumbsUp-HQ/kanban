# UI Specialist Gate Final Audit: APPROVED for KANBA-83 (KB-P3-03)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-83`
- Branch: `feat/KANBA-83`
- Ticket: `KANBA-83` (`KB-P3-03`: `[Phase 3 / API] Hybrid assignees API & access-filtered assignee autocomplete`)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend contract, UX ergonomics, and state synchronization audit was conducted for `KANBA-83` in `/tmp/kb-wt-KANBA-83`. While `KB-P3-03` is a backend REST API ticket without direct frontend screenshots (Screenshots: N/A - Non-UI Ticket per KB-P3-03 proof criteria), it establishes the foundational data contracts and autocomplete interfaces for the Issue Detail Drawer Assignee Selector (`KB-P3-36`), Card Header Assignee Chips (`KB-P3-33`), and Filter Dropdowns. All request/response schemas, discriminated union definitions, free-text pill ergonomics, autocomplete suggestion models, and anti-enumeration invariants were forensically evaluated against S7.2 (item 8b), S3.4, and Section 5.4 specifications.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Discriminated Union Schema** | Explicit `kind: "principal" \| "free_text"` | Pydantic discriminated union on `kind`; enforces mutual exclusivity in request/response | PASS |
| **Free-Text Pill Ergonomics** | Dashed `🏷️` pill with `notify: false` and hint | Emits `notify: false` and exact `hint` string explaining zero access and zero notifications | PASS |
| **Autocomplete Suggestions** | Access-filtered project viewer suggestions | `GET .../assignee-suggestions` returns eligible viewers with zero email/DN/card leaks | PASS |
| **Anti-Enumeration Protection** | Indistinguishable ineligible responses | Nonexistent, inactive, and unauthorized principals return byte-identical `422 ASSIGNEE_NOT_ELIGIBLE` | PASS |
| **Free-Text Bounds & Hygiene** | Normalized plain text (1..120 chars) | Normalized via `normalize_plain_text()`; zero-width chars and HTML tags stripped cleanly | PASS |
| **Capacity & Duplicate Limits** | Max 20 total / 10 free-text; no duplicates | Enforces max bounds (`422 ASSIGNEE_LIMIT`) and duplicate rejection (`409 ASSIGNEE_EXISTS`) | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 7/7 passed in 3.92s; 98.82% combined coverage across assignees API and service | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean, Mypy strict clean (140 files), Lint-imports clean (2 kept, 0 broken) | PASS |

---

### 2. Frontend Contract & UX Ergonomics Audit

1. **Discriminated Union Payload Structure (`AssigneeResponse`):**
   - The API structures assignees as a discriminated union keyed on `kind`:
     * **Principal Assignees:**
       ```json
       {
         "id": "01a1cecc-6fc9-7f5b-80b9-9fd13bcc680d",
         "kind": "principal",
         "principal": {
           "id": "01a1cecc-6ec3-7746-b945-94369ce61c8d",
           "handle": "viewer",
           "display_name": "Viewer",
           "type": "USER"
         }
       }
       ```
     * **Free-Text Assignees:**
       ```json
       {
         "id": "01a1cecc-7348-7940-8bd0-35d94d8c1692",
         "kind": "free_text",
         "free_text": "Vendor: NCC Group",
         "notify": false,
         "hint": "External free-text label - grants zero access and sends zero notifications"
       }
       ```
   - *UX Impact:* This clean discriminated union enables the frontend issue drawer and Kanban cards to easily differentiate internal users from external contractors or organizational labels. Solid avatar pills are rendered for team members, while dashed-border tag pills with a `🏷️` prefix are rendered for free-text assignees.

2. **Free-Text Warning Hint & Transparency:**
   - The `hint` string (`"External free-text label - grants zero access and sends zero notifications"`) and `notify: false` boolean provide immediate semantic context to the client UI.
   - *UX Impact:* When hovering over or clicking a free-text assignee pill, the tooltip directly displays the explanation from the server contract. This prevents user confusion regarding whether external names will receive email alerts or ticket notifications.

3. **Autocomplete Ergonomics & Information Privacy (`/assignee-suggestions`):**
   - `GET /api/v1/projects/{project_ref}/assignee-suggestions?q=<query>&limit=<n>` queries project viewers via indexed lookups on `effective_resource_access`.
   - Escapes special wildcards (`%`, `_`, `\`) in search patterns to prevent query disruption.
   - Restricts item fields strictly to `id`, `handle`, `display_name`, and `type`.
   - *UX Impact:* The dropdown search populates instantly (0.078ms query execution verified in `suggestions-explain.txt`) without exposing private personal data such as user email addresses, LDAP group distinguished names, or OAuth card credentials.

4. **Anti-Enumeration Security & Discrete Error Handling:**
   - Attempting to assign an unauthorized, inactive, cross-workspace, or non-existent handle returns identical `422 ASSIGNEE_NOT_ELIGIBLE` problem payloads.
   - Malformed payloads (missing fields or attempting to provide both principal and free_text) return `422 INVALID_PAYLOAD`.
   - Exceeding assignee bounds triggers `422 ASSIGNEE_LIMIT`.
   - Duplicates trigger `409 ASSIGNEE_EXISTS`.
   - Deleting an assignee that does not belong to the target issue returns `404 NOT_FOUND`.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-83/docs/qa/KANBA-83/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-83`.

Verdict: APPROVED