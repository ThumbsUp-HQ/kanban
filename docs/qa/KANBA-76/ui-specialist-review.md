# UI Specialist Gate Final Audit: APPROVED for KANBA-76 (KB-P3-02)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-76`
- Branch: `feat/KANBA-76`
- Ticket: `KANBA-76` (`KB-P3-02`: `[Phase 3 / API] Issues CRUD API with description ETag / If-Match concurrency`)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend contract, UX ergonomics, and state synchronization audit was conducted for `KANBA-76` in `/tmp/kb-wt-KANBA-76`. While `KB-P3-02` is a backend REST API ticket without direct frontend screenshots (Screenshots: N/A - Non-UI Ticket per KB-P3-02 proof criteria), it establishes the foundational data contracts and concurrency primitives for the Issue Detail Drawer (`KB-P3-36`), Kanban Board View (`KB-P3-33`), and ProseMirror Description Editor (`KB-P3-45`). All request/response schemas, discrete RFC 7807 problem details, restricted parent masking, description ETag concurrency, and Base-62 board rank formatting were forensically evaluated against S7.2, S3.4, and Section 5.4 architecture specifications.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Restricted Parent Masking** | S7.2 8h & S3.4 zero-leakage parent masking | Emits `{"restricted": true, "label": "🔒 Restricted Parent Issue"}` with zero ID, key, or summary leaks | PASS |
| **ETag Concurrency Model** | Strong SHA-256 ETag + `If-Match` | `428 PRECONDITION_REQUIRED` on missing header; `412 PRECONDITION_FAILED` with `current_etag` on stale edit | PASS |
| **API Error Ergonomics** | Discrete RFC 7807 problem details | Discrete codes (`SUMMARY_LENGTH`, `DESCRIPTION_TOO_LARGE`, `DATE_ORDER`, `MODULES_DISABLED`, `EXCLUSIVE_GROUP_CONFLICT`) | PASS |
| **DAG Hierarchy Protection** | Prevent cycles and excessive depth | `409 PARENT_CYCLE` and `409 PARENT_DEPTH_EXCEEDED` cleanly mapped with `field="parent"` | PASS |
| **Base-62 Board Rank** | Deterministic lexical sorting token | `"a" + to_base62(seq).rjust(6, "0")` provides stable ASCII collation order for board cards | PASS |
| **Keyset Pagination** | URL-safe base64 cursor navigation | `sequence_id DESC` ordering with opaque base64url cursor and 422 `INVALID_CURSOR` handling | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 15/15 passed in 14.80s; 99.17% combined coverage (`kanban.api.v1.issues` 100%, `kanban.services.issues` 99%) | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean, Mypy strict clean (122 source files), Lint-imports clean (2 kept, 0 broken) | PASS |

---

### 2. Frontend Contract & UX Ergonomics Audit

1. **Restricted Parent Masking (`RestrictedParentSummary`):**
   - When a parent issue exists but is unreadable under the caller's RLS policy (or belongs to a project/issue the user has no `VIEW` capability for), the API returns:
     ```json
     {
       "restricted": true,
       "label": "🔒 Restricted Parent Issue"
     }
     ```
   - *UX Impact:* This delivers flawless security and ergonomics. In the issue drawer and card hierarchy pills, the UI can safely branch on `issue.parent?.restricted` to render a locked badge without crashing or showing blank fields. Parent identifier, project key, and summary are completely suppressed, preventing unauthorized information disclosure.

2. **Description ETag Concurrency & Mid-Air Collision Avoidance:**
   - Every issue carries a strong ETag corresponding to the SHA-256 hash of its canonical Markdown description: `etag = f'"{sha256_hex}"'`.
   - Modifying `description_markdown` without `If-Match` returns `428 PRECONDITION_REQUIRED`.
   - Stale edits return `412 PRECONDITION_FAILED` containing the fresh `current_etag`:
     ```json
     {
       "type": "urn:kanban:problem:PRECONDITION_FAILED",
       "title": "Precondition Failed",
       "status": 412,
       "code": "PRECONDITION_FAILED",
       "detail": "Current description ETag does not match If-Match header",
       "current_etag": "\"79ab8b08b2395de6e231271e86e0581e3f8e498e9b72a9e4a439d4e6288644ca\""
     }
     ```
   - *UX Impact:* In the ProseMirror editor (`KB-P3-45`), this allows the frontend to detect concurrent edits immediately, present a side-by-side diff resolution dialog to the user, and prevent catastrophic overwrite of teammate notes. The `current_etag` field enables one-click overwrite or reload workflows.

3. **Discrete Form Validation Error Ergonomics:**
   - The API replaces generic 422 errors with granular problem codes and `field` annotations:
     * `SUMMARY_LENGTH`: Annotated with `field="summary"`, enforcing 1..500 character boundaries. Enables inline error helper text on the issue summary input.
     * `DESCRIPTION_TOO_LARGE`: Signals that normalized Markdown exceeds 1 MiB (`MAX_DESCRIPTION_BYTES = 1048576`). Allows the editor to display an explicit file size warning banner.
     * `DATE_ORDER`: `detail="due_date cannot be earlier than start_date"`. Directs the date picker popover to highlight invalid date ranges.
     * `MODULES_DISABLED`: Prevents assigning modules when the project toggle is off.
     * `EXCLUSIVE_GROUP_CONFLICT`: Emitted when selecting multiple labels from the same exclusive label group (e.g., conflicting severity tiers). Enables the label dropdown to enforce radio-button behavior per exclusive group.
     * `PARENT_CYCLE` / `PARENT_DEPTH_EXCEEDED`: Returns 409 Conflict with `field="parent"` to guide tree repositioning.

4. **Base-62 Board Rank Formatting:**
   - Initial board rank token is computed as `initial_board_rank(seq_id) = "a" + to_base62(seq_id).rjust(6, "0")`.
   - *UX Impact:* In the Kanban Board View (`KB-P3-33`), cards are ordered by `board_rank COLLATE "C" ASC`. Fixed-width Base-62 tokens guarantee natural alphanumeric sorting, ensuring newly created issues appear in deterministic order at the bottom of the default column without requiring expensive table re-ranking.

5. **Anti-Enumeration Timing Equalization:**
   - Endpoints are wrapped in `async with timing_floor(floor_ms=25.0)`.
   - Probing non-existent or unreadable issues returns 404 with latency equalized to existing issues, preventing timing side-channel attacks while remaining well within the 100ms interactive UX threshold.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-76/docs/qa/KANBA-76/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-76`.

Verdict: APPROVED