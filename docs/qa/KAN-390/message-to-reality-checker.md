# Forensic Verification Proof Packet: KAN-390

## Audited Branch & Visual Proof Summary
- **Branch:** `swarm-b-kan390-b8c878a3`
- **Ticket ID:** KAN-390
- **Feature Summary:** `[KB-MCP-MINT-MODAL-SIMPLIFY] Move Capability Ceiling into Advanced & Merge Key Type + Scope Tier into Single Unified Selector in Mint New MCP Access Key Modal`
- **Visual Proof Artifacts (`docs/qa/KAN-390/screenshots/`):**
  - `01-1440x900-desktop-default-collapsed.png`: 1440x900 Desktop default collapsed state, showing the clean 4-question form structure, single unified selector (`mint-key-scope-type-select`), and live plain-language summary (`mint-key-summary`).
  - `02-1440x900-desktop-advanced-expanded.png`: 1440x900 Desktop with Advanced Capability & Network Restrictions expanded, revealing Capability Ceiling (`capability-preset-select`) directly above granular bit toggles.
  - `03-1024x768-laptop-collapsed.png`: 1024x768 Laptop compact viewport, verifying clean alignment and responsive scaling.
  - `04-768x1024-tablet-portrait.png`: 768x1024 Tablet Portrait viewport, confirming clear visual hierarchy and non-overflowing summary box.
  - `05-390x844-mobile-portrait.png`: 390x844 Mobile Portrait viewport, verifying mobile touch targets, vertical layout wrapping, and sticky modal actions.
  - `06-844x390-mobile-landscape.png`: 844x390 Mobile Landscape viewport, verifying constrained vertical height with scrollable card content and sticky header/footer.

---

## Scoped Definition of Done Mapping

### 1. Relocate Capability Ceiling into AdvancedSection
- **`kanban/web/src/features/settings/McpAccessStudio.tsx`:**
  - Moved `<label htmlFor="capability-preset-select">Capability Ceiling:</label>` and `<select data-testid="capability-preset-select">` from the primary modal form into `<AdvancedSection title="Advanced Capability & Network Restrictions" testId="advanced-capability-restrictions">` immediately above `Granular Capability Bit Toggles`.
  - Maintained default `capabilityMask` (31) intact when `<AdvancedSection>` is collapsed.
  - Added logic so non-default capability ceiling presets are counted toward `activeOverridesCount`.

### 2. Single Unified Key Type + Scope Tier Selector
- **`kanban/web/src/features/settings/McpAccessStudio.tsx`:**
  - Replaced separate `Key Type` (`mint-owner-kind-select`) and `Scope Tier` (`mint-scope-select`) dropdowns with a single unified selector (`data-testid="mint-key-scope-type-select"`).
  - Structured options into grouped `<optgroup>`s:
    - `For Me (Personal User)`:
      - `personal_user:project` -> `Personal - Single Project` (reveals `mint-project-input`)
      - `personal_user:workspace` -> `Personal - Entire Workspace`
    - `For an Automated Bot / CI (Service Bot)`:
      - `service_bot:project` -> `Service Bot - Single Project` (reveals `mint-project-input`)
      - `service_bot:workspace` -> `Service Bot - Entire Workspace`
      - `service_bot:global` -> `Service Bot - Server / Global` (rendered strictly when `isServerAdmin` is true)
  - When switching between options, `mint-project-input` visibility dynamically toggles, and form submission sends exact `{ owner_kind, scope_tier, allowed_projects }`.

### 3. Reorganize Modal into 4 Plain-English Questions
- **`kanban/web/src/features/settings/McpAccessStudio.tsx` & `McpAccessStudio.css`:**
  - Numbered and structured the modal around 4 clear questions:
    1. **What is the key name?** (`mint-label-input`)
    2. **Who is this key for & what can it access?** (`mint-key-scope-type-select` + conditional `mint-project-input`)
    3. **What can it do?** (`mint-surface-select`, `mint-expiry-select`, collapsed `<AdvancedSection>`)
    4. **Live Plain-Language Key Summary** (`data-testid="mint-key-summary"`): Rendered directly above `.kb-mcp-form-actions`, dynamically answering all 4 questions in clear natural language (e.g., `Key "CI Agent Token" for Service Bot can access Project DEMO and use Agent tools (Full / All Capabilities).`).

### 4. Preserved KAN-382 Modal Layout & Scrolling
- Maintained sticky header, sticky footer (`.kb-mcp-form-actions`), and max-height containment from KAN-382.
- Verified that expanding `<AdvancedSection>` activates smooth vertical scrolling within the modal card while keeping header and submit actions pinned.

### 5. Automated Tests & Quality Invariants
- **Unit & Component Tests:**
  - `McpAccessStudio.test.tsx`: 55 passed (99.09% statement, 96.27% branch, 98.94% function, 99.50% line coverage).
  - `McpAccessStudioModalScroll.test.tsx`: 9 passed.
  - `McpUnifiedStudio.test.tsx`: 24 passed.
  - `formInputsA11y.test.tsx`: 16 passed.
  - Raw coverage and output recorded in `docs/qa/KAN-390/unit-test-results.txt`.
- **E2E Playwright Visual Tests:**
  - `kanban/web/e2e/qa/kan-390-mint-modal-simplify.spec.ts`: 6 tests covering 6 viewports, producing all required visual proof screenshots.
- **Static Checks & Build:**
  - `pnpm --dir kanban/web typecheck` (0 errors).
  - `pnpm --dir kanban/web lint` (0 warnings).
  - `pnpm --dir kanban/web build` (clean Vite bundle).
  - `uv run python -m scripts.check_no_dashes --all` (0 violations).
  - Logs preserved in `docs/qa/KAN-390/build-check.txt`.
- **Specialist Reviews:**
  - `docs/qa/KAN-390/api-specialist-review.md`: APPROVED (N/A - pure frontend form simplification).
  - `docs/qa/KAN-390/ui-specialist-review.md`: APPROVED (UI/UX design review across all viewports).

---

## Verification Commands for Reality-Checker
```bash
# 1. Verify sha256 checksums across all artifacts
sha256sum -c docs/qa/KAN-390/changed-files-manifest.txt

# 2. Verify zero em-dash / en-dash violations
uv run python -m scripts.check_no_dashes --all

# 3. Verify unit tests and coverage
pnpm --dir kanban/web test -- --run src/features/settings/__tests__/McpAccessStudio.test.tsx src/features/settings/__tests__/McpAccessStudioModalScroll.test.tsx

# 4. Verify TypeScript and Linting
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
```
