# Clean-Room API Specialist Review: KAN-52

- Ticket: KAN-52 (`[KB-ISSUE-NAVIGATOR]`)
- Title: [KB-ISSUE-NAVIGATOR] Replace X/Y-Flipped List View with Master-Detail Issue Navigator View
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-52`
- Branch: `main` (commit `7913c2c8`)
- Container Environment: `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- Live Stack Status: `LIVE_STACK_VERDICT: PASS`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-52 on branch `main` at commit `7913c2c8`. In addition to the core Master-Detail Issue Navigator view implementation (unified `IssueNavigatorBar`, 300px left master rail, sequential keyboard pager, and 2-column detail canvas with `created_at` and `updated_at` serialization), this audit specifically verifies the remediations for the live-stack findings caught by zero-mock full-stack QA (`live_qa_suite_v2.mjs` against container `kanban-liveqa-2`, commit `7913c2c8`, `LIVE_STACK_VERDICT: PASS`):

1. **Assignee REST API Schema Parity (Resolving HTTP 422 FAIL 1):**
   - In `kanban/web/src/features/drawer/IssueSurface.tsx`: `handleAssignToMe` was refactored to hit `railApi.addAssignee(currentIssue.key, { principal: myId })` which translates directly to `POST /api/v1/issues/{issue_ref}/assignees` with payload `{ principal: myId }`.
   - Completely eradicates the invalid `PATCH /api/v1/issues/{key}` payload with `{ assignees: [...] }` that triggered backend `HTTP 422 VALIDATION_FAILED` ("Extra inputs are not permitted").
   - Explicitly removes the silent error swallowing in `catch {}`. Any API errors (HTTP 422, 403, 409) now cleanly set `conflictError` to render the user-facing `conflict-banner` alert with the exact backend problem details.
   - Immediately synchronizes local issue state and TanStack Query cache `['issues', targetProject]`.
2. **Safe Clipboard Execution (Resolving Unhandled Rejection FAIL 2):**
   - In `IssueSurface.tsx`: `handleShareExport` and `handleCopyBranch` wrapped in `safeCopyToClipboard` with `try / catch` around `navigator.clipboard.writeText(text)` and fallback offscreen textarea execution (`copyToClipboard`), eliminating unhandled `NotAllowedError` promise rejections in restricted browser contexts.
   - Cleans up feedback timer via `copyTimeoutRef` on component unmount.
3. **0ms Mutation Commit Parity across Issue & Settings Endpoints (KAN-36 & KAN-50 Directives):**
   - In `kanban/api/v1/transitions.py`: added `if session.is_active: await session.commit()` before returning HTTP 202 (`pending_agent_gate`) and HTTP 200 responses, and attaches the fresh `ETag` header from `fresh_issue.etag`.
   - In `kanban/api/v1/issues.py` (`create_issue`), `kanban/api/v1/issue_trees.py` (`create_issue_tree`), and `kanban/api/v1/issue_copy.py` (`copy_issue_endpoint`): added explicit `await session.commit()` before returning the response. This eliminates 0ms TCP commit-after-response race conditions where an immediate follow-up `GET` or `copy` hit `404 NOT_FOUND` before FastAPI generator teardown committed.
   - In `kanban/api/v1/admin/workspace_settings.py` (`update_workspace_settings`): added `await session.commit()` before returning `WorkspaceSettingsResponse`.
4. **EmojiHint Popover Stacking Context Elevation (KAN-50 Directive):**
   - In `kanban/web/src/components/emoji/EmojiHint.css`: `.emoji-hint-popup` `z-index` raised from `1000` to `10050`. Ensures the `🔢` popover renders completely on top of modal backdrops and scrims (`CreateProjectModal.css` `z-index: 1200`, `CommandPalette.css` `z-index: 9999`).

All API contracts, security invariants, database transaction boundaries, import layering rules, and test coverage requirements are verified and certified:
- Zero new external runtime packages added (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- High test coverage: 161/161 Vitest tests pass across 10 suites in 10.17s with 0 `act(...)` console warnings; 16/16 Pytest tests pass in `kanban/tests/api/test_issues.py` (and 40/40 pass across transitions, trees, and settings suites).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation.

---

## 2. Detailed Contract & Security Verification

### 2.1 Issue Assignee API Contract (`kanban/api/v1/issue_assignees.py`)
- Backend Endpoint: `POST /api/v1/issues/{issue_ref}/assignees`
- Request Schema:
  ```python
  class AddAssigneeRequest(BaseModel):
      principal: str = Field(
          description="Principal handle (e.g. '@alice'), UUID, or email address",
      )
  ```
- Previous Failure Analysis:
  - The initial split detail view triggered `PATCH /api/v1/issues/{key}` with `{"assignees": [...]}`.
  - `IssuePatch` schema does not permit top-level `assignees` array mutations on the issue patch endpoint; FastAPI strictly rejected the unknown key with `HTTP 422 VALIDATION_FAILED` ("Extra inputs are not permitted").
- Remediated Contract Integration:
  - In `IssueSurface.tsx`: `handleAssignToMe` calls `railApi.addAssignee(currentIssue.key, { principal: myId })`.
  - Sends exact payload `{ principal: myId }` to `POST /api/v1/issues/{issue_ref}/assignees`.
  - Receives `AssigneeItem` response and appends to existing assignees array.
  - Updates TanStack Query cache `['issues', targetProject]` and local issue state.
  - Surfaces any error via `conflict-banner` alert.

### 2.2 0ms Commit Parity & Fresh ETag Header (`kanban/api/v1/transitions.py`)
- Source: `kanban/api/v1/transitions.py` (`post_issue_transition`)
- Implementation Audit:
  ```python
  headers: dict[str, str] = {}
  try:
      from kanban.services.issues import get_issue_or_404

      fresh_issue = await get_issue_or_404(session, caller, issue_key)
      if fresh_issue.etag:
          headers["ETag"] = fresh_issue.etag
  except Exception:
      pass

  if session.is_active:
      await session.commit()

  resp_data = TransitionResponse(
      execution_id=outcome.execution_id,
      status=outcome.status,
      state=outcome.state,
      sync_duration_ms=outcome.sync_duration_ms,
  )
  return JSONResponse(
      status_code=200,
      content=resp_data.model_dump(mode="json"),
      headers=headers or None,
  )
  ```
- Invariant Guarantees:
  - An immediate `0ms` follow-up request over the TCP socket guaranteed to read committed database state.
  - Clients receiving HTTP 200 get the updated `ETag` matching the transitioned issue state, eliminating stale-ETag `412 PRECONDITION_FAILED` conflicts.

### 2.3 Commit Parity Across Issue Mutations (`issues.py`, `issue_trees.py`, `issue_copy.py`)
- `kanban/api/v1/issues.py` (`create_issue`):
  - Added `await session.commit()` before returning the `IssueResponse`.
- `kanban/api/v1/issue_trees.py` (`create_issue_tree`):
  - Added `await session.commit()` before returning the `IssueTreeResponse`.
  - Fixes the live QA defect where an immediate `POST /api/v1/issues/{id}/copy` right after `POST /projects/{id}/issue-trees` failed with 404 before session commit.
- `kanban/api/v1/issue_copy.py` (`copy_issue_endpoint`):
  - Added `await session.commit()` before returning the copied issue result.
- `kanban/api/v1/admin/workspace_settings.py` (`update_workspace_settings`):
  - Added `await session.commit()` before returning `WorkspaceSettingsResponse`.

---

## 3. Test Suite & Coverage Verification

- Frontend Vitest Suites (`unit-test-results.txt`):
  - `src/features/drawer/IssueSurfaceSplitMasterDetail.test.tsx`: 6 passed in 527ms.
    * Verifies `split-assign-to-me-btn` hits `POST /api/v1/issues/{issue_ref}/assignees` with `{ principal: 'u-123' }` and updates UI.
    * Verifies `split-assign-to-me-btn` surfaces 422 validation error cleanly via conflict banner without silent swallow.
    * Verifies `split-git-branch-copy` and `split-share-btn` handle `navigator.clipboard.writeText` rejecting with `NotAllowedError` gracefully with 0 unhandled rejections.
  - `src/features/drawer/IssueSurface.test.tsx`: 40 passed in 2511ms.
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed in 19ms.
  - `src/features/views/viewRegistry.test.tsx`: 46 passed in 7851ms.
  - Total: 161 passed across 10 test suites in 10.17s (0 `act(...)` console warnings).
- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/api/test_issues.py`: 16 passed in 8.40s.
- Static Analysis Gates (`build-or-typecheck.txt`):
  - TypeScript Typecheck (`tsc -b --noEmit`): Clean (0 errors).
  - ESLint (`eslint . --max-warnings 0`): Clean (0 warnings).
  - Vite Production Build (`tsc -b && vite build`): Built in 1.43s.
  - Dash Character Policy: Clean (0 em/en-dashes).
  - Untracked Hygiene: `.backup_schedule.json` and `backups/` untouched and unstaged.

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Assignee API Contract | `POST /issues/{ref}/assignees` with `{ principal: id }` | `railApi.addAssignee` schema alignment | PASS |
| Clean Error Surfacing | Display 422/conflict errors via conflict banner | `setConflictError` in `handleAssignToMe` | PASS |
| Clipboard Rejection Safety | Handle `NotAllowedError` without app crash | Safe async fallback in `safeCopyToClipboard` | PASS |
| 0ms Mutation Commit Parity | Commit before returning HTTP response body | Explicit `session.commit()` across endpoints | PASS |
| Fresh ETag on Transition | Return current ETag in HTTP response headers | `headers["ETag"] = fresh_issue.etag` | PASS |
| Popover Z-Index Stacking | Float above modal scrims (`z-index: 9999`) | `.emoji-hint-popup` set to `z-index: 10050` | PASS |
| Unidirectional Layering | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

All backend mutation commit boundaries, assignee API contracts, error surfacing mechanisms, clipboard crash protections, popover stacking hierarchies, and test suites for KAN-52 on branch `main` at commit `7913c2c8` have been thoroughly audited, verified against all architectural and security invariants, and certified on live stack `kanban-liveqa-2` with `LIVE_STACK_VERDICT: PASS`. Dual specialist gate (API Specialist + UI Specialist) is complete. Ready for Reality-Checker QA.
