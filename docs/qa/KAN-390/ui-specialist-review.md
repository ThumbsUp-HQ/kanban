# UI & UX Architecture Specialist Gate Review: KAN-390

## Review Overview
- **Ticket ID:** KAN-390
- **Feature Name:** [KB-MCP-MINT-MODAL-SIMPLIFY] Move Capability Ceiling into Advanced & Merge Key Type + Scope Tier into Single Unified Selector in Mint New MCP Access Key Modal
- **Auditor Role:** UI & UX Architecture Specialist
- **Specification:** [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](file:///home/adamoutler/kanban/docs/ARCHITECTURE_AND_PRODUCT_SPEC.md) Section 3 (Multi-Surface MCP Architecture) & Section 6.1 (Ergonomics, Breathable Spacing, and Responsive Design)
- **Verdict:** APPROVED (PASS)

---

## 1. User Interface Surfaces Audited

1. **Mint New MCP Access Key Modal (`kanban/web/src/features/settings/McpAccessStudio.tsx`):**
   - **4-Question Structure:** The modal is cleanly organized around 4 plain-English questions:
     1. `1. What is the key name?` (`mint-label-input`) with auto-focus and clear placeholder `e.g. CI Agent Token`.
     2. `2. Who is this key for & what can it access?` Single unified selector (`mint-key-scope-type-select`) replacing the redundant and confusing separate `Key Type` (`mint-owner-kind-select`) and `Scope Tier` (`mint-scope-select`) dropdowns. Grouped with semantic `<optgroup>` tags:
        - `For Me (Personal User)`: Personal - Single Project, Personal - Entire Workspace.
        - `For an Automated Bot / CI (Service Bot)`: Service Bot - Single Project, Service Bot - Entire Workspace, Service Bot - Server / Global (server admins only).
        - Selecting single project cleanly reveals `Allowed Project` input (`mint-project-input`) with datalist autocomplete.
     3. `3. What can it do?` Groups `Target Surface` (`mint-surface-select`), `Expiration` (`mint-expiry-select`), and collapsed `<AdvancedSection>`.
     4. `4. Key Summary` Live plain-language key summary (`data-testid="mint-key-summary"`) answering all 4 questions in real time.
   - **Capability Ceiling Relocation:** Moved `Capability Ceiling` (`capability-preset-select`) from the main visible form into `<AdvancedSection title="Advanced Capability & Network Restrictions">` immediately above `Granular Capability Bit Toggles`. Default `capabilityMask` (31) remains intact when collapsed, and non-default capability masks cleanly increment `activeOverridesCount`.
   - **Modal Scroll & Sticky Footers (KAN-382 Compliance):** Sticky header (`.kb-snippet-modal-header`) and actions footer (`.kb-mcp-form-actions`) remain permanently reachable without scroll traps across desktop, tablet, and mobile viewports.

2. **Visual Ergonomics & Token Alignment (`McpAccessStudio.css`):**
   - Applied consistent typography, subtle raised background (`var(--bg-surface-raised, #161b22)`), border subtle (`var(--border-subtle, #30363d)`), and breathable padding on `.kb-mcp-key-summary`.
   - Accessible numbering badge `.kb-mcp-question-num` with accent primary color highlighting step progression.

---

## 2. Responsive Viewport Verification (Playwright Screenshots)

The following 6 multi-viewport forensic screenshots in `docs/qa/KAN-390/screenshots/` demonstrate complete compliance:

1. **`01-1440x900-desktop-default-collapsed.png` (1440x900 Desktop Light):**
   - Default modal appearance showing the 4-question progressive layout, single unified selector set to `Service Bot - Single Project`, revealed Allowed Project input with `KAN`, collapsed Advanced section, and live summary: `Key "CI Production Bot" for Service Bot can access Project KAN and use Agent tools (Standard Developer Agent).`
2. **`02-1440x900-desktop-advanced-expanded.png` (1440x900 Desktop Dark):**
   - Dark theme validation with `<AdvancedSection>` expanded. Shows `Capability Ceiling` selector immediately above granular bitmask matrix, with live summary dynamically updating to `(Read-Only Agent)` when preset 1 is selected.
3. **`03-1024x768-laptop-collapsed.png` (1024x768 Laptop Compact):**
   - Clean rendering on standard laptop displays. All 4 questions and live summary fit comfortably within the bounded viewport.
4. **`04-768x1024-tablet-portrait.png` (768x1024 Tablet Portrait):**
   - Tablet portrait orientation showing responsive alignment, readable optgroup styling, and centered dialog presentation.
5. **`05-390x844-mobile-portrait.png` (390x844 Mobile Portrait):**
   - Mobile touch layout with >=44px touch targets on form controls, single-column flow, and sticky action buttons reachable above navigation bars.
6. **`06-844x390-mobile-landscape.png` (844x390 Mobile Landscape):**
   - Extreme vertical constraint test (390px viewport height). Modal card clamps within `calc(100vh - 40px)`, engaging smooth internal vertical scrolling with sticky header and footer reachable.

---

## 3. Ergonomics, Accessibility & Boundary Verification
- **Keyboard Navigation & Esc Dismissal:** Verified ESC key dismissal and full keyboard tab accessibility through all form controls.
- **Accessible Labelling:** All inputs and select elements have programmatically linked `<label>` elements and aria attributes.
- **Zero Em-Dashes/En-Dashes:** Strictly plain ASCII hyphens across all UI text, tooltips, and option labels.
- **Theme Consistency:** Verified both light and dark theme token alignment without background bleed or color clashes.

---

## 4. Certification
The simplified 4-question modal structure and relocated Capability Ceiling provide a drastically superior, intuitive user experience while maintaining 100% security boundary fidelity and backwards compatibility. Approved for merge.
