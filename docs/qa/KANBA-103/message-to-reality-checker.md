# Reality-Checker QA Dossier: KANBA-103 (KB-P3-15)

## Ticket Overview
- Ticket ID: KANBA-103 (Authoritative spec: `docs/tickets/KB-P3-15.md`)
- Title: [Phase 3 / API] Stickies API, complexity heuristic, >=1.5x snooze & atomic ACL-preserving promote-to-doc
- Worktree: `/tmp/kb-wt-KANBA-103`
- Branch: `feat/KANBA-103`
- Implementing Author: `builder-17`

---

## 1. Traceability & Definition of Done Verification

All scoped deliverables from `docs/tickets/KB-P3-15.md` and Sections 8.1, 8.2, 12.2, and 3.4 of the Product Spec have been fully implemented:

1. **Target Files Implemented:**
   - `kanban/services/sticky_heuristic.py`: Complexity heuristic evaluator (`evaluate_sticky_promotion`, `PromotionAssessment`) detecting 5 triggers outside code fences (`char_length > 600`, `line_count > 10`, `headings >= 2`, `structured_block` [GFM table, ```` ```mermaid ````, `.svg`, code fence `> 6` inner lines], `outbound_links >= 3`), integer `>= 1.5x` snooze gate (`len * 2 >= snoozed * 3`), and promoted stub suppression.
   - `kanban/services/activity.py`: Registered 7 sticky event types in `ActivityEventType` (`STICKY_CREATED`, `STICKY_UPDATED`, `STICKY_RECOLORED`, `STICKY_PROMOTION_SNOOZED`, `STICKY_PROMOTED_TO_DOC`, `STICKY_UNARCHIVED_COPY`, `STICKY_TRASHED`) mapped to `ActivityCategory.HISTORY`.
   - `kanban/api/v1/schemas/stickies.py`: Pydantic schemas with `extra="forbid"`, `StickyColorToken` enum (amber, mint, sky, lavender, coral, slate), `StickyCreate`, `StickyUpdate`, `StickyPromoteRequest`, `PromotedDocSummary`, `StickyResponse`, `StickyList`.
   - `kanban/services/stickies.py`: Full CRUD for project and workspace stickies, keyset pagination, optimistic concurrency with `If-Match` ETag hash checks, soft deletion (`deleted_at`), `snooze_sticky_promotion`, `promote_sticky_to_doc` running under `SELECT ... FOR UPDATE` with cross-scope promotion guard (`422 CROSS_SCOPE_PROMOTION_FORBIDDEN`), verbatim direct ACL copy to new Doc and Page, ERA materialization, `object_links(PROMOTED_TO_DOC)` edge insertion, stub serialization, and `unarchive_sticky_copy`.
   - `kanban/api/v1/stickies.py`: 9 REST endpoints and aliases mounted under `/api/v1` wrapped in `timing_floor(floor_ms=25.0)` with RFC 7807 problem responses, ETag, and Location headers.
   - `kanban/api/v1/__init__.py`: Mounted `stickies.router` into the v1 API router.

2. **Heuristic & Promotion Verification:**
   - Evaluates complexity triggers strictly outside code fences.
   - Integer snooze math preserves snooze until body grows by `>= 1.5x` (`len * 2 >= snoozed * 3`).
   - Atomic promotion converts sticky to a Promoted Doc Stub (empty body markdown, `is_promoted_stub=True`, `promoted_to_doc_id` set, `promoted_doc_summary` attached).
   - Subsequent promotion attempts rejected with `409 ALREADY_PROMOTED`.
   - Subsequent body edits on promoted stubs rejected with `409 STICKY_ALREADY_PROMOTED`.
   - Direct ACL rows (`ALLOW` and `DENY` capability masks) copied verbatim to new Doc and root/nested Page.
   - Cross-scope promotion across different projects rejected with `422 CROSS_SCOPE_PROMOTION_FORBIDDEN`.
   - Nested sub-page promotion under existing Doc and parent Page verified.
   - 64KB UTF-8 octet boundary enforced via `_clean_body` raising RFC 7807 `422 STICKY_TOO_LARGE`.
   - Hidden DOM prompt-injection elements pruned on write.

---

## 2. Test Verification & Code Quality

- **Unit & Integration Test Suite:**
  - Ran `pytest kanban/tests/services/test_sticky_heuristic.py kanban/tests/api/test_stickies.py`:
    * `kanban/api/v1/stickies.py`: 100%
    * `kanban/services/sticky_heuristic.py`: 100%
    * `kanban/services/stickies.py`: 95%
    * Total target coverage: **96.88%** (exceeds `>= 95%` requirement).
  - 15/15 tests passed cleanly in 5.75s.

- **Static Analysis & Tooling Gate:**
  - `uv run ruff check kanban`: exit code 0 (zero warnings/errors).
  - `uv run ruff format --check kanban`: exit code 0 (198 files formatted).
  - `uv run mypy --strict kanban`: exit code 0 (196 source files clean).
  - `uv run lint-imports`: exit code 0 (2 kept, 0 broken).
  - `python3 scripts/check_no_dashes.py --all`: exit code 0 (zero Unicode dashes).
  - `make license`: exit code 0 (summary python=112 node=1 violations=0).

- **Artifacts in `docs/qa/KANBA-103/`:**
  - `unit-test-results.txt`: Full verbose pytest output with coverage report.
  - `build-check.txt`: Combined static analysis log.
  - `contract-sample.json`: Recorded HTTP contract exchanges for sticky lifecycle.
  - `acl-preservation-proof.txt`: Side-by-side SQL dump demonstrating verbatim ACL and ERA preservation.
  - `git-diff.patch`: Git diff patch against base commit.
