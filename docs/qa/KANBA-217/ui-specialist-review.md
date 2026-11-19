# UI Specialist Forensic QA Review: KANBA-217

STATUS: APPROVED

Auditor: ui-spec (UI Designer / UX Architect / Accessibility Specialist)
Target Ticket: KANBA-217 ([KB-AUDIT-11] Fix Stickies Snooze 422 Crash, Wire AI Sticky-to-Doc Preview & Valid Doc Target, and Implement Docs Version Diff/Restore & Highlight-to-Issue Linking)
Branch: main (integrated from feat/w4-docs commit 206a4b5)

## 1. Scope and Surface Audited

Per GEMINI.md Mandatory Specialist Gates:
1. Stickies Snooze & Error Resilience (`kanban/web/src/features/stickies/StickyCard.tsx`, `StickyPromotionBanner.tsx`):
   - Snooze action sends valid `promotion_snoozed_at_length`, re-evaluating banner presentation only after >=1.5x character growth (+50%).
   - Wrapped mutations in local inline error state (`setInlineError`), gracefully displaying red warning indicators on network/API failure without triggering full-page React Error Boundaries.
2. AI Sticky-to-Doc Preview Modal (`StickyPromotePreviewModal.tsx`):
   - Accessible modal overlay (`role="dialog"`, `aria-modal="true"`) displaying preserved ACL notice ("Access Grants Preserved: All X explicit ACL grant(s)..."), editable document title, structured Markdown preview with Mermaid flowchart diagram, and clean Cancel / Confirm actions.
   - Promoted Sticky stub (`PromotedStickyStub.tsx`) maps `Open Doc` link directly to valid canonical page route `/projects/:key/docs/:rootPageId` (200 OK, never an unrouted UUID or 404).
3. Text State Preservation Across Markdown / WYSIWYG Toggle:
   - `MarkdownEditor.tsx` synchronizes ProseMirror document state with the raw text buffer, guaranteeing 100% text retention across view mode switches.
4. Docs History Version Diff & 1-Click Restore (`OutlineAndVersionsRail.tsx`):
   - Longest common subsequence (LCS) line diff renderer with color-coded syntax highlights (green addition, red deletion).
   - Statistical summary badge (`+X -Y lines changed`) and segmented toggle (`Diff vs Current` / `Raw Content`).
   - Accessible 1-click `Restore vX` button restoring historical versions non-destructively.
5. Searchable Doc-to-Issue Link Picker (`OutlineAndVersionsRail.tsx`):
   - Modal dialog searching issues by key (`KAN-101`) or title with relationship selector (`VERIFIED_BY_DOC`, `RELATES_TO`), eliminating raw UUID manual entry.

## 2. Visual Proof Inspection (Playwright Screenshots)

All 8 Playwright screenshots in `docs/qa/KANBA-217/screenshots/` were directly inspected via `read_file`:
- `01-sticky-snooze-banner-desktop-light.png`: Candidate sticky cleanly renders promotion banner (`Growing into a spec`) with `Promote to Doc ->` and `Snooze` controls.
- `02-sticky-promote-preview-modal-desktop-light.png`: Centered modal dialog showing ACL notice card, title input, and structured Markdown/Mermaid preview.
- `02-sticky-promote-preview-modal-mobile-dark.png`: Mobile 390x844 dark mode layout with zero horizontal overflow and responsive button stacking.
- `03-promoted-sticky-open-doc-desktop-light.png`: Promoted sticky stub with `Open Doc` link and `Unarchive Copy` option.
- `04-docs-history-diff-restore-desktop-light.png`: Right rail History drawer showing version timeline, +6 -2 line diff with color-coded changes, and prominent `Restore v2` button.
- `04-docs-history-diff-restore-tablet-dark.png`: Tablet dark mode diff viewer with legible green/red contrast.
- `05-docs-highlight-link-picker-desktop-light.png`: Searchable link picker dialog querying issues by key and title.
- `05-docs-highlight-link-picker-mobile-dark.png`: Mobile link picker dialog adapting cleanly to narrow viewports.

## 3. Ergonomics & Accessibility Compliance

- Viewports: Fluid layout across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844) with zero horizontal overflow.
- Contrast: Line diff badges, modal preview text, and buttons meet WCAG AA >= 4.5:1.
- Typography: Plain ASCII hyphens exclusively; zero em-dashes or en-dashes across all source and review files.

## 4. Verdict

The Stickies snooze fixes, AI preview modal, canonical doc routing, history line diff viewer, and issue link picker satisfy all UI, UX, and accessibility requirements.

STATUS: APPROVED
