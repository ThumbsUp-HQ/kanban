/**
 * Playwright E2E for the realtime status chip (KB-P3-33).
 * Forces each connection state via /__dev/realtime and records annotated screenshots plus
 * computed-style proof (chip padding 8px 16px, 24px viewport offset, no overlay).
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const CHIP = '.realtime-status-chip';

test.describe('Realtime status chip (KB-P3-33)', () => {
  test.beforeEach(async ({ page }) => {
    const response = await page.goto('/__dev/realtime');
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="realtime-story"]')).toBeVisible();
    await expect(page.locator(CHIP)).toHaveCount(0);
  });

  test('01: reconnecting chip shows elapsed counter, 24px offset, and no overlay', async ({ page }, testInfo) => {
    const board = page.locator('[data-testid="board-focus-target"]');
    await board.focus();
    await page.locator('[data-testid="force-reconnecting"]').click();

    const chip = page.locator(CHIP);
    await expect(chip).toBeVisible();
    await expect(chip).toHaveText(/^Reconnecting\.\.\./);
    await expect(chip).toHaveAttribute('role', 'status');
    await expect(chip).toHaveText(/Reconnecting\.\.\. [1-9]s/, { timeout: 4000 });

    const box = await chip.boundingBox();
    const viewport = page.viewportSize();
    expect(box).not.toBeNull();
    expect(viewport).not.toBeNull();
    if (box && viewport) {
      expect(Math.round(box.x)).toBe(24);
      expect(Math.round(viewport.height - (box.y + box.height))).toBe(24);
    }

    await probeStyles(page, testInfo, {
      name: 'realtime-chip-reconnecting',
      probes: [{ selector: CHIP, props: ['padding', 'margin', 'position', 'border-radius', 'font-size'] }],
    });

    // Underlying board control must remain interactive: chip does not intercept pointer input.
    await expect(board).toBeVisible();
    await board.click();
    await expect(board).toBeFocused();

    await annotatedScreenshot(page, testInfo, {
      name: '01-reconnecting-chip',
      annotations: [
        { selector: CHIP, label: 'Reconnecting chip', note: 'Text "Reconnecting..." with elapsed counter' },
        { selector: CHIP, label: 'Viewport offset', note: '24px from the bottom-left corner' },
        { selector: '[data-testid="board-focus-target"]', label: 'Interactive content behind', note: 'no overlay' },
      ],
    });
  });

  test('02: sse-fallback chip is a polite status region', async ({ page }, testInfo) => {
    await page.locator('[data-testid="force-sse-fallback"]').click();
    const chip = page.locator(CHIP);
    await expect(chip).toHaveText('Live updates via fallback channel');
    await expect(chip).toHaveAttribute('role', 'status');
    await expect(chip).toHaveAttribute('aria-live', 'polite');

    await annotatedScreenshot(page, testInfo, {
      name: '02-sse-fallback-chip',
      annotations: [
        { selector: CHIP, label: 'Fallback chip', note: 'Text "Live updates via fallback channel"' },
        { selector: CHIP, label: 'role=status', note: 'aria-live polite, from accessibility tree' },
      ],
    });
  });

  test('03: offline chip appears and hides again when open', async ({ page }, testInfo) => {
    await page.locator('[data-testid="force-closed"]').click();
    const chip = page.locator(CHIP);
    await expect(chip).toHaveText('Offline - changes will sync when reconnected');

    await probeStyles(page, testInfo, {
      name: 'realtime-chip-offline',
      probes: [{ selector: CHIP, props: ['padding', 'margin', 'position'] }],
    });

    await annotatedScreenshot(page, testInfo, {
      name: '03-offline-chip',
      annotations: [{ selector: CHIP, label: 'Offline chip', note: 'Text "Offline - changes will sync when reconnected"' }],
    });

    await page.locator('[data-testid="force-open"]').click();
    await expect(chip).toHaveCount(0);
  });

  test('chip never steals focus when state changes', async ({ page }) => {
    const board = page.locator('[data-testid="board-focus-target"]');
    await board.focus();
    await page.evaluate(() => {
      document.querySelector<HTMLButtonElement>('[data-testid="force-closed"]')?.click();
    });
    await expect(page.locator(CHIP)).toBeVisible();
    await expect(board).toBeFocused();
  });
});
