# Reality-Checker Forensic QA Report: KAN-23

## Executive Summary
- Ticket ID: KAN-23 ([KB-P3-AUDIT-17])
- Title: Fix profile display_name wipe on avatar save, harden avatar raster/CSP sandbox, add canvas zoom/pan AvatarCropModal, and add click-to-zoom full-size avatar lightbox
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan23-2313bbdb`
- Target Branch: `feat/KAN-23`
- Reviewer: rc-gate-2 (Clean-Room Forensic QA Gate)
- Review Date: 2026-11-19
- Overall Quality Rating: A
- Production Readiness: READY

---

## Forensic Audit Verification Matrix

### Problem 1: Preserve display_name & Topbar Cache Sync
- Defect: Uploading or deleting an avatar caused the user's uncommitted `display_name` draft to be wiped. In addition, avatar updates failed to synchronize with the topbar user badge without a hard browser reload due to inconsistent response schemas and missing cache invalidation.
- Verification:
  - Inspected `kanban/api/v1/user_settings.py`: Extracted shared `build_me_response` helper returning the canonical 16-field `UserProfileResponse` with a content-hash cache-buster (`avatar_url = /api/v1/users/{id}/avatar?v=<sha256[:12]>`).
  - Unified `GET /api/v1/auth/me`, `PATCH /api/v1/auth/me`, `PUT /api/v1/auth/me/avatar`, and `DELETE /api/v1/auth/me/avatar` to return this identical 16-field structure.
  - Inspected `kanban/web/src/features/settings/PersonalSettingsPage.tsx`: Merged React Query cache data via `setQueryData(['myProfile'], ...)`, invalidated `['myProfile']`, `qk.me()` (`['me']`), and `['auth', 'me']`, and preserved uncommitted user draft inputs (`displayNameInput`, `timezoneInput`).
  - Status: VERIFIED RESOLVED

### Problem 2: Harden Avatar Raster Bounds & Strict CSP
- Defect: Raster processing lacked strict pixel limits and metadata striping, posing decompression bomb and metadata leakage risks. Furthermore, avatar delivery allowed inline styles in its CSP header.
- Verification:
  - Inspected `kanban/attachments/raster.py`:
    - Enforced `MAX_AVATAR_IMAGE_PIXELS = 16_000_000` (16 MP), `MAX_AVATAR_DIMENSION = 4096`, and `MAX_AVATAR_DOWNSCALE_DIMENSION = 1024`.
    - Allowed PIL formats: `PNG`, `JPEG`, `WEBP`. Rejects animated GIF and WebP with HTTP 422.
    - Converted non-RGB modes to RGB and downscaled images exceeding 1024x1024 using high-quality LANCZOS resampling.
    - Completely stripped all EXIF, XMP, and ICC metadata on re-encoding.
  - Inspected `kanban/api/v1/user_settings.py` (`GET /api/v1/users/{principal_id}/avatar`):
    - Configured strict CSP: `Content-Security-Policy: default-src 'none'; sandbox`.
    - Enforced `X-Content-Type-Options: nosniff` and `Cross-Origin-Resource-Policy: same-origin`.
    - Supported conditional HTTP 304 Not Modified responses via `ETag` and `If-None-Match`.
  - Replaced 100% of inline style props in `PersonalSettingsPage.tsx` with dedicated classes in `PersonalSettingsPage.css`.
  - Status: VERIFIED RESOLVED

### Problem 3: Interactive Zero-Dep <canvas> AvatarCropModal
- Defect: Users had no cropping or framing interface when uploading profile pictures, resulting in uncentered, poorly framed avatars.
- Verification:
  - Inspected `kanban/web/src/features/settings/AvatarCropModal.tsx`: Pure HTML5 `<canvas>` implementation without third-party dependencies.
  - Intercepts file picker selection for PNG, JPEG, and WebP images.
  - Displays circular CSS crop guide and semi-transparent vignette framing.
  - Supported zoom/pan controls: 1.0x-4.0x zoom slider, `-` and `+` step buttons, mouse-wheel zoom, 2-pointer pinch-to-zoom, clamped pointer drag-to-pan, and keyboard arrow navigation.
  - Exports a crisp 512x512 raster Blob (`<= 2 MiB`) on Save Picture.
  - Styled exclusively through canonical CSS tokens without inline styles.
  - Status: VERIFIED RESOLVED

### Problem 4: Click-to-Zoom Full-Size Avatar Lightbox
- Defect: Users had no accessible mechanism to inspect their full-resolution profile picture in high detail.
- Verification:
  - Inspected `kanban/web/src/features/settings/PersonalSettingsPage.tsx`: Avatar preview element renders as an accessible `<button type="button" aria-label="Zoom profile picture">` with hover overlay affordance when an avatar is present.
  - Inspected `kanban/web/src/features/settings/AvatarLightboxModal.tsx`: Opens accessible modal with canvas-rendered pan and zoom (1.0x-4.0x), reset view button, backdrop click dismissal, and Escape key handling.
  - Zero inline styles: uses canonical theme design tokens.
  - Status: VERIFIED RESOLVED

---

## Automated Test & Static Analysis Evidence

1. Unit & Integration Tests:
   - Python Pytest: 39 passed in 17.21s (`kanban/tests/attachments/test_sniff_and_raster.py`, `kanban/tests/api/test_user_personal_settings.py`).
     - Line coverage on `kanban/attachments/raster.py`: 95%.
     - Line coverage on `kanban/api/v1/user_settings.py`: 83% (all new helpers and branches covered).
   - Frontend Vitest: 80 passed in 5.84s across touched feature suites (`AvatarCropModal.test.tsx`, `AvatarLightboxModal.test.tsx`, `PersonalSettingsPage.test.tsx`, `personalSettingsApi.test.ts`).
     - Coverage on touched frontend files: 98.98% statements, 96.48% branches, 100% functions, 99.64% lines (all exceed >= 95.10% threshold).
   - CSS Tokens Audit: `cssTokensAudit.test.ts` passed 4 of 4 tests.
   - Raw output logged in `docs/qa/KAN-23/unit-test-results.txt`.

2. Static Analysis & Type Checking:
   - Ruff check: clean (All checks passed).
   - Ruff format check: 1830 files verified clean.
   - Mypy check: Success, no issues found in 524 source files.
   - Import Linter: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database` strictly preserved).
   - TypeScript compiler (`tsc -b --noEmit`): 0 errors.
   - ESLint: 0 warnings, 0 errors (`eslint . --max-warnings 0`).
   - Strict ASCII character check: Zero `\u2014` em-dashes and zero `\u2013` en-dashes across all modified files.
   - Raw output logged in `docs/qa/KAN-23/build-or-typecheck.txt`.

---

## Dual Specialist Gate Audits

1. API Specialist Audit:
   - File: `docs/qa/KAN-23/api-specialist-review.md`
   - Reviewer: `api-spec-2`
   - Status: APPROVED
   - Findings: Verified canonical 16-field profile response unification, cache-buster generation, avatar decompression bomb defense, EXIF metadata sanitization, and strict CSP sandbox transport.

2. UI/UX Specialist Audit:
   - File: `docs/qa/KAN-23/ui-specialist-review.md`
   - Reviewer: `ui-spec-2`
   - Status: APPROVED
   - Findings: Verified circular canvas crop guide, 1.0x-4.0x zoom/pan ergonomics, click-to-zoom full-size lightbox, draft display name preservation, and canonical design token compliance across 16 screenshots.

---

## Visual Proof Artifacts (16 Screenshots Audited)

1. `kan-23-avatar-crop-1.0x-light-desktop.png`: Canvas crop modal at 1.0x zoom (Light, Desktop 1440x900).
2. `kan-23-avatar-crop-1.0x-dark-desktop.png`: Canvas crop modal at 1.0x zoom (Dark, Desktop 1440x900).
3. `kan-23-avatar-crop-1.0x-light-mobile.png`: Canvas crop modal at 1.0x zoom (Light, Mobile 390x844).
4. `kan-23-avatar-crop-1.0x-dark-mobile.png`: Canvas crop modal at 1.0x zoom (Dark, Mobile 390x844).
5. `kan-23-avatar-crop-2.5x-light-desktop.png`: Canvas crop modal at 2.5x zoom (Light, Desktop 1440x900).
6. `kan-23-avatar-crop-2.5x-dark-desktop.png`: Canvas crop modal at 2.5x zoom (Dark, Desktop 1440x900).
7. `kan-23-avatar-crop-2.5x-light-mobile.png`: Canvas crop modal at 2.5x zoom (Light, Mobile 390x844).
8. `kan-23-avatar-crop-2.5x-dark-mobile.png`: Canvas crop modal at 2.5x zoom (Dark, Mobile 390x844).
9. `kan-23-display-name-preserved-light-desktop.png`: Display name draft preserved after avatar upload (Light, Desktop 1440x900).
10. `kan-23-display-name-preserved-dark-desktop.png`: Display name draft preserved after avatar upload (Dark, Desktop 1440x900).
11. `kan-23-display-name-preserved-light-mobile.png`: Display name draft preserved after avatar upload (Light, Mobile 390x844).
12. `kan-23-display-name-preserved-dark-mobile.png`: Display name draft preserved after avatar upload (Dark, Mobile 390x844).
13. `kan-23-avatar-lightbox-light-desktop.png`: Full-size avatar zoom lightbox (Light, Desktop 1440x900).
14. `kan-23-avatar-lightbox-dark-desktop.png`: Full-size avatar zoom lightbox (Dark, Desktop 1440x900).
15. `kan-23-avatar-lightbox-light-mobile.png`: Full-size avatar zoom lightbox (Light, Mobile 390x844).
16. `kan-23-avatar-lightbox-dark-mobile.png`: Full-size avatar zoom lightbox (Dark, Mobile 390x844).

All 16 visual screenshots confirm responsive layout, accessible contrast, and zero layout overflow.

---

## Final Gate Certification
- Overall Quality Rating: A
- Production Readiness: READY
- Recommendation: Proceed to merge into `main` branch.
