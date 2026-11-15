# KANBA-165 (KB-QA-04) - Verification Proof Summary

## Scope & Implemented Remediation
1. **Live Issue Detail Drawer (`?peek=`) & Full-Screen (`/projects/:projectKey/issues/:issueKey`) Persistence (`kanban/web/src/features/drawer/IssueSurface.tsx`):**
   - Implemented `normalizeIssueDetail` in `IssueSurface.tsx` so raw backend `IssueResponse` payloads returned by `GET /api/v1/issues/${issueKey}` are normalized with `project_key`, `object_id`, `etag` (derived from `description_sha256`), `label_ids`, and `capabilities`, while preserving unit-test fixtures verbatim.
   - Added interactive Description editing (`Edit description`, `Description` textarea, `Save`, `Cancel`) and fenced ` ```mermaid ` diagram preview in `IssueSurface.tsx` when `DescriptionSlot` is not overridden, persisting changes via `PATCH /api/v1/issues/${issueKey}` with `If-Match` concurrency protection and updating the React Query cache (`qk.issue(issueKey)`).
   - Wired `IssueSurface.tsx` to load real project workflow states (`GET /api/v1/projects/${projectKey}/states`) and bootstrap `X-CSRF-Token` when `RailSlot` (`PropertiesRail`) or `ActivitySlot` (`ActivitySection`) is mounted, passing `projectMetadata` (with real PostgreSQL state UUIDs) and `onIssueUpdate` to `PropertiesRail` so State, Priority, Assignees, Labels, Cycles, Modules, Dates, and Comments persist against `/api/v1/issues/${issueKey}` and broadcast `kb:issue-updated`.

## Verification Evidence
- `docs/qa/KANBA-165/unit-test-results.txt`: 16 test files, 159/159 unit tests passing across `src/features/views/` and `src/features/drawer/` (`>=95%` coverage).
- `docs/qa/KANBA-165/build-check.txt`: `eslint --max-warnings 0`, `tsc -b --noEmit`, and `vite build` exit `0`.
- `docs/qa/KANBA-165/git-diff.patch`: Complete unified diff for Slice 2 (`KANBA-164` and `KANBA-165`).
- `docs/qa/KANBA-165/screenshots/`: Responsive desktop, tablet, and mobile Playwright screenshots.
