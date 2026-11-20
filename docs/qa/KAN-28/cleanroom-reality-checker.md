# Reality-Checker Forensic QA Audit Report: KAN-28 ([KB-P3-AUDIT-22])

## Verdict & Certification
- **Ticket:** KAN-28 (`[KB-P3-AUDIT-22] Harden /oauth/authorize/decision Against Consent CSRF & Add Self-Service + Admin OAuth 2.1 App Connection Flows on /settings/mcp & /admin/oauth (4 Problems)`)
- **Auditor:** Isolated Clean-Room `reality-checker` Subagent (`6c14a24e-59c1-4319-a6ef-00a24a0d6f83`)
- **Audit Mode:** Passive Clean-Room Forensic Audit (evidence-only inspection)
- **Overall Grade:** **A**
- **Certification Status:** **READY**

---

## 1. Evidence Packet & Diff Cross-Validation

All forensic artifacts in `/home/adamoutler/kanban/docs/qa/KAN-28/` were directly inspected:
- `git-diff.patch` (7,307 lines across 27 files listed in `changed-files-manifest.txt`)
- `unit-test-results.txt`
- `build-or-typecheck.txt`
- `live-fullstack-proof.txt` (Round 5 / commit `9b6ffba`, container `kanban-liveqa-3` on `http://localhost:18953`, zero mocks)
- `api-specialist-review.md` (`STATUS: APPROVED` on `fix/KAN-28-rc4` / `f2e0ff5`)
- `ui-specialist-review.md` (`STATUS: APPROVED` on `fix/KAN-28-rc3` / `abd3da1`)
- `message-to-reality-checker.md`
- All 18 live PNG screenshots in `/home/adamoutler/kanban/docs/qa/KAN-28/screenshots/`

---

## 2. Definition of Done Verification

### DoD 1: `POST /oauth/authorize/decision` Consent CSRF, Origin, Policy & CSP Hardening - PASS
- **Cryptographic CSRF Binding (`kanban/oauth/server.py`, `kanban/api/v1/oauth.py`):**
  - `OAUTH_CONSENT_CSRF_MAX_TTL = 600` and `OAUTH_CONSENT_CSRF_PURPOSE = "oauth/consent-csrf"`.
  - `generate_consent_csrf_token` derives a subkey from `session_hmac_key` via `derive_subkey` and signs `v1|{session_id}|{client_id}|{redirect_uri}|{code_challenge}|{state}|{surface}|{exp}` with HMAC-SHA256.
  - `verify_consent_csrf_token` enforces expiration and constant-time signature validation via `hmac.compare_digest`, raising `ProblemException(code="CSRF_INVALID", status=403)` on failure.
- **Same-Origin Enforcement (`kanban/auth/sessions/csrf.py`):**
  - `verify_same_origin_request` rejects `Sec-Fetch-Site` outside `("same-origin", "none")`.
  - When `Origin` is `"null"`, it is permitted **strictly and only** when `Sec-Fetch-Site` is explicitly `"same-origin"` (supporting native Chromium form POST navigations under `Referrer-Policy: no-referrer`). `Origin: null` with `cross-site`, `none`, or missing `Sec-Fetch-Site` returns `False` (`403 CSRF_INVALID`).
  - Proven in unit tests and live container probes (`Origin: https://evil.example`, `Origin: null + Sec-Fetch-Site: cross-site`, and forged `csrf_token` all returned HTTP `403 CSRF_INVALID`).
- **Policy Re-Verification & CSP (`kanban/api/v1/oauth.py`, `kanban/oauth/server.py`):**
  - Re-verifies `client_record.status != "active"` (302 `unauthorized_client`), re-enforces `surface == "admin" and caller.aal_level < _REQUIRED_AAL_LEVEL` (302 `access_denied&error_description=aal2_required`), and rejects empty `approved_scopes` (302 `invalid_scope`).
  - `render_consent_screen` replaces `'unsafe-inline'` with `style-src 'self' 'sha256-{CONSENT_STYLE_SHA256}'` (`hasUnsafeInline=false` verified live).

### DoD 2: `/settings/mcp`, `+ Connect OAuth App`, `Enter Device Code` & `/oauth/device` - PASS
- `McpAccessStudio.tsx` renders `+ Connect OAuth App` and `Enter Device Code` (`Link to="/oauth/device"`).
- `ConnectOAuthAppModal.tsx` & `.css` provide surface/scope pickers, live Resource URL + RFC 8414 URL copy buttons, and 4 non-collapsed setup tabs (`Claude Code`, `VS Code / Cursor`, `Antigravity`, `Codex`) measured at `offsetHeight = 36px`.
- `DeviceActivatePage.tsx` scopes `allowed_projects` using real project UUIDs (`KAN` and `OPS` verified live), and `PrecompressedSPAStaticApp` (`kanban/web_static.py`) serves `index.html` for `/oauth/device` (`HTTP 200`).

### DoD 3: `/admin/oauth` Admin Registration, AAL2 & `390x844` Mobile Containment - PASS
- `POST /api/v1/admin/oauth-clients` declares `dependencies=[Depends(require_admin_aal2)]`, validates HTTPS / loopback HTTP redirect URIs, logs `ActivityEventType.OAUTH_CLIENT_REGISTERED`, commits, and returns HTTP 201.
- Live `390x844` mobile telemetry verified `docScrollWidth=390`, `docClientWidth=390`, `mainScrollWidth=390`, `containerRight=374`, `registerBtnRight=349`, `subnavRight=362` in both light and dark modes.

### DoD 4: Route Aliases & Immediate `0ms` Project Commit - PASS
- `routes.tsx` redirects `/settings/mcp-keys` -> `/settings/mcp` and `/admin/oauth-clients` -> `/admin/oauth`.
- `kanban/api/v1/projects.py` calls `await session.commit()` before returning across project mutations (`0ms` `GET /api/v1/projects` returned `["KAN", "OPS"]`).

### DoD 5: Tests, Coverage, Static Checks, Zero Mocks & Visual Evidence - PASS
- **Pytest (`unit-test-results.txt`):** 71 passed in 31.62s; 97% combined coverage.
- **Vitest (`unit-test-results.txt`):** 9 test files, 125 tests passed in 6.40s; 99.31% statements, 96.22% branches, 99.51% functions, 99.42% lines (`cssTokensAudit.test.ts` 4/4).
- **Build & Static Analysis (`build-or-typecheck.txt`):** `ruff check`, `ruff format`, `mypy` (0 issues), `lint-imports` (2 kept, 0 broken), `check_no_dashes` (0 forbidden dashes), `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings/errors), `vite build` (1.74s).
- **Zero-Mock Live Full-Stack Proof (`live-fullstack-proof.txt`):** 0 `mockApi`, 0 `page.route`, 0 `console.error`, 0 `pageerror`, 0 `>=500` HTTP responses.

---

## 3. Summary & Final Gate Decision
- **Quality Rating:** Grade **A**
- **Production Readiness:** **READY**
- **Blockers:** None. All 5 Definition of Done criteria are satisfied with concrete, zero-mock, full-stack evidence. Ready for ticket closure (`complete_work`).
