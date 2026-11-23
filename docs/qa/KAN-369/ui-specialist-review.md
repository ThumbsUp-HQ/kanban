# UI Specialist Review (KAN-369 / KB-ADVANCED-DISCLOSURE-03)

## Overview & UX Architecture Verification

- **Ticket**: KAN-369 (`[KB-ADVANCED-DISCLOSURE-03] Project Settings, Workflow Transition Hooks, and Custom Field Editor Progressive Disclosure`)
- **Modules**: `kanban/web/src/features/settings/`, `kanban/web/src/features/workflows/`, `kanban/web/src/features/custom-fields/`
- **Reviewed By**: UI/UX Specialist (`@ui-spec`)
- **Status**: STATUS: APPROVED

---

## UI Implementation Details & Audit

### 1. `ProjectSettingsPage.tsx` Progressive Disclosure
- **Primary Properties Retained**: Project Name, Key, Description, Visibility, and Workflow state Name/Category/Color remain immediately visible and accessible without interaction.
- **Advanced General Settings (`project-general-advanced-section`)**:
  - Encapsulates Agent-Safe Sequence Numbering (`skip_loaded_seq`) and Auto-Archive Days (`auto_archive_days`).
  - Summarizes non-default values using `activeOverridesCount` badge in the summary bar.
- **Workflow State Advanced Settings (`state-advanced-section`)**:
  - State creation and editing collapses Sort Order, Soft WIP Limit, Hard WIP Limit, and validation alerts behind progressive disclosure.
  - Active WIP Limit chips and badges (`wip-overrides-active-badge`) in the state header summarize configured limits at a glance.
- **Label Advanced Settings (`label-advanced-section`)**:
  - Collapses Exclusive Group configuration (`exclusive_group`) behind `<AdvancedSection>`.
- **Keyboard & Focus Management**: Native `<details>` / `<summary>` implementation ensures keyboard space/enter toggling, proper aria-expanded attributes, and seamless tab order.

### 2. `AttachHookDialog.tsx` Progressive Disclosure
- **Primary Hook Attributes**: Hook Name, Transition Trigger (From State and To State), and Action Type (Hook Kind pills) remain primary.
- **Advanced Hook Execution Settings (`attach-hook-advanced-section`)**:
  - Collapses Failure Policy selector (`fail_closed` / `fail_open_warn`), Approved WebAssembly Module SHA-256 selector, Agent Definition selector with timeout and parameter summary, Allowed Mutable Fields checklist, and Raw Execution Logs preview.
  - Active override badges display when non-default failure policy (`fail_open_warn`), custom Wasm modules, or agent definitions are assigned.
- **Ergonomics**: Maintains breathable 8px/16px/24px spacing grid without modal clipping or vertical overflowing.

### 3. `CustomFieldDefinitionEditor.tsx` Progressive Disclosure
- **Primary Field Attributes**: Field Name, Slug, Flavor, Output Format, and Enabled checkbox remain immediately visible in the Basic settings panel.
- **Advanced Format & Sandbox Script Settings (`custom-field-advanced-section`)**:
  - Collapses Format Configuration Metadata (JSON), Sandboxed Script Source Code editor, and Live Test Execution evaluator.
  - Integrates `hasErrors={Boolean(jsonError ?? testError)}` for automatic expansion when syntax or evaluation errors occur.
  - Displays active overrides badge when custom script source or non-empty JSON metadata is populated.

---

## Responsive Layout & Screenshot Verification

All 5 Playwright responsive viewports verified:
1. `01-desktop-light-project-settings.png` (`1440x900` Desktop Light): Clean surface layout with General Settings advanced section expanded and toggled.
2. `02-desktop-dark-workflow-studio.png` (`1440x900` Desktop Dark): Dark theme high contrast surface elevation displaying workflow transition rules and Attach Hook dialog advanced section.
3. `03-tablet-custom-fields.png` (`768x1024` Tablet Portrait): Tablet reflow showing Custom Field Definition Editor with collapsed/expanded format and script section.
4. `04-mobile-portrait-project-settings.png` (`390x844` Mobile Portrait): Reflowed single-column project settings maintaining clear tap targets and readable badges.
5. `05-mobile-landscape-workflow-hooks.png` (`844x390` Mobile Landscape): Compact landscape viewport maintaining scroll accessibility within the modal without clipping.

---

## Specialist Compliance Gates

- **Whitespace & Ergonomics**: Complies with design-system.css tokens (--bg-surface, --text-primary, --border-subtle, --spacing-*).
- **Accessibility & Contrast**: Meets WCAG 2.1 AA standards; focus rings present; screen-reader accessible summary titles.
- **Zero Inline Styles**: Fully tokenized CSS classes.
- **Zero Em/En-Dashes**: Verified with 0 forbidden dash violations.
- **Unit Test Coverage**: Comprehensive test coverage across all affected components exceeding the 95% threshold.
