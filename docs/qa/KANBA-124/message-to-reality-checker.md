# Forensic Verification & Reality Checker Summary: KANBA-124 (KB-P3-43)

## Ticket Identification & Overview
- **Ticket ID:** `KANBA-124` (`KB-P3-43`)
- **Title:** `[Phase 3 / Frontend] Ticket header & overflow actions (8l-8q): Subscribe 🔔, Copy link & Object Graph 🔗 (Cmd+Shift+C), Make a copy, rule-explained Archive & blast-radius Delete`
- **Specification Source:** `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` S7.1, S7.2 (8l-8q), S12.1, S12.3; `docs/tickets/KB-P3-43.md`
- **Branch & Worktree:** `feat/KANBA-124` in `/tmp/kb-wt-KANBA-124`

---

## Implemented Deliverables

1. **`SubscribeAction.tsx` (`issueSurfaceSlots.subscribe`):**
   - 1-click toggle between `🔔 Subscribe` and `Subscribed`.
   - Optimistic update rollback on mutation failure.
   - Disclosure chevron `▾` triggering per-event mute popover.
   - 7 granular mutable event checkboxes (`COMMENT_CREATED`, `ISSUE_STATE_CHANGED`, `ISSUE_FIELD_CHANGED`, `ISSUE_DESCRIPTION_CHANGED`, `ISSUE_LABELS_CHANGED`, `ASSIGNEE_ADDED`, `ASSIGNEE_REMOVED`).
   - Mutations dispatched via `PATCH /api/v1/issues/{issue_ref}/subscription` with `{ muted_event_types }`.

2. **`LinkGraphAction.tsx` (`issueSurfaceSlots.link`):**
   - `[🔗]` button displaying Object Graph popover.
   - Global keyboard chord `Cmd/Ctrl+Shift+C` copying Markdown `[KEY](canonical_url)` with live screen-reader announcement (`aria-live="polite"`).
   - Suppressed keyboard shortcut when focus is within editable form inputs, textareas, selects, or `contenteditable` elements.
   - Safe clipboard writing handling browser security limitations and absent clipboard API gracefully.
   - Displays outbound and inbound links.
   - Far-endpoint masking: endpoints with `restricted: true` are rendered as `🔒 Restricted Object` with zero entity keys, IDs, or links leaked.
   - Displays `link_state === 'FLAGGED_INVALID'` with `🕸️⚠️` broken link badge and EmojiHint.
   - Link creation limited strictly to 6 user-creatable types (`BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `DUPLICATES`, `VERIFIED_BY_DOC`, `DERIVED_FROM_STICKY`), completely excluding reserved system type `PROMOTED_TO_DOC`.
   - Single-click link deletion for outbound links.

3. **`IssueOverflowMenu.tsx` (`issueSurfaceSlots.overflow`):**
   - Clean 4-item dropdown:
     * `📑 Make a copy` -> opens duplicate dialog.
     * `↗ Open in full screen` / `Return to side panel` -> zero-remount layout toggle.
     * `🗄️ Archive` / `Unarchive` -> rule-gated: enabled only when issue state group is `completed` or `cancelled`. For active items, sets `aria-disabled="true"` with exact visible sub-label `"Only completed or canceled work items can be archived"`.
     * `🗑️ Delete...` -> gated by `'DELETE'` capability; opens blast-radius modal.

4. **`MakeCopyDialog.tsx`:**
   - Summary preview: `[Copy] <summary>` clamped to 500 characters.
   - 3 distinct checkboxes: `Include sub-issues`, `Include attachments`, `Link as RELATES_TO` (all default unchecked).
   - Creator attribution banner: `"Created by will be set to @<handle>"`.
   - Handles `201 Created` with skipped restricted sub-issue count announcement.
   - Inline alert for `422 COPY_TOO_LARGE` errors.

5. **`DeleteBlastRadiusModal.tsx`:**
   - Pre-flight blast radius calculation: `"{N} sub-issues unparented, {M} inbound object_links flagged"`.
   - Soft-trash retention notice: `"Moved to trash for {retention_days} days before permanent audited purge."`.
   - Destructive confirmation sending `DELETE /api/v1/issues/{key}` with `Kb-Blast-Hash: <blast_hash>`.
   - Handles `412 BLAST_RADIUS_CHANGED` with inline alert and refreshed blast radius.

6. **`actionsApi.ts`:**
   - Strictly typed API client using OpenAPI-backed `apiFetch` with zero `any`.
   - Endpoints implemented:
     * `fetchSubscription`, `subscribeIssue`, `unsubscribeIssue`, `patchSubscription`
     * `fetchCanonicalUrl`, `fetchObjectLinks`, `createObjectLink`, `deleteObjectLink`
     * `copyIssue`, `archiveIssue`, `unarchiveIssue`
     * `fetchDeletePreview`, `deleteIssue`

7. **Dev Story & E2E Suite:**
   - `DrawerActionsStory.tsx` mounted at `/__dev/drawer-actions`.
   - 15 Playwright E2E tests across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).
   - Annotated visual screenshots and computed style probes captured in `docs/qa/KANBA-124/`.

---

## Architectural & Security Invariants Verified

- **Zero Unicode Dashes:** Checked via `scripts/check_no_dashes.py --all`. Zero em-dash (`U+2014`) or en-dash (`U+2013`) characters present across repository.
- **Strict CSP:** Zero JSX inline `style=` attributes. All styling defined in `drawerActions.css` and `DrawerActionsStory.css`.
- **Zero Warnings & Safe Typing:** `tsc -b --noEmit` and `eslint . --max-warnings 0` both pass with 0 errors and 0 warnings.
- **Strict License Policy:** `scripts/license_gate.py` passes; zero GPL/AGPL dependencies.
- **Coverage Mandate:** Unit tests achieve `>= 95%` across statements (99.43%), branches (95.92%), functions (99.09%), and lines (100.00%).
