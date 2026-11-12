# API Specialist Gate Final Audit: APPROVED for KANBA-85 (KB-P3-05)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-85`
- Branch: `feat/KANBA-85`
- Ticket: `KANBA-85` (`KB-P3-05`: `[Phase 3 / API] Threaded comments, reactions, permalinks & access-checked @mentions`)

---

### 1. Executive Summary & Verification Matrix
A forensic backend architecture and API Specialist Gate audit was conducted for `KANBA-85` in `/tmp/kb-wt-KANBA-85`. `KB-P3-05` delivers the core discussion layer for issues, featuring canonical Markdown comments, depth-1 reply threading, keyset cursor pagination, ETag concurrency, soft delete, an 8-emoji reaction engine, and access-checked `@mention` resolution with zero silent ACL widening. All 6 REST endpoints, DDL/RLS policies, regex mention filters, and activity event emissions were evaluated against Spec Sections 7.2 (8k), 5.1, 3.4, and Section 5.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Router & Mounting** | 6 endpoints mounted on `build_v1_router()` | Mounted on `build_v1_router()` via `comments_router` in `kanban/api/v1/comments.py` | PASS |
| **Timing Equalization** | 25.0ms timing floor on all endpoints | All 6 endpoints wrapped in `async with timing_floor(floor_ms=25.0):` | PASS |
| **Database DDL & RLS** | `comment_reactions` with FORCE RLS | DDL has `ENABLE` and `FORCE ROW LEVEL SECURITY`, delegating to issue `VIEW` | PASS |
| **Mention Parsing Filter** | Ignore code fences, inline code, link URLs | `extract_mentions` strips ```, ~~~, `, and markdown/raw URLs before matching | PASS |
| **Mention Cap & Error** | Max 50 distinct handles per comment | Exceeding 50 handles raises RFC 7807 `422 TOO_MANY_MENTIONS` | PASS |
| **Mention Anti-Enumeration** | Nonexistent / cross-workspace handles silent | Ignored and kept as plain text with zero warning or enumeration leak | PASS |
| **Access Gate (409 Warning)** | Warn before mentioning unauthorized users | Emits RFC 7807 `409 MENTION_ACCESS_WARNING` with `unauthorized_mentions` | PASS |
| **Zero Silent Widening** | Bypass via `acknowledge_mentions` without ACL | Emits `201` with `unnotified_mentions`; zero rows inserted into `resource_acl_entries` | PASS |
| **Threading Constrained** | Max reply depth 1, max 200 inlined replies | Depth > 1 returns `422 INVALID_PARENT_COMMENT`; inlines up to 200 replies | PASS |
| **Keyset Pagination** | URL-safe base64 `created_at` + `id` cursor | Keyset navigation enforced; malformed cursors return `422 INVALID_CURSOR` | PASS |
| **ETag Concurrency** | If-Match required for updates | Missing header returns `428`; mismatched sha256 returns `412 PRECONDITION_FAILED` | PASS |
| **Soft-Delete Preservation** | Preserve thread hierarchy on delete | Sets `deleted_at`, returns `deleted: true`, nulls body/sha, keeps replies | PASS |
| **Emoji Reaction Allowlist** | 8 canonical emojis with NFC normalization | Allowlist enforced (`👍 👎 😄 🎉 😕 ❤️ 🚀 👀`); non-allowlist returns `422` | PASS |
| **Copyable Permalinks** | Deep permalink fragment format | Emits `/projects/{proj}/issues/{key}#comment-{uuid}` | PASS |
| **Activity Ledger** | Emits CREATED, EDITED, DELETED, ACKNOWLEDGED | Emitted under category `COMMENT`; reactions emit zero rows (no noise) | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 13/13 passed in 6.15s; 96.72% branch+line coverage across target modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean, Mypy strict clean (234 files), Lint-imports clean | PASS |

---

### 2. Forensic Architectural Analysis

1. **REST Router Mounting & Timing Equalization:**
   - Mounted in `kanban/api/v1/comments.py` and composed in `kanban/api/v1/__init__.py:build_v1_router()`:
     * `GET /api/v1/issues/{issue_ref}/comments`
     * `POST /api/v1/issues/{issue_ref}/comments`
     * `PATCH /api/v1/comments/{comment_id}`
     * `DELETE /api/v1/comments/{comment_id}`
     * `PUT /api/v1/comments/{comment_id}/reactions/{emoji}`
     * `DELETE /api/v1/comments/{comment_id}/reactions/{emoji}`
   - Every single endpoint is wrapped with `async with timing_floor(floor_ms=25.0):`, ensuring timing side-channels during author lookups, capability evaluations, and soft-delete updates are completely suppressed.

2. **Database DDL & Row-Level Security (`comment_reactions`):**
   - Migration `p3_05_comment_threads_reactions` creates `comment_reactions` with composite primary key `(comment_id, principal_id, emoji)`.
   - Enforces `ALTER TABLE comment_reactions ENABLE ROW LEVEL SECURITY;` and `ALTER TABLE comment_reactions FORCE ROW LEVEL SECURITY;`.
   - `SELECT`, `INSERT`, and `DELETE` policies delegate directly to the parent issue's `VIEW` capability via `app_has_object_capability(ic.issue_id, 1)` and verify that `principal_id` matches the authenticated caller's session.
   - Foreign key constraint to `issue_comments(id) ON DELETE CASCADE` ensures clean referential cleanup.

3. **Mention Extraction & Anti-Enumeration Boundary (Spec S3.4):**
   - In `kanban/services/mentions.py`, `extract_mentions()` strips fenced code blocks (` ``` ` and `~~~`), inline code spans (` ` `), markdown link targets (`[text](url)` -> `[text]`), and raw URLs before executing regex matching.
   - Regex `(?<![\w@])@([a-z0-9][a-z0-9_.-]{0,38})` extracts distinct handles. Bounded by `MAX_DISTINCT_MENTIONS = 50`; exceeding 50 handles aborts with `422 TOO_MANY_MENTIONS`.
   - In `resolve_mentions()`:
     * Nonexistent handles or handles belonging to users in external workspaces are ignored and left as plain text. No warning is returned, and no enumeration signal is leaked.
     * For users inside the caller's workspace boundary lacking `Capability.VIEW` on the target issue, the service halts execution and returns RFC 7807 `409 MENTION_ACCESS_WARNING` with the structured list of `unauthorized_mentions`.
     * If the client re-submits the request with `acknowledge_mentions` containing those user IDs, the comment is created (`201`), returning the acknowledged users in `unnotified_mentions`.
     * **Zero Silent Widening:** `resource_acl_entries` is never modified. The mentioned user receives zero access to the issue.

4. **Threading & Keyset Cursor Pagination:**
   - Threading is strictly limited to depth 1 (`parent_comment_id` must point to an active top-level comment on the same issue). Attempts to reply to a reply or an invalid parent return `422 INVALID_PARENT_COMMENT`.
   - `list_comments()` fetches top-level comments ordered by `created_at ASC, id ASC`, inlining up to 200 replies per top-level comment.
   - Paginates via opaque base64-encoded `created_at|id` cursors. Malformed cursor strings fail gracefully with `422 INVALID_CURSOR`.

5. **Concurrency Control & Soft Delete:**
   - Edits require `If-Match: "<hex body_sha256>"`. Missing `If-Match` returns RFC 7807 `428 PRECONDITION_REQUIRED`. Mismatched SHA-256 returns `412 PRECONDITION_FAILED`.
   - Deletion is a soft delete setting `deleted_at = clock_timestamp()`. `serialize_comment()` masks soft-deleted comments: `deleted: true`, `body_markdown: None`, `body_sha256: None`, while preserving the reply thread underneath.

6. **Emoji Reaction Allowlist & Idempotency:**
   - Emojis in URL paths are URL-decoded and NFC-normalized.
   - Strictly validated against the 8-emoji canonical allowlist (`👍`, `👎`, `😄`, `🎉`, `😕`, `❤️`, `🚀`, `👀`). Unauthorized emojis trigger `422 EMOJI_NOT_ALLOWED`.
   - `PUT` and `DELETE` reaction endpoints are fully idempotent, returning aggregated reaction counts and caller state (`reacted_by_me`). Reactions emit zero activity ledger records to avoid event log bloat.

7. **Permalinks & Activity Ledger:**
   - Every comment response includes a canonical copyable permalink (`/projects/{proj}/issues/{key}#comment-{uuid}`).
   - Emits structured activity events under category `COMMENT`: `COMMENT_CREATED`, `COMMENT_EDITED`, `COMMENT_DELETED`, and `MENTION_ACCESS_ACKNOWLEDGED`.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have completed the backend architecture and API Specialist Gate audit for `KANBA-85`. All REST contracts, timing floors, RLS policies, mention security barriers, concurrency controls, and pagination mechanisms are satisfied.

Verdict: APPROVED