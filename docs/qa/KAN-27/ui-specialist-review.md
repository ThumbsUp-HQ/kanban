# UI/UX Specialist Review: KAN-27

## Audit Metadata
- Ticket ID: KAN-27 ([KB-P3-AUDIT-21])
- Title: Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan27-rc1-0fa848cb`
- Target Branch: `fix/KAN-27-rc1`
- Base Commit: `5998e9ab`
- Head Commit: `d61b35d0`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates the frontend user experience, interaction flows, accessibility (WCAG AA), modal ergonomics, design token adherence, CSP compliance, and live visual artifact verification for ticket KAN-27 ([KB-P3-AUDIT-21]) on branch `fix/KAN-27-rc1` (commit `d61b35d0`).

The ticket implements self-service external identity linking directly on the `/settings/profile` page with comprehensive error handling, AAL2 step-up support, and zero-CSP violations:
1. **`+ Connect <Provider>` Provider Buttons (`PersonalSettingsPage.tsx`):**
   - Fetches enabled public auth cards (`GET /api/v1/auth/cards`), filters out `LOCAL_ADMIN` and already-linked identities, and renders distinct `+ Connect <Provider>` buttons (`data-testid="connect-provider-<slug>"`).
   - OIDC and OAuth2 providers invoke `startLinkIdentity(card.slug)`. If `AAL2_REQUIRED` or `AAL2_STALE` is encountered, the component intercepts the challenge, prompts for secondary authentication, and automatically resumes linking before navigating to the upstream `authorize_url`.
   - On successful callback return, the component parses `?linked=<slug>`, renders a success alert (`[data-testid="identity-linked-banner"]`), invalidates `['myIdentities']`, and strips URL parameters cleanly via `window.history.replaceState`.
   - On error or conflict, parses `?link_error=<code>` (such as `409 IDENTITY_ALREADY_LINKED`), rendering a high-contrast dismissible error banner (`[data-testid="identity-link-error-banner"]`).
2. **Accessible LDAP Linking Modal (`data-testid="ldap-credentials-modal"`):**
   - When connecting an LDAP provider, renders an accessible modal dialog prompting for LDAP username and password.
   - Includes full keyboard navigation, `Escape` key dismissal when not submitting, accessible labels, clear validation errors, and focus management.
   - Seamlessly handles AAL2 step-up prompts before completing LDAP credential verification.
3. **Empty State & Server Admin Ergonomics:**
   - When no external login providers are enabled in the workspace, renders a clear explanatory notice.
   - For Server Administrators, renders an accessible navigation link directly to the Auth Studio (`Configure Providers in Admin Auth Studio ->` linking to `/admin/auth`).
4. **Security & CSP Invariants:**
   - 0 inline `style={...}` JSX attributes (`style-src 'self'`).
   - 100% canonical CSS design tokens (`cssTokensAudit.test.ts` passes 4/4).
   - Strict ASCII hyphens (-), zero em/en-dashes.
5. **RC1 Live-QA Remediation Verification:**
   - Single-head migration `p4_23_oidc_link_intent_fk` corrected the foreign key reference from `principals(id)` to `identity_link_intents(id)`.
   - Proved zero FK constraint failures during real fullstack ASGI POST `/api/v1/auth/identities/link/start`.
   - Verified session preservation (@alice, aal_level=1) and duplicate conflict rejection (@admin, IDENTITY_ALREADY_LINKED).

---

## Ergonomics & Developer Experience Audit

### 1. Identity Linking Flow & Visual State
- Connected identities display provider icons, display names, external usernames/emails, creation timestamps, and accessible `Unlink` buttons with confirmation dialogs.
- Available providers display in a dedicated card strip with tactile hover states and clear visual distinction between OIDC/OAuth2 redirect flows and LDAP in-page modal flows.

### 2. URL State Hygiene
- Search query parameters (`?linked=<slug>` and `?link_error=<code>`) are immediately consumed on mount, displayed in accessible alerts, and scrubbed from the browser address bar without triggering full page reloads, preserving bookmark and navigation cleanliness.

### 3. Step-Up Authentication UX
- High-privilege operators (administrators or users with enrolled MFA) attempting to link a new external identity are seamlessly guided through AAL2 step-up re-authentication before sensitive provider linking executes, eliminating silent authorization drops.

### 4. Live Visual & Screenshot Artifact Verification
All 6 Playwright visual proof artifacts in `docs/qa/KAN-27/screenshots/` were audited:
- `live-kan27-connect-buttons-desktop-dark.png`: Verified dark mode contrast (>= 4.5:1), button spacing (8px gap), and zero text clipping.
- `live-kan27-connect-buttons-desktop-light.png`: Verified light mode breathable padding (16px/24px) and circular provider badges.
- `live-kan27-connect-buttons-mobile-light.png`: Verified mobile viewport responsive wrapping and >= 44x44px touch targets.
- `live-kan27-empty-providers-desktop-light.png`: Verified empty state message typography and accessible link to `/admin/auth`.
- `live-kan27-ldap-modal-desktop-dark.png`: Verified dark mode modal backdrop blur, accessible labels, input contrast, and button hierarchy.
- `live-kan27-ldap-modal-desktop-light.png`: Verified light mode modal alignment, keyboard focus rings, and action button contrast.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes added across all components.
- All styles leverage canonical CSS classes in `PersonalSettingsPage.css`.
- `cssTokensAudit.test.ts` passes 4/4 tests cleanly.

### 2. Static Analysis & Type Safety
- `pnpm --dir kanban/web exec tsc -b --noEmit`: Clean (0 errors).
- `pnpm --dir kanban/web exec eslint . --max-warnings 0`: Clean (0 errors).
- `uv run ruff check .` and `uv run ruff format --check .`: Clean (0 errors).
- `uv run mypy`: Clean (0 errors across 1099 source files).
- `uv run lint-imports`: Clean (2 kept, 0 broken).

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).
- Verified clean via `python3 -m scripts.check_no_dashes --all`.

### 4. Test Coverage & Verification
- 66/66 Vitest unit tests passing in `PersonalSettingsPage.test.tsx` (7.28s).
- `PersonalSettingsPage.tsx` coverage: 98.39% Statements, 95.43% Branch, 99.00% Functions, 100% Lines (all >= 95%).
- 292/292 Pytest backend tests passing in `kanban/tests/auth/`, with `auth_identities.py` achieving 95% coverage.
- Migration lifecycle test (`test_p4_23_oidc_link_intent_fk_migration.py`) passed upgrade -> downgrade -> upgrade cycle on PostgreSQL 16.
- Real PostgreSQL ASGI E2E lifecycle test (`test_identity_linking_real_pg_e2e.py`) passed zero-mock end-to-end verification.

---

## Final Verification Checklist

1. [x] `+ Connect <Provider>` button rendering and filtering verified
2. [x] OIDC/OAuth2 redirect initiation with `Set-Cookie` browser binding verified
3. [x] AAL2 conditional requirement and step-up challenge interception verified
4. [x] Accessible LDAP credentials modal with keyboard navigation verified
5. [x] Empty state notice and Server Admin link to `/admin/auth` verified
6. [x] `?linked` and `?link_error` URL parsing and `replaceState` cleanup verified
7. [x] Zero inline `style={...}` JSX attributes (100% CSP compliant)
8. [x] 100% canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
9. [x] Strict ASCII hyphenation verified (0 em/en-dashes across repo and wiki)
10. [x] Frontend test suite passes: 66 Vitest tests passing with 98.39% statements and 95.43% branch coverage
11. [x] Backend test suite passes: 292 Pytest tests passing with 95% coverage on `auth_identities.py`
12. [x] Visual evidence verified across 6 annotated desktop, mobile, dark, and light screenshots

---

## Verdict & Certification
STATUS: APPROVED

All frontend ergonomics, modal accessibility, step-up authentication handling, design token contracts, visual artifacts, and test coverage for KAN-27 RC1 have been verified and certified. Ready for dual specialist signoff and coordinator merge into `main`.
