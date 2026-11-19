# API, Security, and MCP Specialist Audit: KAN-23

- **Ticket ID**: KAN-23 ([KB-P3-AUDIT-17])
- **Worktree**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan23-2313bbdb`
- **Branch**: `feat/KAN-23`
- **Auditor**: Clean-Room API/MCP/Security Specialist (`api-spec-2`)
- **Status**: STATUS: APPROVED

---

## 1. Scope and Architectural Review

Ticket KAN-23 addresses profile `display_name` wipe on avatar save, avatar raster sanitization, CSP sandbox hardening on avatar retrieval, and interactive canvas cropping and lightbox modals.

The review verified:
1. **Zero New Dependencies**: Neither `pyproject.toml` nor `kanban/web/package.json` was modified. All canvas crop and lightbox interactions are implemented using vanilla HTML5 Canvas and standard React hooks.
2. **Admin Route Protection Invariant**: No `/api/v1/admin/*` routes were introduced or altered. All existing admin route invariants remain intact.
3. **Import Layering & Architectural Integrity**: `uv run lint-imports` passed cleanly (2 kept, 0 broken). Layering order `agent -> mcp -> kanban -> database` is strictly maintained.
4. **Strict Dash Policy**: `python3 -m scripts.check_no_dashes --all` confirmed 0 em-dashes (\u2014) and 0 en-dashes (\u2013) across code, tests, and documentation.

---

## 2. API Contract and Backend Security Audit

### 2.1 Canonical 16-Field `UserProfileResponse` Unification
- **Helper Extraction**: Shared helper `build_me_response` in `kanban/api/v1/user_settings.py` unifies response structure across:
  - `GET /api/v1/auth/me`
  - `PATCH /api/v1/auth/me`
  - `PUT /api/v1/auth/me/avatar`
  - `DELETE /api/v1/auth/me/avatar`
- **Fields Validated**: All 16 fields (`id`, `principal_id`, `workspace_id`, `handle`, `username`, `display_name`, `email`, `is_server_admin`, `is_workspace_admin`, `is_project_admin`, `workspace_role`, `workspace_capabilities`, `timezone`, `avatar_url`, `has_local_password`, `aal_level`, `mfa_pending`) are consistently populated.
- **Cache-Buster Generation**: When an avatar is present, `avatar_url` includes the content-hash parameter (`?v=<sha256[:12]>`), preventing stale cached avatar icons on client navigations while avoiding cache desynchronization.

### 2.2 Avatar Raster Decompression and Sanitization Hardening
- **Bounds Enforced in `kanban/attachments/raster.py`**:
  - `MAX_AVATAR_IMAGE_PIXELS = 16_000_000` (16 MP)
  - `MAX_AVATAR_DIMENSION = 4096` px
  - `MAX_AVATAR_DOWNSCALE_DIMENSION = 1024` px
- **Format Restrictions**: Strictly limited to `PNG`, `JPEG`, and `WEBP`. Rejects animated GIF and animated WebP with HTTP 422 (`ANIMATED_AVATAR_NOT_ALLOWED`).
- **Decompression Bomb Defense**: `Image.DecompressionBombWarning` is caught and converted into HTTP 422 (`IMAGE_DIMENSIONS_EXCEEDED`).
- **Metadata Sanitization**: Re-encoding allocates fresh `Image.new()` buffers, completely stripping EXIF, XMP, and ICC metadata to eliminate metadata leakage or parser exploit vectors.
- **Async Thread Safety**: All raster operations run within worker threads via `anyio.to_thread.run_sync` constrained by `_RASTER_SEMAPHORE`.

### 2.3 Strict CSP and HTTP Transport Security on Avatar Endpoint
- **Endpoint**: `GET /api/v1/users/{principal_id}/avatar`
- **Headers Audited**:
  - `Content-Security-Policy`: Updated from `default-src 'none'; style-src 'unsafe-inline'` to `"default-src 'none'; sandbox"`. This completely eliminates unsafe inline style execution.
  - `X-Content-Type-Options`: `nosniff`
  - `Cross-Origin-Resource-Policy`: `same-origin`
  - `ETag` and `If-None-Match`: SHA-256 etag computation with HTTP 304 Not Modified response support.

---

## 3. Test Coverage and Quality Validation

- **Backend Pytest Execution**:
  - 39 tests passed across `kanban/tests/api/test_user_personal_settings.py` and `kanban/tests/attachments/test_sniff_and_raster.py`.
  - Line coverage on `kanban/attachments/raster.py`: 95%.
  - Line coverage on `kanban/api/v1/user_settings.py`: 83% (up from 78% on main; all newly added functions and branches tested).
- **Frontend Vitest Execution**:
  - 80 unit tests passed across `AvatarCropModal.test.tsx`, `AvatarLightboxModal.test.tsx`, `PersonalSettingsPage.test.tsx`, and `personalSettingsApi.test.ts`.
  - All touched frontend files achieved >= 96% branch coverage and >= 98% line coverage (exceeding the >= 95.10% threshold).
- **CSS Token Audit**: `cssTokensAudit.test.ts` passed (4/4 tests). Zero inline styles in JSX; 100% canonical CSS tokens.
- **Static Gate Cleanliness**:
  - `uv run ruff check`: 0 errors
  - `uv run mypy`: 0 errors in 524 source files
  - `uv run lint-imports`: 2 kept, 0 broken
  - `pnpm --filter @kanban/web check`: 0 errors

---

## 4. Verdict and Handoff

The backend API contracts, security sanitization, and CSP transport protections for KAN-23 are verified clean, robust, and fully compliant with project invariants.

- **Status**: STATUS: APPROVED
- **Next Step**: Hand off to UI/UX specialist (`@ui-spec-2`) for audit of the canvas crop and lightbox interfaces, followed by clean-room forensic QA gate (`@rc-gate-2`).
