# Reality Checker Briefing: KAN-379

- **Ticket:** KAN-379
- **Title:** [KB-ISSUE-HEADER-TO-SIDEBAR] Compact Split Issue Header: Replace Duplicate #KAN-xxx with Edit, Move Add Comment to Bottom & Relocate Access/Toolbar Controls to Right Sidebar
- **Author/Builder:** `@b-kan379`
- **Branch:** `feat/KAN-379`
- **Status:** READY FOR VERIFICATION

---

## 1. Executive Summary & Problem Resolution

### Problem 1: Redundant #KAN-xxx Key in Split Header
In `.surface__header--split`, the breadcrumb already displays the project and issue key (e.g. `Platform Core / KAN-52`), but a duplicate `<span className="mono issue-header__key">#{currentIssue.key}</span>` was rendered directly next to it.
**Solution:**
Replaced the duplicate key span directly with the `✎ Edit` button (`data-testid="split-edit-btn"`), bound to `handleStartEditDescription`.

### Problem 2: Add Comment Button Location
The `💬 Add comment` button was positioned in the top toolbar row, detached from the activity and discussion section.
**Solution:**
Moved `💬 Add comment` (`data-testid="split-add-comment-btn"`) down to the Activity / Comments section (`split-section-activity` in `IssueSurface.tsx`), positioned in `.split-activity-actions`. Clicking the button scrolls to and focuses the comment composer textarea.

### Problem 3: Multi-Row Split Header and Toolbar Clutter
The split view header was cluttered by `<AccessPill issue={currentIssue} />` and an entire separate toolbar row (`.split-action-toolbar`) between the header and the body, consuming excessive vertical space.
**Solution:**
Moved `<AccessPill issue={currentIssue} />` and all remaining split toolbar controls (`split-state-select`, `split-assign-btn`, `split-favorite-btn` / `favorite-issue-toggle`, `split-share-btn`, `SubscribeSlot`, `LinkSlot`, and `OverflowSlot`) into the right-hand properties sidebar (`.split-right-column`).
This leaves a single slim header row above the issue title on the main column, providing breathable whitespace and clear visual hierarchy.

---

## 2. Verification Packet Contents

The QA packet in `docs/qa/KAN-379/` contains:
1. `git-diff.patch`: Complete diff of all modified and added files.
2. `unit-test-results.txt`: Test output demonstrating 100% pass across all 91 vitest tests.
3. `build-check.txt`: Output of TypeScript typecheck, ESLint, Vite production build, and check_no_dashes.
4. `ui-specialist-review.md`: UI/UX Specialist sign-off covering layout, whitespace, and accessibility.
5. `api-specialist-review.md`: API Specialist sign-off covering endpoint contracts, action callbacks, and mutation stability.
6. `screenshots/`: 5 responsive screenshots:
   - `01-desktop-split-view-light.png`: Desktop 1440x900 light mode showing single-line slim header, right sidebar action controls, and bottom Add comment button.
   - `02-desktop-split-view-dark.png`: Desktop 1440x900 dark mode showing high-contrast slim header without duplicate key.
   - `03-tablet-split-view-landscape.png`: Tablet 1024x768 light mode showing responsive header and right column toolbar.
   - `04-mobile-landscape-split-surface.png`: Mobile landscape 844x390 light mode showing fluid layout.
   - `05-mobile-portrait-split-surface.png`: Mobile portrait 390x844 dark mode showing single-column layout.
7. `changed-files-manifest.txt`: SHA-256 checksums of all touched files.

---

## 3. Automated Validation Command

To verify the test suite:
```bash
pnpm --dir kanban/web exec vitest run src/features/drawer/IssueSurface.test.tsx src/features/drawer/IssueSurfaceSplitMasterDetail.test.tsx src/app/__tests__/MenuConsolidation.test.tsx src/app/__tests__/MenuConsolidation_KAN366.test.tsx src/styles/__tests__/cssTokensAudit.test.ts
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build
uv run python -m scripts.check_no_dashes --all
```
