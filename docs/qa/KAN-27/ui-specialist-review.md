# UI/UX Specialist Review: KAN-27

## Audit Metadata
- Ticket ID: KAN-27 ([KB-P3-AUDIT-21])
- Title: Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-27`
- Target Branch: `main`
- Merged HEAD SHA: `23ae056d`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates frontend user experience, interaction flows, accessibility (WCAG AA), modal ergonomics, design token adherence, CSP compliance, and zero-mock live container screenshot artifacts for ticket KAN-27 ([KB-P3-AUDIT-21]) on `main` (commit `23ae056d`).

The ticket implements self-service external identity linking directly on the `/settings/profile` page with comprehensive error handling, AAL2 step-up support, zero-CSP violations, and verified single-head migration `p4_23_oidc_link_intent_fk`:
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
   - When no external login providers are enabled in the workspace, renders a clear explanatory notice: `"No external identity providers (OIDC, OAuth2, LDAP) are currently enabled in this workspace."`.
   - For Server Administrators, renders an accessible navigation link directly to the Auth Studio (`Configure Providers in Admin Auth Studio ->` linking to `/admin/auth`).
4. **Security & CSP Invariants:**
   - 0 inline `style={...}` JSX attributes (`style-src 'self'`).
   - 100% canonical CSS design tokens (`cssTokensAudit.test.ts` passes 4/4).
   - Strict ASCII hyphens (-), zero em/en-dashes.
5. **Database Foreign Key Correction (`p4_23_oidc_link_intent_fk`):**
   - Corrected foreign key constraint in `p4_23_oidc_link_intent_fk` so `oidc_auth_requests.link_intent_id` references `identity_link_intents(id)` rather than `principals(id)`.
   - Verified zero FK errors during live POST `/api/v1/auth/identities/link/start`, browser cookie binding, session preservation (@alice, aal_level=1), and duplicate subject collision rejection (@admin).

---

## UI/UX & Live Visual Artifact Verification

All 9 Playwright visual proof artifacts in `docs/qa/KAN-27/screenshots/` were audited:
1. `live-kan27-empty-providers-desktop-light.png`: Light mode empty state notice on `/settings/profile` displaying explanatory notice and direct navigation link to `/admin/auth`.
2. `live-kan27-connect-buttons-desktop-light.png`: Light mode connected identities view displaying available provider buttons (`+ Connect Corp SSO`, `+ Connect Corp LDAP`) with readable typography and clean margins.
3. `live-kan27-connect-buttons-desktop-dark.png`: Dark mode provider buttons with WCAG AA compliant text contrast and intact dark card tokens.
4. `live-kan27-connect-buttons-tablet-light.png`: Tablet viewport (768x1024) responsiveness with wrapped provider button strip.
5. `live-kan27-connect-buttons-mobile-light.png`: Mobile viewport (390x844, scrollWidth = 390) with responsive card stacking and accessible touch targets (>= 44x44px).
6. `live-kan27-ldap-modal-desktop-light.png`: Accessible LDAP credentials modal dialog in light mode with username/password inputs, keyboard focus outlines, and submit/cancel buttons.
7. `live-kan27-ldap-modal-desktop-dark.png`: Dark mode LDAP credentials modal with high-contrast text and dark modal backdrop.
8. `live-kan27-linked-banner-desktop-light.png`: Light mode post-linking confirmation banner (`Account successfully linked (corp-sso).`) and updated identities table displaying provider badge, external email, creation timestamp, and Unlink action.
9. `live-kan27-linked-banner-desktop-dark.png`: Dark mode linked confirmation banner and identities table row with WCAG AA contrast.

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
- `PersonalSettingsPage.tsx` coverage: 98.39% Statements, 95.43% Branch, 99.00% Functions, 100% Lines.
- 292/292 Pytest backend tests passing in `kanban/tests/auth/`, with `auth_identities.py` achieving 95% coverage.
- Migration lifecycle test `test_p4_23_oidc_link_intent_fk_migration.py` passed upgrade -> downgrade -> upgrade cycle on PostgreSQL 16.
- Real PostgreSQL ASGI E2E lifecycle test `test_identity_linking_real_pg_e2e.py` passed zero-mock end-to-end verification.

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
12. [x] Visual evidence verified across 9 desktop, tablet, mobile, dark, light, and modal screenshots

---

## Verdict & Certification
STATUS: APPROVED

All frontend ergonomics, modal accessibility, step-up authentication handling, design token contracts, and live visual artifacts for KAN-27 on `main` (commit `23ae056d`) have been verified and certified. Ready for Clean-Room Reality-Checker QA.
