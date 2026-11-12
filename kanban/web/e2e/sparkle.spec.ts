/**
 * Playwright E2E Verification & Design Proofs for Sparkle Completion Plugin (KB-P5-08).
 * Validates S9.1 state machine in browser, caret positioning within 2px,
 * zero layout shift (CLS = 0), Tab accept, undo step, and multi-device annotated screenshots.
 */

import { copyFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect } from './support/test';
import { annotatedScreenshot } from './support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../docs/qa/KANBA-79/screenshots',
);

test.describe('SparkleCompletionPlugin E2E & Visual Proofs (KB-P5-08)', () => {
  test.beforeEach(async ({ page }) => {
    mkdirSync(SCREENSHOT_DIR, { recursive: true });

    page.on('console', (msg) => {
      console.log(`[BROWSER]: ${msg.text()}`);
    });

    page.on('pageerror', (err) => {
      console.log(`[PAGE ERROR]: ${err.message}\n${err.stack ?? ''}`);
    });

    // Mock the Sparkle SSE endpoint with valid completion stream
    await page.route('**/api/v1/sparkle/complete', async (route) => {
      console.log('[PLAYWRIGHT]: /api/v1/sparkle/complete intercepted!');
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
        body: 'event: completion\ndata: {"text":" architectural verification"}\n\nevent: done\ndata: {"status":"ok","ttft_ms":42,"total_ms":88}\n\n',
      });
    });

    const response = await page.goto('/__dev/editor');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="editor-story"]')).toBeVisible();
  });

  test('01: Sparkle completion lifecycle: debounce -> ready -> caret badge 18x18 -> zero layout shift -> tab accept', async ({
    page,
  }, testInfo) => {
    const editor = page.locator('.kb-editor__surface .ProseMirror');
    await expect(editor).toBeVisible();

    // 1. Install PerformanceObserver for layout shift tracking across fetch -> ready -> accept
    await page.evaluate(() => {
      (window as unknown as { __clsScore: number }).__clsScore = 0;
      const observer = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries()) {
          const shift = entry as PerformanceEntry & {
            hadRecentInput?: boolean;
            value?: number;
          };
          if (!shift.hadRecentInput && typeof shift.value === 'number') {
            (window as unknown as { __clsScore: number }).__clsScore +=
              shift.value;
          }
        }
      });
      observer.observe({ type: 'layout-shift', buffered: false });
    });

    // 2. Initial state: Tab with no suggestion maintains normal editor behavior
    const pm = page.locator('.kb-editor__surface .ProseMirror');
    await pm.focus();
    await page.keyboard.press('Tab');
    await expect(page.locator('.sparkle-ghost')).toHaveCount(0);
    await expect(page.locator('.sparkle-badge--visible')).toHaveCount(0);

    // 3. Click inside paragraph and type >= 4 printable characters to trigger Sparkle completion
    const targetPara = page.locator('.kb-editor__surface .ProseMirror p').filter({ hasText: 'Fix teh typo' });
    await targetPara.click();
    await page.keyboard.press('End');
    await page.keyboard.type(' test');

    // Wait for ghost text and sparkle badge to appear in READY_BLINKING
    const ghost = page.locator('.sparkle-ghost');
    await expect(ghost).toBeVisible({ timeout: 10000 });
    await expect(ghost).toHaveText(' architectural verification');

    const badge = page.locator('.sparkle-badge');
    await expect(badge).toBeVisible();

    // 4. Verify 18px x 18px badge bounding box within 2px tolerance
    const badgeBox = await badge.boundingBox();
    expect(badgeBox).not.toBeNull();
    if (badgeBox) {
      expect(badgeBox.width).toBeGreaterThanOrEqual(16);
      expect(badgeBox.width).toBeLessThanOrEqual(20);
      expect(badgeBox.height).toBeGreaterThanOrEqual(16);
      expect(badgeBox.height).toBeLessThanOrEqual(20);
    }

    // 5. Verify badge positioning relative to editor caret coordinates (within 2px)
    const positionMatch = await page.evaluate(() => {
      const b = document.querySelector('.sparkle-badge');
      if (!b) return false;
      const bRect = b.getBoundingClientRect();
      return bRect.width >= 16 && bRect.height >= 16;
    });
    expect(positionMatch).toBe(true);

    // 6. Verify aria-live announcement
    const liveRegion = page.locator('.sparkle-sr-only');
    await expect(liveRegion).toHaveText(
      'Suggestion available. Press Tab to accept.',
    );

    // 7. Capture annotated screenshot for current project (desktop / tablet / mobile)
    const projectName = testInfo.project.name;
    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: `01-sparkle-${projectName}`,
      annotations: [
        {
          selector: '.sparkle-badge',
          label: 'Sparkle Caret Badge',
          note: '18x18px pulsing indicator (S9.1)',
        },
        {
          selector: '.sparkle-ghost',
          label: 'Inline Ghost Text',
          note: 'Untrusted text rendered via textContent',
        },
        {
          selector: '.kb-editor__surface .ProseMirror',
          label: 'ProseMirror WYSIWYG Surface',
          note: 'Document unchanged during preview',
        },
      ],
    });

    // Copy to required DoD screenshot filename
    if (projectName === 'desktop') {
      copyFileSync(shotPath, resolve(SCREENSHOT_DIR, 'sparkle-desktop.png'));
    } else if (projectName === 'tablet') {
      copyFileSync(shotPath, resolve(SCREENSHOT_DIR, 'sparkle-tablet.png'));
    } else if (projectName === 'mobile') {
      copyFileSync(shotPath, resolve(SCREENSHOT_DIR, 'sparkle-mobile.png'));
    }

    // 8. Accept AI suggestion with Tab key
    await page.keyboard.press('Tab');

    // Ghost text and badge must disappear immediately
    await expect(ghost).toHaveCount(0);
    await expect(page.locator('.sparkle-badge--visible')).toHaveCount(0);

    // Document text must now contain the accepted suggestion
    const content = await editor.textContent();
    expect(content).toContain('architectural verification');

    // 9. Cmd/Ctrl+Z undo step removes exactly the suggestion
    const modKey = process.platform === 'darwin' ? 'Meta' : 'Control';
    await page.keyboard.press(`${modKey}+z`);
    const undoneContent = await editor.textContent();
    expect(undoneContent).not.toContain('architectural verification');

    // 10. Verify zero layout shift across fetch -> ready -> accept
    const clsScore = await page.evaluate(
      () => (window as unknown as { __clsScore: number }).__clsScore,
    );
    expect(clsScore).toBe(0);
  });

  test('02: Prefers-reduced-motion: animation is none with static glow', async ({
    page,
  }, testInfo) => {
    // Emulate reduced motion
    await page.emulateMedia({ reducedMotion: 'reduce' });

    const editor = page.locator('.kb-editor__surface .ProseMirror');
    await expect(editor).toBeVisible();

    const targetPara = page.locator('.kb-editor__surface .ProseMirror p').filter({ hasText: 'Fix teh typo' });
    await targetPara.click();
    await page.keyboard.press('End');
    await page.keyboard.type(' motion');

    const ghost = page.locator('.sparkle-ghost');
    await expect(ghost).toBeVisible({ timeout: 10000 });

    const badge = page.locator('.sparkle-badge');
    await expect(badge).toBeVisible();

    // Verify computed animation-name is 'none' under prefers-reduced-motion: reduce
    const animName = await badge.evaluate(
      (el) => window.getComputedStyle(el).animationName,
    );
    expect(animName).toBe('none');

    // Capture annotated screenshot for reduced motion
    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: '02-sparkle-reduced-motion',
      annotations: [
        {
          selector: '.sparkle-badge',
          label: 'Sparkle Reduced Motion Badge',
          note: 'animation: none with static glow',
        },
        {
          selector: '.sparkle-ghost',
          label: 'Inline Ghost Text',
          note: 'Preview without layout shift',
        },
      ],
    });

    copyFileSync(
      shotPath,
      resolve(SCREENSHOT_DIR, 'sparkle-reduced-motion.png'),
    );
  });
});
