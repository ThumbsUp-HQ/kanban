# UI Specialist Review: KANBA-214

- Ticket: KANBA-214 ([KB-AUDIT-08] Fix Project Danger Zone Trash 422 and Implement Project Trash/Restore, Server Permanent Purge, and Project Workflow States/WIP/Priorities/Labels Settings)
- Reviewer Persona: UI Specialist / UX Architect
- Status: APPROVED
- Date: 2026-11-19

## Summary of Changes Reviewed
1. Danger Zone Fixes & Confirmation Dialogs:
   - Fixed the 422 Unprocessable Entity error when moving projects to trash by sending explicit `mode: "trash"` instead of missing or obsolete payload parameters.
   - Added Stage 2 blast-radius impact summary card (`.kb-danger-confirm-card`) displaying exact item counts (work items, sub-issues, docs, stickies).
   - Added confirmation phrase input requiring exact phrase match (`trash-project-kan`) to enable confirmation button.
   - Added `SERVER_ADMIN`-only permanent purge button (`💥 Permanently Purge Project (Irreversible)...`) with distinctive destructive styling (`.kb-btn-purge`) and separate confirmation phrase (`permanent-purge-kan`).

2. Project Trash & Retention UI:
   - Added dedicated `Trash & Retention` tab in `ProjectSettingsPage.tsx`.
   - Implemented kind filter pills (`All`, `Issues`, `Cycles`, `Modules`, `Stickies`, `Docs`) with active highlight states.
   - Designed table listing soft-deleted items with object type icon badges, key/identifier, title/summary, retention days countdown pills (`XX days remaining`), and accessible 1-click `Restore` action.

3. Workflow States & WIP Limits:
   - Implemented workflow state authoring form supporting state name, category group, color picker, sort order, and default flag.
   - Added Soft WIP limit and Hard WIP limit numeric inputs with client-side validation enforcing `hard >= soft`.
   - Added state reordering controls (up/down order adjustments) and delete action with default protection.

4. Priorities & Labels Management:
   - Priorities tab: custom slug, label, emoji, color hex, order, and default status CRUD.
   - Labels tab: label name, color hex, and exclusive group classification CRUD.

5. Searchable Principal Picker (Members Tab):
   - Replaced raw UUID text input with interactive searchable Principal Picker.
   - Integrated live filtering across Users, Groups, and Agents by display name, `@handle`, or UUID with semantic identity icons (`👤`, `👥`, `🤖`).
   - Added `🔍 Inspect Effective Access` button triggering the Access Inspector popover.

6. General Settings & Modules:
   - Added `Default Modules` multi-select alongside `Enable Modules` checkbox.
   - Added auto-archive threshold input in days.

7. Archive Action & Hard WIP Enforcement:
   - Wired `Archive` action in `IssueOverflowMenu.tsx` for issues in `Done` or `Cancelled` states.
   - Verified Board and Table views enforce configured Hard WIP limits with snap-back for standard members and override prompt for project admins.

## Visual Proof & Multi-Viewport Audit
All 42 screenshots in `docs/qa/KANBA-214/screenshots/` were generated via Playwright and inspected:
- Desktop (1440x900): Light and Dark modes verify breathable whitespace, crisp typography, and aligned form layouts.
- Tablet (1024x768): Responsive grid gracefully stacks form fields; tables retain horizontal scroll with sticky headers.
- Mobile (390x844): Tabs overflow cleanly via touch-scrollable nav bar; modal confirmation cards fit within viewport without truncation.

## Verdict
Approved with Grade A. Meets all UI/UX ergonomic guidelines, semantic emoji conventions, and accessibility standards.
