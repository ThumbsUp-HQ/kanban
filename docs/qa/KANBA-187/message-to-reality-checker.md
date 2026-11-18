# KANBA-187 Forensic Verification Handover to reality-checker

## Task & Scope Overview
- **Ticket**: KANBA-187 (`[KB-USER-SETTINGS]`) - User Personal Settings Studio: Profile, Timezone, Avatar Upload, Password Change, and MFA Self-Service.
- **Branch**: `feat/kanba-186-187` (commit 2 on top of KANBA-186 `07a795f105e85995c539685eb4c24000927bea4b`).
- **Workspace**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-auth-settings-builder-d406043d`.

## Forward Migration Chain Standard
Per the Zero-Guesswork Database Migration Standard in `database/GEMINI.md`:
- Linear chain: `p4_18_oauth_mcp_scoping` -> `p4_19_persistent_sessions` (KANBA-186) -> `p4_20_user_personal_settings` (KANBA-187).
- Migration `p4_20_user_personal_settings` provisions:
  - `public.user_preferences` table with RLS enabled and forced (`FORCE ROW LEVEL SECURITY`).
  - Permissions and RLS policies for `kanban_app` (scoped to workspace/principal) and `kb_auth_owner` (bypass helper).
  - Security definer functions: `kb_auth.user_update_own_profile(UUID, TEXT, TEXT)`, `kb_auth.local_get_credential_by_principal(UUID)`, `kb_auth.webauthn_credential_update_nickname(UUID, UUID, TEXT)`, `kb_auth.session_revoke_all_except(UUID, UUID)`, `kb_auth.user_get_avatar(UUID)`.
- Validated via `uv run kanban-ctl db check-migrations --static-only` and `database/tests/migrations/test_p4_20_user_personal_settings_migration.py`.

## Key Implementations & Defenses
1. **Profile & Timezone (`PATCH /api/v1/auth/me`)**:
   - Updates `display_name` on `principals` and `timezone` on `user_preferences`.
   - Strict IANA validation via `zoneinfo.available_timezones()`, returning `422 INVALID_TIMEZONE` on bad input.
2. **Avatar Upload & Streaming (`PUT /api/v1/auth/me/avatar`, `GET /api/v1/users/{id}/avatar`)**:
   - Zero external dependency body parsing supporting multipart form-data and binary streaming.
   - Enforces max 2 MiB file size limit (`413 PAYLOAD_TOO_LARGE`).
   - Magic byte header sniffing rejecting SVG payloads with `415 UNSUPPORTED_MEDIA_TYPE` (preventing XSS/SSRF/DOM clobbering vectors).
   - Re-encodes raster payloads with Pillow to clean strip metadata and malicious chunks.
   - Serves avatar with hardened CSP headers: `default-src 'none'; style-src 'unsafe-inline'; sandbox` and `X-Content-Type-Options: nosniff`.
3. **Password Rotation & Session Invalidation (`POST /api/v1/auth/me/password`)**:
   - Enforces min 14 characters for `SERVER_ADMIN` / `WORKSPACE_ADMIN` and min 12 characters for standard users.
   - Rejects unchanged passwords with `422 PASSWORD_UNCHANGED`.
   - On successful rotation, revokes all other active sessions across devices using `kb_auth.session_revoke_all_except(principal_id, current_session_id)`, while preserving current session.
4. **Passkeys & MFA Self-Service (`PATCH /api/v1/auth/webauthn/credentials/{id}`, `GET /api/v1/auth/mfa/status`, `DELETE /api/v1/auth/mfa/totp`)**:
   - Rename and delete passkeys.
   - Real-time factor summary returning TOTP status, passkeys count, and remaining recovery codes.
   - Lockout prevention: prevents admins from disabling TOTP if they have zero passkeys remaining (`409 LAST_FACTOR`).
5. **Frontend Studio & CSS Token Compliance**:
   - Route `/settings/profile` wired in `kanban/web/src/app/routes.tsx`.
   - UI sections: Profile & Timezone, Avatar with live preview, Change Password with Show/Hide toggle, Passkeys list with rename modal, 2FA status card, TOTP setup modal, and 10 recovery codes modal.
   - Intercepts `403 AAL2_REQUIRED` responses to display step-up modal before re-attempting sensitive operations.
   - 100% canonical CSS tokens in `PersonalSettingsPage.css` verified by `cssTokensAudit.test.ts`.

## Genuine Verification Proof Artifacts
- `git-diff.patch`: Exact patch of KANBA-187 diff against KANBA-186 commit (`07a795f105e85995c539685eb4c24000927bea4b`), excluding `docs/qa/KANBA-187`.
- `changed-files-manifest.txt`: List of all 20 modified and added files.
- `unit-test-results.txt`: Output from pytest (`kanban/tests/api/test_user_personal_settings.py`, migration tests, static model tests) and vitest (`PersonalSettingsPage.test.tsx`, `cssTokensAudit.test.ts`).
- `build-check.txt`: Output from `make check` (ruff, mypy, lint-imports, check_no_dashes, check-migrations) and web `typecheck` / `lint` / `build`.
- `contract-sample.json`: Concrete request and response bodies for all user settings endpoints.
- `screenshots/`: 12 genuine Playwright screenshots across Desktop (`1440x900`), Tablet (`1024x768`), and Mobile (`390x844`):
  - `01-personal-settings-studio-desktop.png`, `01-personal-settings-studio-tablet.png`, `01-personal-settings-studio-mobile.png`
  - `02-password-change-desktop.png`, `02-password-change-tablet.png`, `02-password-change-mobile.png`
  - `03-passkeys-mfa-desktop.png`, `03-passkeys-mfa-tablet.png`, `03-passkeys-mfa-mobile.png`
  - `04-recovery-keys-modal-desktop.png`, `04-recovery-keys-modal-tablet.png`, `04-recovery-keys-modal-mobile.png`
