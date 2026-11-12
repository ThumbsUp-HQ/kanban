# Message to Reality-Checker: KANBA-90 (KB-P3-11)

## Overview
- **Ticket**: KANBA-90 (`KB-P3-11`: `[Phase 3 / API] Saved views CRUD, filter DSL & 2D group/sub-group query engine`)
- **Status**: Ready for Forensic QA Audit
- **Branch**: `feat/KANBA-90` in worktree `/tmp/kb-wt-KANBA-90`

## Implementation Details

### 1. Pydantic v2 Schemas (`kanban/api/v1/schemas/views.py`)
- `ViewType` (`board`, `list`, `calendar`, `timeline`, `spreadsheet`)
- `ViewVisibility` (`private`, `shared`)
- `GroupAxis` (`none`, `state`, `state_group`, `priority`, `assignee`, `cycle`, `module`)
- `FilterSpec` (`extra="forbid"`) with complexity boundaries:
  - `state_ids`: max 50 items
  - `priority_ids`: max 20 items
  - `assignee_ids`: max 50 items (supports `'me'`, `'unassigned'`, or valid UUID strings)
  - `label_ids`: max 50 items
  - `cycle_ids`: max 20 items (supports `'none'`, `'active'`, or valid UUID strings)
  - `module_ids`: max 20 items (supports `'none'` or valid UUID strings)
  - `search_query`: max 255 chars
- `IssueQueryRequest` with mandatory 2D grouping validation (`group_by != sub_group_by` when both not `none`).
- `IssueQueryResponse` with 2D `groups` hierarchy, `wip` limit calculations (`is_over_limit`), keyset pagination, and `timeline_links` for gantt rendering.

### 2. Filter DSL Compiler (`kanban/services/view_dsl.py`)
- Parameterized SQL predicate compilation (`compile_issue_filter_predicates`):
  - `state_ids` and `state_groups` (with active/backlog separation)
  - `priority_ids`
  - `assignee_ids` (`'me'` resolves to caller principal; `'unassigned'` filters on null assignee)
  - `label_ids` with `label_match` (`all` via having count, `any` via exists)
  - `cycle_ids` (`'none'` for unassigned, `'active'` for current active cycle)
  - `module_ids` (`'none'` for unassigned, rejected when `modules_enabled=False`)
  - `parent_issue_id`
  - `start_date` and `due_date` ranges
  - `overdue_only` (due date past today and state_group not in `'completed'`, `'cancelled'`)
  - `blocked` (has incoming unresolved blocker links)
  - `gate_status` (`pending` on non-null `pending_transition_exec_id`)
  - `include_archived` (defaults to False)
  - `search_query` (websearch_to_tsquery ILIKE match on summary and description)
- Strict validation (`validate_group_axes`):
  - Duplicate axis rejection (`422 DUPLICATE_GROUP_AXIS`)
  - Modules gate (`422 MODULES_DISABLED` if `group_by='module'`, `sub_group_by='module'`, or `module_ids` non-empty when `projects.modules_enabled=False`)

### 3. 2D Query Engine (`kanban/services/query_engine.py`)
- Tamper-proof HMAC SHA-256 query cursor tokens (`encode_query_cursor`, `decode_query_cursor`):
  - Binds caller `sort_by`, `sort_dir`, `filters`, `group_by`, and `sub_group_by` in query hash.
  - Rejects mismatched query parameters or altered signatures with `422 INVALID_CURSOR`.
- Native keyset pagination:
  - Supports ordering by `board_rank`, `created_at`, `updated_at`, `sequence_id`, `priority`, `due_date`.
  - Type-safe cursor value casting in `_parse_cursor_val` to prevent Postgres operator mismatch.
- 2D group/sub-group aggregation with WIP enforcement:
  - Groups issues across primary axis and secondary sub-axis.
  - Computes WIP counts against workflow state WIP limits and flags `is_over_limit`.
- Timeline dependency link extraction:
  - Fetches blocking/relates_to links between issues returned in current page.
  - Filters out references to unreadable issues under RLS to prevent leakage.

### 4. Saved Views Service (`kanban/services/views.py`)
- Full CRUD for views under Universal Object Graph:
  - Object registration via `register_object` with `object_kind='view'`.
  - Visibility enforcement: `private` views owned by creator (hidden from other members); `shared` views visible to project members.
  - Automatic `rebuild_effective_access_for_object` materialization.
  - Activity ledger logging: `VIEW_CREATED`, `VIEW_UPDATED`, `VIEW_DELETED` under category `HISTORY`.
  - Safe Markdown description normalization.

### 5. API Endpoints (`kanban/api/v1/views.py`)
- Mounted under `/api/v1`:
  - `POST /api/v1/projects/{project_ref}/views` (201 Created + Location header + ETag)
  - `GET /api/v1/projects/{project_ref}/views` (200 OK, lists visible views)
  - `GET /api/v1/views/{view_id}` (200 OK + ETag)
  - `PATCH /api/v1/views/{view_id}` (200 OK + ETag, If-Match concurrency check)
  - `DELETE /api/v1/views/{view_id}` (204 No Content)
  - `POST /api/v1/projects/{project_ref}/issues:query` (200 OK, dynamic ad-hoc 2D query)
  - `POST /api/v1/views/{view_id}/issues:query` (200 OK, saved view 2D query with overrides)
- 25.0ms timing floor applied via `@timing_floor(floor_ms=25.0)`.

## Quality and Verification Summary
- **Unit Tests**: 12/12 passing in 7.02s across `kanban/tests/api/test_views.py` and `kanban/tests/services/test_query_engine.py`.
- **Code Coverage**: 96.47% branch + line coverage across target modules (exceeds >= 95% threshold).
  - `kanban/api/v1/views.py`: 100%
  - `kanban/services/query_engine.py`: 97%
  - `kanban/services/view_dsl.py`: 95%
  - `kanban/services/views.py`: 96%
- **Static Analysis & Linting**:
  - `ruff check`: All checks passed.
  - `ruff format --check`: 100% formatted.
  - `mypy --strict`: Success in 277 source files.
  - `lint-imports`: 2 contracts kept, 0 broken.
  - `scripts.check_no_dashes`: 0 dash violations.
  - `make license`: 0 license violations.
- **Contract Samples**: 6 verified wire exchanges in `docs/qa/KANBA-90/contract-sample.json`:
  1. `create_view_shared_201`
  2. `query_issues_2d_swimlane_200`
  3. `get_view_private_unreadable_404`
  4. `modules_disabled_422`
  5. `duplicate_group_axis_422`
  6. `invalid_cursor_422`
