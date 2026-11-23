# UI/UX Specialist Review & Verification: KAN-367

- **Ticket ID:** KAN-367
- **Title:** [KB-ADVANCED-DISCLOSURE-01] Auth Card Studio Inverted Advanced Section Refactor and Auto-Derived Slug UX
- **Reviewer Persona:** UI Designer & UX Architect (`@ui-spec`)
- **Target Surfaces:** `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`, `adminAuth.css`, `AuthCardEditorDrawer.test.tsx`
- **Audit Date:** 2026-11-23
- **Verdict:** APPROVED (Grade-A)

---

## 1. Architectural & Ergonomic Assessment

### A. Inverted Progressive Disclosure Correction
In the prior architecture, mandatory authentication fields (`Provider Kind`, `Slug`, `Display Name`) and advanced configurations were disorganized: primary identity fields were trapped in an open-by-default container while complex helper tools like Google JSON Importer occupied primary form space.

Under `KAN-367`:
1. **Primary Form Flow (Always Visible):**
   - 1-Click Provider Presets bar (Google, GitHub, Active Directory, OpenLDAP, Custom SSO).
   - Provider Kind dropdown (`OIDC`, `OAUTH2`, `LDAP`, `LOCAL_ADMIN`).
   - Display Name input (with real-time auto-slug derivation).
   - Enable Card toggle checkbox.
   - Primary Connection parameters:
     - For OIDC/OAuth2: Issuer URL, Client ID, Client Secret (or write-only mask with replace option), Authorized Callback URL display with 1-click clipboard copy, Authorized JS Origin.
     - For LDAP: Server URL, Bind DN, Bind DN Password (or write-only mask with replace option), Base DN.
2. **Advanced Section (Progressive Disclosure):**
   - Collapsed by default via `<AdvancedSection defaultOpen={false}>`.
   - Encapsulates:
     - Slug Identifier (with real-time auto-slug generator indicator).
     - Button Subtext (optional branded sign-in CTA subtitle).
     - Icon Preset selector (shield, google, github, active-directory, ldap, key, lock, globe).
     - Auto-provision Users toggle checkbox.
     - Allowed Email Domains comma-separated input.
     - Access Policy mode selector (`any_user` vs `restricted`).
     - Restricted allowlists / group mappings (Admin allowlist, User allowlist, Admin groups, User groups).
     - Protocol-specific advanced parameters:
       - OIDC: Scopes input, Token Auth Method selector, Google Cloud JSON Importer dropzone & paste modal.
       - LDAP: StartTLS checkbox (auto-locked if scheme is ldap://), User Search Filter, Subject Attribute, Email Attribute, Full Name Attribute, SPKI SHA-256 Pin, CA Certificate PEM.

### B. Auto-Derived Slug UX
- In create mode, as the administrator types the `Display Name`, a URL-safe, kebab-case `Slug Identifier` is derived in real time (e.g. "Google Workspace SSO" -> `google-workspace-sso`).
- Erasing or clearing the display name clears the slug.
- If the administrator manually edits or customizes the slug field, the `slugCustomized` flag activates, preventing further display name changes from overwriting their explicit slug preference.
- In edit mode, the slug is permanently locked (`disabled={true}`) to prevent breaking active OAuth2 redirect URIs and deep links.

### C. Active Overrides Badge & Error Auto-Expansion
- `<AdvancedSection>` receives `activeOverridesCount={activeAdvancedCount}`, rendering a semantic badge (e.g., `N custom settings active`) indicating how many non-default configurations are stored inside the collapsed drawer.
- If a validation failure occurs in any hidden advanced field (e.g. malformed slug regex, subtext exceeding 120 chars, malformed SPKI 64-hex pin), `hasAdvancedErrors` passes `hasErrors={true}` to `<AdvancedSection>`. The section auto-expands so the user immediately sees the field validation error without hunting.

### D. Zero Inline Styles & Theme Compliance
- Strict adherence to zero inline styles (`style={...}`). All visual styling is defined through CSS class declarations in `adminAuth.css` and `AdvancedSection.css` leveraging design system tokens (`var(--accent-primary)`, `var(--bg-canvas)`, `var(--border-subtle)`).
- Tested across light and dark color schemes, with full contrast ratio compliance.

---

## 2. Multi-Viewport & Responsive Layout Audit

The drawer was verified across 5 standard responsive breakpoints (matching artifacts in `docs/qa/KAN-367/screenshots/`):
- **1440x900 Desktop (Dark Mode, Expanded):** `<AdvancedSection>` expands smoothly with scrollable container and clear visual hierarchy.
- **1440x900 Desktop (Light Mode, Collapsed):** Primary connection parameters immediately actionable; advanced parameters cleanly stowed.
- **768x1024 Tablet (Portrait, Collapsed):** Responsive inputs flex to full width with 44px touch targets.
- **390x844 Mobile (Portrait, Expanded):** Focus trap and vertical scroll operate cleanly within viewport bounds.
- **844x390 Mobile (Landscape, Collapsed):** Compact header and drawer height adjust gracefully.

---

## 3. Verdict & Sign-off

- **Accessibility (a11y):** `<details>` / `<summary>` implementation with `role="button"`, `aria-expanded`, `aria-controls`, and keyboard navigation (Enter/Space) conforms to WCAG 2.1 AA.
- **Design System Consistency:** Matches 👍kanban design language.
- **Final Verdict:** APPROVED (Grade-A).
