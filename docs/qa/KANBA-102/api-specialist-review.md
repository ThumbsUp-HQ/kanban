# API Specialist Gate Review: KANBA-102 (KB-P3-13)

- **Ticket**: `KANBA-102` (`KB-P3-13`: Activity feed API with 4 tabs (All, Comments, History, Agent/Workflow Gates) & cursor pagination)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-102` (`HEAD: ee8e65d`)
- **Worktree**: `/tmp/kb-wt-KANBA-102`
- **Scope**: `kanban/api/v1/activity.py`, `kanban/api/v1/schemas/activity.py`, `kanban/services/activity_feed.py`, `kanban/services/activity.py`

---

### 1. Architectural & Security Evaluation

#### A. REST API Endpoints & Timing Floor (S7.1, S7.2 8j, S3.4)
- Both endpoints (`GET /api/v1/issues/{issue_ref}/activity` and `GET /api/v1/projects/{project_ref}/activity`) are wrapped in `timing_floor(floor_ms=25.0)`.
- Issue-scoped retrieval enforces `Capability.VIEW` on the target issue. Unreadable or nonexistent issues return uniform HTTP 404 responses with zero principal or issue key side-channel leakage.
- Project-scoped retrieval enforces `Capability.VIEW` on the project and evaluates RLS visibility per issue row: issues with an explicit `DENY VIEW` ACL produce 0 items and contribute 0 to the aggregated counts summary.
- Query limits are bounded strictly between 1 and 100 (`ge=1, le=100`, default 50).

#### B. 4-Tab Filtering & Single-Query Counts Aggregation
- Full support for the four Plane-parity drawer tabs: `all`, `comments`, `history`, `gates`.
- Deterministic event category taxonomy:
  - `COMMENT`: `COMMENT_CREATED`, `COMMENT_EDITED`, `COMMENT_DELETED`, `MENTION_ACCESS_ACKNOWLEDGED`.
  - `HISTORY`: all issue, provenance (`CREATOR_OVERRIDDEN`), link, state, label, module, cycle, WIP override (`WIP_HARD_LIMIT_OVERRIDDEN`), archive, trash, and doc/page/sticky lifecycle events.
  - `AGENT_GATE`: `SYNC_HOOK_REJECTED`, `HOOK_FAIL_OPEN_WARN`, `GATE_PENDING`, `GATE_APPROVED`, `GATE_REJECTED`, `GATE_TIMED_OUT`, `GATE_CANCELLED`.
- Counts aggregation query executes under RLS, returning `{all, comments, history, gates}` in a single database round trip to drive drawer tab badges without redundant network queries.

#### C. Keyset Cursor Pagination & HMAC Tampering Defenses
- Cursors are minted as base64url HMAC-SHA256 signed tokens encoding `{scope_id, tab, order, created_at_ns, id}`.
- Tampered tokens, malformed signatures, or tokens passed to a mismatched tab, order, or scope immediately fail with HTTP 422 `INVALID_CURSOR`.
- Cursor pagination correctly navigates across monthly partition boundaries (e.g. `2026-10-31T23:59:59Z` to `2026-11-01T00:00:01Z`) in both `desc` and `asc` order without skipping or duplicating records.

#### D. Hydration, Redaction & Privacy Isolation (S3.4)
- Comment hydration: Active comments are batch-joined in 1 query per page, returning `{id, body_markdown, permalink, edited_at, reactions}`.
- Soft-deleted comments (`issue_comments.deleted_at IS NOT NULL`): Serialized as `{id, deleted: true}` with **zero** `body_markdown` leakage, even if historic text exists in the immutable activity payload.
- Actor boundary redaction: Principals outside the caller's workspace visibility boundary pass through the `KB-P2-11` visibility redactor and serialize as `{"redacted": true, "label": "1 External Collaborator"}` with zero handle or email leakage.
- Linked object masking: Unreadable linked objects in `LINK_CREATED` / `LINK_DELETED` events are masked as `{"restricted": true, "label": "Restricted Object"}`.
- Hash-chain audit exposure: Cryptographic `row_hash` and `prev_hash` hex strings are exposed only when `include_hashes=true` is explicitly requested, remaining `None` otherwise.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 12/12 pytest passed in 4.39s across `test_activity_feed.py` and `test_activity.py`, verifying positive 4-tab filtering, deleted comment body suppression, actor redaction, project RLS filtering, hash-chain exposure, boundary limits, and HMAC cursor tamper resistance.
- **Coverage**: 96.58% total coverage across touched modules:
  - `kanban/api/v1/activity.py`: 100%
  - `kanban/services/activity_feed.py`: 96%
- **Static Analysis**: Ruff check clean, Ruff format clean (750 files), Mypy strict clean (313 files), ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.
- **Proof Bundle**: Complete forensic bundle (`contract-sample.json`, `unit-test-results.txt`, `build-check.txt`, `git-diff.patch`, `ui-specialist-review.md`).

---

### 3. Gate Verdict

The 4-tab activity feed API, HMAC-signed cursor pagination, comment hydration, actor privacy redaction, and counts aggregation comply with all architectural, security, and quality invariants.

**VERDICT: APPROVED**
