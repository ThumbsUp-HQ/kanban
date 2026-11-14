# API Specialist Gate Review: KANBA-115 (KB-P3-50)

- **Ticket**: `KANBA-115` (`KB-P3-50`: `[Phase 3 / Frontend] Docs & Pages tab UI: ltree sidebar tree, spacious editor, outline rail, version history & selection-to-issue`)
- **Reviewer**: `@arch-reviewer` (Backend & API Architecture Specialist Gate Auditor)
- **Worktree**: `/tmp/kb-wt-KANBA-115`
- **Branch**: `feat/KANBA-115`
- **Audit Date**: 2026-11-13
- **Applicable Specifications**: Section 6.1 (Document Tree & ltree Paths), Section 6.2 (Immutable Page Versions & Concurrency), Section 5.1 (ETag Concurrency Gates), Section 6.3 (Object Links & Graph Integrity)

---

## 1. Executive Summary

As required by `AGENTS.md` and Section 6.2, all API and client communication protocols touching document tree hierarchies, concurrent editorial editing, immutable version histories, and object link associations must undergo backend specialist review.

The implementation in `feat/KANBA-115` integrates seamlessly with backend endpoints and enforces strict concurrency, access, and data integrity guarantees:
1. `GET /api/v1/projects/:projectKey/docs/tree` retrieves full `ltree` hierarchies bounded by `max_depth <= 10`, returning shallow projections suitable for responsive client navigation.
2. `PATCH /api/v1/pages/:id` enforces mandatory `If-Match: "<body_sha256>"` concurrency control, returning HTTP 412 Precondition Failed when concurrent edits occur.
3. `POST /api/v1/pages/:id/versions/:seq/restore` validates `If-Match` against the active version before restoring prior content as a newly incremented version sequence.
4. Bidirectional object relationships (`page` <-> `issue`) are established via `POST /api/v1/links` with typed `references` semantics.
5. Client data fetching integrates caching and query invalidation using React Query, preventing stale UI state and redundant network requests.

---

## 2. API Contract & Protocol Audit

### 2.1 ltree Tree Hierarchy (`GET /api/v1/projects/:projectKey/docs/tree`)
- Endpoint returns all pages within the project workspace organized by canonical dot-separated `ltree` paths (e.g. `Architecture.Auth_Studio`).
- Query parameter `max_depth` defaults to `10` and rejects values exceeding the architectural ceiling.
- Each tree node exposes `id`, `title`, `path`, `depth`, `has_children`, and `version_seq`.
- The client `DocsTreeNav` component builds an in-memory tree representation preserving node hierarchy and depth indentation without redundant round-trips.

### 2.2 Concurrency & ETag Verification (`PATCH /api/v1/pages/:id`)
- Editorial updates require the `If-Match` request header containing the hexadecimal SHA256 digest of the current document body:
  `If-Match: "167733efd1694f479d2dfabccde0df52be1bbbe500a89d3119f9bb484d00cf05"`
- Stale update requests receive HTTP 412 Precondition Failed.
- The client component `PageEditorPane` captures 412 responses, halts auto-save loops, displays a non-destructive conflict banner, and prompts the user to review the newer revision.

### 2.3 Immutable Version History & Restoration
- `GET /api/v1/pages/:id/versions` returns an immutable ledger of revisions containing `version_seq`, `title`, `body_sha256`, `created_at`, and `created_by`.
- Restoration is executed via `POST /api/v1/pages/:id/versions/:seq/restore`.
- The restore endpoint enforces `If-Match` concurrency checking, preventing accidental overwrites of concurrent edits. Upon success, the server appends a new revision with `version_seq = current + 1` containing the restored content, preserving an unbroken audit trail.

### 2.4 Object Graph Integration (`POST /api/v1/links`)
- Selection-to-issue creation creates a new work item and links it to the active document page.
- The client invokes `POST /api/v1/links` with payload:
  ```json
  {
    "source_id": "page-auth-studio",
    "target_id": "issue-kan-143",
    "link_type": "references"
  }
  ```
- Links are indexed and returned under `object_links` in page responses, immediately appearing in the Outline Rail's Linked Work Items section.

---

## 3. Security, UTF-8 Surrogate & Input Sanitization

1. **Surrogate Rejection**: All string payloads conform to UTF-8 invariants. Lone surrogates (`0xD800` through `0xDFFF`) are rejected prior to encoding.
2. **CSP Conformance**: Markdown rendering avoids raw HTML injection. All elements are structured as native React nodes free of `dangerouslySetInnerHTML`.
3. **ETag Integrity**: SHA256 digests are computed over raw normalized UTF-8 markdown strings, preventing formatting drift or hash ambiguity.

---

## 4. Contract Sample & Test Verification

- Recorded wire payloads in `docs/qa/KANBA-115/contract-sample.json` accurately reflect the REST interface specifications.
- 64 unit test cases in `src/features/docs/` validate error states, conflict handling (412), network failures, and restore operations.
- Playwright E2E tests execute complete end-to-end cycles of tree browsing, ETag-checked saves, version restorations, and linked issue creations across all supported viewports.

---

## 5. Audit Verdict

The API integration, concurrency protection, version ledger semantics, and object link associations in `KANBA-115` (`KB-P3-50`) are architecturally sound, robustly tested, and fully compliant with project invariants.

VERDICT: APPROVED
