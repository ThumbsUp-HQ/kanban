# API Specialist Gate Review: KANBA-100 (KB-P3-08)

- **Ticket**: `KANBA-100` (`KB-P3-08`: Make a copy API (sub-issues, attachments, RELATES_TO link))
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-100` (`HEAD: 612b0da`)
- **Worktree**: `/tmp/kb-wt-KANBA-100`
- **Scope**: `kanban/api/v1/issue_copy.py`, `kanban/api/v1/schemas/issue_copy.py`, `kanban/services/issue_copy.py`, `kanban/services/activity.py`

---

### 1. Architectural & Security Evaluation

#### A. REST API Endpoint & Capability Bounds (S7.2 8n, S3.4)
- `POST /api/v1/issues/{issue_ref}/copy` is wrapped in `timing_floor(floor_ms=25.0)`.
- Access control strictly verifies that the caller holds `Capability.VIEW` on the source issue (unreadable returns uniform HTTP 404) and `Capability.EDIT` on the source project (unauthorized returns HTTP 403 `INSUFFICIENT_CAPABILITY`).
- Pydantic v2 schemas enforce `extra="forbid"`, rejecting unknown query or body parameters with HTTP 422.
- Successful copy returns HTTP 201 with `Location: /api/v1/issues/{canonical_key}` pointing to the newly cloned top-level issue.

#### B. Cloned Field Semantics & Invariants
- `summary` is prepended with `"[Copy] "` and bounded to 500 characters.
- `description_markdown` is re-normalized via `normalize_to_markdown()` with a strict 1 MiB byte ceiling (`422 DESCRIPTION_TOO_LARGE`).
- `priority_id`, labels, and modules are duplicated (modules are copied strictly when `project.modules_enabled` is true).
- Fields omitted from cloning: assignees, cycle, start/due dates, parent, comments, subscriptions, activity, and existing object links. Custom field duplication is cleanly deferred to Phase 5 (KB-P5-01).
- The new issue receives a fresh atomic sequence ID (`allocate_issue_sequence`), project default workflow state, initial board rank, and sets `created_by_id = original_created_by_id = caller`.

#### C. Subtree Traversal & RLS Boundary Isolation
- Descendant subtree collection via `issues_get_copy_subtrees` evaluates `app_has_object_capability(id, 1)` per row up to depth 6.
- If a descendant is unreadable to the caller, it and its entire descendant subtree are pruned.
- The response returns `skipped: {"restricted_sub_issues": <count>}` as an opaque integer count only, strictly preventing side-channel leakage of unreadable issue keys, titles, or hierarchy depths.
- Size safety ceiling: total readable issues exceeding 200 (`1 + readable_sub_issues > 200`) immediately aborts with HTTP 422 `COPY_TOO_LARGE` before performing any database inserts.

#### D. Attachment Metadata & Typed Object Linking
- `include_attachments`: clones attachment metadata referencing the immutable blob SHA-256 and storage key without byte re-uploading. Attachments belonging to skipped sub-issues are not copied.
- `link_as_relates_to`: delegates to `create_object_link` to create a bidirectional `RELATES_TO` edge connecting the new top-level issue back to the original source issue.

#### E. Transactional Atomicity & Activity Recording
- Entire clone workflow runs inside an atomic transaction (`session.begin_nested()`). Any failure rolls back all issue rows, labels, modules, attachments, and link records.
- Emits `ActivityEventType.ISSUE_CREATED` for each created issue (`payload={"key": ..., "copied_from": ...}`) and `ActivityEventType.ISSUE_COPIED` on the source issue.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 9/9 pytest passed in 5.43s across `test_issue_copy.py`, verifying positive flow, explicit `DENY` sub-issue skipping, 500-char summary truncation, 201-issue `COPY_TOO_LARGE` boundary, depth-6 hierarchy preservation, attachment duplication, module gating, atomic rollback, and capability checks.
- **Coverage**: 100.00% statement and branch coverage across touched modules:
  - `kanban/api/v1/issue_copy.py`: 100%
  - `kanban/services/issue_copy.py`: 100%
- **Static Analysis**: Ruff check clean, Ruff format clean, Mypy strict clean (209 files), ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.
- **Proof Bundle**: Complete forensic proof bundle (`git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, `contract-sample.json`, `message-to-reality-checker.md`).

---

### 3. Gate Verdict

The Make a Copy API complies with all architectural, security, access control, subtree boundary, and quality invariants.

**VERDICT: APPROVED**
