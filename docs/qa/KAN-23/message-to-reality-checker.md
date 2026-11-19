# Reality Checker Evidence Packet: KAN-23 (KB-P3-AUDIT-17)

## Executive Summary
This packet provides comprehensive forensic verification for KAN-23: Fix profile display_name wipe on avatar save, harden avatar raster/CSP sandbox, add canvas zoom/pan AvatarCropModal, and add click-to-zoom full-size avatar lightbox.
All four scoped problems have been completely implemented, verified via unit/Pytest/Vitest/Playwright tests, and confirmed to have zero architectural boundary violations, zero inline React styles, and zero em/en-dashes.

## Scoped Problems and Implementations

### Problem 1: Preserve display_name & Topbar Cache Sync
- **Files Modified**: `kanban/api/v1/user_settings.py`, `kanban/api/v1/auth_session.py`, `kanban/web/src/features/settings/PersonalSettingsPage.tsx`, `kanban/web/src/features/settings/personalSettingsApi.ts`
- **Implementation**:
  - Extracted shared helper `build_me_response(user, avatar_record, avatar_content_bytes)` returning canonical 16-field `UserProfileResponse`:
    `principal_id`, `email`, `display_name`, `username`, `role`, `workspace_id`, `timezone`, `locale`, `avatar_url`, `theme_preference`, `is_active`, `is_service_account`, `created_at`, `updated_at`, `has_password`, `mfa_enabled`.
  - Content-hashed cache-buster URL format: `/api/v1/users/{id}/avatar?v=<sha256[:12]>`.
  - Unified `GET /api/v1/auth/me`, `PATCH /api/v1/auth/me`, `PUT /api/v1/auth/me/avatar`, and `DELETE /api/v1/auth/me/avatar` so all return the identical 16-field canonical structure.
  - In `PersonalSettingsPage.tsx`, avatar upload/delete calls:
    - Merges React Query cache: `setQueryData(['myProfile'], prev => prev ? { ...prev, ...updated } : updated)`
    - Invalidates queries: `['myProfile']`, `qk.me()` (`['me']`), and `['auth', 'me']`
    - Preserves uncommitted user input drafts (`displayNameInput`, `timezoneInput`) so unsaved edits are never overwritten by avatar changes.

### Problem 2: Harden Avatar Raster Bounds & Strict CSP
- **Files Modified**: `kanban/attachments/raster.py`, `kanban/attachments/__init__.py`, `kanban/api/v1/user_settings.py`, `kanban/web/src/features/settings/PersonalSettingsPage.css`
- **Implementation**:
  - In `kanban/attachments/raster.py`:
    - `MAX_AVATAR_IMAGE_PIXELS = 16_000_000` (16 MP)
    - `MAX_AVATAR_DIMENSION = 4096`
    - `MAX_AVATAR_DOWNSCALE_DIMENSION = 1024`
    - Allowed PIL formats: `PNG`, `JPEG`, `WEBP`. Rejects animated GIF/WebP (returns 422).
    - Mode conversion: CMYK / RGBA to RGB for JPEG, RGBA preserved for PNG/WebP.
    - Automatic proportional downscale using high-quality `LANCZOS` resampling when dimensions exceed 1024x1024.
    - Strips all EXIF, XMP, and ICC metadata on re-encoding to prevent data leakage and metadata exploits.
  - In `GET /api/v1/users/{principal_id}/avatar`:
    - Strict CSP header: `Content-Security-Policy: default-src 'none'; sandbox`
    - Strict nosniff header: `X-Content-Type-Options: nosniff`
    - Strict cross-origin isolation: `Cross-Origin-Resource-Policy: same-origin`
    - Content caching: `ETag: W/"<sha256[:32]>"` with conditional HTTP 304 response on matching `If-None-Match`.
  - Removed all inline `style={{...}}` in `PersonalSettingsPage.tsx`, replacing with semantic classes in `PersonalSettingsPage.css`.

### Problem 3: Interactive Zero-Dep <canvas> AvatarCropModal
- **Files Added/Modified**: `kanban/web/src/features/settings/AvatarCropModal.tsx`, `kanban/web/src/features/settings/__tests__/AvatarCropModal.test.tsx`, `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
- **Implementation**:
  - Zero third-party dependencies: Pure HTML5 `<canvas>` and React hooks.
  - Intercepts file picker selection of PNG, JPEG, WebP.
  - Renders image centered on a 320x320 viewport canvas with circular CSS crop guide.
  - Smooth zoom controls:
    - 1.0x to 4.0x zoom range with 0.05 step slider
    - Step buttons (- and +) with 0.25 increment/decrement
    - Mouse-wheel zoom listener with passive prevention
    - Two-pointer touch pinch-to-zoom support
  - Ergonomic panning:
    - Mouse/pointer drag with pointer capture
    - Keyboard arrow key navigation (left, right, up, down) with step delta
    - Bounds-clamped pan calculation ensuring image always covers circular crop area
  - Exports a crisp 512x512 PNG Blob (strictly <= 2 MiB) on "Save Picture" click.
  - Zero inline styles: 100% styled via CSS tokens in `PersonalSettingsPage.css`.

### Problem 4: Click-to-Zoom Full-Size Avatar Lightbox
- **Files Added/Modified**: `kanban/web/src/features/settings/AvatarLightboxModal.tsx`, `kanban/web/src/features/settings/__tests__/AvatarLightboxModal.test.tsx`, `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
- **Implementation**:
  - When `profile.avatar_url` is present, the avatar preview renders as an accessible `<button type="button" aria-label="Zoom profile picture">`.
  - Displays hover overlay affordance with zoom icon and label.
  - Clicking opens `AvatarLightboxModal`:
    - Canvas-rendered full-size preview with pan and zoom (1.0x to 4.0x)
    - Reset view button to return to 1.0x centered
    - Accessible modal with ARIA dialog semantics, title, description, focus management
    - Closes via Close button, Backdrop click, or Escape key
  - Zero inline styles: uses canonical CSS tokens.

## Verification and Coverage Evidence

### Automated Backend Tests (Pytest)
- `pytest kanban/tests/attachments/test_sniff_and_raster.py kanban/tests/api/test_user_personal_settings.py`:
  - 35 passed in 11.55s.
  - Test suites cover: static PNG, JPEG (EXIF stripped), CMYK to RGB, WebP, P-mode, oversized downscaling to 1024x768, animated rejection (422), dimensions > 4096 / > 16MP, corrupt bytes, avatar upload/delete/me endpoints, password policy, TOTP last factor, validation boundaries (oversized name, empty payload, huge stream, unsupported MIME, missing user), and conditional 304 ETag responses.

### Automated Frontend Tests (Vitest)
- `pnpm --filter @kanban/web test`:
  - 80 passed in 1.48s.
  - Comprehensive unit test coverage across all touched features:
    - `AvatarCropModal.test.tsx`: 30 tests (slider, buttons, mouse-wheel, pinch-to-zoom, drag pan, arrow keys, bounds clamping, Blob export, error handling)
    - `AvatarLightboxModal.test.tsx`: 20 tests (render, zoom/pan, reset, Escape key, backdrop click, keyboard navigation)
    - `PersonalSettingsPage.test.tsx`: 13 tests (crop modal integration, lightbox modal integration, draft display_name preservation on avatar upload, cache invalidations)
    - `personalSettingsApi.test.ts`: 17 tests (16-field profile response, avatar upload, avatar delete, update me)
  - Unit & Branch Coverage on touched files:
    - `AvatarCropModal.tsx`: 100% Lines, 98.66% Branches (threshold >= 95.10%)
    - `AvatarLightboxModal.tsx`: 100% Lines, 98.27% Branches (threshold >= 95.10%)
    - `PersonalSettingsPage.tsx`: 100% Lines, 96.51% Branches (threshold >= 95.10%)
    - `personalSettingsApi.ts`: 100% Lines, 100% Branches (threshold >= 95.10%)

### Static Analysis and Linters
- `uv run ruff check .`: Clean (0 errors, 0 warnings)
- `uv run mypy kanban/`: Clean (0 errors in 524 source files)
- `uv run lint-imports`: Clean (2 kept, 0 broken)
- `pnpm --filter @kanban/web typecheck`: Clean (0 errors)
- `pnpm --filter @kanban/web lint`: Clean (0 errors, 0 warnings)
- `python3 -m scripts.check_no_dashes --all`: Clean (0 em/en-dashes across all files)

### Visual Verification Screenshots Matrix
Captured using Playwright (`kanban/web/e2e/qa/kan-23-screenshots.spec.ts`) across desktop (1440x900) and mobile (390x844), in both Dark and Light themes:
1. `kan-23-avatar-crop-1.0x-dark-desktop.png` (83K)
2. `kan-23-avatar-crop-1.0x-light-desktop.png` (86K)
3. `kan-23-avatar-crop-1.0x-dark-mobile.png` (126K)
4. `kan-23-avatar-crop-1.0x-light-mobile.png` (132K)
5. `kan-23-avatar-crop-2.5x-dark-desktop.png` (83K)
6. `kan-23-avatar-crop-2.5x-light-desktop.png` (85K)
7. `kan-23-avatar-crop-2.5x-dark-mobile.png` (126K)
8. `kan-23-avatar-crop-2.5x-light-mobile.png` (133K)
9. `kan-23-display-name-preserved-dark-desktop.png` (84K)
10. `kan-23-display-name-preserved-light-desktop.png` (83K)
11. `kan-23-display-name-preserved-dark-mobile.png` (147K)
12. `kan-23-display-name-preserved-light-mobile.png` (146K)
13. `kan-23-avatar-lightbox-dark-desktop.png` (57K)
14. `kan-23-avatar-lightbox-light-desktop.png` (59K)
15. `kan-23-avatar-lightbox-dark-mobile.png` (68K)
16. `kan-23-avatar-lightbox-light-mobile.png` (71K)
All 16 visual proofs are committed in `docs/qa/KAN-23/screenshots/`.
