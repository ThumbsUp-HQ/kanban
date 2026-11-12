# Reality Checker Verification Summary: KANBA-100 (KB-P3-08)

## Ticket Overview
- Ticket ID: KANBA-100
- Specification: Spec Section 7.2 (8n)
- Title: [Phase 3 / API] Make a copy API (sub-issues, attachments, RELATES_TO link)
- Branch: feat/KANBA-100
- Worktree: /tmp/kb-wt-KANBA-100

## Scope and Architectural Boundaries
- Implemented `POST /api/v1/issues/{issue_ref}/copy` with timing floor decoration (`@timing_floor(floor_ms=25.0)`).
- Request schema `IssueCopyRequest` (`extra="forbid"`) supports:
  - `include_sub_issues: bool = False`
  - `include_attachments: bool = False`
  - `link_as_relates_to: bool = False`
- Response schema `IssueCopyResponse` (`extra="forbid"`) returns:
  - `issue`: Full serialized new issue.
  - `copied_sub_issues`: List of `CopiedSubIssueSummary(source_key, copy_key)`.
  - `skipped`: `IssueCopySkipped(restricted_sub_issues=<count>)` - count only, zero key/title leaks.
  - `copied_attachments`: Count of duplicated attachment records.
  - `link_id`: Optional UUID string of the top-level RELATES_TO link.
- Security and RLS:
  - Caller requires `VIEW` capability on the source issue and `EDIT` capability on the source project.
  - Sub-issue tree traversal uses `SECURITY DEFINER` function `issues_get_copy_subtrees(p_root_id uuid)` up to depth 6.
  - Descendants where the caller lacks `VIEW` (capability mask 1) are skipped along with their entire subtrees.
  - If total readable issues in the subtree exceed 200, the endpoint raises 422 `COPY_TOO_LARGE` prior to any mutations.
- Atomicity:
  - The entire clone operation (issues, labels, modules, attachments, links, and activity records) executes inside a single database transaction.
- Activity Ledger:
  - Emits `ISSUE_CREATED` on every created copy with `payload.copied_from` pointing to the source issue id.
  - Emits `ISSUE_COPIED` on the source issue with `payload.copy_id`, `copy_key`, `include_sub_issues`, and `include_attachments`.
  - Emits `LINK_CREATED` via `create_object_link` when `link_as_relates_to` is enabled.
- Custom Fields Out-of-Scope Statement:
  - Per specification Section 7.2 (8n) and ticket instructions, custom field copying is explicitly out-of-scope until Phase 5 (KB-P5-01). This is documented in code comments and this verification packet.

## Proof Artifacts in docs/qa/KANBA-100/
1. `git-diff.patch`: Complete diff relative to `main`.
2. `unit-test-results.txt`: 9/9 unit tests passing with 100% statement and branch coverage on `kanban.api.v1.issue_copy` and `kanban.services.issue_copy`.
3. `build-check.txt`: All static checks passing cleanly:
   - `ruff check kanban database` (0 errors)
   - `ruff format --check .` (774 files clean)
   - `mypy --strict kanban database` (0 errors across 331 files)
   - `lint-imports` (2 contracts kept, 0 broken)
   - `scripts.check_no_dashes --all` (0 unicode dashes)
   - `make license` (0 violations)
4. `contract-sample.json`: Recorded HTTP exchanges covering:
   - `copy_issue_default_201`
   - `copy_issue_with_options_and_skipped_201`
   - `copy_issue_too_large_422`
   - `copy_issue_non_viewer_404`
   - `copy_issue_non_editor_403`
5. `api-specialist-review.md`: Dual Specialist Gate sign-off from API Specialist.
6. `ui-specialist-review.md`: Dual Specialist Gate sign-off from UI Specialist confirming contract ergonomics and mapping to the 3-checkbox copy dialog.

## Verification Checklist
- [x] All 6 mandatory test cases implemented and passing in `kanban/tests/api/test_issue_copy.py`.
- [x] Coverage >= 95% (achieved 100.00% statement and branch coverage).
- [x] Timing floor applied to route handler.
- [x] Fail-closed permissions and zero info leakage on restricted descendants.
- [x] Plain ASCII hyphens used exclusively.
