# Message to Reality-Checker: KANBA-186 ([KB-AUTH-PERSIST])

### Architectural Context & Invariants
- **Forward Migration Mapping:** Per KANBA-189 instructions, `p4_19_persistent_sessions` chains strictly linearly from `p4_18_oauth_mcp_scoping`. The Alembic chain is verified via `uv run kanban-ctl db check-migrations --static-only` and `test_p4_19_persistent_sessions_migration.py`.
- **OIDC Session Rollback Remediation:** Fixed `OidcFlow.callback` by explicitly committing the transaction immediately after `create_after_login`, preventing the rollback upon DB session disposal.
- **Unified Cookie Issuance:** Implemented `attach_session_and_csrf_cookies` in `kanban/auth/sessions/cookies.py`, issuing `Max-Age` + `Expires` when `remember_me=True` and fallback plain-HTTP cookies when operating under direct or proxied plain HTTP.
- **CSRF Token Stability:** `GET /api/v1/auth/session` reuses existing valid CSRF cookies without issuing redundant `Set-Cookie` headers, preventing concurrency races during parallel requests.
- **Accessibility (WCAG 2.2 AA):**
  - Added "Keep me signed in on this device" checkbox (`data-testid="login-remember-me-checkbox"`).
  - Show/Hide password toggles added to `LdapLoginForm.tsx` and `LocalAdminDisclosure.tsx`.
  - Accessible keyboard navigation (`Escape`, `ArrowDown`/`ArrowUp`, and focus restoration) in `Topbar.tsx` avatar menu, `LdapLoginForm`, and `SecondFactorStep`.
  - `AuthCardButton.tsx` responsive text wrapping to prevent clipping at 200% zoom.
- **Token Compliance:** All CSS references in `auth.css` use canonical tokens verified by `cssTokensAudit.test.ts`.
- **No Em-Dashes:** Verbatim adherence to ASCII hyphens across all commit messages and documentation.
