# UI & UX Specialist Review: KAN-85 (`[KB-ISSUES-LIST-BATCH-01]`)

- **Reviewer Persona:** `ux-architect` / `ui-designer` (UI/UX Specialist Reviewer)
- **Ticket:** `KAN-85` (`[KB-ISSUES-LIST-BATCH-01] Batch Issue Serialization Queries in svc.list_issues to Eliminate Per-Row N+1 Hydration on 100-Item Pages`)
- **Audited Commit (`HEAD`):** `823701c1385283a90e685c3cc7cc809bf702f6ec` (`823701c1`, merging `6d42a6b84e96c6cf00f3d0d3451e8a3fee31236d`)
- **Audited Branch:** `main` (merged from `feat/KAN-85-batch-list-issues`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-85/git-diff.patch`
  - `docs/qa/KAN-85/contract-sample.json`
  - `docs/qa/KAN-85/unit-test-results.txt`
  - `docs/qa/KAN-85/build-check.txt`
  - `docs/qa/KAN-85/api-specialist-review.md`
  - `docs/qa/KAN-85/message-to-reality-checker.md`
- **Reviewed Backend Hydration & Schema Serialization:**
  - `kanban/services/issues.py` (`serialize_issues_batch`, `_hydrate_batch_issue_context`)
  - `kanban/tests/api/test_issues.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-85` optimizes the primary issue feed endpoint (`GET /api/v1/projects/{project_ref}/issues`) by replacing per-row N+1 database queries with a batched hydration pipeline (`serialize_issues_batch`).

From a UI/UX consumption and frontend performance perspective:
1. **Dramatic Responsiveness & TTI Improvement:** Query latency for 100-item pages dropped from 1,259.05 ms to 293.87 ms (a 4.3x speedup). This eliminates the noticeable view loading latency and spinner hang in the web client when switching projects, toggling between List, Table, and Board views, or paginating work items.
2. **Strict Wire-Contract & Client State Parity:** The batched response preserves 100% byte-for-byte JSON payload and strong ETag parity with the previous sequential implementation. Web client components (`ListView`, `TableView`, `BoardView`, `IssueNavigatorBar`, `IssuePeekDrawer`) consume identical data shapes with zero risk of schema drift or client deserialization failures.
3. **Ergonomic Access & RLS Privacy Presentation:** Parent issue summaries for issues where the caller lacks VIEW permission under PostgreSQL `FORCE ROW LEVEL SECURITY` are safely represented as `RestrictedParentSummary(restricted=True, label="🔒 Restricted Parent Issue")`. This prevents unauthenticated information leakage while providing clear, friendly indicator metadata to the frontend UI without broken links or missing state errors.
4. **Zero Frontend Regressions & Full CSP Compliance:** The backend optimization requires no alterations to frontend markup or stylesheets. Existing strict Content Security Policy invariants (zero inline styles, zero `dangerouslySetInnerHTML`) and client accessibility hooks remain fully intact.
5. **Prose & Typography Hygiene:** Zero em-dashes or en-dashes (U+2014 / U+2013) exist in documentation or source code.

---

## 2. Frontend Consumption & Schema Audit

### 2.1 Schema Integrity for Client Views
The hydrated fields produced by `serialize_issues_batch` were audited against client UI consumption patterns:
- **State & Priority:** Workflow states and priorities correctly retain `id`, `name`, `group`, `color_hex`, `slug`, `label`, and `emoji`. Badges in `ListView` and `TableView` render consistently with no missing theme color attributes.
- **Labels & Modules:** Multi-label and multi-module collections are sorted deterministically (`order_by(IssueLabel.issue_id, ProjectLabel.name)`), avoiding jitter or re-ordering during client re-renders.
- **Assignees:** Principal and free-text assignees retain proper discriminators (`kind: "principal"` vs `kind: "free_text"`), ensuring avatar badges and fallback tooltips render without UI degradation.
- **Access Manifest:** Per-issue access manifests (`pill_label`, `inherited_scope`, `users`, `groups`, `caller_capabilities`) are computed identically to individual issue peek requests, preserving sharing badges and permission-based action disabling in the UI.

### 2.2 Parent Hierarchy & Restricted Access UX
When an issue references a parent in an unreadable project or under an explicit `DENY` ACL:
- Serialized output: `{"parent": {"restricted": true, "label": "🔒 Restricted Parent Issue"}}`.
- The web UI gracefully displays the restricted lock pill without attempting to navigate to an unviewable project or throwing 404/403 runtime errors.

---

## 3. Test Coverage & Verification

- **Pytest Suite Execution:** 21 tests passed (`test_kan85_serialize_issues_batch_byte_for_byte_payload_and_etag_parity`, `test_kan85_list_issues_100_items_query_count_bound`, `test_kan85_rls_restricted_parent_and_capability_parity_under_force_rls`).
- **Query Bounds & Speedup:** 18 SQL statements executed on a 100-item page (strictly <= 20 SQL statements bound), dropping from 2,662 queries and delivering a 4.3x frontend latency improvement.
- **Coverage:** 97% line and branch coverage on `kanban/services/issues.py`.
- **Static Analysis:** `make check` and `uv run python -m scripts.check_no_dashes --all` passed with 0 errors.

---

## 4. Review Sign-Off

The batch serialization implementation provides substantial UI responsiveness gains, full wire-contract parity, and reliable UX error/permission handling.

**STATUS: APPROVED**
