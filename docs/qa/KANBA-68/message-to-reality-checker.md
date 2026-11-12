# Reality-Checker Verification Packet: KANBA-68 (KB-P3-14)

## Ticket Metadata
- Ticket ID: `KANBA-68`
- Spec Key: `KB-P3-14`
- Title: `[Phase 3 / API] Docs & pages API: ltree hierarchy CRUD/move, append-only version history/restore & outline extraction`
- Epic: `KB-E3`
- Spec Sections: `8.1`, `5.1`, `12.2`, `3.4`
- Dependencies: `KB-P2-13`, `KB-P2-11`, `KB-P1-09`, `KB-P1-14`
- Gates: `reality-checker` (Passive Forensic Mode), `api-specialist`, `ui-specialist`

---

## User Story
As a **project member or knowledge agent**, I need **REST endpoints to create, edit, move, and organize hierarchical Docs and `ltree` Pages (`max_depth <= 10`), extract heading outlines, and inspect or restore immutable `page_versions` snapshots** so that **permanent architecture specs live in canonical Markdown with ETag concurrency and explicit sharing visibility**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** All target modules exist and implement the specified domain behavior:
  - `kanban/services/lexorank.py`: Base-62 `midpoint_rank(prev, next_)` algorithm conforming to C-collation order.
  - `kanban/services/markdown_outline.py`: `extract_markdown_outline(body_markdown)` parsing ATX headings strictly outside code fences and HTML comments with deterministic slug anchor deduplication.
  - `kanban/services/activity.py`: Appended 8 `DOC_*` and `PAGE_*` event types under `HISTORY` category.
  - `kanban/api/v1/schemas/docs.py`: Pydantic models with `extra="forbid"`, `restricted: bool = False`.
  - `kanban/api/v1/docs.py`: Implemented all 14 REST endpoints mounted on `build_v1_router()` with 25.0ms timing floor.
  - `kanban/services/docs.py`: Complete domain service implementing ltree hierarchy, restricted ancestor masking via ltree path parsing (`_extract_ancestor_uuids`), Base-62 sort_rank computation, optimistic locking with `If-Match` SHA-256 ETag, and soft delete.
- [x] **Mandatory Unit Tests Passing & >= 95% Coverage:** Pytest suite passes 100% (30/30 passed) with >= 95% line and branch coverage across all 4 target modules (`kanban.api.v1.docs`, `kanban.services.docs`, `kanban.services.markdown_outline`, `kanban.services.lexorank`).
- [x] **Build, Typecheck, and Static Analysis Clean:** `ruff check`, `ruff format --check`, `mypy --strict kanban database`, `lint-imports`, `make license`, and `python -m scripts.check_no_dashes --all` all exit `0`.
- [x] **Contract Sample Captured:** `docs/qa/KANBA-68/contract-sample.json` captures wire exchanges for doc/page CRUD, versions, restore, move, tree, and deletions.
- [x] **Specialist Gate Approvals:** Independent reviews from `@arch-reviewer` (`api-specialist-review.md`) and `@ui-specialist` (`ui-specialist-review.md`) ending with explicit `APPROVED` lines.
- [x] **Zero Forbidden Unicode Dashes:** Repo-wide check confirms zero `U+2014` or `U+2013` dashes.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-68/`.

---

## Mandatory Feature Unit Tests Matrix (10 DoD Cases Covered across 30 Tests)

| DoD Case | Category | Test Target | Verification Description |
| :--- | :--- | :--- | :--- |
| **Case 1** | Docs & Pages CRUD, Outline & ETag | `test_docs_pages.py::test_case_1_docs_pages_crud_versions_and_outline` | Create doc and pages P1->P2->P3; verify outline anchors, breadcrumbs hierarchy, ETag generation, version sequence increments, and list/get versions. |
| **Case 2** | Version Restore Concurrency | `test_docs_pages.py::test_case_1_docs_pages_crud_versions_and_outline` | Restore version 1 under `If-Match` yields version 4 with version 1 content; GET page reflects restored content. |
| **Case 3** | Tree Move & DAG Guards | `test_docs_pages.py::test_case_2_tree_move_and_dag_guards` | Moving P1 under P3 fails with 409 `PAGE_CYCLE`; moving to foreign doc fails with 422 `PAGE_PARENT_DOC_MISMATCH`; depth > 10 fails with 422 `PAGE_MAX_DEPTH_EXCEEDED`. |
| **Case 4** | Lexorank Sibling Ordering | `test_docs_pages.py::test_lexorank_sibling_ordering` | Positional insertion using `after_page_id`, `before_page_id`, and moving before first sibling maintains strict C-collation ordering. |
| **Case 5** | Concurrency & Validation Bounds | `test_docs_pages.py::test_concurrency_and_boundaries` | Missing `If-Match` returns 428; stale `If-Match` returns 412 with `current_etag`; title > 500 chars fails with 422 `TITLE_LENGTH`; body > 1 MiB fails with 422 `BODY_TOO_LARGE`. |
| **Case 6** | Security & Restricted Ancestor Masking | `test_docs_pages.py::test_security_and_restricted_ancestor_masking` | When caller has `VIEW` on P2 but `DENY VIEW` on ancestor P1: GET P1 returns 404; GET P2 and GET doc tree mask P1 as `{"restricted": true, "label": "🔒 Restricted Page"}` with zero ID, title, or slug leaks. |
| **Case 7** | Soft-Delete Subtree Cascade | `test_docs_pages.py::test_soft_delete_lifecycle` | Deleting page P1 soft-deletes P1 and descendant P2 in `objects`; deleting doc soft-deletes document and all pages; subsequent GET returns 404. |
| **Case 8** | Title-Only & Body-Only PATCH | `test_docs_pages.py::test_doc_patch_and_etag_caching` | PATCH title only requires no `If-Match`; PATCH body only validates `If-Match`; GET with `If-None-Match` returns 304 Not Modified. |
| **Case 9** | Workspace-Scoped Docs & Slugs | `test_docs_pages.py::test_workspace_level_docs_and_duplicate_slugs` | Workspace-level doc (`project_id=None`) lists correctly; duplicate titles allocate deduplicated slug suffixes (`-1`). |
| **Case 10** | Version Pagination & Restore Guards | `test_docs_pages.py::test_version_history_edge_cases` | Cursor-based version pagination; missing version seq returns 404; restore with missing/stale `If-Match` returns 428/412; unknown doc/page ref returns 404. |

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Lexorank Service** | `kanban/services/lexorank.py` | Base-62 positional arithmetic with `midpoint_rank(prev, next_)` supporting infinite fractional midpoint generation. |
| **Markdown Outline Service** | `kanban/services/markdown_outline.py` | AST/fenced-code-aware ATX heading parser outside code fences/HTML comments with GitHub-slug deduplication. |
| **Activity Event Types** | `kanban/services/activity.py` | Appended 8 `DOC_*` and `PAGE_*` events under `HISTORY` category. |
| **Docs Schemas** | `kanban/api/v1/schemas/docs.py` | Pydantic v2 schemas: `DocCreate`, `DocUpdate`, `DocResponse`, `PageCreate`, `PageUpdate`, `PageMove`, `PageResponse`, `PageTreeNode`, `BreadcrumbItem`, `OutlineItem`, `PageVersionResponse` with `extra="forbid"`. |
| **Docs Service Layer** | `kanban/services/docs.py` | Full domain implementation: CRUD, Base-62 sorting, ltree path ancestor parsing, restricted ancestor masking, ETag/If-Match concurrency, soft deletion. |
| **Docs API Router** | `kanban/api/v1/docs.py` | 14 REST endpoints mounted at `/api/v1/docs` and `/api/v1/pages` with 25.0ms timing floor. |
| **Router Mount** | `kanban/api/v1/__init__.py` | Mounted `docs_router` into canonical v1 API router tree. |
| **Problem Exceptions** | `kanban/api/problems.py` | Added `current_etag` parameter to `Problem` and `ProblemException` for 412 precondition responses. |

---

## Forensic Proof Artifacts in `docs/qa/KANBA-68/`
1. `git-diff.patch`: Complete unified git diff against base commit.
2. `unit-test-results.txt`: Test suite output and exit code for 30 target tests (>= 95% coverage across all target modules, EXIT: 0).
3. `build-check.txt`: Static analysis and build check results (ruff, format, mypy, lint-imports, license, check_no_dashes all EXIT: 0).
4. `contract-sample.json`: Captured HTTP wire exchanges for all key doc and page operations.
5. `api-specialist-review.md`: Independent audit and approval from API Specialist (`@arch-reviewer`).
6. `ui-specialist-review.md`: Independent audit and approval from UI Specialist (`@ui-specialist`).
7. `message-to-reality-checker.md`: This forensic sign-off document.
