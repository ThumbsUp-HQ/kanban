# Message to Reality-Checker: KAN-85 (`[KB-ISSUES-LIST-BATCH-01]`)

## Ticket Scope & Browser Screenshot Classification
- **Ticket:** `KAN-85` - `[KB-ISSUES-LIST-BATCH-01] Batch Issue Serialization Queries in svc.list_issues to Eliminate Per-Row N+1 Hydration on 100-Item Pages`
- **Browser Screenshots:** `N/A - Non-UI Backend Optimization Ticket`
- **Owned Slice Modified:**
  - `kanban/services/issues.py`
  - `kanban/tests/api/test_issues.py`
  - `docs/qa/KAN-85/*`

## Requirement-to-Evidence Mapping

1. **Batched Issue Serialization (`serialize_issues_batch` in `kanban/services/issues.py`):**
   - **Implementation:** Implemented `serialize_issues_batch(session: AsyncSession, caller: PrincipalContext, issues: Sequence[Issue]) -> list[IssueResponse]` and `_hydrate_batch_issue_context` in `kanban/services/issues.py`. Bulk-fetches projects, workflow states, project priorities, sprint cycles, parent issue summaries (with `RestrictedParentSummary` masking when a parent is unreadable under caller `FORCE ROW LEVEL SECURITY`), project labels, modules, assignees (principal and free-text), effective resource access + principals, direct resource ACL entries, project/workspace role bindings, transitive group closure, spine `ObjectRecord` + `Workspace.name`, active group definitions and member counts, archive eligibility (batched open sub-issue check), pending async transition gate holds, latest completed transition gate verdicts, and creator provenance / override reasons using batched `IN (...)` queries.
   - **Evidence:** `docs/qa/KAN-85/git-diff.patch` and `kanban/services/issues.py`.

2. **Wire-Contract & ETag Parity in `svc.list_issues` (`kanban/services/issues.py`):**
   - **Implementation:** Updated `list_issues` in `kanban/services/issues.py` to call `await serialize_issues_batch(session, caller, page)` while preserving 100% byte-for-byte `IssueResponse` JSON payload and strong `ETag` digest parity with `[await serialize_issue(session, caller, item) for item in page]`.
   - **Evidence:** `docs/qa/KAN-85/contract-sample.json` (`"byte_for_byte_payload_parity": true`, `"byte_for_byte_etag_parity": true`) and `docs/qa/KAN-85/unit-test-results.txt` (`test_kan85_serialize_issues_batch_byte_for_byte_payload_and_etag_parity` and `test_realistic_304_issue_merge_preserves_83_existing_and_paginates_all_open_issues`).

3. **SQL Query Count & Latency Reduction on 100-Item Pages (`<= 20` SQL Statements Bound):**
   - **Before (`[await serialize_issue(session, caller, item) for item in page]` on 100 issues):** `2,662` SQL statements (`1,259.05 ms`).
   - **After (`await serialize_issues_batch(session, caller, page)` via `list_issues` on 100 issues):** `18` SQL statements (`293.87 ms`, strictly `<= 20` SQL statements total) - a `147.9x` reduction in SQL statements and `4.3x` latency speedup under `kanban_app` `FORCE ROW LEVEL SECURITY`.
   - **Evidence:** `docs/qa/KAN-85/contract-sample.json` and `test_kan85_list_issues_100_items_query_count_bound` in `kanban/tests/api/test_issues.py`.

4. **Mandatory Unit Tests, `FORCE RLS` Parity & `>= 95%` Coverage (`97%` Achieved):**
   - **Tests Added in `kanban/tests/api/test_issues.py`:**
     1. `test_kan85_serialize_issues_batch_byte_for_byte_payload_and_etag_parity`: Verifies byte-for-byte `.model_dump_json()`, `.model_dump(mode="json")`, and `.etag` parity across workflow states, priorities, cycles, modules, labels, principal + free-text assignees, secret scrubbing, archive eligibility (open sub-issues, eligible, already archived), creator override provenance, pending async gate holds, latest gate verdicts, direct ACL `ALLOW`/`DENY` overrides, groups, agents, and OBO + ephemeral project confinement.
     2. `test_kan85_list_issues_100_items_query_count_bound`: Attaches a SQLAlchemy `before_cursor_execute` listener on the ASGI app's `kanban_app` engine and asserts `GET /api/v1/projects/QBND/issues?limit=100` on 100 seeded issues returns `200 OK` with 100 items in `<= 20` SQL statements.
     3. `test_kan85_rls_restricted_parent_and_capability_parity_under_force_rls`: Verifies under `kanban_app` `FORCE ROW LEVEL SECURITY` that unreadable parents mask as `RestrictedParentSummary` (`{"restricted": True, "label": "\ud83d\udd12 Restricted Parent Issue"}`) with zero identifier leakage and per-issue capabilities match single-issue `GET /api/v1/issues/{key}` responses.
   - **Coverage & Static Checks:** `docs/qa/KAN-85/unit-test-results.txt` (`21 passed`, `97%` line+branch coverage on `kanban/services/issues.py`) and `docs/qa/KAN-85/build-check.txt` (`make check` and `uv run python -m scripts.check_no_dashes --all` exit `0`).
