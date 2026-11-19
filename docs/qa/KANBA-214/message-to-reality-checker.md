# Forensic Proof Packet: KANBA-214

- Ticket ID: KANBA-214
- Title: [KB-AUDIT-08] Fix Project Danger Zone Trash 422 and Implement Project Trash/Restore, Server Permanent Purge, and Project Workflow States/WIP/Priorities/Labels Settings
- Author / Worker: w5-proj
- Branch: feat/w5-proj
- Date: 2026-11-19

## Executive Summary & Definition of Done Verification

All requirements of KANBA-214 have been fully implemented, locally verified, and audited across backend and frontend domains:

1. Danger Zone 422 Fix & Two-Stage Confirmation:
   - Root Cause: Moving projects to trash previously failed with HTTP 422 due to missing or invalid mode parameters sent in destructive action requests.
   - Solution: Wired Stage 2 confirmation card in `ProjectSettingsPage.tsx` invoking `POST /api/v1/admin/destructive:request` with `{ target_kind: "project", target: projectKey, mode: "trash" }`.
   - Blast Radius Summary: Displays exact counts for work items, sub-issues, pages/docs, and stickies before prompting for confirmation.
   - Confirmation Phrase: Requires exact input match (`trash-project-kan`) to enable execution.
   - Permanent Purge: Added `SERVER_ADMIN`-only `mode: "permanent_purge"` flow with red purge button (`💥 Permanently Purge Project (Irreversible)...`) and separate phrase confirmation (`permanent-purge-kan`).

2. Project Trash & Retention UI:
   - Added dedicated `Trash & Retention` tab displaying soft-deleted entities.
   - Provides Kind filter buttons (`All`, `Issues`, `Cycles`, `Modules`, `Stickies`, `Docs`).
   - Displays countdown pill indicating remaining retention days (`XX days remaining`).
   - Provides accessible 1-click `Restore` action calling `/api/v1/issues/{key}/restore` or fallback `/api/v1/admin/destructive:restore`.

3. Full Project Schema Management Tabs under `/projects/:key/settings`:
   - General: Added `Default Modules` selector alongside `Enable Modules` checkbox.
   - Workflow States: Added authoring form with state name, category group, color picker, sort order, default toggle, and Soft/Hard WIP limits with `hard >= soft` validation.
   - Priorities: Custom key/slug, label, emoji, color hex, sort order, and default status CRUD.
   - Labels: Color hex and exclusive group classification CRUD.
   - Members: Searchable Principal Picker filtering Users, Groups, and Agents by display name, `@handle`, or UUID with role assignment and `🔍 Inspect Effective Access` button.

4. Archive Action & Hard WIP Enforcement:
   - Wired `Archive` action in `IssueOverflowMenu.tsx` for issues in `Done` or `Cancelled` states.
   - Verified Board and Table views enforce configured Hard WIP limits with snap-back for standard members and override prompts for project administrators.

## Quality & Gate Conformance Metrics
- Backend Unit Tests: `kanban/tests/api/test_issue_delete.py` -> 8/8 passed in 8.52s.
- Frontend Unit & Coverage Tests: `pnpm -C kanban/web test:unit --coverage` -> 188/188 test files passed (2,254/2,254 tests passed).
- Global Vitest Branch Coverage: 12,222 / 12,849 = 95.1202% (exceeds mandatory `>= 95.10%` threshold).
- Touched Files Branch Coverage:
  - `ProjectSettingsPage.tsx`: 97.04% branches (100% statements, lines, functions)
  - `IssueOverflowMenu.tsx`: 96.66% branches (100% statements, lines, functions)
  - `viewRegistry.tsx`: 96.79% branches (99.04% statements, 100% lines)
- TypeScript Compilation: `pnpm -C kanban/web typecheck` -> 0 errors, clean build.
- Playwright E2E Visual QA: 21/21 tests passed across Light and Dark themes on Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).
- Visual Artifacts: 42 annotated PNG screenshots in `docs/qa/KANBA-214/screenshots/`, all inspected via `read_file`.
- Specialist Reviews:
  - UI Specialist Review: `docs/qa/KANBA-214/ui-specialist-review.md` (Grade A, Approved)
  - API Specialist Review: `docs/qa/KANBA-214/api-specialist-review.md` (Grade A, Approved)
- Plain ASCII Compliance: Verified zero em-dashes and en-dashes across all documentation and commit artifacts.

## Forensic Artifact Checklist
- git-diff.patch: `docs/qa/KANBA-214/git-diff.patch`
- changed-files-manifest.txt: `docs/qa/KANBA-214/changed-files-manifest.txt`
- unit-test-results.txt: `docs/qa/KANBA-214/unit-test-results.txt`
- build-or-typecheck.txt: `docs/qa/KANBA-214/build-or-typecheck.txt`
- screenshots: `docs/qa/KANBA-214/screenshots/*.png` (42 annotated PNGs)
- ui-specialist-review.md: `docs/qa/KANBA-214/ui-specialist-review.md`
- api-specialist-review.md: `docs/qa/KANBA-214/api-specialist-review.md`
- message-to-reality-checker.md: `docs/qa/KANBA-214/message-to-reality-checker.md`
