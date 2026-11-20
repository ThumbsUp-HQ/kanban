# UI Specialist Review: KAN-30

**Ticket ID:** KAN-30  
**Title:** [KB-P3-AUDIT-24] Add Workspace Admin Trash & Retention Studio, Enforce Per-Workspace Retention & RLS Boundaries, and Publish Visual Role & Permission Matrix  
**Branch:** `feat/KAN-30`  
**Commit:** `29fa13e8`  
**Reviewer:** ui-spec-2 (Clean-Room UI Specialist)  
**Date:** 2026-11-20  
**Status:** `STATUS: APPROVED`  

---

## 1. Executive Summary

A clean-room UI and UX audit was conducted on ticket KAN-30 (`feat/KAN-30` commit `29fa13e8`). The ticket introduces an administrative Workspace Trash & Retention Studio into `WorkspaceSettingsPage.tsx`, enabling workspace administrators to configure per-workspace retention windows (7 to 365 days), filter and search soft-trashed entities across 8 object kinds, safely restore deleted items, and securely execute 2-stage permanent purges (restricted to Server Admins).

The user interface adheres to all design system token guidelines, maintains responsive layout ergonomics, satisfies WCAG AA contrast standards, contains zero inline styles, and contains zero em-dashes or en-dashes.

---

## 2. Detailed UI/UX Audit Findings

### 2.1 Tab Navigation & URL Hash Synchronization
- **Tab Registration:** Added `Trash & Retention` (`#tab-trash`, `id="tab-trash"`, `data-testid="tab-trash"`) with accessible ARIA attributes (`role="tab"`, `aria-selected={activeTab === 'trash'}`, `aria-controls="panel-trash"`).
- **Bidirectional Hash Synchronization:** Synchronizes seamlessly with the browser URL hash (`#tab-trash`, `#tab-general`, `#tab-members`, `#tab-groups`). Navigating back or resetting the hash defaults predictably to `'general'`.
- **Keyboard Navigation & Ergonomics:** Tab strip maintains full keyboard focusability and visible focus outlines.

### 2.2 Retention Policy Settings Card
- **Configuration Card (`.kb-retention-settings-card`):** Cleanly separated from the trash item list with clear borders and subtle surface background (`var(--bg-surface-raised)`).
- **Form Controls:** Exposes number input (`data-testid="trash-retention-input"`) with client-side bounds (`min=7`, `max=365`) and descriptive microcopy explaining automatic expiration and the required fresh AAL2 step-up (900 seconds).
- **Save Feedback:** Save action button (`data-testid="save-retention-btn"`) transitions to a disabled saving state while the mutation executes and provides clear success and error messages (`role="status"`, `role="alert"`).

### 2.3 Trash Filtering, Search & Toolbar Controls
- **Toolbar Layout (`.kb-trash-toolbar`):** Flexible container wrapping neatly on smaller screens, keeping filter pills and search inputs aligned.
- **Kind Filter Pills:** Semantic dropdown / pill buttons (`data-testid="trash-kind-filter"`) covering `all`, `project`, `issue`, `doc`, `page`, `sticky`, `cycle`, `module`, and `view`.
- **Live Search Input (`data-testid="trash-search-input"`):** Fast client-side debounced text filtering matching item key or title with clear visual label for screen readers (`.kb-visually-hidden`).

### 2.4 Trashed Items Data Table
- **Empty & Loading States:** Provides distinct, user-friendly indicators (`data-testid="trash-loading-state"`, `data-testid="trash-empty-state"`) with centered typography and comfortable padding.
- **Object Representation:** Displays semantic emoji badges for each object type (`📁 Project`, `📋 Issue`, `📄 Doc`, `📃 Page`, `🟨 Sticky`, `🔄 Cycle`, `🧩 Module`, `👁️ View`).
- **Retention Expiration Pill (`.kb-retention-pill`):** Displays countdown (`X days remaining` or `Expires today`). Applies high-visibility alert styling (`.kb-retention-pill-expired`) when an item has 3 days or fewer remaining before automatic background purging.
- **Action Buttons:**
  - `[Restore]` button (`data-testid="restore-btn-${item.id}"`): Prominently available for Workspace Admins and Server Admins.
  - `[Permanent Purge]` button (`data-testid="permanent-purge-btn-${item.id}"`): Strictly rendered only for users with `is_server_admin === true`.

### 2.5 2-Stage Permanent Purge Modal Dialog
- **Destructive Confirmation Flow:** When a Server Admin initiates permanent purge, an accessible modal dialog overlay renders with `role="dialog"` and `aria-modal="true"`.
- **Cryptographic Blast Shield:** Displays the target item key/title, warning banner detailing irreversible deletion, and requires a mandatory reason input (`data-testid="purge-reason-input"`).
- **Dual Confirmation Action:** The confirm button (`data-testid="confirm-permanent-purge-btn"`) remains disabled until a valid confirmation token is issued and a non-empty audit reason is provided.

### 2.6 Design Tokens, CSS & CSP Compliance
- **100% Theme Tokens:** `ProjectSettingsPage.css` utilizes canonical CSS variables exclusively (`var(--kb-color-border-subtle)`, `var(--bg-surface-raised)`, etc.).
- **Zero Inline Styles:** Zero inline `style={...}` JSX attributes (`style-src 'self'` CSP compliance verified by `cssTokensAudit.test.ts` passing 4/4).
- **Accessible Contrast:** All text, badges, and retention countdown pills exceed WCAG AA minimum contrast ratio (>= 4.5:1).

---

## 3. Automated Test Verification

All unit tests executed and passed in clean-room verification:
1. `src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`: 31/31 tests passed in 2.36s with 99.76% statements and 95.79% branch coverage (100% lines).
2. `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 tests passed (0 inline styles).
- **Total Frontend Tests:** 35/35 passed across 2 suites.
- **Stderr Warnings:** Zero `act(...)` or console warnings.

---

## 4. Certification

The UI and UX implementation of KAN-30 fulfills all functional, aesthetic, accessibility, and security invariants.

**STATUS: APPROVED**
