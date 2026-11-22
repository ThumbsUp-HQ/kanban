# API & Security Specialist Review: KAN-309 (`[KB-ISSUES-TTFD-01]`)

- **Reviewer Persona:** `backend-architect` / `api-tester` / `security-engineer` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-309` (`[KB-ISSUES-TTFD-01] Cut Issues View Time-to-First-Display on 300+ Tickets via Single-Flight Staged Loading, Batched lod=summary API, and Lazy Issue Detail Hydration`)
- **Audited Commit (`HEAD`):** `e662d6781584b9883dd45ade51d0d280008325c1` (`e662d678`, merging `ad9a1daf7cae5088eb7c8b4e72ce006a8e8be342`)
- **Audited Branch:** `main` (merged from `feat/KAN-309-ttfd-summary-lod`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-309/git-diff.patch`
  - `docs/qa/KAN-309/contract-sample.json`
  - `docs/qa/KAN-309/unit-test-results.txt`
  - `docs/qa/KAN-309/build-check.txt`
  - `docs/qa/KAN-309/message-to-reality-checker.md`
  - `docs/qa/KAN-309/screenshots/01-desktop-light-issues-ttfd-summary.png`
  - `docs/qa/KAN-309/screenshots/02-desktop-dark-issues-ttfd-summary.png`
  - `docs/qa/KAN-309/screenshots/03-tablet-issues-ttfd-summary.png`
  - `docs/qa/KAN-309/screenshots/04-mobile-portrait-issues-ttfd-summary.png`
  - `docs/qa/KAN-309/screenshots/05-mobile-landscape-issues-ttfd-summary.png`
- **Reviewed Source & Test Files:**
  - `kanban/api/v1/issues.py`
  - `kanban/api/v1/schemas/issues.py`
  - `kanban/services/issues.py`
  - `kanban/web/openapi.json`
  - `kanban/web/src/api/schema.gen.ts`
  - `kanban/tests/api/test_issues.py`
  - `kanban/web/src/features/views/viewsApi.ts`
  - `kanban/web/src/features/views/viewRegistry.tsx`
  - `kanban/web/src/features/board/BoardView.tsx`
  - `kanban/web/src/features/board/boardApi.ts`
  - `kanban/web/src/features/drawer/IssueSurface.tsx`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-309` optimizes the Time-to-First-Display (TTFD) across Board, List, and Table views for projects with 300+ issues. Prior to this optimization, loading issues views required transferring full Markdown description bodies and computing deep access manifests across every row in the project, compounded by duplicate unpaginated network requests on board mounting.

The implementation introduces:
1. **Tiered Level-of-Detail (LOD) Querying:** `GET /api/v1/projects/{project_ref}/issues` and `GET /api/v1/issues/{issue_key}` accept `lod: Literal["summary", "standard", "full"] = Query(default="full")`.
2. **SQL Column Deferral & Selective Batch Hydration:** When `lod == "summary"`, SQLAlchemy query execution applies `defer(Issue.description_markdown)` to eliminate unnecessary IO and network payload bloat. `serialize_issues_batch` bypasses expensive transitive group closures, ACL computations, role bindings, and activity log scans while strictly preserving all board and list display metadata (key, summary, state, priority, assignees, labels, module_ids, cycle, board_rank, gate_status, estimate_points, due_date, updated_at, created_at, and strong ETag).
3. **OpenAPI & TypeScript Parity:** The OpenAPI 3.1 specification (`openapi.json`) and generated schema (`schema.gen.ts`) cleanly reflect optional `description_markdown` and `access_manifest` fields alongside the new `lod` query parameter.
4. **Single-Flight Staged Loading & Lazy Hydration:** Two-phase staged loading renders Phase 1 (first 100 summary cards) immediately while Phase 2 hydrates remaining issues in the background. The issue drawer lazily loads full descriptions and access manifests on click, rendering an accessible skeleton during network flight.
5. **Quality & Test Compliance:** 20 Pytest unit/integration tests and 161 Vitest frontend tests passed with zero failures. Static analysis (`make check`, `pnpm check:api`, `tsc`, `eslint`) and repo-wide dash checks passed cleanly with 0 errors.

---

## 2. API Contract & Wire Protocol Verification

### 2.1 Backend Level of Detail API (`kanban/api/v1/issues.py`, `kanban/services/issues.py`)
- Endpoint signature:
  `GET /api/v1/projects/{project_ref}/issues?lod=summary&limit=100`
- Query parameter validation:
  - Allowed values: `"summary"`, `"standard"`, `"full"`.
  - Default: `"full"` for complete backwards compatibility.
- Database query optimization:
  - When `lod == "summary"`: `stmt = stmt.options(defer(Issue.description_markdown))` prevents fetching large Markdown text from Postgres.
  - In `_hydrate_batch_issue_context`: `overridden_issue_ids` activity queries, transitive group closures, and ACL lookups are skipped.
  - In `serialize_issues_batch`: `description_markdown = None`, `access_manifest = None`, and `capabilities = ["VIEW"]`.
- Strong ETag Preservation:
  - `compute_issue_etag` utilizes the stored `description_sha256` column hash without loading `description_markdown`, ensuring HTTP caching (`If-None-Match` -> `304 Not Modified`) remains fully functional.

### 2.2 Wire Frame Contracts (`docs/qa/KAN-309/contract-sample.json`)
The recorded wire exchanges verify:
- `summary_lod_sample`: Demonstrates lightweight summary item payload where `description_markdown: null`, `access_manifest: null`, and `capabilities: ["VIEW"]`, while preserving full card layout metadata.
- `full_lod_sample`: Demonstrates full item payload for drawer hydration where `description_markdown` and full `access_manifest` are fully populated.

---

## 3. Security, RLS & Invariant Verification

1. **Anti-Enumeration and RLS Retention:** Even in `lod=summary` mode, project resolution (`get_project_or_404`), keyset pagination, and issue filtering run under caller RLS session context (`kanban_app` with `FORCE ROW LEVEL SECURITY`). Unreadable projects or issues are never exposed.
2. **Masked Parent Summary Retention:** Parent issue summaries continue to respect `RestrictedParentSummary` masking when the caller lacks `VIEW` permission on parent issues, retaining KAN-85 security invariants.
3. **Lazy Authorization Elevation:** Heavyweight capability evaluation and access manifests are safely deferred until single-issue inspection (`GET /api/v1/issues/{key}?lod=full`), aligning with least-privilege principles and drastically reducing computational overhead during initial view display.

---

## 4. Test Verification & Code Coverage

- **Pytest Suite (`kanban/tests/api/test_issues.py`):**
  - `test_kan309_list_issues_lod_summary_defers_description_and_omits_access_manifest`: PASSED
  - `test_kan85_serialize_issues_batch_byte_for_byte_payload_and_etag_parity`: PASSED (backwards compatibility retained)
  - `test_kan85_list_issues_100_items_query_count_bound`: PASSED
  - `test_kan85_rls_restricted_parent_and_capability_parity_under_force_rls`: PASSED
  - 20 total tests passed in 10.48s
- **Frontend Vitest Suite:**
  - 161 total tests passed in 10.28s across `viewsApi.test.ts`, `viewRegistry.test.tsx`, `IssueSurface.test.tsx`, `BoardView.test.tsx`, and `boardApi.test.ts`.
- **Static Analysis & Schema Parity:**
  - `pnpm --dir kanban/web run check:api`: 0 errors (100% parity between OpenAPI spec and TypeScript schema)
  - `make check`: 0 errors
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (zero em/en-dashes)

---

## 5. Review Sign-Off

The API contracts, database query optimizations, ETag consistency, and security boundaries for `KAN-309` are approved.

**STATUS: APPROVED**
