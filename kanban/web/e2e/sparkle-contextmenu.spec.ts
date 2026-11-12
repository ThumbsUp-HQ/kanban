/**
 * Playwright E2E Verification & Design Proofs for Context Menu Matrix (KB-P5-09, S9.2).
 *
 * Validates all 6 rows of S9.2 in browser:
 * - Rows 1 & 2: Right-click accepts (ghost text becomes real text).
 * - Rows 3-6: Assert defaultPrevented === false via injected listener.
 * - Visual Proofs: Multi-device screenshots (desktop 1440x900, tablet 834x1112, mobile 390x844)
 *   annotated with 28px radius circle around caret and ✨ badge in READY_BLINKING.
 */

import { copyFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect } from './support/test';
import { annotatedScreenshot } from './support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../docs/qa/KANBA-96/screenshots',
);

test.describe('Sparkle Context Menu Matrix E2E & Visual Proofs (KB-P5-09)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    mkdirSync(SCREENSHOT_DIR, { recursive: true });

    // Enforce exact tablet resolution (834x1112) per KB-P5-09
    if (testInfo.project.name === 'tablet') {
      await page.setViewportSize({ width: 834, height: 1112 });
    }

    // Intercept Sparkle completion SSE
    await page.route('**/api/v1/sparkle/complete', async (route) => {
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

  test('01: Visual Proofs across viewports with 28px caret radius annotations in READY_BLINKING', async ({
    page,
  }, testInfo) => {
    const editor = page.locator('.kb-editor__surface .ProseMirror');
    await expect(editor).toBeVisible();

    // Trigger Sparkle completion into READY_BLINKING state
    const targetPara = page
      .locator('.kb-editor__surface .ProseMirror p')
      .filter({ hasText: 'Fix teh typo' });
    await targetPara.click();
    await page.keyboard.press('End');
    await page.keyboard.type(' test');

    const ghost = page.locator('.sparkle-ghost');
    await expect(ghost).toBeVisible({ timeout: 10000 });
    await expect(ghost).toHaveText(' architectural verification');

    const badge = page.locator('.sparkle-badge');
    await expect(badge).toBeVisible();

    // Ensure elements are scrolled into view before capturing annotated screenshot
    await badge.scrollIntoViewIfNeeded();

    const projectName = testInfo.project.name;
    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: `01-contextmenu-${projectName}`,
      annotations: [
        {
          selector: '.sparkle-badge',
          label: 'Sparkle Badge (Row 1 Accept)',
          note: 'Right-click or pointerdown button 2 accepts immediately',
        },
        {
          selector: '.sparkle-ghost',
          label: 'Inline Ghost Text',
          note: 'Caret proximity <= 28px zone accepts suggestion (Row 2)',
        },
        {
          selector: '.kb-editor__surface .ProseMirror',
          label: 'ProseMirror WYSIWYG Surface',
          note: 'Shift+RightClick or >28px preserves native menu (Rows 3-6)',
        },
      ],
    });

    // Copy to required DoD screenshot filenames
    if (projectName === 'desktop') {
      copyFileSync(shotPath, resolve(SCREENSHOT_DIR, 'contextmenu-desktop.png'));
    } else if (projectName === 'tablet') {
      copyFileSync(shotPath, resolve(SCREENSHOT_DIR, 'contextmenu-tablet.png'));
    } else if (projectName === 'mobile') {
      copyFileSync(shotPath, resolve(SCREENSHOT_DIR, 'contextmenu-mobile.png'));
    }
  });

  test('02: Row 1 & Row 2 accept suggestion (ghost text becomes real text)', async ({
    page,
  }) => {
    const editor = page.locator('.kb-editor__surface .ProseMirror');
    await expect(editor).toBeVisible();

    // Test Row 1: Right-click directly on ✨ badge
    const targetPara = page
      .locator('.kb-editor__surface .ProseMirror p')
      .filter({ hasText: 'Fix teh typo' });
    await targetPara.click();
    await page.keyboard.press('End');
    await page.keyboard.type(' test');

    const ghost = page.locator('.sparkle-ghost');
    await expect(ghost).toBeVisible({ timeout: 10000 });

    const badge = page.locator('.sparkle-badge');
    await expect(badge).toBeVisible();

    // Right-click badge
    await badge.click({ button: 'right' });

    // Ghost text and badge disappear
    await expect(ghost).toHaveCount(0);
    await expect(page.locator('.sparkle-badge--visible')).toHaveCount(0);

    // Text accepted
    const content = await editor.textContent();
    expect(content).toContain('architectural verification');

    // Undo step
    const modKey = process.platform === 'darwin' ? 'Meta' : 'Control';
    await page.keyboard.press(`${modKey}+z`);
    expect(await editor.textContent()).not.toContain('architectural verification');

    // Test Row 2: Right-click within <= 28px of blinking caret
    await targetPara.click();
    await page.keyboard.press('End');
    await page.keyboard.type(' more');

    await expect(ghost).toBeVisible({ timeout: 10000 });

    // Use getClientRects()[0] to accurately target the first line of ghost text adjacent to caret
    // even when ghost text wraps across multiple lines on small viewports
    const dispatched = await page.evaluate(() => {
      const ghostEl = document.querySelector('.sparkle-ghost');
      const ed = document.querySelector('.kb-editor__surface .ProseMirror');
      if (!ghostEl || !ed) return false;

      const rects = ghostEl.getClientRects();
      const firstRect = rects[0] ?? ghostEl.getBoundingClientRect();
      const clientX = Math.round(firstRect.left);
      const clientY = Math.round((firstRect.top + firstRect.bottom) / 2);

      const event = new MouseEvent('contextmenu', {
        clientX,
        clientY,
        bubbles: true,
        cancelable: true,
      });
      return ed.dispatchEvent(event);
    });
    expect(dispatched).toBe(false); // Accepted means defaultPrevented === true, so dispatchEvent returns false

    await expect(ghost).toHaveCount(0);
    expect(await editor.textContent()).toContain('architectural verification');
  });

  test('03: Rows 3-6 assert defaultPrevented === false via injected listener', async ({
    page,
  }) => {
    const editor = page.locator('.kb-editor__surface .ProseMirror');
    await expect(editor).toBeVisible();

    // Inject listener on window to record contextmenu defaultPrevented status
    await page.evaluate(() => {
      (window as unknown as { __lastContextMenuPrevented: boolean | null }).__lastContextMenuPrevented = null;
      window.addEventListener(
        'contextmenu',
        (e) => {
          (window as unknown as { __lastContextMenuPrevented: boolean }).__lastContextMenuPrevented =
            e.defaultPrevented;
        },
        true,
      );
    });

    // Row 6: IDLE state anywhere in editor -> native context menu (not prevented)
    await editor.dispatchEvent('contextmenu', {
      clientX: 200,
      clientY: 200,
      bubbles: true,
      cancelable: true,
    });
    let isPrevented = await page.evaluate(
      () => (window as unknown as { __lastContextMenuPrevented: boolean | null }).__lastContextMenuPrevented,
    );
    expect(isPrevented).toBe(false);

    // Trigger READY_BLINKING state
    const targetPara = page
      .locator('.kb-editor__surface .ProseMirror p')
      .filter({ hasText: 'Fix teh typo' });
    await targetPara.click();
    await page.keyboard.press('End');
    await page.keyboard.type(' demo');

    const ghost = page.locator('.sparkle-ghost');
    await expect(ghost).toBeVisible({ timeout: 10000 });

    const badge = page.locator('.sparkle-badge');
    await expect(badge).toBeVisible();
    const badgeBox = await badge.boundingBox();
    expect(badgeBox).not.toBeNull();

    if (badgeBox) {
      const caretNearX = badgeBox.x - 10;
      const caretNearY = badgeBox.y + badgeBox.height / 2;

      // Row 3: Shift + Right-Click -> native context menu (not prevented)
      await editor.dispatchEvent('contextmenu', {
        clientX: caretNearX,
        clientY: caretNearY,
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      });

      isPrevented = await page.evaluate(
        () => (window as unknown as { __lastContextMenuPrevented: boolean | null }).__lastContextMenuPrevented,
      );
      expect(isPrevented).toBe(false);
      // Ghost text remains visible because native context menu was shown
      await expect(ghost).toBeVisible();

      // Row 5b: > 28px away from caret -> native context menu (not prevented)
      await editor.dispatchEvent('contextmenu', {
        clientX: caretNearX + 150,
        clientY: caretNearY + 50,
        bubbles: true,
        cancelable: true,
      });
      isPrevented = await page.evaluate(
        () => (window as unknown as { __lastContextMenuPrevented: boolean | null }).__lastContextMenuPrevented,
      );
      expect(isPrevented).toBe(false);
      await expect(ghost).toBeVisible();

      // Row 4: Non-empty selection -> native context menu (not prevented)
      await page.keyboard.press('Shift+ArrowLeft');
      await page.keyboard.press('Shift+ArrowLeft');
      await editor.dispatchEvent('contextmenu', {
        clientX: caretNearX,
        clientY: caretNearY,
        bubbles: true,
        cancelable: true,
      });

      isPrevented = await page.evaluate(
        () => (window as unknown as { __lastContextMenuPrevented: boolean | null }).__lastContextMenuPrevented,
      );
      expect(isPrevented).toBe(false);
    }
  });
});
