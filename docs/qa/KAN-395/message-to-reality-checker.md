# Integration Reality-Checker Briefing: KAN-395 (Round-1 QA Remediation)

- **Ticket**: KAN-395 (Support 1,200+ character OAuth state tokens, RFC 8707 Resource Scoping, and MCP Protocol Negotiation for Google Gemini MCP OAuth 2.1 integration)
- **Branch**: `fix/KAN-395-rc1` (created from `main`)
- **Remediation Target**: Round-1 QA Remediation responding to clean-room reality-checker audit.
- **Review Status**:
  - API Specialist Review: APPROVED (`docs/qa/KAN-395/api-specialist-review.md`)
  - UI Specialist Review: APPROVED (`docs/qa/KAN-395/ui-specialist-review.md`)

## Round-1 QA Remediation Actions Completed

1. **`ConnectOAuthAppModal.css` Mobile URL Wrapping and Vertical Spacing**:
   - Modified `.kb-connect-oauth-url` with `white-space: normal; word-break: break-all; overflow-wrap: anywhere; min-width: 0;` so long URLs wrap cleanly without horizontal truncation or blowouts on `390x844` mobile.
   - Adjusted `.kb-connect-oauth-card` height allowance to `max-height: min(94vh, 860px)` and tightened vertical padding/margins across `.kb-connect-oauth-header` (12px 20px), `.kb-connect-oauth-body` (12px 20px, gap 10px), `.kb-connect-oauth-endpoints` (10px 12px, gap 8px), `.kb-connect-oauth-tabs` (min-height 36px, gap 6px), `.kb-connect-oauth-tab` (height 32px, padding 4px 10px), and `.kb-connect-oauth-gemini-hint` (padding 6px 10px, gap 3px, margin 0 on `<p>`).
   - Verified via Playwright screenshots on `1440x900` that the entire Gemini hint AND code snippet fit visibly above the fold with zero mid-line slicing of `agent:write.`, even when the dynamic `Target Project` selector is active!
   - On `390x844` mobile portrait, connector tabs wrap cleanly across two rows without slicing at any scroll edge or clipping the close button.

2. **Light Theme Support in `CONSENT_STYLE_CSS` (`kanban/oauth/server.py`)**:
   - Added full `@media (prefers-color-scheme: light)` CSS variables block to `CONSENT_STYLE_CSS` with crisp WCAG AA light-mode tokens:
     - `--bg: #f8fafc`
     - `--card: #ffffff`
     - `--card-bg: #ffffff`
     - `--border: #cbd5e1`
     - `--text: #0f172a`
     - `--text-muted: #475569`
     - `--muted: #475569`
     - `--primary: #2563eb`
     - `--primary-hover: #1d4ed8`
     - `--danger: #dc2626`
     - `--danger-hover: #b91c1c`
     - `--badge-bg: #dbeafe`
     - `--badge-text: #1e40af`
     - `--badge-host-bg: #f1f5f9`
     - `--surface-raised: #f1f5f9`
     - `--scope-name: #0f172a`
     - `--btn-deny-bg: #e2e8f0`
     - `--btn-deny-hover: #cbd5e1`
   - Added automated unit test assertion in `kanban/tests/oauth/test_oauth_unit.py` verifying `@media (prefers-color-scheme: light)` is present in `render_consent_screen` output.
   - Verified light mode renders a genuine, distinct light-theme consent screen.

3. **Complete Verbatim `unit-test-results.txt`**:
   - `docs/qa/KAN-395/unit-test-results.txt` contains complete, unabridged, verbatim output from BOTH test suites:
     - Backend: `uv run pytest mcp/tests/test_protocol.py mcp/tests/test_metadata.py kanban/tests/oauth/ --cov=kanban.api.v1.oauth --cov=kanban.oauth --cov=mcp.protocol --cov=mcp.metadata -v`: 65 passed in 31.25s, 84% combined coverage.
     - Frontend: `COVERAGE_INCLUDE="src/features/settings/ConnectOAuthAppModal.tsx,src/features/settings/McpAccessStudio.tsx,src/features/auth/LoginPage.tsx" pnpm --dir kanban/web test src/features/settings/__tests__/ConnectOAuthAppModal.test.tsx src/features/settings/__tests__/McpAccessStudio.test.tsx src/features/auth/LoginPage.test.tsx --coverage`: 3 test files passed, 85 passed tests in 5.74s, 99.48% line coverage, 95.64% branch coverage (exceeding >=95% gate).

4. **Multi-Viewport Zero-Mock Screenshots Recaptured**:
   - All 14 Playwright screenshots in `docs/qa/KAN-395/screenshots/` recaptured fresh via `scripts/capture_kan395_rc1_screenshots.mjs`:
     - `oauth-consent-screen-1200-state-1440x900-light.png`: SHA-256 `4c262251deff1290fefa4330db0a651b895230f3ab785eee7054287088bbeea5`
     - `oauth-consent-screen-1200-state-1440x900-dark.png`: SHA-256 `bdff9e40094c81717e4299942beb5d2a0d72ef464cc3d6be713285dba542b002` (distinct SHA-256 hashes!)
     - `oauth-consent-screen-1200-state-1024x768.png`
     - `oauth-consent-screen-1200-state-768x1024.png`
     - `oauth-consent-screen-1200-state-390x844.png`
     - `connect-oauth-modal-gemini-workspace-1440x900-light.png`
     - `connect-oauth-modal-gemini-workspace-1440x900-dark.png`
     - `connect-oauth-modal-gemini-workspace-1024x768.png`
     - `connect-oauth-modal-gemini-workspace-768x1024.png`
     - `connect-oauth-modal-gemini-workspace-390x844.png`
     - `connect-oauth-modal-gemini-project-1440x900-light.png`
     - `connect-oauth-modal-gemini-project-390x844.png`
     - `connect-oauth-modal-gemini-server-1440x900-light.png`
     - `connect-oauth-modal-gemini-server-390x844.png`
     - `live-gemini-oauth-consent.png` preserved intact from live production verification.

5. **Static Checks and Linting (`docs/qa/KAN-395/build-check.txt`)**:
   - Ruff check: All checks passed!
   - Ruff format check: 807 files already formatted!
   - Mypy: Success: no issues found in 803 source files!
   - Plain ASCII check: Verified with `scripts/check_no_dashes.py --all` (0 em/en-dashes).
   - TypeScript: `pnpm --dir kanban/web typecheck` (0 errors).
   - ESLint: `pnpm --dir kanban/web lint` (0 errors, 0 warnings).
   - Web Build: `pnpm --dir kanban/web build` (built in 1.34s).
