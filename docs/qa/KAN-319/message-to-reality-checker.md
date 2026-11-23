# Evidence Packet & Verification Hand-off: KAN-319

- **Ticket ID:** KAN-319
- **Title:** [EPIC][KB-ADVANCED-DISCLOSURE-AUDIT] Screen-by-Screen "Advanced" Progressive Disclosure Audit & Refactor Epic (Spawn Child Tickets per Screen Group)
- **Author / Implementer:** `b-kan319`
- **Branch:** `feat/KAN-319`
- **Audit Target:** `reality-checker` (Forensic QA Gate)
- **Target Verification Level:** Grade-A READY Certification

---

## 1. Executive Summary

Ticket KAN-319 mandates an end-to-end screen-by-screen progressive disclosure audit across `kanban/web/src/`, decomposing future screen group work into discrete child tickets (`KAN-367` through `KAN-371`), building a shared accessible `<AdvancedSection>` component, and refactoring the inverted progressive disclosure in `AuthCardEditorDrawer.tsx`.

All requirements have been met with zero regressions, zero inline styles, zero em-dashes or en-dashes, and verified visual and automated unit test proof.

---

## 2. Deliverables & Artifact Index

1. **Audit Matrix & Child Tickets:**
   - Matrix Path: `docs/qa/KAN-319/advanced-disclosure-audit-matrix.md`
   - Child Tickets Created on Project `KAN` (`parent: "KAN-319"`, `state: "Todo"`):
     - `KAN-367`: Auth Card Studio Inverted Advanced Section Refactor and Auto-Derived Slug UX
     - `KAN-368`: Issue Creation Modal, Detail Surface, Properties Rail, and Search DSL Progressive Disclosure
     - `KAN-369`: Project Settings, Workflow Transition Hooks, and Custom Field Editor Progressive Disclosure
     - `KAN-370`: Workspace Settings, Personal Settings Security Details, and Flow Analytics Tunables Progressive Disclosure
     - `KAN-371`: Admin Studios McpAccessStudio Presets, OAuth Governance, Import, and AI Runner Progressive Disclosure
   - Ticket Comment: Published to `KAN-319` via MCP `add_comment` (Permalink: `KAN-319#c-01a2067e`).

2. **Shared Accessible `<AdvancedSection>` Component:**
   - Implementation: `kanban/web/src/ui/AdvancedSection.tsx`
   - Styling: `kanban/web/src/ui/AdvancedSection.css`
   - Re-export: `kanban/web/src/components/AdvancedSection.tsx`
   - Unit Tests: `kanban/web/src/ui/AdvancedSection.test.tsx` and `kanban/web/src/components/__tests__/AdvancedSection.test.tsx`
   - Features: Full WAI-ARIA (`aria-expanded`, `aria-controls`, `aria-labelledby`), keyboard navigation (`Enter` and `Space`), active overrides counter pill (`N custom settings active`), auto-expansion on error (`hasErrors={true}`), clean CSS transitions, and zero inline styles.
   - Test Coverage: 100% statement, 97.2% branch, 100% function, 100% line coverage (exceeds >=95% mandate).

3. **`AuthCardEditorDrawer.tsx` Progressive Disclosure Refactor:**
   - Inverted disclosure corrected: Core identity and connection parameters (`Display Name`, `Provider Kind`, `Enabled` switch, `Issuer URL`, `Client ID`, `Client Secret`) are always visible in the default flow.
   - Advanced settings collapsed: `Slug`, `Button Subtitle`, `Card Icon Preset`, `Auto-provision Users`, `Allowed Email Domains`, `Access Policy`, `Scopes`, `Token Auth Endpoint`, and Google JSON importer are housed inside `<AdvancedSection defaultOpen={false}>`.
   - Auto-derived slug: Automatically generates a kebab-case slug from the Display Name until explicitly edited by the user.
   - Inline styles purged: All six inline style blocks replaced with semantic classes in `kanban/web/src/features/admin-auth/adminAuth.css`.
   - Regressions: 0. All 45 tests in `AuthCardEditorDrawer.test.tsx` pass cleanly.

4. **Forensic Evidence & Specialist Reviews:**
   - UI Specialist Review: `docs/qa/KAN-319/ui-specialist-review.md` (APPROVED)
   - API Specialist Review: `docs/qa/KAN-319/api-specialist-review.md` (APPROVED)
   - Playwright E2E Log: `docs/qa/KAN-319/playwright-advanced-disclosure.txt`
   - Vitest Unit Test Log: `docs/qa/KAN-319/unit-test-results.txt`
   - Build Verification Log: `docs/qa/KAN-319/build-check.txt`
   - Git Diff Patch: `docs/qa/KAN-319/git-diff.patch`
   - Manifest Checksum: `docs/qa/KAN-319/changed-files-manifest.txt`

5. **Responsive Visual Screenshots (`docs/qa/KAN-319/screenshots/`):**
   - `1440x900-desktop-light-collapsed.png` (Desktop 1440x900 Light collapsed default)
   - `1440x900-desktop-dark-expanded.png` (Desktop 1440x900 Dark expanded with overrides)
   - `768x1024-tablet-collapsed.png` (Tablet portrait 768x1024 collapsed)
   - `390x844-mobile-portrait-expanded.png` (Mobile portrait 390x844 expanded)
   - `844x390-mobile-landscape-collapsed.png` (Mobile landscape 844x390 collapsed)

---

## 3. Verification Instructions for Reality Checker

1. Confirm git diff: `git diff main --stat`
2. Run unit test suite: `COVERAGE_INCLUDE="src/ui/AdvancedSection.tsx,src/components/AdvancedSection.tsx" pnpm --dir kanban/web exec vitest run src/components/__tests__/AdvancedSection.test.tsx src/ui/AdvancedSection.test.tsx src/features/admin-auth/AuthCardEditorDrawer.test.tsx --coverage`
3. Run typography/dashes linter: `uv run python -m scripts.check_no_dashes --all`
4. Verify checksum manifest: `cd docs/qa/KAN-319 && sha256sum -c changed-files-manifest.txt`
5. Inspect screenshots in `docs/qa/KAN-319/screenshots/`
