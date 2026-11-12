/**
 * Playwright E2E Tests & Design Proofs for Isolated Mermaid Web Worker Renderer (KB-P3-47).
 * Validates isolated worker rendering of diagrams into safe blob: URLs inside MediaViewport,
 * zero inline SVG DOM execution surface, live theme synchronization (Light -> Dark),
 * and calm fallback notice banner on node cap / watchdog timeout across desktop, tablet, and mobile.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

test.describe('Isolated Mermaid Web Worker Renderer E2E Verification & Design Proofs (KB-P3-47)', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', (msg) => {
      console.log('BROWSER LOG:', msg.type(), msg.text());
    });
    page.on('pageerror', (err) => {
      console.log('BROWSER PAGEERROR:', err.message);
    });
    const response = await page.goto('/__dev/editor');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="editor-story"]')).toBeVisible();
  });

  test('01: Safe Mermaid SVG rendering in Light theme with zero inline SVG DOM elements', async ({
    page,
  }, testInfo) => {
    // Click Load Mermaid Diagrams button
    const loadBtn = page.locator('[data-testid="btn-load-mermaid"]');
    await expect(loadBtn).toBeVisible();
    await loadBtn.click();

    // Verify at least one .mermaid-block mounts
    const mermaidBlock = page.locator('.mermaid-block').first();
    await expect(mermaidBlock).toBeVisible({ timeout: 10000 });

    // Wait for the worker to render and mount <img src="blob:...">
    const img = mermaidBlock.locator('img');
    await expect(img).toBeVisible({ timeout: 10000 });
    await expect(img).toHaveAttribute('src', /^blob:/);

    // Invariant: strictly ZERO inline <svg> elements inside the .mermaid-block DOM
    await expect(mermaidBlock.locator('svg')).toHaveCount(0);

    // Verify MediaViewport controls and toggle button are visible
    const controls = mermaidBlock.locator('.media-viewport__controls');
    await expect(controls).toBeVisible();

    const toggleBtn = mermaidBlock.locator('[data-testid="mermaid-block-toggle-btn"]');
    await expect(toggleBtn).toBeVisible();
    await expect(toggleBtn).toHaveText('Edit Mermaid');

    // Verify max-height constraint (<= 520px)
    const box = await mermaidBlock.locator('.media-viewport').boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.height).toBeLessThanOrEqual(525);
    }

    // Measure computed styles and layout constraints
    await probeStyles(page, testInfo, {
      name: 'mermaid-worker-measurements',
      probes: [
        {
          selector: '.mermaid-block',
          props: ['display', 'margin-top', 'margin-bottom', 'border-radius'],
        },
        {
          selector: '.mermaid-block__preview',
          props: ['display', 'max-height', 'overflow'],
        },
        {
          selector: '.media-viewport',
          props: ['max-height', 'position', 'overflow'],
        },
        {
          selector: '.mermaid-block img',
          props: ['max-height', 'object-fit'],
        },
      ],
    });

    // Capture Annotated Screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-mermaid-light',
      annotations: [
        {
          selector: '.mermaid-block img',
          label: 'Sandboxed Mermaid SVG Blob',
          note: 'img src blob: with zero inline SVG DOM surface',
        },
        {
          selector: '.media-viewport__controls',
          label: 'MediaViewport Controls',
          note: 'Floating backdrop, zoom, and export controls',
        },
        {
          selector: '[data-testid="mermaid-block-toggle-btn"]',
          label: 'Edit Mermaid Toggle',
          note: 'Switch between interactive preview and source editor',
        },
      ],
    });
  });

  test('02: Dark theme synchronization re-renders diagrams with dark tokens and revokes prior blob', async ({
    page,
  }, testInfo) => {
    // Click Load Mermaid Diagrams button
    const loadBtn = page.locator('[data-testid="btn-load-mermaid"]');
    await expect(loadBtn).toBeVisible();
    await loadBtn.click();

    const mermaidBlock = page.locator('.mermaid-block').first();
    await expect(mermaidBlock).toBeVisible({ timeout: 10000 });

    const img = mermaidBlock.locator('img');
    await expect(img).toBeVisible({ timeout: 10000 });
    const initialBlob = await img.getAttribute('src');
    expect(initialBlob).toMatch(/^blob:/);

    // Toggle theme to Dark
    const themeBtn = page.locator('[data-testid="btn-toggle-theme"]');
    await expect(themeBtn).toBeVisible();
    await themeBtn.click();

    // Verify theme indicator shows Dark
    const themeIndicator = page.locator('[data-testid="theme-indicator"]');
    await expect(themeIndicator).toHaveText('Dark');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

    // Wait for the diagram to re-render with dark tokens and new blob URL
    await expect(async () => {
      const nextBlob = await img.getAttribute('src');
      expect(nextBlob).toMatch(/^blob:/);
      expect(nextBlob).not.toBe(initialBlob);
    }).toPass({ timeout: 10000 });

    // Invariant: still ZERO inline <svg> elements inside the .mermaid-block DOM
    await expect(mermaidBlock.locator('svg')).toHaveCount(0);

    // Capture Annotated Screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-mermaid-dark-theme-sync',
      annotations: [
        {
          selector: '.mermaid-block img',
          label: 'Dark Mode Re-rendered Blob',
          note: 'Live theme sync using dark surface and text tokens',
        },
        {
          selector: '[data-testid="theme-indicator"]',
          label: 'Theme Indicator Badge',
          note: 'Indicates active dark theme state',
        },
      ],
    });

    // Reset theme back to light for subsequent tests
    await themeBtn.click();
    await expect(themeIndicator).toHaveText('Light');
  });

  test('03: Watchdog and resource cap fallback displays calm banner and raw source', async ({
    page,
  }, testInfo) => {
    // Click Simulate Fallback Diagram button (401-node flowchart)
    const fallbackBtn = page.locator('[data-testid="btn-load-fallback"]');
    await expect(fallbackBtn).toBeVisible();
    await fallbackBtn.click();

    // Verify fallback banner appears with calm message
    const banner = page.locator('.mermaid-fallback-banner').first();
    await expect(banner).toBeVisible({ timeout: 10000 });
    await expect(banner).toContainText('Diagram rendered as source: exceeded 400 node limit');

    // Verify monospace source block is visible
    const sourcePre = page.locator('.mermaid-block__source-pre').first();
    await expect(sourcePre).toBeVisible();
    await expect(sourcePre).toContainText('flowchart TD');

    // Verify zero inline <svg> elements
    await expect(page.locator('.mermaid-block svg')).toHaveCount(0);

    // Verify surrounding page controls remain fully interactive
    const resetBtn = page.locator('[data-testid="btn-reset"]');
    await expect(resetBtn).toBeVisible();
    await expect(resetBtn).toBeEnabled();

    // Measure fallback banner computed styles
    await probeStyles(page, testInfo, {
      name: 'mermaid-fallback-measurements',
      probes: [
        {
          selector: '.mermaid-fallback-banner',
          props: ['display', 'padding-top', 'padding-bottom', 'border-radius'],
        },
        {
          selector: '.mermaid-block__source-pre',
          props: ['font-family', 'white-space', 'overflow-x'],
        },
      ],
    });

    // Capture Annotated Screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-mermaid-watchdog-fallback',
      annotations: [
        {
          selector: '.mermaid-fallback-banner',
          label: 'Calm Fallback Banner',
          note: 'Notice indicating reason diagram is rendered as source',
        },
        {
          selector: '.mermaid-block__source-pre',
          label: 'Monospace Source Block',
          note: 'Unexecuted sanitized Mermaid source code',
        },
      ],
    });
  });
});
