# Reality-Checker Audit Note: KANBA-102 (KB-P3-13)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-102` / `KB-P3-13`: `[Phase 3 / API] Activity feed API with 4 tabs (All, Comments, History, Agent/Workflow Gates) & cursor pagination`) implements the cursor-paginated activity feed REST API supporting Plane-parity filter tabs, single-query counts aggregation, HMAC-signed cursor keyset pagination, cryptographic hash chain verification exposure, comment hydration with soft-delete sanitization, and access-boundary redaction.

1. **Target Files**:
   - `kanban/api/v1/activity.py`: Two REST endpoints mounted on `build_v1_router()` wrapped with `timing_floor(floor_ms=25.0)`:
     * `GET /api/v1/issues/{issue_ref}/activity` (`Capability.VIEW` on issue, status 200)
     * `GET /api/v1/projects/{project_ref}/activity` (`Capability.VIEW` on project, status 200)
   - `kanban/api/v1/schemas/activity.py`: Pydantic request/response schemas with `ConfigDict(extra="forbid")`, validating `tab` enum (`all`, `comments`, `history`, `gates`), `order` enum (`desc`, `asc`), `limit` range (`1..100`), `include_hashes` boolean, discriminated `ActorSummary` (`normal` vs `redacted`), `ActiveCommentSummary` vs `SoftDeletedCommentSummary`, and `ActivityFeedResponse` with custom serializer suppressing null hashes.
   - `kanban/services/activity_feed.py`: Service layer implementing HMAC-SHA256 cursor minting and validation, `get_issue_activity`, `get_project_activity`, single-query counts aggregation under RLS, actor resolution with project membership boundary checks, payload sanitization (masking unreadable linked objects and redacting out-of-boundary principals), and batch comment hydration.
   - `kanban/services/activity.py`: Added `AGENT_GATE = "AGENT_GATE"` to `ActivityCategory`; registered `CREATOR_OVERRIDDEN`, `WIP_HARD_LIMIT_OVERRIDDEN`, `SYNC_HOOK_REJECTED`, `HOOK_FAIL_OPEN_WARN`, `GATE_PENDING`, `GATE_APPROVED`, `GATE_REJECTED`, `GATE_TIMED_OUT`, `GATE_CANCELLED` under appropriate categories.
   - `kanban/tests/services/test_activity.py`: Unit tests verifying taxonomy and category mapping.
   - `kanban/tests/api/test_activity_feed.py`: Comprehensive test suite covering all 5 mandatory feature test cases plus edge cases and branch coverage.

2. **Security & Redaction Invariants**:
   - **Soft-Deleted Comment Sanitization**: For `COMMENT_CREATED` and `COMMENT_EDITED` events where the associated comment has been soft-deleted (`deleted_at IS NOT NULL`), `body_markdown` is strictly omitted (serializing as `{"id": "...", "deleted": true}`), preventing deleted content leakage even if historical payloads exist.
   - **Out-of-Boundary Actor Redaction**: Principals lacking effective access on the project scope are scrubbed of usernames, emails, and identifiers, serializing strictly as `{"redacted": true, "label": "1 External Collaborator"}`.
   - **Unreadable Linked Object Masking**: Linked objects in `LINK_CREATED` / `LINK_DELETED` events that the caller cannot read under RLS are masked as `{"restricted": true, "label": "Restricted Object"}`.
   - **Anti-Enumeration Equivalence**: Unreadable or nonexistent issues and projects return byte-identical `404 NOT_FOUND` responses.
   - **HMAC Keyset Cursor Protection**: Opaque base64url cursors carry an HMAC-SHA256 signature binding `scope_id`, `tab`, `order`, `created_at_ns`, and `id`. Tampered or mismatched cursors return `422 INVALID_CURSOR`.
   - **Cryptographic Hash Chain Exposure**: `prev_hash` and `row_hash` 64-character lowercase hex strings are exposed only when `include_hashes=true`, otherwise omitted.

3. **Verification & Quality Status**:
   - **Unit Tests**: 6/6 passed in 4.36s with **96.58%** combined branch + line coverage (`kanban.api.v1.activity` 100%, `kanban.services.activity_feed` 96%).
   - **Static Checks**: Ruff check clean, Ruff format clean (750 files), Mypy strict clean (313 source files), Lint-imports clean (2 kept, 0 broken), License gate clean (violations=0), Zero non-ASCII dashes repo-wide.
   - **Contract Proof**: `contract-sample.json` captures all required wire exchanges (`tab=all` with `counts`, `tab=comments` with active and soft-deleted comments, `tab=gates`, `include_hashes=true`, `422 INVALID_CURSOR`, and non-viewer `404`).
   - **UI / Screenshots**: `Screenshots: N/A - Non-UI Ticket`.
