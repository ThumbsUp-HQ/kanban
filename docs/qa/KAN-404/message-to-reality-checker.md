# Reality-Checker Verification Packet: KAN-404 (Round-1 Remediation)

## Ticket Context
- Ticket ID: KAN-404 (`[GATE-0][KB-WEBSUDO-SLIDING-AND-REPLAY] Global Sliding-Window WebSudo (AAL2) + Singleflight In-Place Modal & Transparent Request Replay`)
- Feature Branch: `fix/KAN-404-rc1`
- Base Commit: `0a204b9f` (branched directly from `main`)
- Status: Ready for Round-1 Clean-Room Reality-Checker forensic QA audit

---

## Executive Summary & Architecture Overview

Ticket KAN-404 delivers enterprise-grade sliding-window WebSudo (AAL2) authentication across both backend and frontend architectures, eliminating jarring full-page step-up redirections that previously caused lost form state in administrative drawers and settings studios.

### Key Architectural Invariants Enforced:
1. **Zero Database Migrations in RC1:**
   - Migration #80 (`p6_18_websudo_sliding_aal2`) is already merged on `main`. Zero migrations or database files were created or modified in RC1.
   - All 82 migrations on `main` remain valid under `uv run kanban-ctl db check-migrations --static-only` with single head `p6_20_oauth_clients_status_check`.
2. **Hardened SECURITY DEFINER RPCs & Sliding WebSudo Window:**
   - `kb_auth.session_touch_aal2(p_session_id UUID, p_idle_seconds INT, p_abs_seconds INT, p_force BOOLEAN DEFAULT FALSE)`:
     - Enforces a 900-second (15-minute) idle timeout window sliding from `aal2_last_active_at`.
     - Enforces a 14,400-second (4-hour) absolute session cap measured strictly from the original `aal2_verified_at` timestamp.
     - Built-in 30-second write throttling prevents database connection and disk I/O saturation during rapid user activity (`<= 1` DB write per 30 seconds unless forced).
     - Informational session reads (`GET /api/v1/auth/session` and `GET /api/v1/auth/me`) do NOT advance `aal2_last_active_at`. They reflect current elevation state passively without extending the sliding window.
     - Automatically revokes elevation (`aal_level := 1`, `aal2_last_active_at := NULL`, `aal2_verified_at := NULL`) if either the 15-minute idle window or 4-hour absolute cap has elapsed.
   - `kb_auth.session_drop_aal2(p_session_id UUID)`:
     - Explicit step-down routine for instant admin session locking.
3. **Dual-Policy Backend Elevation Boundaries:**
   - Normal Administrative APIs (`require_admin_aal2`, `_RequireAal2`):
     - Validates and slides `aal2_last_active_at` via `kb_auth.session_touch_aal2` (or verified timestamp within 900s).
     - Emits `X-KB-AAL2-Expires-At` HTTP response header on elevated responses.
   - Irreversible Operations (`verification_only=True`):
     - Dual-control approvals (`kanban/custom_fields/approvals.py`).
     - MFA deletions (`DELETE /api/v1/auth/webauthn/credentials/{id}`, `DELETE /api/v1/auth/mfa/totp`, `POST /api/v1/auth/mfa/recovery/regenerate`).
     - Bound strictly to fresh `aal2_verified_at <= 900s` regardless of touch activity.
     - Strict guard: `caller.aal2_verified_at is None` immediately raises 403 `AAL2_REQUIRED` (never falls through).
4. **Touch and Drop Endpoints & Session Reflection:**
   - `POST /api/v1/auth/aal2/touch`: Returns `200 { "aal2_active": bool, "aal2_expires_at": str | None }` without raising 403 when expired.
   - `POST /api/v1/auth/aal2/drop`: Drops elevation to AAL1 immediately.
   - `GET /api/v1/auth/session` and `GET /api/v1/auth/me`: Reflect `aal2_active` and `aal2_expires_at` in JSON payloads passively.
5. **Frontend Singleflight Coordinator & In-Place Replay:**
   - `kanban/web/src/api/client.ts`:
     - Cookie-first CSRF token extraction (`__Host-kb_csrf`, `kb_csrf` checked before memory cache).
     - Singleflight coordinator deduplicates concurrent 403 step-up challenges behind a shared `pendingAal2StepUp` promise.
     - Upon verification, refreshes CSRF token and reconstructs `timeoutSignal` before replaying the original request.
     - Strict max 1 replay enforcement to prevent infinite loops.
     - Rejection with silent `Aal2StepUpCancelledError` on user modal dismissal (cancelled step-up ignored by callers without error alerts).
6. **WebSudoModalHost & Dirty Keepalive:**
   - Mounted globally in `AppShell.tsx` at `z-index: 10050` (authoritative singleflight modal above all drawers and overlays).
   - Traps Tab key focus inside the active modal dialog and dismisses on Escape key press.
   - Supplies contextual cancel button copy (`"Cancel"` instead of `"Cancel and return to sign-in"`).
   - Hook `useAal2DirtyKeepalive(isDirty)` pings `/api/v1/auth/aal2/touch` only when the form is actually dirty (`hasUnsavedChanges` / `isDirty`), preventing idle open drawers from bypassing timeout.
   - Compact WebSudo countdown/lock pill (`data-testid="admin-sudo-pill"`) in `AdminStudioSubnav.tsx` subscribes to `kb:aal2-stepup-success` and `kb:aal2-expires-at` to transition immediately upon verification.
   - Responsive flex wrapping prevents clipping on `AdminStudioSubnav` across all viewports.
   - Mobile `AuthCardRow` CSS layout at 390x844 prevents toggle switch and button overlap.

---

## Round-1 Remediation Details (All 5 Findings Resolved)

1. **Consolidated Duplicate Local AAL2 Modals/Banners & Preserved Drawer State on Cancel/Error:**
   - Removed duplicate page-local AAL2 state and modals from all 8 studios: `AuthStudioPage.tsx`, `AiStudioPage.tsx`, `AgentStudioPage.tsx`, `OAuthClientGovernanceStudio.tsx`, `RunnerStudioPage.tsx`, `McpAccessStudio.tsx`, `WorkflowStudioPage.tsx`, `PersonalSettingsPage.tsx` + `ErrorHelpHint.tsx`.
   - Replaced with authoritative global `WebSudoModalHost.tsx` + singleflight request replay in `client.ts`.
   - Callers silently catch and ignore `isAal2StepUpCancelled(err)` (`Aal2StepUpCancelledError`), keeping drawers open with entered secrets intact.
   - Fixed `AuthCardEditorDrawer.tsx`: secrets (`secretInput`) are no longer wiped in `finally`. Secrets are retained on cancel or submission error and only cleared upon successful save.
2. **`AdminStudioSubnav` Live Sudo Pill Update & Responsive Unclipping + `adminAuth.css` Mobile Overlap Fix:**
   - Subscribed `AdminStudioSubnav.tsx` to `kb:aal2-stepup-success` and `kb:aal2-expires-at` custom window events; immediately updates countdown from `Sudo Locked` to active `15:00` without page refresh.
   - Added responsive flex wrapping to `AdminStudioSubnav.css` ensuring tabs (Migration, System, Diagnostics) and `admin-sudo-pill` never clip off-screen.
   - Updated `kanban/web/src/features/admin-auth/adminAuth.css` (`.auth-card-right`) at mobile viewport (390x844) so `.auth-toggle-switch` never overlaps `Test handshake` and `Delete` has clear spacing.
3. **Wired `useAal2DirtyKeepalive(isDirty)` to REAL Form Dirty State:**
   - `AuthCardEditorDrawer.tsx`, `AiProviderEditorDrawer.tsx`, and `AgentDefinitionEditorDrawer.tsx` now pass actual dirty flags (`hasUnsavedChanges` / `isDirty`) instead of `isOpen`. Untouched drawers never ping `/api/v1/auth/aal2/touch`.
4. **`WebSudoModalHost.tsx` Accessibility & `approvals.py:310` Strict Guard:**
   - Added Tab focus trap and Escape key dismissal to `WebSudoModalHost.tsx`.
   - Configured `cancelButtonLabel="Cancel"` in `SecondFactorStep` when hosted in WebSudo modal.
   - Enforced strict `caller.aal2_verified_at is None` check in `kanban/custom_fields/approvals.py:310` raising 403 `AAL2_REQUIRED`.
5. **Complete Automated Test Suites & Coverage:**
   - Expanded `test_websudo_sliding_aal2.py` testing non-advancement of sliding window on session read, 30s write throttle, 14,400s absolute cap, and `approvals.py` None verification guard.
   - Pytest: 16 backend tests passed with 100% success.
   - Vitest: 398 frontend tests across 13 test files passed with 100% success.
   - Static checks: check-migrations, ruff, mypy, no-dashes, typecheck, lint, build all 100% clean.

---

## Verification Artifacts & Passive Evidence

All raw test logs, static check logs, screenshot captures, and cryptographic checksums are stored in `docs/qa/KAN-404/`:

1. `docs/qa/KAN-404/unit-test-results.txt`:
   - Raw output of 16 backend unit tests (`kanban/tests/auth/test_websudo_sliding_aal2.py`, `database/tests/test_p1_17_models.py`, `kanban/tests/security/test_admin_routes_protected.py`, `database/tests/migrations/test_p6_18_websudo_sliding_aal2_migration.py`).
   - Raw output of 398 Vitest frontend tests across 13 test files.
   - Total: 414 automated tests passed, 0 failures.
   - Code coverage on target modules:
     - All files: 99.6% Statements, 95.67% Branches, 100% Functions, 99.68% Lines.
     - `WebSudoModalHost.tsx`: 100% Statements, 97.05% Branches, 100% Functions, 100% Lines.
     - `AdminStudioSubnav.tsx`: 100% Statements, 97.77% Branches, 100% Functions, 100% Lines.
     - `AgentDefinitionEditorDrawer.tsx`: 99.05% Statements, 95.23% Branches, 100% Functions, 99.03% Lines.
     - `AiProviderEditorDrawer.tsx`: 100% Statements, 95.54% Branches, 100% Functions, 100% Lines.
     - `AuthCardEditorDrawer.tsx`: 99.41% Statements, 95.61% Branches, 100% Functions, 99.56% Lines.
2. `docs/qa/KAN-404/build-check.txt`:
   - Static migration check: 82 migrations valid, single head `p6_20_oauth_clients_status_check`.
   - Python linter: `uv run ruff check kanban/ database/ agent/` (0 errors, 0 warnings).
   - Python typecheck: `uv run mypy kanban/` (Success: no issues found in 679 source files).
   - Style check: `python3 scripts/check_no_dashes.py --all` (0 Unicode dashes).
   - Web typecheck: `pnpm --dir kanban/web typecheck` (exit code 0).
   - Web linter: `pnpm --dir kanban/web lint` (0 errors, 0 warnings).
   - Web production build: `pnpm --dir kanban/web build` (exit code 0, 762 modules transformed).
3. `docs/qa/KAN-404/screenshots/`:
   - `01-desktop-1440x900-light-websudo-modal-over-drawer.png`: WebSudo modal with "Cancel" button overlaid at z-index: 10050 cleanly above open LDAP drawer with typed credentials and secrets preserved.
   - `02-desktop-1440x900-dark-admin-sudo-pill-active.png`: Dark theme showing right-aligned active sudo countdown pill (`data-testid="admin-sudo-pill"`) with green shield icon, countdown time, and lock button, with subnav completely unclipped.
   - `03-desktop-1024x768-light-websudo-replay-success.png`: Post-replay success state showing transparent save and new LDAP card rendered in list.
   - `04-tablet-portrait-768x1024-light-websudo-modal.png`: Tablet viewport with responsive WebSudo modal cleanly centered over form.
   - `05-mobile-portrait-390x844-light-admin-sudo-pill-locked.png`: Mobile viewport showing responsive unclipped `AdminStudioSubnav` with locked sudo pill AND non-overlapping mobile `AuthCardRow` with toggle switch, `Edit`, and `Delete` action buttons.
   - All screenshots visually verified via `read_file`.
4. `docs/qa/KAN-404/git-diff.patch`:
   - Clean, scoped patch against base `0a204b9f` covering only implementation changes (excluding `docs/qa/KAN-404`).
5. `docs/qa/KAN-404/changed-files-manifest.txt`:
   - SHA-256 checksums for all files in the QA packet, verifiable via `sha256sum -c`.
