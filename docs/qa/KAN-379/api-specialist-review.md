# API Specialist Review & Verification: KAN-379

- **Ticket ID:** KAN-379
- **Reviewer Persona:** Senior Backend & API Architect (`@api-spec`)
- **Target Surfaces:** REST API Endpoints, Action Toolbar Contracts, MCP Data Boundaries, and Client Mutation Integrity
- **Audit Date:** 2026-11-23
- **Verdict:** APPROVED (Zero REST or MCP Contract Regressions; Action Triggers and State Mutation Contracts 100% Preserved)

---

## 1. Scope & System Topology Audit

A thorough forensic audit of all route interactions, action triggers, and component boundaries modified under KAN-379 was conducted:
- **Modified Frontend Components:**
  - `kanban/web/src/features/drawer/IssueSurface.tsx`:
    - In `.surface__header--split`, replaced duplicate `#{currentIssue.key}` text span with `✎ Edit` button (`data-testid="split-edit-btn"`), binding directly to `handleStartEditDescription`.
    - Relocated `<AccessPill issue={currentIssue} />` and `.split-action-toolbar` into `.split-right-column`.
    - Preserved all action button callbacks:
      - State selector (`data-testid="split-state-select"`) -> `handleHeaderStateChange` -> `PATCH /api/v1/projects/{project_ref}/issues/{issue_key}`.
      - Assign button (`data-testid="split-assign-btn"`) -> `handleAssignClick` -> `POST /api/v1/issues/{issue_ref}/assignees`.
      - Favorite toggle (`data-testid="favorite-issue-toggle"`, child `data-testid="split-favorite-btn"`) -> `toggleFavorite` -> local storage + event broadcast.
      - Share export button (`data-testid="split-share-btn"`) -> `handleShareExport` -> clipboard permalink copy.
      - Action slots (`SubscribeSlot`, `LinkSlot`, `OverflowSlot`) -> preserved within `.split-action-toolbar`.
    - Relocated `💬 Add comment` button (`data-testid="split-add-comment-btn"`) to `split-section-activity` -> `handleAddCommentClick` -> smoothly scrolls to and focuses comment composer textarea.
  - `kanban/web/src/features/drawer/IssueSurface.css`:
    - Updated `.split-pager` with `margin-left: auto` for proper flex distribution in the single slim header.
    - Updated `.split-action-toolbar` with card styling for placement inside the right column.
    - Added `.split-activity-actions` and `.split-edit-btn` styles.
- **Updated Test Suites:**
  - `kanban/web/src/features/drawer/IssueSurface.test.tsx`: Added dedicated KAN-379 test suite verifying split header, activity section comment button, and right column action toolbar.
  - `kanban/web/src/features/drawer/IssueSurfaceSplitMasterDetail.test.tsx`: Added dedicated KAN-379 test case verifying duplicate key absence, edit button placement, and toolbar elements in right sidebar.
  - `kanban/web/src/app/__tests__/MenuConsolidation.test.tsx`: Verified all 8 tests pass.
  - `kanban/web/src/app/__tests__/MenuConsolidation_KAN366.test.tsx`: Verified all 9 tests pass.
  - `kanban/web/src/styles/__tests__/cssTokensAudit.test.ts`: Verified all 6 token audit tests pass.

Zero backend Python files, database migration schemas, or MCP tool definitions required modification, confirming zero wire-level breaking changes.

---

## 2. API Contract & Mutation Invariants

1. **State Transition Endpoint Contract:**
   - Selecting a new state via `data-testid="split-state-select"` invokes `patchIssue` targeting `PATCH /api/v1/projects/{project_ref}/issues/{issue_key}` with payload `{ state_id: targetStateId }`.
   - Error handling (e.g. 409 conflict, circuit breaker rework pause) remains fully intact.
2. **Assignee Endpoint Contract:**
   - Clicking `data-testid="split-assign-btn"` invokes `POST /api/v1/issues/{issue_ref}/assignees` with `{ kind: "principal", principal_id: currentUserId }`.
3. **Selector & Test ID Stability:**
   - All critical selectors (`split-edit-btn`, `split-add-comment-btn`, `split-action-toolbar`, `split-state-select`, `split-assign-btn`, `split-share-btn`, `favorite-issue-toggle`, `split-favorite-btn`) remain available for automated testing and reality-checker verification.

---

## 3. Specialist Sign-Off

The changes for KAN-379 maintain 100% backward and forward compatibility across all API mutation endpoints and action contracts. Status: APPROVED.
