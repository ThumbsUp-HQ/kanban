# Forensic QA Verification Packet: KANBA-220

## Summary Information
- Ticket ID: KANBA-220 ([KB-AUDIT-14] Implement Invalid Object Link Auditor & Purger UI and Wire Functional Access Manifest ACL Management, Agent Kill Switch, and Activity Redaction)
- Branch: feat/w6-acl
- Author: w6-acl (Wave 6 Builder)
- Target: Coordinator & Reality-Checker QA Gate

## Requirements & Verification Matrix

### 1. Eliminate /objects/KAN/access 404s & Fix Role Badges
- Implementation:
  - Added `isNonAddressableAccessRoute` guard in `kanban/web/src/app/HeaderPills.tsx` checking `/your-work`, `/admin/*`, `/settings/*`, `/drafts`, `/login`, `/setup`, `/workspaces`.
  - Prevented Topbar from defaulting to `projectKey = 'KAN'` on non-project routes.
  - In `kanban/security/access_manifest.py`, decoupled `workspace_admin` from `workspace_role` and mapped project roles cleanly.
  - In `kanban/web/src/features/access/AccessInspectorPopover.tsx`, resolved role labels so `@member` shows accurate project role (`Admin [Project Role]`, `Edit [Project Role]`, or `[Direct Share]`, never mislabeled `[Workspace Admin]`).
- Verification Proof:
  - Unit tests: `HeaderPills.test.tsx` (95.00% branch coverage), `AccessInspectorPopover.test.tsx` (95.07% branch coverage).
  - Screenshots: `01-access-inspector-popover-dark-desktop.png`, `01-access-inspector-popover-light-desktop.png`.

### 2. Wire Functional Manage Access... ACL CRUD & Agent Kill Switch
- Implementation:
  - Created `ManageAccessModal.tsx` and `ManageAccessModal.css`.
  - Filter chips (All, Users, Groups, Agents), searchable principal picker, ALLOW/DENY radios, presets (Viewer, Commenter, Editor, Full Admin), capability grid, active ACL entries table with revocation.
  - Connected `button.access-inspector__btn--secondary` (`[Manage Access...]`) visible only to callers with `Capability.SHARE` or `Capability.ADMIN`.
  - Interactive Agent Kill Switch (`AgentKillSwitchControl.tsx`) with 2-stage confirmation strip, revoking active agent and OBO tokens with immutable audit logging.
- Verification Proof:
  - Unit tests: `ManageAccessModal.test.tsx` (97.67% branch coverage), `test_objects_access_endpoint.py` (100% pass).
  - Screenshots: `02-manage-access-modal-dark-desktop.png`, `02-manage-access-modal-light-desktop.png`.

### 3. Unify External Collaborator Redaction Across Activity Tabs
- Implementation:
  - Added `redacted: bool` and `label: str | None` to comment author schemas (`kanban/api/v1/schemas/comments.py`).
  - Implemented author masking in `kanban/services/comments.py` dynamically setting author to `External Collaborator` when the author is outside the caller's visibility boundary.
  - In `CommentCard.tsx` and `GateActivityRow.tsx`, render `External Collaborator` label, suppress handles, and hide edit/delete actions.
- Verification Proof:
  - Unit tests: `CommentCard.test.tsx` (98.41% branch coverage), `GateActivityRow.test.tsx` (97.87% branch coverage).

### 4. Build Invalid Object Link Auditor & Purger (/admin/link-auditor)
- Implementation:
  - Built `LinkAuditorStudio.tsx` and `LinkAuditorStudio.css`.
  - Route guarded with `AdminRouteGuard` requiring `(isServerAdmin || isWorkspaceAdmin) && isAal2`. Non-admins receive uniform `NotFoundView`.
  - 6-class metric overview cards (Dangling Source, Dangling Target, Soft-Deleted Endpoint, Archived Policy Violation, Type Matrix Violation, Cross-Workspace Leak, Permission Severed).
  - Keyset-paginated table of flagged links with human source and target keys.
  - Inspect drawer rendering JSON snapshots of link row, source entity, and target entity.
  - Audited purge modal requiring mandatory justification of at least 10 characters (enforcing 422 on omitted reason).
- Verification Proof:
  - Unit tests: `LinkAuditorStudio.test.tsx` (96.90% branch coverage).
  - Screenshots:
    - `03-link-auditor-studio-dark-desktop.png`, `03-link-auditor-studio-light-desktop.png`
    - `04-inspect-link-drawer-dark-desktop.png`, `04-inspect-link-drawer-light-desktop.png`
    - `05-audited-purge-modal-dark-desktop.png`, `05-audited-purge-modal-light-desktop.png`

## Automated Quality & Coverage Metrics
- Global Vitest Branch Coverage: 96.01% (threshold >= 95.10%). Statements: 99.21%, Functions: 98.80%, Lines: 99.58%.
- Vitest Test Results: 201/201 test files passed, 2550/2550 tests passed.
- Pytest Test Results: 2/2 passed.
- Playwright E2E Results: 15/15 passed across desktop, tablet, and mobile.
- ESLint Results: 0 errors, 0 warnings.
- TypeScript Check: 0 errors.
- Production Build: Passed in 1.09s.

## Forensic Proof Artifacts in docs/qa/KANBA-220/
- `git-diff.patch`: Complete diff of all changes.
- `changed-files-manifest.txt`: List of modified and added files.
- `unit-test-results.txt`: Raw test and coverage output.
- `build-or-typecheck.txt`: Clean ESLint, TypeCheck, and Vite build output.
- `ui-specialist-review.md`: UI Specialist gate review.
- `api-specialist-review.md`: API Specialist gate review.
- `screenshots/`: 30 verified PNG screenshots across light/dark themes and desktop/tablet/mobile viewports.
