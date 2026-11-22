# Message to Reality-Checker: KAN-84 (`[KB-MIGRATION-MERGE-QA-01]`)

## Audited Commit & Environment Context
- **Repository HEAD Commit SHA:** `a29cd88b34abba131d1cef9c17ef5254352c24ce`
- **Author & Committer Identity:** `Adam Outler <adamoutler@gmail.com>`
- **Protected Instance Isolation:** Per project governance, `k.hackedyour.info` (`192.168.1.101`) was NOT used as a destructive test bed. All 304-issue merge rehearsals, REST keyset pagination benchmarks, and Playwright visual captures ran against an isolated local hermetic container (`kanban-kan84-qa` on `127.0.0.1:18984`) and local PostgreSQL `FORCE ROW LEVEL SECURITY` fixtures, after which `kanban-kan84-qa` was torn down cleanly.

## Requirement-to-Evidence Mapping

1. **Normalized Workflow State Matching (`PlaneMapper` & `PlaneImporter`):**
   - **Code:** `kanban/importer/plane_mapper.py` (`normalize_state_key`) and `kanban/importer/plane_importer.py` (Stage 2 `states_by_norm` and Stage 8 `states_by_proj_and_norm`).
   - **Proof:** `docs/qa/KAN-84/git-diff.patch`, `docs/qa/KAN-84/unit-test-results.txt` (`test_normalize_state_key_and_crazy_ideas_issue_landing` and `test_realistic_304_issue_merge_preserves_83_existing_and_paginates_all_open_issues`), and `docs/qa/KAN-84/contract-sample.json` (`GET /api/v1/projects/KAN/states` showing exactly `6` workflow states with `0` duplicate `"Crazy Ideas"` state).

2. **Optional `state_group` Filter on `GET /api/v1/projects/{project_ref}/issues`:**
   - **Code:** `kanban/api/v1/issues.py` (`StateGroupFilter` `Literal` query parameter), `kanban/services/issues.py` (`WorkflowState.state_group.in_(...)` subquery), `kanban/web/openapi.json`, and `kanban/web/src/api/schema.gen.ts`.
   - **Proof:** `docs/qa/KAN-84/contract-sample.json` (`filtered_open_29` returning all `29` open `KAN-83..KAN-55` issues on page 1 with `next_cursor: null` in `283.1 ms`), plus HTTP `422` validation check on invalid `state_group` in `kanban/tests/importer/test_merge_into_existing_project_realistic.py`.

3. **Full Multi-Page Cursor Traversal in Frontend Views & Standalone Board:**
   - **Code:** `kanban/web/src/features/views/viewsApi.ts` (`fetchAllProjectIssues`), `kanban/web/src/features/views/viewRegistry.tsx` (updated BOTH `issuesQuery` and `refreshLive` `kb:issue-updated` handler), `kanban/web/src/features/board/boardApi.ts` (`fetchAllBoardIssues`), and `kanban/web/src/features/board/BoardView.tsx`.
   - **Proof:** `kanban/web/src/features/views/paginationMergeIntegration.test.tsx` (`6` integration tests passing in `docs/qa/KAN-84/unit-test-results.txt`, `100%` statement/line coverage across `viewsApi.ts`, `boardApi.ts`, and `BoardView.tsx`) and real zero-mock Playwright screenshots in `docs/qa/KAN-84/screenshots/` (`01-desktop-light-board-304.png` through `06-mobile-landscape-board-304.png`).

4. **Realistic 304-Issue Merge Non-Clobber & Visual Proof (`83` Existing + `221` Merged):**
   - **Proof:** `docs/qa/KAN-84/live-fullstack-proof.txt` and `docs/qa/KAN-84/screenshots/` confirm `Backlog: 1`, `Crazy_Ideas: 7`, `Todo: 21`, `In Progress: 0`, `Done: 270`, and `Cancelled: 5` (`304` total issues), with `shellMs: 338 ms` (`< 3000 ms` budget) and `0` console/page errors. Note on API pagination latency: individual API calls execute well under 1.2s (`states: 39.2 ms`, `alias: 29.0 ms`, `filtered_open_29: 283.1 ms`, and `~800-1050 ms` per 100-item full-detail serialized page in debug/single-worker local container).

5. **Static Analysis, Unit Coverage & Dual Specialist Sign-Offs:**
   - `docs/qa/KAN-84/build-check.txt` (`make check`, `typecheck`, `lint`, `build`, `check_no_dashes` all exit `0`).
   - `docs/qa/KAN-84/unit-test-results.txt` (`91` backend tests passing at `96%-98%` module coverage; `105` frontend tests passing at `100%` statement coverage).
   - `docs/qa/KAN-84/api-specialist-review.md` (`STATUS: APPROVED`) and `docs/qa/KAN-84/ui-specialist-review.md` (`STATUS: APPROVED`).
   - `docs/qa/KAN-84/changed-files-manifest.txt` (`sha256sum` verified across all modified code and QA artifacts).
