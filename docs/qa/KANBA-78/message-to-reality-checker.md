# Forensic Verification Proof Packet: KANBA-78 (KB-P3-48)

- **Ticket:** `KANBA-78` (`KB-P3-48`: `[Phase 3 / Frontend] Client safe SVG blob sanitizer, <MediaViewport> pan/zoom lightbox & external media shield badge`)
- **Author:** `builder-22` (Implementation Author)
- **Worktree:** `/tmp/kb-wt-KANBA-78` on branch `feat/KANBA-78`
- **Base Commit:** `32bd3aa970184890a8256f9f8d18d4b1277b63fb` (feat/KANBA-38)
- **Spec References:** S5.4 (Pictures, Safe SVG Rendering & <MediaViewport> UX), S3.5 (Hostile Media), S6.2 (Extended Emoji Registry & Media Backdrop)
- **Gate Reviews:** `ui-specialist`, `reality-checker`

---

## 1. Executive Summary & Verification Packet

This ticket implements comprehensive client-side vector and raster media rendering hardening, client-side safe SVG sanitization with acyclic `<use>` DAG validation, an interactive `<MediaViewport>` with pan/zoom and Lightbox modal, and external media proxy badges with air-gap mode placeholders.

### Verification Proof Artifacts in `docs/qa/KANBA-78/`

1. `git-diff.patch`: Complete unified diff against base commit `32bd3aa970184890a8256f9f8d18d4b1277b63fb` (160 KB).
2. `unit-test-results.txt`: Vitest unit test suite output verifying 105/105 tests passing with 100% Stmts, 95.43% Branch, 100% Funcs, and 100% Lines coverage across touched modules (`src/editor/media` and `src/components/emoji`). Exit code: 0.
3. `build-check.txt`: Raw outputs of `tsc -b --noEmit` (typecheck), `eslint . --max-warnings 0` (lint, 0 errors, 0 warnings), and `tsc -b && vite build` (production Vite client build). Exit code: 0.
4. `e2e-results.txt`: Playwright E2E suite output verifying 12/12 passing tests across chromium desktop (1440x900), tablet (1024x768), and mobile (390x844) viewports under production CSP. Exit code: 0.
5. `svg-sanitizer-corpus.json`: Structured corpus of 17 test cases documenting raw hostile inputs (<script>, <foreignObject>, <iframe>, <image> tracking pixels, <style> CSS injection, SMIL <animate> attribute mutations, inline event handlers, external <use> hrefs, self/mutual cycles, depth limits, billion-laughs expansion bombs, and byte limits) along with sanitizer verdicts and outputs.
6. `computed-styles-desktop.json`, `computed-styles-tablet.json`, `computed-styles-mobile.json`: Concrete style probes validating container constraints (`.media-viewport` max-height = 520px, `.emoji-hint` = 24px x 24px, `.media-bg--checkerboard` repeating conic gradient).
7. `screenshots/`: 12 annotated high-resolution screenshots across desktop, tablet, and mobile viewports:
   - `01-svg-checkerboard-backdrop-desktop.png`, `01-svg-checkerboard-backdrop-tablet.png`, `01-svg-checkerboard-backdrop-mobile.png`: Dark-stroke SVG diagram in Dark theme toggled to high-contrast checkerboard canvas backdrop.
   - `02-lightbox-pan-zoom-desktop.png`, `02-lightbox-pan-zoom-tablet.png`, `02-lightbox-pan-zoom-mobile.png`: Full-viewport Lightbox modal dialog open at scaled zoom level with accessible close controls and focus trap.
   - `03-external-proxied-badge-desktop.png`, `03-external-proxied-badge-tablet.png`, `03-external-proxied-badge-mobile.png`: External proxied image displaying 🌐 external shield badge and hover tooltip explanation.
   - `04-airgap-media-placeholder-desktop.png`, `04-airgap-media-placeholder-tablet.png`, `04-airgap-media-placeholder-mobile.png`: Air-gap local-only mode rendering 📴 offline placeholder card with zero external network requests.
8. `dependency-evaluation.md`: Supply chain audit and sign-offs for `dompurify@3.4.17` (Apache-2.0 OR MPL-2.0, exact lockfile SHA-256 `a595db411768d7424814230f8c358d44baea0194af56b32501d815fb5d0d5617`, license gate clean, citing Board posts #167, #170, #178).
9. `ui-specialist-review.md`: Dedicated independent review authored by `@ui-specialist`.

---

## 2. Technical Invariants & Verification Checklist

- [x] **Zero Inline SVG DOM Elements:** Invariant strictly asserted by both Vitest unit tests and Playwright E2E tests (`expect(viewport.locator('svg')).toHaveCount(0)`). All SVGs render via `<img src="blob:...">`.
- [x] **Client-Side Safe SVG Sanitizer (`safeSvg.ts`):**
  - Strict SVG tag allowlist (20 tags) and forbidden tags (`script`, `foreignObject`, `iframe`, `image`, `style`, `animate`, `animateTransform`, `animateMotion`, `set`, `feImage`, `filter`).
  - Strips all `style` attributes to comply with strict CSP `style-src 'self'`.
  - Strips all `on*` event handlers and non-fragment `href` / `xlink:href` attributes.
  - Acyclic `<use>` local DAG validation: rejects cycles (`SVG_USE_CYCLE`), enforces max depth <= 4 (`SVG_USE_MAX_DEPTH`), and limits transitive expanded nodes to <= 500 (`SVG_EXPANSION_LIMIT_EXCEEDED`).
  - Enforces 2 MiB byte limit (`SVG_TOO_LARGE`).
  - Integrated with W3C Trusted Types policy (`kanban-sanitizer`) under `require-trusted-types-for 'script'`.
- [x] **Media URL Resolver (`mediaUrlResolver.ts`):**
  - Resolves `attachment://<id>` to signed download endpoint.
  - Rewrites external HTTP/HTTPS URLs to `/api/v1/media-proxy` and sets `isExternalProxied: true`.
  - When `airGapMode` is enabled, returns `airgap-blocked` state with target host and prevents all network requests.
- [x] **Pan & Zoom Controls (`panZoomMath.ts`, `MediaViewport.tsx`, `MediaLightbox.tsx`):**
  - Cursor-centered zoom clamped strictly between 0.10 (10%) and 8.00 (800%) with 1.25x steps.
  - Transforms applied strictly via CSSOM property assignment (`imgRef.current.style.transform = ...`), with zero HTML style attribute injection.
  - Backdrop toggle cycles `theme -> light -> dark -> checkerboard` without mutating `document.documentElement` or global application theme.
  - Full modal `MediaLightbox` with `role="dialog"`, `aria-modal="true"`, focus trapping, and Escape key restoration.
- [x] **ProseMirror NodeViews (`MediaNodeViews.tsx`):**
  - NodeViews for `image` and fenced ```` ```svg ```` blocks rendering inside `<MediaViewport>`.
  - Automatic `blob:` URL revocation on unmount or node destruction.
- [x] **Extended Emoji Registry:**
  - `EXTENDED_EMOJI_REGISTRY.externalMedia`: glyph `🌐`, domain `External Media Shield`, defaultHint `Proxied anonymously via Kanban Media Shield`.
- [x] **Zero Unicode Dashes:**
  - Strictly enforced ASCII hyphens (`-`) across all codebase files, tests, documentation, and proof files.
- [x] **>= 95% Automated Test Coverage:**
  - Unit test coverage: 100% Stmts, 95.43% Branch, 100% Funcs, 100% Lines.
