# Reality-Checker Verification Packet: KAN-404

## Ticket Context
- Ticket ID: KAN-404 (`[GATE-0][KB-WEBSUDO-SLIDING-AND-REPLAY] Global Sliding-Window WebSudo (AAL2) + Singleflight In-Place Modal & Transparent Request Replay`)
- Feature Branch: `feat/KAN-404-websudo-sliding-replay`
- Base Commit: `71b847ba`
- Status: Ready for forensic Reality-Checker audit

---

## Executive Summary & Architecture Overview

Ticket KAN-404 delivers enterprise-grade sliding-window WebSudo (AAL2) authentication across both backend and frontend architectures, eliminating the jarring full-page step-up redirections that previously caused lost form state in administrative drawers.

### Key Architectural Invariants Enforced:
1. **Linear Database Migration & Single-Head Chain:**
   - Linear Alembic migration `p6_18_websudo_sliding_aal2` (revision `p6_18_websudo_sliding_aal2`, parent `p6_17_server_admin_role_access`) adds `aal2_last_active_at TIMESTAMPTZ` to `sessions`.
   - Backfills active `aal_level = 2` sessions from `aal2_verified_at`.
   - Recreates `kb_auth.session_create`, `session_resolve`, `session_rotate`, and `session_get_metadata` to carry `aal2_last_active_at`.
   - Zero historical migration modification: historical SQL files remain completely untouched.
   - Preserves single-head Alembic chain (80 total migrations valid under `uv run kanban-ctl db check-migrations --static-only`).
   - Strict ORM model parity in `database/models/auth.py` (`UserSession.aal2_last_active_at`).
2. **Hardened SECURITY DEFINER RPCs:**
   - `kb_auth.session_touch_aal2(p_session_id UUID, p_idle_seconds INT, p_abs_seconds INT, p_force BOOLEAN DEFAULT FALSE)`:
     - Enforces 900-second (15-minute) idle timeout window.
     - Enforces 14,400-second (4-hour) absolute session cap from original `aal2_verified_at`.
     - Built-in 30-second write throttling prevents database connection saturation during rapid user activity.
     - Automatically revokes elevation (`aal_level := 1`, `aal2_last_active_at := NULL`, `aal2_verified_at := NULL`) if either window has elapsed.
   - `kb_auth.session_drop_aal2(p_session_id UUID)`:
     - Explicit step-down routine for instant admin session locking.
     - Grants execute exclusively to `kanban_app` with `OWNER TO kb_auth_owner` and `search_path = pg_catalog, public`.
3. **Dual-Policy Backend Elevation Boundaries:**
   - Normal Administrative APIs (`require_admin_aal2`, `_RequireAal2`):
     - Validates and slides `aal2_last_active_at` via `kb_auth.session_touch_aal2` (or verified timestamp within 900s).
     - Emits `X-KB-AAL2-Expires-At` HTTP response header on elevated responses.
   - Irreversible Operations (`verification_only=True`):
     - Dual-control approvals (`kanban/custom_fields/approvals.py`).
     - MFA deletions (`DELETE /api/v1/auth/webauthn/credentials/{id}`, `DELETE /api/v1/auth/mfa/totp`, `POST /api/v1/auth/mfa/recovery/regenerate`).
     - Bound strictly to fresh `aal2_verified_at <= 900s` regardless of touch activity.
4. **Touch and Drop Endpoints & Session Reflection:**
   - `POST /api/v1/auth/aal2/touch`: Returns `200 { "aal2_active": bool, "aal2_expires_at": str | None }` without raising 403 when expired.
   - `POST /api/v1/auth/aal2/drop`: Drops elevation to AAL1 immediately.
   - `GET /api/v1/auth/session` and `GET /api/v1/auth/me`: Reflect `aal2_active` and `aal2_expires_at` in JSON payloads.
5. **Frontend Singleflight Coordinator & In-Place Replay:**
   - `kanban/web/src/api/client.ts`:
     - Cookie-first CSRF token extraction (`__Host-kb_csrf`, `kb_csrf` checked before memory cache).
     - Singleflight coordinator deduplicates concurrent 403 step-up challenges behind a shared `pendingAal2StepUp` promise.
     - Upon verification, refreshes CSRF token and reconstructs `timeoutSignal` before replaying the original request.
     - Strict `max 1 replay` enforcement to prevent infinite loops.
     - Rejection with silent `Aal2StepUpCancelledError` on user modal dismissal.
6. **WebSudoModalHost & Dirty Keepalive:**
   - Mounted globally in `AppShell.tsx` at `z-index: 10050` (above all drawers and modals).
   - Hook `useAal2DirtyKeepalive(isDirty)` periodically pings `/api/v1/auth/aal2/touch` while unsaved drawer changes exist, wired into `AuthCardEditorDrawer.tsx`, `AiProviderEditorDrawer.tsx`, and `AgentDefinitionEditorDrawer.tsx`.
   - Compact WebSudo countdown/lock pill (`data-testid="admin-sudo-pill"`) in `AdminStudioSubnav.tsx` with zero render cascades.
   - Obsolete `!isAal2` `<NotFoundView />` gates removed from `routes.tsx`, `LinkAuditorStudio.tsx`, and `AdminDiagnosticsStudio.tsx`.

---

## Changed Files Summary

### Database Layer
- `database/migrations/sql/p6_18_websudo_sliding_aal2.up.sql`
- `database/migrations/sql/p6_18_websudo_sliding_aal2.down.sql`
- `database/migrations/versions/p6_18_websudo_sliding_aal2.py`
- `database/models/auth.py`
- `database/tests/migrations/test_p6_18_websudo_sliding_aal2_migration.py`

### Backend Services & API Layer
- `kanban/api/deps.py`
- `kanban/api/request_id.py`
- `kanban/api/v1/auth_mfa.py`
- `kanban/api/v1/auth_session.py`
- `kanban/api/v1/auth_webauthn.py`
- `kanban/api/v1/user_settings.py`
- `kanban/auth/mfa/policy.py`
- `kanban/auth/sessions/resolver.py`
- `kanban/auth/sessions/service.py`
- `kanban/tests/auth/test_websudo_sliding_aal2.py`
- `kanban/tests/auth/test_aal2_policy.py`

### Frontend Layer
- `kanban/web/src/api/client.ts`
- `kanban/web/src/app/AppShell.tsx`
- `kanban/web/src/components/help/WebSudoModalHost.tsx`
- `kanban/web/src/features/admin/AdminStudioSubnav.tsx`
- `kanban/web/src/features/admin/AdminDiagnosticsStudio.tsx`
- `kanban/web/src/features/admin/LinkAuditorStudio.tsx`
- `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`
- `kanban/web/src/features/ai/AiProviderEditorDrawer.tsx`
- `kanban/web/src/features/agents/AgentDefinitionEditorDrawer.tsx`
- `kanban/web/src/routes.tsx`
- `kanban/web/src/api/__tests__/websudoReplay.test.tsx`

### Test & Automation Scripts
- `scripts/capture_kan404_screenshots.mjs`

---

## Verification Artifacts & Passive Evidence

All raw test logs, static check logs, screenshot captures, and cryptographic checksums are stored in `docs/qa/KAN-404/`:

1. `docs/qa/KAN-404/unit-test-results.txt`:
   - Raw output of 17 backend unit tests (`kanban/tests/auth/test_websudo_sliding_aal2.py`, `kanban/tests/auth/test_aal2_policy.py`, `database/tests/test_p1_17_models.py`, `kanban/tests/security/test_admin_routes_protected.py`, `database/tests/migrations/test_p6_18_websudo_sliding_aal2_migration.py`).
   - Raw output of 16 Vitest frontend tests (`kanban/web/src/api/__tests__/websudoReplay.test.tsx`).
   - Total: 33 tests passed, 0 failures.
   - Code coverage on new/modified modules:
     - `WebSudoModalHost.tsx`: 100% Statements, 100% Functions, 100% Lines.
     - `AdminStudioSubnav.tsx`: 98.46% Statements, 94.11% Functions, 98.43% Lines.
     - Overall frontend modules: 99.13% Statements, 96.77% Functions, 99.12% Lines.
2. `docs/qa/KAN-404/build-check.txt`:
   - Static migration check: 80 migrations valid, single head `p6_18_websudo_sliding_aal2`.
   - Python linter: `uv run ruff check kanban/ database/` (0 errors, 0 warnings).
   - Style check: `python3 scripts/check_no_dashes.py --all` (0 dashes).
   - Web typecheck: `pnpm --dir kanban/web typecheck` (exit code 0).
   - Web linter: `pnpm --dir kanban/web lint` (0 errors, 0 warnings).
   - Web production build: `pnpm --dir kanban/web build` (exit code 0, 762 modules transformed).
3. `docs/qa/KAN-404/screenshots/`:
   - `01-desktop-1440x900-light-websudo-modal-over-drawer.png`: WebSudo modal overlaid at z-index: 10050 cleanly above open LDAP drawer with typed credentials preserved.
   - `02-desktop-1440x900-dark-admin-sudo-pill-active.png`: Dark theme showing right-aligned active sudo countdown pill (`data-testid="admin-sudo-pill"`) with green shield icon, countdown time, and lock button.
   - `03-desktop-1024x768-light-websudo-replay-success.png`: Post-replay success state showing transparent save and new LDAP card rendered in list.
   - `04-tablet-portrait-768x1024-light-websudo-modal.png`: Tablet viewport with responsive WebSudo modal cleanly centered.
   - `05-mobile-portrait-390x844-light-admin-sudo-pill-locked.png`: Mobile viewport showing locked sudo pill in subnav.
   - All screenshots visually verified via `read_file` with zero clipping, overflow, or occlusion.
4. `docs/qa/KAN-404/git-diff.patch`:
   - Clean, scoped patch against `71b847ba` covering `database/` and `kanban/`.
5. `docs/qa/KAN-404/changed-files-manifest.txt`:
   - SHA-256 checksums for all files in the QA packet, verifiable via `sha256sum -c`.
