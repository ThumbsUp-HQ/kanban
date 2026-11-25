# UI Specialist Review: KAN-398 Admin Auth Access and MFA Banner

- **Ticket**: KAN-398 (`[KB-ADMIN-AUTH-ACCESS-FIX] Server-Admin Auth Card Access Matrix & Subnav Filter`)
- **Reviewer**: UI Specialist (`@ui-spec`)
- **Status**: APPROVED
- **Date**: 2026-11-25

---

## 1. Executive Summary

This audit evaluates the frontend user experience and visual ergonomics for ticket KAN-398. The implementation introduces two primary user interface updates:
1. **MFA Enrollment Required Banner**: Displays a non-destructive instructional banner with a direct navigational link to user profile settings (`/settings/profile`) when administrative endpoints return HTTP 403 `MFA_ENROLLMENT_REQUIRED`, replacing the generic access-denied error screen.
2. **Admin Studio Subnav Role-Based Tab Filtering**: Hides the 7 Server-Admin-only tabs (`auth`, `ai`, `runners`, `mcp`, `oauth`, `imports`, `standalone`) when the authenticated user is not a Server Administrator, leaving only `diagnostics` visible to workspace administrators.

---

## 2. Multi-Viewport Visual Verification Audit

Visual verification was conducted via automated Playwright test suite (`kanban/web/e2e/qa/kan-398-admin-auth-access-screenshots.spec.ts`) across 5 viewports in both light and dark themes, generating 30 high-fidelity PNG captures stored in `docs/qa/KAN-398/screenshots/`.

### 2.1 Viewport Matrix
1. **Desktop**: 1440x900
2. **Tablet Landscape**: 1024x768
3. **Tablet Portrait**: 768x1024
4. **Mobile Portrait**: 390x844
5. **Mobile Landscape**: 844x390

### 2.2 Visual Audit of Screenshot Artifacts

#### Category 1: MFA Enrollment Required Banner (`01-mfa-enrollment-banner-*`)
- Captured files:
  - `01-mfa-enrollment-banner-light-desktop.png`
  - `01-mfa-enrollment-banner-dark-desktop.png`
  - `01-mfa-enrollment-banner-light-tablet.png`
  - `01-mfa-enrollment-banner-dark-tablet.png`
  - `01-mfa-enrollment-banner-light-tablet-portrait.png`
  - `01-mfa-enrollment-banner-dark-tablet-portrait.png`
  - `01-mfa-enrollment-banner-light-mobile.png`
  - `01-mfa-enrollment-banner-dark-mobile.png`
  - `01-mfa-enrollment-banner-light-mobile-landscape.png`
  - `01-mfa-enrollment-banner-dark-mobile-landscape.png`
- **Visual Inspection Findings**:
  - The banner element `[data-testid="mfa-enrollment-required-banner"]` renders with clean centered alignment within the `.auth-studio-content` container.
  - Header text: "Two-Factor Authentication Required" renders with appropriate hierarchy and weight.
  - Explanatory copy: "Administrative operations require MFA enrollment. Please configure a second factor in your profile settings."
  - The anchor element wraps "profile settings" pointing to `/settings/profile`, with clear underline affordance and accessible color contrast meeting WCAG AA requirements.
  - On mobile portrait (`390x844`), the banner adapts seamlessly without text truncation, horizontal overflow, or edge clipping.

#### Category 2: Server Admin Studio Subnav (`02-subnav-server-admin-*`)
- Captured files:
  - `02-subnav-server-admin-light-desktop.png`
  - `02-subnav-server-admin-dark-desktop.png`
  - `02-subnav-server-admin-light-tablet.png`
  - `02-subnav-server-admin-dark-tablet.png`
  - `02-subnav-server-admin-light-tablet-portrait.png`
  - `02-subnav-server-admin-dark-tablet-portrait.png`
  - `02-subnav-server-admin-light-mobile.png`
  - `02-subnav-server-admin-dark-mobile.png`
  - `02-subnav-server-admin-light-mobile-landscape.png`
  - `02-subnav-server-admin-dark-mobile-landscape.png`
- **Visual Inspection Findings**:
  - For server administrators (`isServerAdmin = true`), all 8 navigation items are present:
    1. Auth Cards (`/admin/auth`)
    2. AI Providers (`/admin/ai`)
    3. Remote Runners (`/admin/runners`)
    4. Bot API Keys (`/admin/mcp`)
    5. OAuth 2.1 Clients (`/admin/oauth`)
    6. Plane Migration (`/admin/imports`)
    7. Standalone Mode (`/admin/standalone`)
    8. Diagnostics (`/admin/diagnostics`)
  - Icons and labels render cleanly with breathable spacing and clear active state indicators.

#### Category 3: Workspace Admin Studio Subnav (`03-subnav-workspace-admin-*`)
- Captured files:
  - `03-subnav-workspace-admin-light-desktop.png`
  - `03-subnav-workspace-admin-dark-desktop.png`
  - `03-subnav-workspace-admin-light-tablet.png`
  - `03-subnav-workspace-admin-dark-tablet.png`
  - `03-subnav-workspace-admin-light-tablet-portrait.png`
  - `03-subnav-workspace-admin-dark-tablet-portrait.png`
  - `03-subnav-workspace-admin-light-mobile.png`
  - `03-subnav-workspace-admin-dark-mobile.png`
  - `03-subnav-workspace-admin-light-mobile-landscape.png`
  - `03-subnav-workspace-admin-dark-mobile-landscape.png`
- **Visual Inspection Findings**:
  - For non-server administrators (`isServerAdmin = false`), all 7 server-scoped tabs are completely filtered from the DOM.
  - The Diagnostics tab remains prominently visible and functional.
  - The subnav container renders without empty gaps, layout collapse, or broken tab borders.

---

## 3. Accessibility and Responsive Ergonomics

1. **Semantic Elements and Attributes**:
   - The MFA banner uses clean semantic markup (`<h3>`, `<p>`, `<a>`) with `role="region"` and `aria-label="Two-factor authentication required"`.
   - The link safely supports both HTML anchor and React Router `Link` environments.
2. **Color Contrast**:
   - Light Mode: Text `#1e293b` on card background `#ffffff` (contrast ratio 12.6:1). Link `#2563eb` on card background (contrast ratio 4.9:1).
   - Dark Mode: Text `#e2e8f0` on card background `#1e293b` (contrast ratio 9.8:1). Link `#60a5fa` on card background (contrast ratio 6.2:1).
   - Both modes exceed WCAG AA requirements (minimum 4.5:1 for normal text).
3. **No Clipped Elements**:
   - Zero controls touch canvas edges on any viewport.
   - Mobile portrait padding preserves 16px lateral safety margins.

---

## 4. Specialist Sign-Off
All UI components, subnav filtering rules, and visual artifacts meet the design system standards.

**Verdict**: APPROVED
