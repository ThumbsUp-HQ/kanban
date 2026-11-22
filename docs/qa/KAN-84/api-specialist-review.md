# API Specialist Review: KAN-84 (`[KB-MIGRATION-MERGE-QA-01]`)

- **Reviewer Persona:** `backend-architect` (API Specialist Reviewer)
- **Ticket:** `KAN-84` (`[KB-MIGRATION-MERGE-QA-01]`)
- **Audited Commit (`HEAD`):** `a29cd88b34abba131d1cef9c17ef5254352c24ce` (`a29cd88b`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-84/git-diff.patch`
  - `docs/qa/KAN-84/contract-sample.json`
  - `docs/qa/KAN-84/unit-test-results.txt`
  - `docs/qa/KAN-84/build-check.txt`
  - `docs/qa/KAN-84/live-fullstack-proof.txt`
- **Reviewed Source & Test Files:**
  - `kanban/importer/plane_mapper.py`
  - `kanban/importer/plane_importer.py`
  - `kanban/api/v1/issues.py`
  - `kanban/services/issues.py`
  - `kanban/web/openapi.json`
  - `kanban/web/src/api/schema.gen.ts`
  - `kanban/tests/importer/test_merge_into_existing_project_realistic.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

The KAN-84 backend, importer, and REST API changes meet enterprise production standards for transactional safety, data integrity, multi-tenant RLS enforcement, and OpenAPI contract parity. Merging 221 legacy `KANBA` issues (`KANBA-1..233` with 12 sequence gaps) into an active 83-issue `KAN` project (`KAN-1..83`) preserves all pre-existing issues byte-for-byte, allocates fresh monotonic sequences `KAN-84..304`, records legacy key aliases (`KANBA-1 -> KAN-84`), deduplicates workflow states across separator variants (`"Crazy Ideas"` -> `"Crazy_Ideas"`, `"Canceled"` -> `"Cancelled"`), and exposes server-side `state_group` filtering alongside keyset pagination on `GET /api/v1/projects/{project_ref}/issues`.

All backend (`91 passed`, `96%` total coverage across the 4 audited modules) and frontend (`105 passed`, `100%` line/statement/function coverage on tested view/API modules) suites, static checks (`ruff`, `mypy`, `lint-imports`, `check_no_dashes`, `check-migrations`), and live Docker full-stack contract assertions (`http://127.0.0.1:18984`) passed cleanly with zero mocks.

---

## 2. Transactional Merge & Non-Clobber Guarantees

Audited `PlaneImporter` (`kanban/importer/plane_importer.py`) and `kanban/tests/importer/test_merge_into_existing_project_realistic.py`:

- **Target Project Resolution & Exclusion Isolation (`plane_importer.py:203-260`, `838-845`):**
  - When `target_project_identifier` is supplied (`"KAN"`), `PlaneImporter._execute_import` validates the existing `Project` row in the caller's workspace or raises `ImportIntegrityError` (`plane_importer.py:224-236`).
  - Excluded projects (`exclude_project_identifiers={"TEST"}`) are filtered out prior to project, state, label, cycle, module, and issue ingestion (`plane_importer.py:203-220`, `379-382`, `838-845`). Test verification confirms `0` leaked `TEST` issues (`test_merge_into_existing_project_realistic.py:588-600`).
- **Sequence Allocation Without Overwrite (`plane_importer.py:847-880`, `906-907`, `952-1176`):**
  - Unmapped active issues are sorted ascending by source `sequence_id` (`plane_importer.py:855`) and assigned fresh target sequences in batches `<= 1000` via PostgreSQL `allocate_issue_sequences(:proj_id, :count, true)` (`plane_importer.py:862-870`).
  - For the 221 `KANBA` issues (`1..233` with 12 gaps) merged onto `KAN-1..83`, sequences allocate cleanly as `KAN-84..304`, raising `projects.issue_seq_counter` to `304` and setting `report.sequence_high_water_mark = 304`.
  - Pre-existing `KAN-1..83` records (`id`, `sequence_id`, `canonical_key`, `summary`, `description_markdown`, `description_sha256`, `state_id`, `priority_id`, `board_rank`, `created_at`, `updated_at`, `archived_at`) are never mutated during merge (`test_merge_into_existing_project_realistic.py:464-490`, `571-585`).
- **Legacy Key Aliasing & Provenance (`plane_importer.py:1030-1033`, `1153-1161`):**
  - Remapped issues persist an `IssueKeyAlias` record (`legacy_key="KANBA-1"`, `issue_id=issue_id`, `source_system="plane"`) and prepend `> Imported from \`KANBA-1\`` to the normalized description.
  - `GET /api/v1/issues/KANBA-1` resolves cleanly to `KAN-84` with HTTP `200`, JSON `key="KAN-84"`, and header `X-Kanban-Canonical-Key: KAN-84` (`issues.py:72-103`, `contract-sample.json:125-137`).
- **Post-Import Graph Integrity & Idempotency (`plane_importer.py:1313-1326`, `test_merge_into_existing_project_realistic.py:616-642`):**
  - `audit_object_links(:ws)` runs at the end of import and aborts with `ImportIntegrityError` if `invalid_link_count > 0`.
  - Re-running `PlaneImporter.run_import` against the same `PlaneBundle` produces `report2.to_create == 0` and maintains `304` total issues.

---

## 3. Separator-Insensitive Workflow State Normalization

Audited `normalize_state_key` (`kanban/importer/plane_mapper.py:73-81`) and `PlaneImporter` (`kanban/importer/plane_importer.py:374-443`, `920-923`, `1036-1056`):

- **`normalize_state_key` Contract (`plane_mapper.py:73-81`):**
  - Handles `None` / empty input (`""`), runs `normalize_plain_text(name)[:500].strip().lower()`, collapses `[\s_-]+` to `""`, and canonicalizes US spelling `"canceled"` to `"cancelled"`.
  - Verified mappings: `"Crazy Ideas"` / `"Crazy_Ideas"` / `"crazy-ideas"` -> `"crazyideas"`, `"Canceled"` -> `"cancelled"`, `"In Progress"` -> `"inprogress"` (`test_merge_into_existing_project_realistic.py:652-658`).
- **Zero Duplicate `WorkflowState` Guarantee (`plane_importer.py:374-430`):**
  - State ingestion checks exact lower-case name (`states_by_name`), then separator-collapsed key (`states_by_norm`), then canonical group fallback (`states_by_group` restricted to `{"backlog", "todo", "inprogress", "done", "cancelled"}`) before inserting a new `WorkflowState`.
  - Newly created states update both `states_by_name` and `states_by_norm` (`plane_importer.py:427-429`) to prevent intra-bundle duplicates.
  - Issue-level fallback resolution (`plane_importer.py:1045-1051`) mirrors this lookup order via `states_by_proj_and_norm` (`plane_importer.py:921-923`).
  - Verified in both unit tests (`len(all_states) == 6`, `"Crazy Ideas"` lands in `Crazy_Ideas`, `"Canceled"` lands in `Cancelled`, `test_merge_into_existing_project_realistic.py:725-748`) and live container proof (`GET /api/v1/projects/KAN/states` returned `count: 6`, `duplicate_crazy_ideas_count: 1`, `contract-sample.json:4-41`).

---

## 4. API Endpoint, Security, Pagination & OpenAPI Sync

Audited `kanban/api/v1/issues.py` and `kanban/services/issues.py`:

- **Keyset Pagination & Bounds (`issues.py:130-170`, `services/issues.py:1199-1250`):**
  - `GET /api/v1/projects/{project_ref}/issues` enforces `limit: int = Query(ge=1, le=100) = 50` and `cursor: str | None = Query(max_length=64) = None`.
  - `svc.list_issues` decodes `cursor` via `decode_issue_cursor` (raising `422 INVALID_CURSOR` on malformed or non-positive values), filters `Issue.sequence_id < last_seq`, orders deterministically by `Issue.sequence_id.desc()`, fetches `limit + 1` rows, and emits `next_cursor = encode_issue_cursor(page[-1].sequence_id)` only when more rows remain.
  - Across `304` issues with `limit=100`, live traversal produced `4` pages of sizes `[100, 100, 100, 4]` covering `KAN-304..KAN-1` with `304` unique keys and `next_cursor: null` on page 4 (`contract-sample.json:42-87`).
- **`state_group` Multi-Value Filter & Validation (`issues.py:29`, `145-148`, `services/issues.py:1229-1237`):**
  - `StateGroupFilter = Literal["backlog", "unstarted", "started", "completed", "cancelled"]` is bound to `state_group: list[StateGroupFilter] | None = Query(...)`.
  - Invalid values (e.g., `state_group=invalid_group`) are rejected at the API boundary with HTTP `422` (`test_merge_into_existing_project_realistic.py:442-445`).
  - Archive filter conflict (`include_archived=false` with `only_archived=true`) raises `422 ARCHIVE_FILTER_CONFLICT` (`issues.py:151-157`).
  - `svc.list_issues` filters `Issue.state_id.in_(select(WorkflowState.id).where(WorkflowState.project_id == project.id, WorkflowState.state_group.in_(list(state_group))))` so project scoping is preserved.
- **RLS, Timing Equalization & Read-Taint Recording (`issues.py:27-28`, `137-139`, `158-169`, `deps.py:147-205`, `timing.py:18-59`):**
  - Authentication (`Depends(get_principal)`) and RLS session binding (`Depends(get_rls_session)` executing under `kanban_app` with `FORCE ROW LEVEL SECURITY`) are enforced on every request.
  - `timing_floor(floor_ms=25.0)` wraps `list_issues`, `get_issue`, `create_issue`, and `patch_issue` to mitigate timing side channels (`issues.py:46, 71, 121, 158`).
  - `await taint_recorder.record_project_ids([project_ref])` runs on `list_issues` (`issues.py:169`) and `[issue.project_id]` on `get_issue` (`issues.py:73`).
- **OpenAPI & TypeScript Schema Parity (`kanban/web/openapi.json`, `kanban/web/src/api/schema.gen.ts:23248-23257`):**
  - `openapi.json` and `schema.gen.ts` both reflect the `state_group?: ("backlog" | "unstarted" | "started" | "completed" | "cancelled")[] | null` query parameter on `list_issues_api_v1_projects__project_ref__issues_get`.

---

## 5. Verification Evidence, Test Coverage & Live Latencies

### 5.1 Automated Test & Coverage Summary (`docs/qa/KAN-84/unit-test-results.txt`)
- **Backend Pytest:** `91 passed in 61.20s` across 11 test files (`PYTEST_EXIT=0`, `COV_REPORT_EXIT=0`).
  - `kanban/api/v1/issues.py`: `98%` (`69` stmts, `1` miss, `14` branches, `1` partial)
  - `kanban/importer/plane_importer.py`: `96%` (`548` stmts, `14` miss, `192` branches, `17` partial)
  - `kanban/importer/plane_mapper.py`: `97%` (`144` stmts, `3` miss, `62` branches, `2` partial)
  - `kanban/services/issues.py`: `97%` (`465` stmts, `11` miss, `188` branches, `8` partial)
  - **Combined Audited Backend Total:** `96%` (`1226` stmts, `29` miss, `456` branches, `28` partial) - exceeds the `>=95%` project mandate on every audited module.
- **Frontend Vitest:** `5` test files, `105 passed` in `16.74s` (`VITEST_EXIT=0`), with `100%` Stmts / `97.62%` Branch / `100%` Funcs / `100%` Lines across `BoardView.tsx`, `boardApi.ts`, and `viewsApi.ts`.

### 5.2 Static Analysis & Build Gates (`docs/qa/KAN-84/build-check.txt`)
- `uv run ruff check .`: Passed (`All checks passed!`)
- `uv run ruff format --check .`: Passed (`2102 files already formatted`)
- `uv run mypy`: Passed (`Success: no issues found in 1216 source files`)
- `uv run lint-imports`: Passed (`Contracts: 2 kept, 0 broken`)
- `uv run python -m scripts.check_no_dashes --all`: Passed (`0` em/en-dashes)
- `uv run python -m database.migrations.cli check-migrations --static-only`: Passed (`All 65 migrations valid. Single head: p6_03_multi_source_imports_and_aliases`)
- `pnpm --dir kanban/web typecheck` / `lint` / `build`: All exited `0` (`726 modules transformed`, `built in 1.18s`).

### 5.3 Live Full-Stack HTTP Latencies (`docs/qa/KAN-84/live-fullstack-proof.txt`)
Measured against ephemeral container `kanban-kan84-qa` (`http://127.0.0.1:18984`, commit `a29cd88b`, zero mocks):
- `GET /api/v1/healthz`: `200 OK`
- `GET /api/v1/projects/KAN/states`: `200 OK` in `39.2 ms` (`6` states, `0` duplicates)
- `GET /api/v1/issues/KANBA-1`: `200 OK` in `29.0 ms` (`X-Kanban-Canonical-Key: KAN-84`)
- `GET /api/v1/projects/KAN/issues?state_group=backlog&state_group=unstarted&state_group=started&limit=100`: `200 OK` in `283.1 ms` (`29` open issues `KAN-83..KAN-55`, `next_cursor: null`)
- `GET /api/v1/projects/KAN/issues?limit=100` (4 sequential pages, `304` issues total): `3224.9 ms` cumulative:
  - Page 1 (`100` items, `KAN-304..KAN-205`): `1119.5 ms`
  - Page 2 (`100` items, `KAN-204..KAN-105`): `1049.3 ms`
  - Page 3 (`100` items, `KAN-104..KAN-5`): `1006.5 ms`
  - Page 4 (`4` items, `KAN-4..KAN-1`): `49.1 ms`

### 5.4 Non-Blocking Architectural Observation
- `svc.list_issues` currently hydrates each returned `Issue` via `await serialize_issue(session, caller, item)` in a loop (`services/issues.py:1249`), which explains why `100`-item pages take `1006.5 ms - 1119.5 ms` while `4`-item pages take `49.1 ms` and `29`-item filtered pages take `283.1 ms`. While this does not violate correctness, RLS, or any KAN-84 acceptance criterion, a future follow-up ticket batching `serialize_issue` queries (labels, modules, access manifests, capabilities, assignees, provenance) would bring `limit=100` latency well under the `200 ms` p95 target.

---

## 6. Sign-Off

All KAN-84 API, importer, security, OpenAPI schema, coverage, and live full-stack contract requirements are verified and complete.

**STATUS: APPROVED**
