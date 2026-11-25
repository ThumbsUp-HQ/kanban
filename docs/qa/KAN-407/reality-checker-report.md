# Reality-Checker Forensic QA Report: KAN-407 (Round 2)

- **Ticket:** `KAN-407` (`[SLICE-1-P2][KB-AUTH-SIMPLIFY] Phase 2: Simplify Multi-Card Auth & RBAC UI (AD/OIDC Presets, Disclosure & Backend Wiring)`)
- **Parent Epic:** `KAN-405`
- **Next Phase:** `KAN-408`
- **Feature Branch:** `feat/KAN-407-slice1-auth-simplify` (base `8c6a77e2`, head `fdaeba1c` per coordinator)
- **Worktree Audited:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan407-1e894da6`
- **QA Packet Audited:** `/home/adamoutler/kanban/docs/qa/KAN-407/`
- **Audit Mode:** Clean-room passive forensic audit (read-only sandbox; `sha256sum -c changed-files-manifest.txt` and `python3 scripts/check_no_dashes.py --all` pre-verified exit `0` by Coordinator)
- **Date:** 2026-11-25
- **Grade:** **A**
- **Verdict:** **READY**

---

## 1. Round-1 Remediation Verification

| Round-1 Check / Remediation Item | Code & CSS Evidence Verified | Visual Screenshot Evidence Verified | Status |
| :--- | :--- | :--- | :---: |
| **Active preset button WCAG 2.2 AA contrast & hover specificity** | `kanban/web/src/features/admin-auth/adminAuth.css` lines 600-605: `.auth-preset-btn.auth-preset-btn--active, .auth-preset-btn.auth-preset-btn--active:hover` sets `background: var(--accent-primary); color: var(--accent-primary-fg); border-color: var(--accent-primary);`. | `01-desktop-1440x900-light.png`: `Active Directory (sAMAccountName)` preset button renders with solid royal-blue background and crisp white text/icon. | **PASS** |
| **Break-Glass modal danger CTA & card-row Delete button isolation** | `adminAuth.css` lines 1198-1213 defines dedicated `.auth-modal-btn-danger` (`background: var(--bg-danger, #dc2626); color: #ffffff;`), while `.auth-btn-danger` (lines 294-301) preserves outlined secondary styling (`color: var(--danger-fg, #b91c1c); border-color: var(--danger-fg);`). `AuthStudioPage.tsx` line 1130 applies `auth-modal-btn-danger` to `confirm-break-glass-action`. | `02-desktop-1440x900-dark.png`: `Confirm & Disable` renders solid crimson red (`#dc2626`) with crisp white text; background card-row `Delete` remains clean dark outlined secondary. `05-mobile-portrait-390x844.png`: card-row `Delete` buttons render clean outlined secondary styling. | **PASS** |
| **Pytest clean coverage output & 0 warnings** | `docs/qa/KAN-407/unit-test-results.txt` lines 1-83: full term-missing coverage table across `kanban/api/v1/admin/*` and `kanban/auth/*`, `69 passed in 36.56s`, zero warnings. (`KAN-407` modified 0 Python files.) | N/A | **PASS** |
| **Specialist reviews & SHA-256 manifest parity** | `api-specialist-review.md` (`APPROVED`) and `ui-specialist-review.md` (`APPROVED`); `changed-files-manifest.txt` and `SHA256SUMS.txt` list all 11 files identically (pre-verified exit `0` by Coordinator). | All 5 PNGs inspected directly via `read_file`. | **PASS** |

---

## 2. Implementation & Security Invariant Verification

Inspected directly in worktree `swarm-b-kan407-1e894da6` (`AuthStudioPage.tsx`, `AuthCardEditorDrawer.tsx`, `adminAuthApi.ts`, `adminAuth.css`, `RbacPolicyBuilder.tsx`, `RbacPolicyBuilder.css`, `02-implemented-changes.md`, and `git-diff.patch`):

1. **Exclusive Tab Rendering & Single-Mount Isolation (`AuthStudioPage.tsx`):**
   - Header CTA (lines 736-759) renders `+ Add auth card` only when `activeTab === 'cards'`, `+ Add Local User` only when `activeTab === 'users'`, and `null` on `roles`.
   - Tab panels (lines 879-1039) use strictly mutually exclusive `{activeTab === 'cards' && ...}`, `{activeTab === 'users' && ...}`, and `{activeTab === 'roles' && ...}` blocks. Duplicate `#panel-roles` mount is eliminated and `#panel-users` is unmounted on the `roles` tab.
2. **Client-Side Break-Glass Anti-Lockout Safeguard (`AuthStudioPage.tsx`, `adminAuthApi.ts`):**
   - `isSoleActiveAdminCard(card, allCards)` in `adminAuthApi.ts` (lines 376-392) detects sole active admin cards (including `LOCAL_ADMIN` with no active external `OIDC`/`OAUTH2`/`LDAP` fallback).
   - `handleToggleEnabled` (lines 1707-1713 in diff / 333+ in file) and `handleDeleteCard` open `[data-testid="break-glass-warning-dialog"]` (`AuthStudioPage.tsx` lines 1060-1147) detailing the 3-layer anti-lockout safeguards before sending mutating requests.
3. **Zero `input[type="password"]` & Autofill Suppression (`AuthCardEditorDrawer.tsx`, `adminAuth.css`):**
   - Both OIDC Client Secret (lines 1050-1065) and LDAP Bind DN Password (lines 1138-1153) use `type="text"`, `className="auth-editor-input kb-masked-api-key"` (`-webkit-text-security: disc`), `autoComplete="off"`, `data-1p-ignore="true"`, `data-lpignore="true"`, `data-bwignore="true"`, and `data-form-type="other"`. Zero `input[type="password"]` elements exist in `AuthCardEditorDrawer.tsx`.
4. **Backend Wiring, Validation & Keepalive (`AuthCardEditorDrawer.tsx`):**
   - `is_enabled: isEnabled` is wired in `constructPayload()` (line 619), edit `UpdateAuthCardPayload` (line 680), and create `CreateAuthCardPayload` (line 698).
   - `[data-testid="oidc-localhost-warning"]` (lines 1006-1014) renders when `window.location.hostname` or `origin` is `localhost` or `127.0.0.1`.
   - Client-side CA PEM validation (lines 551-553, 763, 1765-1767) enforces `-----BEGIN CERTIFICATE-----` and surfaces errors inside `<AdvancedSection>` (`hasAdvancedErrors`).
   - `useAal2DirtyKeepalive(isDirty)` (lines 4, 227-284) extends WebSudo during active drawer edits without false-dirty mount state.
5. **RBAC Bulk Quick-Selectors & Auto-Slug (`RbacPolicyBuilder.tsx`):**
   - `handleBulkCategoryPermissions` (lines 244-304) powers `Select All`, `Clear All`, and `Read-Only` buttons across Workspace, Issue, and Field fieldsets (lines 445-600) via `PUT /api/v1/admin/rbac/roles/permissions:batch`.
   - `handleRoleNameChange` / `handleRoleSlugChange` (lines 317-329) auto-generates slugs with `slugManuallyEdited` override preservation.
6. **Scope, Migration & Overlap Guard Invariants:**
   - `PersonalSettingsPage.tsx` has 0 lines modified in `git-diff.patch`.
   - 0 Python files and 0 Alembic migrations modified; `Depends(require_admin_aal2)` remains intact across all `/api/v1/admin/*` routes.

---

## 3. Multi-Viewport Visual Inspection (All 5 Screenshots)

Every PNG in `docs/qa/KAN-407/screenshots/` was visually inspected directly via `read_file`:

1. `01-desktop-1440x900-light.png`: Add Authentication Card drawer over Auth Studio in light mode. `Active Directory (sAMAccountName)` active preset has crisp white text on royal blue; `Bind DN Password` displays disc-masked bullets; `Optional & Advanced Settings` shows `3 custom settings active` badge; zero clipping.
2. `02-desktop-1440x900-dark.png`: Dark mode Break-Glass Anti-Lockout Warning modal over `Local Administrator` card row. High-contrast modal header, 3-layer safeguard list, crisp `Cancel` secondary button, and solid red `Confirm & Disable` CTA (`auth-modal-btn-danger`). Background `Delete` button uses subtle outlined styling.
3. `03-desktop-1024x768.png`: `Roles & Permissions` tab with single `RbacPolicyBuilder` mount, no `+ Add Local User` button, no `#panel-users`, and unobstructed `Select All`, `Clear All`, `Read-Only` toolbars across Workspace (8), Issue (10), and Field (12) permissions.
4. `04-tablet-portrait-768x1024.png`: Edit `Google Workspace OIDC` drawer displaying copyable `Authorized Redirect URI`, yellow `[data-testid="oidc-localhost-warning"]` callout for `http://127.0.0.1:18407`, encrypted `Client Secret` placeholder (`dek_kid: dek-oidc`), and `Replace Stored Secret` checkbox.
5. `05-mobile-portrait-390x844.png`: Mobile portrait Auth Studio with `Sudo 14:50 Lock` pill visible, wrapped title row (`flex-wrap: wrap`) keeping `Documentation ->` inside viewport bounds, stacked provider cards with `HEALTHY` latency badges, toggles, `Edit`, and clean outlined `Delete` buttons with zero horizontal overflow.

---

## 4. Metric, Timing & Handoff Parity Audit

Cross-checked `unit-test-results.txt`, `build-check.txt`, `message-to-reality-checker.md`, `api-specialist-review.md`, `ui-specialist-review.md`, `docs/workouts/slice-1-auth-rbac/02-implemented-changes.md`, and Kanban ticket comments:

| Metric / Artifact | `unit-test-results.txt` / `build-check.txt` | `message-to-reality-checker.md` | `api-specialist-review.md` | `ui-specialist-review.md` | `02-implemented-changes.md` | Parity |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Backend Pytest** | `69 passed in 36.56s` | `69 passed in 36.56s` | `69 tests passed`, `36.56s` | `69 tests`, `36.56s` | `69 passed in 36.56s` | **1:1** |
| **Frontend Vitest** | `122 passed` (`8` + `59` + `55`) in `10.13s`, 0 `act(...)` warnings | `122 passed in 10.13s`, 0 warnings | `122 tests passed in 10.13s` (`55`, `59`, `8`) | `122 tests`, `10.13s` | `122 tests passed in 10.13s` | **1:1** |
| **Vitest Coverage** | Combined `99.02%` Stmts / `95.76%` Branch / `100%` Funcs / `99.8%` Lines (Drawer `95.57%`, Studio `95.68%`, RBAC `97.59%`) | Exact match (`99.02%` / `95.76%` / `100%` / `99.8%`) | Exact match (`95.76%`, `95.57%`, `95.68%`, `97.59%`) | `95.76%` branch coverage | Exact match (`99.02%` / `95.76%` / `100.0%` / `99.80%`) | **1:1** |
| **Build & Static Checks** | `ruff` pass, `mypy` 0 issues (`680 source files`), `check_no_dashes.py` 0 violations, `tsc -b --noEmit` exit 0, `eslint --max-warnings 0` exit 0, `vite build` `1.39s` | Exact match (`680 source files`, `1.39s`) | Exact match (`680 source files`, `1.39s`) | Exact match (`1.39s`) | Exact match (`680 source files`, `1.39s`) | **1:1** |
| **Kanban Handoff Comments** | Verified via `kanban` `read_ticket` on `KAN-405` and `KAN-408`: both initial `Phase 2 Handoff Packet` (`01a21440`) and Rev-2 remediation addendum (`KAN-405#c-01a21471`, `KAN-408#c-01a21471`) are posted. | - | - | - | - | **PASS** |

**Non-Blocking Observations (Informational Only):**
- In `api-specialist-review.md`, two endpoint labels use shorthand/typo (`POST /api/v1/admin/rbac/roles/permissions:batch` and `/api/v1/admin/auth/cards`), whereas the actual verified implementation in `RbacPolicyBuilder.tsx` (lines 213, 273) and `adminAuthApi.ts` (lines 169-275) uses `PUT /api/v1/admin/rbac/roles/permissions:batch` and `/api/v1/admin/auth-cards`.
- The Rev-2 Kanban comments (`KAN-405#c-01a21471` and `KAN-408#c-01a21471`) record `Commit SHA: 76f121d5`, prior to the QA-packet sync commit `fdaeba1c` noted by the Coordinator.
- `02-implemented-changes.md` lives at `docs/workouts/slice-1-auth-rbac/02-implemented-changes.md` as specified by `KAN-407` DoD (not duplicated inside `docs/qa/KAN-407/`).

---

## 5. Final Certification

- **Specification & DoD Compliance:** 100% of `KAN-407` requirements and `KAN-406` Rev-2 dispositions verified against code, tests, screenshots, and specialist sign-offs.
- **Grade:** **A**
- **Verdict:** **READY** (approved for `KAN-407` ticket closure and promotion into `KAN-408` live workout execution).
