# Reality Checker Forensic Audit Packet: KAN-309

## Summary of Changes
Ticket: `KAN-309` ([KB-ISSUES-TTFD-01] Cut Issues View Time-to-First-Display on 300+ Tickets via Single-Flight Staged Loading, Batched lod=summary API, and Lazy Issue Detail Hydration).
Branch: `feat/KAN-309-ttfd-summary-lod`

All 4 problems specified in the authoritative KAN-309 specification have been fully implemented and verified with zero compiler, linter, or test failures:

### Problem 1: Backend lod=summary API and Batch Serialization
- Modified `kanban/api/v1/issues.py` and `kanban/api/v1/schemas/issues.py`:
  - Added `lod: Literal["summary", "standard", "full"] = Query(default="full")` to `GET /api/v1/projects/{project_ref}/issues` and `GET /api/v1/issues/{issue_key}`.
  - Made `description_markdown` and `access_manifest` in `IssueResponse` optional (`None` allowed when deferred/omitted).
- Modified `kanban/services/issues.py`:
  - In `list_issues`: when `lod == "summary"`, applied SQLAlchemy `defer(Issue.description_markdown)` to prevent retrieving heavyweight text bodies over the wire.
  - In `_hydrate_batch_issue_context` and `serialize_issues_batch`: conditionally bypassed heavyweight per-row computations (closure queries, ACL checks, role bindings, audit activities, and access manifest assembly) when `lod == "summary"`, setting `description_markdown=None`, `access_manifest=None`, and `capabilities=["VIEW"]`.
  - Preserved strong ETag generation via the persisted `description_sha256` column without loading `description_markdown`.
  - Kept complete backwards compatibility with KAN-85 batch serialization tests.
- Synchronized OpenAPI spec (`kanban/web/openapi.json`) and regenerated TypeScript bindings (`kanban/web/src/api/schema.gen.ts`).

### Problem 2: BoardView Network Loop and Metadata Deduplication
- Modified `kanban/web/src/features/board/BoardView.tsx`:
  - Bound `issuesQuery` with `enabled: propIssues === undefined && Boolean(projectKey)`, preventing duplicate unpaginated `fetchAllBoardIssues` loops when `issues` are provided by `IssuesWorkspaceRoute`.
  - Deduplicated project metadata query with `queryKey: qk.project(projectKey)` and `staleTime: 60_000`, sharing cached metadata seamlessly across the workspace.
- Modified `kanban/web/src/features/board/boardApi.ts`:
  - Extended `fetchAllBoardIssues` options with `lod?: 'summary' | 'standard' | 'full'`, defaulting queries to `lod=summary`.

### Problem 3: Single-Flight Two-Phase Staged Loading
- Modified `kanban/web/src/features/views/viewsApi.ts`:
  - Added `lod` parameter support to `fetchProjectIssues` and `fetchAllProjectIssues` (defaulting to `lod=summary`).
  - Implemented `fetchStagedProjectIssues`: Phase 1 retrieves page 1 (`limit=100, lod=summary`) and fires `onPhase1(items, hasMore)` immediately for sub-millisecond initial render; Phase 2 traverses any remaining pages in the background with signal cancellation.
- Modified `kanban/web/src/features/views/viewRegistry.tsx`:
  - Eliminated duplicate initial network fetch on mount by setting `enabled: false` on `issuesQuery`, allowing single-flight staged loading in `refreshLive` to manage query cache updates.
  - Added `isStagedLoading` state, displaying `<div data-testid="issues-staged-loading-indicator" className="issues-staged-loading-indicator" role="status" aria-live="polite">Loading additional issues...</div>` while background pages hydrate.
  - Bound `AbortController` cancellation to unmount and project switch events.

### Problem 4: Lazy Issue Detail Hydration with Skeleton Placeholder
- Modified `kanban/web/src/features/drawer/IssueSurface.tsx`:
  - Seeded `placeholderData` on `useQuery(qk.issue(issueKey))` from cached list/board summary items and `issuesList`.
  - Immediate hydration: clicking a card renders header, title, state, priority, and assignees without network latency.
  - Added `<div data-testid="issue-description-skeleton" className="surface__description-skeleton surface__skeleton" aria-busy="true">` in both drawer mode and split view mode while `GET /api/v1/issues/{issue_key}?lod=full` loads `description_markdown` and `access_manifest` in the background.

## Verification Proofs
1. **Unit & Integration Tests (`docs/qa/KAN-309/unit-test-results.txt`):**
   - Pytest: 20/20 passed in `kanban/tests/api/test_issues.py` (including `test_kan309_list_issues_lod_summary_defers_description_and_omits_access_manifest`).
   - Vitest: 161/161 passed across all touched frontend modules (`viewsApi.test.ts`, `viewRegistry.test.tsx`, `IssueSurface.test.tsx`, `BoardView.test.tsx`, `boardApi.test.ts`).
2. **Quality & Build Checks (`docs/qa/KAN-309/build-check.txt`):**
   - ESLint: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
   - TypeScript: 0 errors (`tsc -b --noEmit`).
   - Vite Production Build: Successful production bundle generated.
   - Dash Enforcement: 0 em-dashes or en-dashes (`python -m scripts.check_no_dashes --all`).
3. **Contract Samples (`docs/qa/KAN-309/contract-sample.json`):**
   - Sample payloads for `lod=summary` (lightweight list/board) and `lod=full` (hydrated detail).
4. **Git Diff (`docs/qa/KAN-309/git-diff.patch`):**
   - Clean diff strictly limited to assigned slice files.
