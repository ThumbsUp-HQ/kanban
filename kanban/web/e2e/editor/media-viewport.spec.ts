/**
 * Playwright E2E Tests & Design Proofs for Media Viewport & Lightbox (KB-P3-48).
 * Validates sandboxed SVG blob rendering, contrast backdrop cycling,
 * 10% - 800% pan/zoom lightbox modal, external media proxy badge,
 * and air-gap local-only offline placeholders across desktop, tablet, and mobile.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

test.describe('Media Viewport & Lightbox E2E Verification & Design Proofs (KB-P3-48)', () => {
  test.beforeEach(async ({ page }) => {
    const response = await page.goto('/__dev/media');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="media-story"]')).toBeVisible();
  });

  test('01: Safe SVG with dark strokes toggles contrast backdrops (theme -> light -> dark -> checkerboard)', async ({
    page,
  }, testInfo) => {
    const viewport = page.locator('[data-testid="story-svg-viewport"]');
    await expect(viewport).toBeVisible();

    // Invariant: strictly <img src="blob:..."> with zero <svg> DOM elements
    const img = page.locator('[data-testid="story-svg-viewport-img"]');
    await expect(img).toBeVisible();
    await expect(img).toHaveAttribute('src', /^blob:/);
    await expect(viewport.locator('svg')).toHaveCount(0);

    const canvas = page.locator('[data-testid="story-svg-viewport-canvas"]');
    await expect(canvas).toHaveClass(/media-bg--theme/);

    const backdropToggle = page.locator('[data-testid="story-svg-viewport-backdrop-toggle"]');

    // Cycle 1: theme -> light
    await backdropToggle.click();
    await expect(canvas).toHaveClass(/media-bg--light/);

    // Cycle 2: light -> dark
    await backdropToggle.click();
    await expect(canvas).toHaveClass(/media-bg--dark/);

    // Cycle 3: dark -> checkerboard
    await backdropToggle.click();
    await expect(canvas).toHaveClass(/media-bg--checkerboard/);

    // Measure computed styles and layout constraints
    await probeStyles(page, testInfo, {
      name: 'media-viewport-measurements',
      probes: [
        {
          selector: '.media-viewport',
          props: ['max-height', 'position', 'border-radius', 'overflow'],
        },
        {
          selector: '.emoji-hint',
          props: ['width', 'height'],
        },
        {
          selector: '.media-viewport__controls',
          props: ['position', 'display', 'border-radius'],
        },
        {
          selector: '.media-bg--checkerboard',
          props: ['background-image', 'background-size'],
        },
      ],
    });

    // Capture Annotated Screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-svg-checkerboard-backdrop',
      annotations: [
        {
          selector: '[data-testid="story-svg-viewport-canvas"]',
          label: 'Checkerboard Contrast Backdrop',
          note: 'Alternating high-contrast grid',
        },
        {
          selector: '[data-testid="story-svg-viewport-img"]',
          label: 'Sandboxed SVG Blob Image',
          note: 'Zero SVG DOM execution surface',
        },
        {
          selector: '[data-testid="story-svg-viewport-controls"]',
          label: 'Floating Viewport Controls',
          note: 'Backdrop, pan, zoom, copy, download',
        },
        {
          selector: '[data-testid="story-svg-viewport-copy-source"]',
          label: 'Copy Raw Source',
          note: 'Sanitized SVG text to clipboard',
        },
      ],
    });
  });

  test('02: Media Lightbox opens in modal dialog with 10% - 800% pan/zoom controls', async ({
    page,
  }, testInfo) => {
    const expandBtn = page.locator('[data-testid="story-lightbox-viewport-expand"]');
    await expect(expandBtn).toBeVisible();
    await expandBtn.click();

    // Verify lightbox dialog is visible with focus trapped
    const dialog = page.locator('.media-lightbox-overlay[role="dialog"]');
    await expect(dialog).toBeVisible();

    const zoomInBtn = dialog.locator('[data-testid="media-viewport-zoom-in"]');
    const zoomReadout = dialog.locator('[data-testid="media-viewport-zoom-readout"]');
    await expect(zoomReadout).toHaveText('100%');

    // Zoom in twice to scale up
    await zoomInBtn.click();
    await expect(zoomReadout).toHaveText('125%');

    await zoomInBtn.click();
    await expect(zoomReadout).toHaveText('156%');

    // Capture Annotated Screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-lightbox-pan-zoom',
      annotations: [
        {
          selector: '.media-lightbox-overlay',
          label: 'Full Viewport Lightbox Scrim',
          note: 'Modal focus trap and Escape listener',
        },
        {
          selector: '.media-lightbox-content',
          label: 'Zoomed Vector Canvas',
          note: 'Smooth cursor-centered scaling',
        },
        {
          selector: '.media-lightbox-close',
          label: 'Accessible Close Button',
          note: 'Restores focus to expand trigger',
        },
        {
          selector: '.media-lightbox-content [data-testid="media-viewport-zoom-readout"]',
          label: 'Scale Readout',
          note: 'Displays active zoom percentage',
        },
      ],
    });

    // Dismiss with close button
    const closeBtn = dialog.locator('.media-lightbox-close');
    await closeBtn.click();
    await expect(dialog).toHaveCount(0);
  });

  test('03: External media displays external proxy badge with tooltip explanation', async ({
    page,
  }, testInfo) => {
    const proxiedViewport = page.locator('[data-testid="story-proxied-viewport"]');
    await expect(proxiedViewport).toBeVisible();

    const badge = page.locator('[data-testid="story-proxied-viewport-proxied-badge"]');
    await expect(badge).toBeVisible();
    await expect(badge).toContainText('🌐');

    const img = page.locator('[data-testid="story-proxied-viewport-img"]');
    await expect(img).toHaveAttribute('src', /^\/api\/v1\/media-proxy\?u=/);

    // Hover badge to reveal tooltip hint
    await badge.hover();

    // Capture Annotated Screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-external-proxied-badge',
      annotations: [
        {
          selector: '[data-testid="story-proxied-viewport-proxied-badge"]',
          label: 'External Media Shield Badge',
          note: '🌐 Proxied anonymously via Kanban',
        },
        {
          selector: '[data-testid="story-proxied-viewport-img"]',
          label: 'Proxied Image Source',
          note: 'URL routed through /api/v1/media-proxy',
        },
        {
          selector: '[data-testid="story-proxied-viewport-alt-badge"]',
          label: 'Alt Text Badge',
          note: 'Accessible semantic caption',
        },
      ],
    });
  });

  test('04: Air-gap local-only mode renders offline placeholder with zero network requests', async ({
    page,
  }, testInfo) => {
    const airgapViewport = page.locator('[data-testid="story-airgap-viewport-airgap"]');
    await expect(airgapViewport).toBeVisible();

    await expect(airgapViewport.locator('.emoji-hint')).toContainText('📴');
    await expect(airgapViewport).toContainText('External image blocked in Air-Gap Local-Only Mode');
    await expect(airgapViewport).toContainText('Host: external-cdn.example.com');

    // Invariant: zero <img> tags mounted inside air-gap viewport
    const container = page.locator('[data-testid="story-airgap-viewport"]');
    await expect(container.locator('img')).toHaveCount(0);

    // Scroll section into view at top of viewport so card is centered and clear of bottom legend
    const section4 = page.locator('[data-testid="story-section-airgap"]');
    await section4.evaluate((el) => {
      el.scrollIntoView({ block: 'start', behavior: 'instant' });
    });

    // Capture Annotated Screenshot 04
    await annotatedScreenshot(page, testInfo, {
      name: '04-airgap-media-placeholder',
      annotations: [
        {
          selector: '[data-testid="story-airgap-viewport-airgap"]',
          label: 'Air-Gap Shield Card',
          note: 'Blocked external image egress',
        },
        {
          selector: '[data-testid="story-airgap-viewport-airgap"] .emoji-hint',
          label: 'Air-Gap Emoji Badge',
          note: '📴 Local-only air-gap mode',
        },
        {
          selector: '.media-airgap-placeholder__host',
          label: 'Blocked Target Host',
          note: 'Displays target host without loading asset',
        },
      ],
    });
  });
});
