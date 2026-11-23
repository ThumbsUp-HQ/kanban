# Forensic Reality-Checker QA Handoff: KAN-366

## 1. Executive Summary

- **Ticket Key**: `KAN-366`
- **Title**: `[KB-MENU-ISSUE-ACTIONS] Issue Header & Split-Pane Action Bar Parity with Duplicate Control Elimination`
- **Domain**: Issue Header & Split-Pane Action Toolbar Consolidation, Action Control Disambiguation, and Fullscreen Ergonomics
- **Target Files**:
  - `kanban/web/src/features/drawer/IssueHeader.tsx`
  - `kanban/web/src/features/drawer/IssueSurface.tsx`
  - `kanban/web/src/features/drawer-actions/LinkGraphAction.tsx`
  - `kanban/web/src/features/drawer-actions/IssueOverflowMenu.tsx`
  - `kanban/web/src/app/__tests__/MenuConsolidation_KAN366.test.tsx`
- **Branch**: `feat/KAN-366`
- **Status**: READY FOR AUDIT (Grade-A Target)

---

## 2. Technical Implementation Details

### A. Split-Pane Action Bar Parity (`IssueSurface.tsx`)
1. In `IssueSurface.tsx` under `mode === 'split'`, the `split-action-toolbar` renders:
   - `SubscribeSlot` (`slots.subscribe`): Subscriptions and notification preferences.
   - `LinkSlot` (`slots.link` / `LinkGraphAction`): Typed Object Graph relations manager.
   - `OverflowSlot` (`slots.overflow` / `IssueOverflowMenu`): More actions menu (Make a copy, Fullscreen toggle, Archive, Delete).
2. Existing split-mode action buttons (Edit description, Add comment, Assign to me, State selector, Favorite toggle, Share/Export) remain fully functional with zero regressions.

### B. Action Control Deduplication & Disambiguation (`IssueHeader.tsx` & `LinkGraphAction.tsx`)
1. In `IssueHeader.tsx`, `copy-issue-link-btn` (clipboard web URL copy) and `LinkGraphAction` (Object Graph relations manager) are visually and semantically disambiguated:
   - `copy-issue-link-btn`: Glyph `🔗` (swaps to `Copied!` upon click), accessible label `Copy issue link for ${issue.key}`, title `Copy issue link`.
   - `link-graph-trigger` (`LinkGraphAction`): Distinct network/graph glyph `🕸️`, accessible label `Link and Object Graph`, title `Link and Object Graph`.
   - `copy-issue-key-btn`: Distinct clipboard glyph `📋`, accessible label `Copy issue key ${issue.key}`, title `Copy issue key`.
2. Strict test assertions verify glyph distinctness (`copyLinkBtn.textContent !== linkGraphTrigger.textContent`) and aria label distinctness.

### C. Fullscreen Toggle Ergonomics (`IssueHeader.tsx`, `IssueOverflowMenu.tsx`, & `IssueSurface.tsx`)
1. Dual-state directional glyphs:
   - Drawer / Split mode: Glyph `↗` with accessible label `Open in full screen` and title `Open in full screen (Meta+Shift+F)`.
   - Fullscreen mode: Glyph `↙` with accessible label `Return to side panel` and title `Return to side panel (Meta+Shift+F)`.
2. `IssueOverflowMenu.tsx` dynamically renders the matching directional glyph (`↙` vs `↗`) corresponding to the active mode.
3. In `IssueSurface.tsx`, `handleToggleFullScreen` now supports `split` mode, navigating directly to `toFullScreenPath(resolvedProject, issueKey)` so clicking "Open in full screen" from the split-pane overflow menu properly opens the full screen view.
4. Registered global shortcut `Meta+Shift+F` / `Control+Shift+F`.

---

## 3. Verification & Test Evidence

### A. Mandatory Feature Unit Tests (`MenuConsolidation_KAN366.test.tsx`)
1. **Test Case 1 (Split-pane IssueSurface Action Bar Parity)**:
   - Renders `SubscribeSlot`, `LinkSlot`, and `OverflowSlot` inside `split-action-toolbar`.
   - Renders default concrete slot components (`LinkGraphAction`, `IssueOverflowMenu`) in split mode.
   - Verifies split header breadcrumbs, sequential pager, and position counter.
2. **Test Case 2 (Deduplication and Disambiguation of Action Controls)**:
   - Verifies distinct glyphs and aria labels for `copy-issue-link-btn` (`🔗`) vs `LinkGraphAction` (`🕸️`).
   - Verifies distinct glyph for `copy-issue-key-btn` (`📋`).
   - Verifies fullscreen toggle dual-state glyphs (`↗` / `↙`) and labels across `IssueHeader` and `IssueOverflowMenu`.
3. **Test Case 3 (Action Slots Mutations in Split Mode)**:
   - Executes state transitions via `split-state-select` invoking `railApi.patchIssue`.
   - Executes 1-click self-assignment via `split-assign-btn` invoking `railApi.addAssignee`.
   - Toggles issue favorite state in `localStorage` and updates button label.
   - Executes Object Graph link creation via `LinkGraphAction` slot popover invoking `actionsApi.createObjectLink`.
   - Triggers fullscreen transition from split-pane overflow menu slot.

### B. Specialist Audits
- API Specialist Review: Signed and approved in `docs/qa/KAN-366/api-specialist-review.md`.
- UI Specialist Review: Signed and approved in `docs/qa/KAN-366/ui-specialist-review.md`.

### C. Verification Bundle
- `docs/qa/KAN-366/git-diff.patch`
- `docs/qa/KAN-366/unit-test-results.txt`
- `docs/qa/KAN-366/build-check.txt`
- `docs/qa/KAN-366/api-specialist-review.md`
- `docs/qa/KAN-366/ui-specialist-review.md`
- `docs/qa/KAN-366/screenshots/` (5 responsive screenshots)
- `docs/qa/KAN-366/message-to-reality-checker.md`
- `docs/qa/KAN-366/changed-files-manifest.txt`
