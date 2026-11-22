# API & Security Specialist Review: KAN-85 (`[KB-ISSUES-LIST-BATCH-01]`)

- **Reviewer Persona:** `backend-architect` / `security-engineer` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-85` (`[KB-ISSUES-LIST-BATCH-01] Batch Issue Serialization Queries in svc.list_issues to Eliminate Per-Row N+1 Hydration on 100-Item Pages`)
- **Audited Commit (`HEAD`):** `823701c1385283a90e685c3cc7cc809bf702f6ec` (`823701c1`, merging `6d42a6b84e96c6cf00f3d0d3451e8a3fee31236d`)
- **Audited Branch:** `main` (merged from `feat/KAN-85-batch-list-issues`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-85/git-diff.patch`
  - `docs/qa/KAN-85/contract-sample.json`
  - `docs/qa/KAN-85/unit-test-results.txt`
  - `docs/qa/KAN-85/build-check.txt`
  - `docs/qa/KAN-85/message-to-reality-checker.md`
- **Reviewed Source & Test Files:**
  - `kanban/services/issues.py`
  - `kanban/tests/api/test_issues.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-85` addresses the critical N+1 query amplification in `GET /api/v1/projects/{project_ref}/issues`. Previously, each issue in a page triggered 20+ isolated queries to hydrate states, priorities, cycles, modules, labels, assignees, provenance, parent summaries, archive eligibility, gates, and access manifests, resulting in 2,662 SQL statements and 1,259.05 ms latency on a 100-item page.

The implementation introduces `serialize_issues_batch` and `_hydrate_batch_issue_context` in `kanban/services/issues.py`, converting per-issue queries into batched `IN (...)` operations executing under strict PostgreSQL `FORCE ROW LEVEL SECURITY` (`kanban_app` role).

Results and audit findings:
1. **Dramatic Statement & Latency Reduction:** On a 100-item page, database queries dropped from 2,662 to **18 SQL statements** (well below the `<= 20` query budget mandated by the ticket, a **147.9x** reduction). Execution time dropped from 1,259.05 ms to **293.87 ms** (a **4.3x** speedup).
2. **100% Byte-for-Byte & ETag Parity:** Rigorously verified across `.model_dump_json()`, `.model_dump(mode="json")`, and SHA-256 ETag digests. All hydrated models are identical to sequential `serialize_issue` outputs.
3. **Strict RLS & Anti-Enumeration Integrity:** Parent issues for which the caller lacks `VIEW` permission are safely masked as `RestrictedParentSummary(restricted=True, label="🔒 Restricted Parent Issue")` with zero identifier or summary leakage. Per-issue caller capabilities match single-issue `GET /api/v1/issues/{key}` endpoints exactly.
4. **Coverage & Quality Standards:** 21 Pytest tests passed with **97%** statement and branch coverage on `kanban/services/issues.py`. Static analysis (`make check`) and repository-wide dash checks (`uv run python -m scripts.check_no_dashes --all`) passed with 0 errors.

---

## 2. Architectural Analysis & Query Optimization

### 2.1 Batched Hydration Pipeline (`kanban/services/issues.py`)
`_hydrate_batch_issue_context` collects entity IDs across all issues in the page:
- `project_ids = list({i.project_id for i in issues})`
- `state_ids = list({i.state_id for i in issues})`
- `priority_ids = list({i.priority_id for i in issues})`
- `cycle_ids = list({i.cycle_id for i in issues if i.cycle_id is not None})`
- `parent_ids = list({i.parent_issue_id for i in issues if i.parent_issue_id is not None})`
- `issue_ids = [i.id for i in issues]`

Batch queries executed in constant-time batches:
1. Projects, States, Priorities, Cycles fetched via `.where(Table.id.in_(...))`
2. Parents: `select(Issue.id, Issue.sequence_id, Issue.summary, Project.identifier).join(Project).where(Issue.id.in_(parent_ids))`
3. Labels: `select(IssueLabel.issue_id, ProjectLabel).join(ProjectLabel).where(IssueLabel.issue_id.in_(issue_ids))`
4. Modules: `select(IssueModule.issue_id, Module).join(Module).where(IssueModule.issue_id.in_(issue_ids))`
5. Assignees: `select(IssueAssignee).where(IssueAssignee.issue_id.in_(issue_ids))`
6. Archive eligibility: open sub-issues checked in a single aggregation:
   `select(Issue.parent_issue_id, func.count()).where(Issue.parent_issue_id.in_(issue_ids), ...).group_by(Issue.parent_issue_id)`
7. Gate holds and latest verdicts: batched over `issue_ids` with `is_active=True` and windowed/grouped latest verdicts
8. Access manifests: `_batch_build_access_manifest` batches effective resource access, ACL entries, project/workspace memberships, and transitive group closures.

### 2.2 Query Count Verification (`docs/qa/KAN-85/contract-sample.json`)
Verified on `GET /api/v1/projects/QBND/issues?limit=100`:
- Baseline (per-row serialization): 2,662 SQL statements, 1,259.05 ms
- Batched (`serialize_issues_batch`): 18 SQL statements, 293.87 ms
- Query reduction factor: 147.9x
- Latency speedup factor: 4.3x
- Strict bound check: 18 <= 20 SQL statements (PASS)

---

## 3. Security, RLS & Anti-Enumeration Verification

### 3.1 Restricted Parent Masking under PostgreSQL `FORCE RLS`
- Tested in `test_kan85_rls_restricted_parent_and_capability_parity_under_force_rls`:
  - When a parent issue has an explicit `DENY` capability entry (or is in an unreadable project), PostgreSQL RLS filters out the parent row from `Issue.id.in_(parent_ids)`.
  - `serialize_issues_batch` detects `parent_issue_id is not None and parent_issue_id not in ctx.parents_by_id`, emitting `RestrictedParentSummary()`.
  - Verified JSON serialization produces `{"restricted": true, "label": "🔒 Restricted Parent Issue"}`, with zero leakage of parent ID, parent key, or parent summary.

### 3.2 Caller Capability Parity
- For callers with partial permissions (e.g. `VIEWER`, or `MEMBER` with an explicit `DENY` on `EDIT`), `_batch_evaluate_capabilities` evaluates effective access masks identically to `evaluate_capabilities`.
- Unit test assertions verify `item["capabilities"] == single_get["capabilities"]` for every issue on the page.

---

## 4. Test Suite Execution & Coverage

- **Pytest Suite (`kanban/tests/api/test_issues.py`, `kanban/tests/importer/test_merge_into_existing_project_realistic.py`):**
  - `test_kan85_serialize_issues_batch_byte_for_byte_payload_and_etag_parity`: PASSED
  - `test_kan85_list_issues_100_items_query_count_bound`: PASSED (18 queries <= 20)
  - `test_kan85_rls_restricted_parent_and_capability_parity_under_force_rls`: PASSED
  - 21 total tests passed in 38.55s
- **Module Coverage:**
  - `kanban/services/issues.py`: **97%** statement and branch coverage (771 statements, 18 missed, 306 branches, 16 partial). Exceeds the 95% project requirement.
- **Static Analysis & Dash Verification:**
  - `make check`: 0 errors
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (zero em/en-dashes)

---

## 5. Review Sign-Off

The API optimization, SQL query bounds, byte-for-byte serialization parity, and security invariants for `KAN-85` are completely verified.

**STATUS: APPROVED**
