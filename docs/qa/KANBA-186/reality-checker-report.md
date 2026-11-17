# Forensic QA Reality-Checker Audit Report: KANBA-186

## Metadata
- **Ticket ID:** KANBA-186
- **Title:** [KB-AUTH-PERSIST] Fix OIDC Session Rollback, Add Keep Me Signed In Persistence, and Remediate Sign-In & Session Accessibility (WCAG 2.2 AA)
- **Module:** `kanban.auth.sessions`, `kanban.auth.oidc`, `database.migrations`, `kanban-web` (`AuthContext.*`, `useSessionGuard.*`, `LoginPage.*`, `Topbar.*`, `LdapLoginForm.*`, `LocalAdminDisclosure.*`, `SecondFactorStep.*`, `auth.css`)
- **Evaluated Commit:** `2b3c84d` (merged into `main`)
- **Auditor:** reality-checker (Passive Forensic QA Gate)
- **Date:** 2026-11-17
- **Overall Grade:** A
- **Verdict:** READY

---

## 1. Reality Check & Scope Validation

### 1.1 UI & Visual Proof Audit
- **Classification:** Full Stack Feature & Remediation (Backend Session/Cookie Lifetimes + Web UI Login & Shell Accessibility).
- **Screenshots Inspected:** Audited all 6 Playwright screenshots in `docs/qa/KANBA-186/screenshots/`:
  - `01-login-remember-me-desktop.png`, `01-login-remember-me-tablet.png`, `01-login-remember-me-mobile.png`:
    - Shows "Keep me signed in on this device" checkbox (`data-testid="login-remember-me-checkbox"`), checked by default, clearly explaining the 30-day absolute / 7-day idle policy.
    - Shows accessible Show/Hide password toggle inside `LdapLoginForm` and `LocalAdminDisclosure` meeting WCAG 2.2 AA target size criteria.
    - Demonstrates responsive card text wrapping preventing truncation at 200% zoom.
  - `02-workspace-reload-persistent-desktop.png`, `02-workspace-reload-persistent-tablet.png`, `02-workspace-reload-persistent-mobile.png`:
    - Shows calm workspace shell after browser reload, with session state preserved without redirecting to `/login`.
    - Shows topbar avatar dropdown featuring the new `Personal Settings` entrypoint (`data-testid="topbar-personal-settings-link"`) alongside preserved administrative links ("System Storage, Backups & Deployment", "Admin Auth Studio", "Admin MCP Keys").
    - Confirms keyboard accessibility (`Escape` returns focus, `ArrowDown`/`ArrowUp` cycles menu items).

### 1.2 Specialist Gates Cross-Validation
- **Dual Specialist Mandate:** Both API and UI specialists must review.
- **API Specialist Review:** `docs/qa/KANBA-186/api-specialist-review.md` present and audited.
  - Reviewer: `api-specialist` (Backend Architect & API Tester Persona).
  - Assessment: Verified linear migration `p4_19_persistent_sessions` chaining from `p4_18_oauth_mcp_scoping`, explicit OIDC transaction commit, unified cookie issuance with `remember_me` lifetimes (30-day `Max-Age` / `Expires`), dual plain-HTTP fallback cookies, and CSRF token stability on `GET /api/v1/auth/session`.
  - Verdict: **APPROVED**.
- **UI Specialist Review:** `docs/qa/KANBA-186/ui-specialist-review.md` present and audited.
  - Reviewer: `ui-specialist` (ArchitectUX & UI Designer Persona).
  - Assessment: Validated centralized `AuthContext`, deep-link preservation in `useSessionGuard`, password visibility controls with volatile DOM/state zeroing in `finally` blocks, keyboard focus return on `Escape`, and WCAG 2.2 AA design token compliance.
  - Verdict: **APPROVED**.

---

## 2. Forensic Proof Packet Inspection (`docs/qa/KANBA-186/`)

1. **`git-diff.patch`**:
   - Matches merged commit `2b3c84d`.
   - Forward database migration `database/migrations/versions/p4_19_persistent_sessions.py` chains from `p4_18_oauth_mcp_scoping` and adds `remember_me` boolean to `sessions` table.
   - `OidcFlow.callback` explicitly commits session transaction before redirecting.
   - `kanban/auth/sessions/cookies.py` implements unified `attach_session_and_csrf_cookies` handling `Max-Age` / `Expires` and plain-HTTP fallbacks.
   - `GET /api/v1/auth/session` reuses valid existing CSRF cookie without redundant `Set-Cookie` headers.
   - Frontend components (`AuthContext.tsx`, `useSessionGuard.ts`, `LoginPage.tsx`, `Topbar.tsx`, etc.) implement session caching, deep-link preservation, password toggles, and keyboard navigation.

2. **`changed-files-manifest.txt`**:
   - Lists 40 modified/created files with verified SHA-256 digests and line counts.

3. **`unit-test-results.txt`**:
   - Backend Pytest: 25 passed in 1.47s (`test_session_persistence.py`, `test_oidc_flow.py`), Exit Code: 0.
   - Frontend Vitest: 51 passed in 1.92s (`cssTokensAudit.test.ts`, `SecondFactorStep.test.tsx`, `Topbar.test.tsx`, `LoginPage.test.tsx`), Exit Code: 0.

4. **`build-check.txt`**:
   - Backend Ruff: All checks passed.
   - Backend Mypy: Success (1047 source files clean).
   - Backend Lint-Imports: 2 contracts kept, 0 broken.
   - Migration Check: `uv run python -m database.migrations.cli check-migrations --static-only`: All 58 migrations valid, single head: `p4_19_persistent_sessions`.
   - Frontend Typecheck: `tsc -b --noEmit` clean.
   - Frontend Lint: `eslint . --max-warnings 0` clean.
   - Frontend Vite Build: Production bundle built in 1.01s.
   - Dash Check: `scripts.check_no_dashes --all` passed with 0 violations.

5. **`contract-sample.json`**:
   - Verified JSON contract demonstrating `login_persistent_true` (with `Max-Age=2592000` and `Expires`), `login_persistent_false` (session cookies), and `get_session_stability_with_existing_csrf` (empty `set_cookie_headers`).

---

## 3. Definition of Done Compliance Matrix

| Requirement | Implementation Evidence | Status |
| :--- | :--- | :---: |
| Forward Migration Mapping | `p4_19_persistent_sessions` chains from `p4_18_oauth_mcp_scoping`; single head verified | PASS |
| OIDC Callback Transaction Commit | Explicit `await session.commit()` in `OidcFlow.callback`; tested in `test_oidc_callback_commits_session_and_survives_reload` | PASS |
| Unified Cookie Issuance | `attach_session_and_csrf_cookies` in `kanban/auth/sessions/cookies.py` | PASS |
| "Keep me signed in" Lifetimes | `Max-Age=2592000` (30 days), 7-day idle timeout; ephemeral cookies when unchecked | PASS |
| Plain-HTTP Fallback Cookies | Sets `kb_session` and `kb_csrf` alongside `__Host-` cookies for non-TLS/local dev | PASS |
| CSRF Token Stability | `GET /api/v1/auth/session` reuses active valid token; zero redundant `Set-Cookie` | PASS |
| Centralized AuthContext & Session Guard | `AuthContext.tsx` wraps root; `useSessionGuard.ts` preserves `?next=` parameter | PASS |
| Show/Hide Password & Volatile Sanitization | Toggle button present; password cleared in `finally` block in `LdapLoginForm` and `LocalAdminDisclosure` | PASS |
| Topbar Avatar Menu Accessibility | Focus return on `Escape`, `ArrowDown`/`ArrowUp` traversal, `Personal Settings` entrypoint | PASS |
| Responsive Text Reflow (200% Zoom) | Auth card buttons wrap cleanly without truncation; verified in screenshot `01` | PASS |
| Dual Specialist Approvals | API Specialist and UI Specialist both issued independent `APPROVED` verdicts | PASS |
| Comprehensive Proof Packet | 6 Playwright screenshots, 25 backend + 51 frontend tests, full build check exit 0 | PASS |

---

## 4. Certification

The forensic proof submitted in `docs/qa/KANBA-186/` provides indisputable, comprehensive evidence of correctness, durable session persistence, forward database schema consistency, and complete UI/UX accessibility.

- **Grade:** A
- **Verdict:** READY
