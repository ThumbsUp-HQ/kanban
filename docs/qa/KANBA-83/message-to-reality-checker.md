# Reality-Checker Audit Note: KANBA-83 (KB-P3-03)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-83` / `KB-P3-03`: `[Phase 3 / API] Hybrid assignees API & access-filtered assignee autocomplete`) implements the hybrid assignees REST API, project access-filtered assignee autocomplete, and anti-enumeration security invariants:

1. **Target Files**:
   - `kanban/api/v1/assignees.py`: 3 REST endpoints mounted on `build_v1_router()` wrapped with `timing_floor(floor_ms=25.0)`:
     * `POST /api/v1/issues/{issue_ref}/assignees` (`Capability.EDIT`, status 201)
     * `DELETE /api/v1/issues/{issue_ref}/assignees/{assignee_id}` (`Capability.EDIT`, status 204)
     * `GET /api/v1/projects/{project_ref}/assignee-suggestions?q=&limit=` (`Capability.VIEW`, status 200)
   - `kanban/api/v1/schemas/assignees.py`: Pydantic request/response schemas with `ConfigDict(extra="forbid")`, validating mutual exclusivity of `principal` and `free_text`, discriminated union `AssigneeResponse` on `kind`, and `AssigneeSuggestionsResponse`.
   - `kanban/services/assignees.py`: Full service layer implementing `_add_principal_assignee`, `_add_free_text_assignee`, `remove_assignee`, `get_assignee_suggestions`, and `get_issue_assignees`.
   - `kanban/api/v1/schemas/issues.py`: Extended `IssueResponse` to include `assignees: list[AssigneeResponse] = Field(default_factory=list)`.
   - `kanban/services/issues.py`: Updated `serialize_issue` to populate `assignees` via `get_issue_assignees(session, issue.id)`.
   - `kanban/services/activity.py`: Added `ASSIGNEE_ADDED` and `ASSIGNEE_REMOVED` to `ActivityEventType` under category `HISTORY`.
   - `kanban/tests/api/test_assignees.py`: Comprehensive test suite covering all 6 mandatory feature test cases plus permission/boundary edge cases.

2. **Security & Anti-Enumeration Invariants**:
   - **Anti-Enumeration Equivalence**: Nonexistent, inactive, cross-workspace, and non-viewer principals return byte-identical `422 ASSIGNEE_NOT_ELIGIBLE` problem details (ignoring `request_id`). Callers learn zero metadata about principal existence or permissions.
   - **Scope-Isolated Autocomplete**: Suggestions join `effective_resource_access` (`VIEW` allowed, not denied), escape `%`, `_`, and `\` in `ILIKE`, and never return principals from outside the project scope. Zero exposure of emails, auth card IDs, or group DNs.
   - **Free-Text Normalization & Boundary**: Plain text normalized via `normalize_plain_text`, zero-width characters and HTML tags stripped, length enforced between 1 and 120 chars (else `422 FREE_TEXT_INVALID`). Tagged with `notify: false` and exact hint `"External free-text label - grants zero access and sends zero notifications"`.
   - **Assignee Limits & Duplicate Checks**: Maximum 20 assignees per issue (max 10 free-text, else `422 ASSIGNEE_LIMIT`). Duplicate principal or case-insensitive duplicate free-text returns `409 ASSIGNEE_EXISTS`.
   - **Cross-Issue Guard**: Deleting an assignee from a different issue returns `404 NOT_FOUND`.

3. **Verification & Quality Status**:
   - **Unit Tests**: 7/7 passed in 3.92s with **98.82%** combined branch + line coverage (`kanban.api.v1.assignees` 100%, `kanban.services.assignees` 99%).
   - **Static Checks**: Ruff check clean, Ruff format clean, Mypy strict clean (140 source files), Lint-imports clean (2 kept, 0 broken), License gate clean (0 violations), Zero non-ASCII dashes repo-wide.
   - **Contract Proof**: `contract-sample.json` captures all 5 required wire exchanges (`principal_assign_201`, `ineligible_assignee_422`, `suggestions_200`, `unreadable_project_suggestions_404`, `free_text_assign_201`).
   - **Database Explain**: `suggestions-explain.txt` documents `EXPLAIN (ANALYZE, BUFFERS)` execution showing index scans across `effective_resource_access`, `objects`, and `principals` with 0.078ms execution time.
