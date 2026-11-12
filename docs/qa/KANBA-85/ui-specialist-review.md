# UI Specialist Gate Final Audit: APPROVED for KANBA-85 (KB-P3-05)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-85`
- Branch: `feat/KANBA-85`
- Ticket: `KANBA-85` (`KB-P3-05`: `[Phase 3 / API] Threaded comments, reactions, permalinks & access-checked @mentions`)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend contract, UX ergonomics, and schema serialization audit was conducted for `KANBA-85` in `/tmp/kb-wt-KANBA-85`. While `KB-P3-05` is a backend REST API and discussion service ticket without direct frontend screenshots (Screenshots: N/A - Non-UI Ticket per KB-P3-05 specification), it defines the core data contracts and interactive state machines for the Issue Activity Stream (`KB-P3-36`), Comment Editor with Sparkle completion (`KB-P5-08`), Mention Access Confirmation Modal, Emoji Reaction Picker, and Deep Permalinks. All request/response schemas, keyset cursor pagination models, discrete RFC 7807 problem details, soft-delete rendering models, and anti-enumeration invariants were forensically evaluated against S7.2 (8k), S5.1, S3.4, and Section 5.4 architecture specifications.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Mention Access Warning Modal** | Discrete `409 MENTION_ACCESS_WARNING` payload | Emits machine-readable `unauthorized_mentions` with handles and IDs for UI confirmation | PASS |
| **Mention Bypass & Zero Widening**| Resubmit with `acknowledge_mentions` bypass | Returns `201` with `unnotified_mentions`; zero modification to `resource_acl_entries` | PASS |
| **Anti-Enumeration Invariants** | Unresolvable / cross-workspace handles silent | Left as plain text with zero warning and zero enumeration leak to caller | PASS |
| **Threaded Comment Structure** | Depth-1 replies with inlined grouping | Up to 200 inlined replies per top-level comment; rejects depth > 1 (`422`) | PASS |
| **Keyset Cursor Pagination** | Opaque base64 created_at + id cursor | Enforces deterministic keyset navigation; malformed cursor returns `422 INVALID_CURSOR` | PASS |
| **Optimistic Concurrency (ETag)**| `If-Match` ETag concurrency on edits | Stale edits return `412 PRECONDITION_FAILED`; missing header returns `428` | PASS |
| **Soft-Delete Degradation** | Preserve thread hierarchy on delete | Soft-deletes with `deleted: true`, nulls body/sha, and preserves nested replies | PASS |
| **Emoji Reaction Ergonomics** | Canonical 8-emoji allowlist with NFC norm | Idempotent `PUT`/`DELETE` returning `{emoji, count, reacted_by_me}`; non-allowlist returns `422` | PASS |
| **Permalinks** | Copyable deep-link fragment | Emits `/projects/{proj}/issues/{key}#comment-{uuid}` for clipboard integration | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 13/13 passed in 5.98s; 96.72% branch + line coverage across API and service modules | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (634 files), Mypy strict clean (234 files), Lint-imports clean (2 kept, 0 broken) | PASS |

---

### 2. Frontend Contract & UX Ergonomics Audit

1. **Pre-Send Mention Access Warning Modal (`409 MENTION_ACCESS_WARNING`):**
   - When a user drafts a comment mentioning a colleague who lacks `VIEW` permissions on the issue (e.g. `@maya`), the API returns:
     ```json
     {
       "type": "https://kanban/problems/mention-access-warning",
       "title": "Mentioned users cannot see this issue",
       "status": 409,
       "code": "MENTION_ACCESS_WARNING",
       "detail": "Resubmit with acknowledge_mentions to post without granting access.",
       "unauthorized_mentions": [
         {
           "handle": "maya",
           "principal_id": "01a1ced9-f970-7164-917f-49d913e552f3"
         }
       ]
     }
     ```
   - *UX Impact:*
     * Rather than failing cryptically or silently leaking confidential issues, the SPA catches `409 MENTION_ACCESS_WARNING` and presents a clear, actionable confirmation modal:
       "The following mentioned user cannot see this issue: @maya. They will not be notified and will not be granted access to this issue. Do you want to post anyway?"
     * The modal provides two buttons: "Edit Comment" and "Post Anyway".
     * If the user confirms "Post Anyway", the client simply re-posts with `acknowledge_mentions: ["01a1ced9-f970-7164-917f-49d913e552f3"]`.
     * The comment posts successfully with `unnotified_mentions` documented in the response, while `resource_acl_entries` remains completely untouched.
     * Mentions outside the workspace boundary or non-existent usernames remain plain text without warning, preventing attackers from probing valid usernames.

2. **Threaded Discussion Ergonomics & Pagination:**
   - Single-level nesting (`parent_comment_id`) prevents chaotic, infinitely nested comment trees.
   - The top-level comment schema inlines up to 200 replies directly inside `replies: list[CommentResponse]`. If replies exceed 200, `replies_next_cursor` is provided for on-demand lazy loading ("Load more replies").
   - `CommentList` utilizes opaque URL-safe keyset cursors (`created_at|id`) with max 100 items per page (default 50). This guarantees stable, zero-shift infinite scroll even as new comments are submitted in real-time.

3. **Concurrency & Safe Editing (`If-Match` ETag):**
   - Comment edits require the `If-Match` HTTP header matching the comment's `body_sha256`.
   - If a concurrent edit occurred (e.g. edited from another browser tab or device), the server rejects the collision with `412 PRECONDITION_FAILED` and provides `current_etag`.
   - *UX Impact:* The comment editor can notify the user of concurrent modifications and offer a diff view, preventing silent data loss.

4. **Soft-Delete Degradation:**
   - Deleting a comment sets `deleted_at` while preserving the thread structure.
   - The serializer returns `deleted: true` with `body_markdown: null` and `body_sha256: null`.
   - *UX Impact:* The frontend renders a subtle placeholder card ("This comment was deleted") while preserving the reply tree beneath it, ensuring that child conversations do not become orphaned or visually detached.

5. **Emoji Reactions Strip & Toggle State:**
   - Strictly validates against the 8 canonical emojis (`👍`, `👎`, `😄`, `🎉`, `😕`, `❤️`, `🚀`, `👀`) with NFC normalization.
   - Reaction responses return `{emoji, count, reacted_by_me}`, enabling instant UI chip toggling and optimistic counter increments/decrements.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-85/docs/qa/KANBA-85/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-85` along with your changes and `git-diff.patch`.

Verdict: APPROVED
