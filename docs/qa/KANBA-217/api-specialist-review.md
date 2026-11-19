# API Specialist Forensic QA Review: KANBA-217

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KANBA-217 (Fix Stickies Snooze 422 Crash, Wire AI Sticky-to-Doc Preview & Valid Doc Target, and Implement Docs Version Diff/Restore & Highlight-to-Issue Linking)
Branch: feat/w4-docs (integrated into main at commit 9069325)
Review Date: 2026-11-18

## 1. Architectural & Engineering Assessment

### 1.1 Sticky Snooze Schema Alignment (kanban/api/v1/schemas/stickies.py, kanban/services/stickies.py)
- Added `promotion_snoozed_at_length: int | None` to `StickyUpdate` Pydantic schema, eliminating the HTTP 422 Unprocessable Entity error when snoozing promotion recommendations.
- When `promotion_snoozed_at_length` is updated, `evaluate_sticky_promotion` re-evaluates promotion recommendations dynamically based on character count thresholds (re-triggering only after >= 1.5x body expansion).
- Client handles error states inline within stickies components, preventing uncaught error boundary crashes.

### 1.2 Direct Link Creation Endpoint (kanban/api/v1/links.py, kanban/api/v1/schemas/links.py)
- Implemented `POST /api/v1/links` (`create_link_direct`) accepting `DirectLinkCreateRequest` (`source_id`, `target_id`, `link_type`).
- Enforces taint checking across source and target projects (`taint_guard.check_write`).
- Adheres to Universal Object Graph integrity by delegating to `create_object_link` with RLS session isolation and timing floor defense (25.0ms) against enumeration attacks.
- Supports typed link relationships including `VERIFIED_BY_DOC` and `RELATES_TO`.

### 1.3 Project Page Creation & First-Doc Race Remediation (kanban/api/v1/docs.py, kanban/services/docs.py)
- Implemented `POST /api/v1/projects/{project_ref}/docs/pages` to create hierarchical pages within a project, automatically creating a parent doc container if one does not exist.
- Returns 201 Created with `Location` and `ETag` response headers.
- Eliminates transient 404 races when provisioning the first document in a new project.
- Enhanced `_resolve_page_id` to transparently resolve doc UUIDs and doc canonical keys to their root page, preventing 404 navigation errors when opening promoted documents.
- `PromotedDocSummary` schema enriched with `root_page_id` and `root_page_canonical_key`.

### 1.4 Docs Version Diff, Restore, and Link Picker APIs
- Page versioning endpoints (`GET /api/v1/pages/{page_ref}/versions`) return full history diffs.
- Non-destructive 1-click restore persists a new version snapshot while preserving chronological audit history.
- Searchable link picker connects highlights to issue entities without requiring raw UUID entry.

## 2. Test Verification & Code Quality

- Automated E2E & Component Tests: `kanban/web/e2e/qa/kanba217-docs-stickies-qa.spec.ts` passes with full visual and behavioral coverage across 8 scenarios.
- Backend Pytest Suites: `kanban/tests/api/test_links.py` and docs service tests pass cleanly.
- Frontend Vitest Suites: 2306 unit tests pass with >=95% branch coverage.
- Static Analysis: `ruff check` (0 errors), `mypy` (0 errors), `pnpm typecheck` (0 errors), `pnpm lint` (0 errors).
- Plain ASCII Check: `scripts.check_no_dashes --all` passed (0 em/en-dashes).

## 3. Wave 4 Sibling Ticket Verification (KANBA-211 and KANBA-212)

- `KANBA-211` (`docs/qa/KANBA-211/api-specialist-review.md`): Verified existing STATUS: APPROVED. Cycles and modules lifecycle transitions, soft/hard state updates, and burnup metrics conform to API contracts.
- `KANBA-212` (`docs/qa/KANBA-212/api-specialist-review.md`): Verified existing STATUS: APPROVED. Backend ETag 304 hashing incorporates all issue attributes, optimistic locking `If-Match` 412/428 handling works cleanly, and mock strings are fully purged.

## 4. Specialist Verdict

The sticky snooze schema, direct link creation, project page creation, and doc root resolution satisfy all architectural, schema, and security invariants.
`STATUS: APPROVED`
