import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';
import type { Page } from '@playwright/test';

/**
 * Scrolls the document layout viewport so the target element appears cleanly
 * below the sticky header without visual viewport clipping in mobile emulation.
 */
async function scrollToTarget(page: Page, selector: string, topOffset = 140): Promise<void> {
  await page.evaluate(
    ({ sel, offset }) => {
      const el = document.querySelector(sel);
      if (el) {
        const rect = el.getBoundingClientRect();
        const targetY = Math.max(0, window.scrollY + rect.top - offset);
        window.scrollTo(0, targetY);
      }
    },
    { sel: selector, offset: topOffset },
  );
}

test.describe('TokenStory E2E Verification & Design Proofs (KB-P3-30)', () => {
  test.beforeEach(async ({ page }) => {
    const response = await page.goto('/__dev/tokens');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="token-story"]')).toBeVisible();
  });

  test('01: token table in light theme', async ({ page }, testInfo) => {
    const optLight = page.locator('[data-testid="theme-option-light"]');
    await optLight.click();
    await expect(optLight).toHaveAttribute('aria-checked', 'true');

    const drawerWCell = page.locator('[data-testid="token-row---drawer-w"] td:nth-child(3)');
    const drawerWText = (await drawerWCell.innerText()).trim();

    await annotatedScreenshot(page, testInfo, {
      name: '01-token-table-light',
      annotations: [
        {
          selector: '[data-testid="token-table-header"]',
          label: 'Token Table Header',
          note: 'Declared vs computed values',
        },
        {
          selector: '[data-testid="token-row---card-pad"]',
          label: '--card-pad Row',
          note: '16px 18px',
        },
        {
          selector: '[data-testid="token-row---drawer-w"]',
          label: '--drawer-w Row',
          note: drawerWText,
        },
        {
          selector: '[data-testid="theme-option-light"]',
          label: 'Theme Switcher',
          note: 'Light active',
        },
      ],
    });
  });

  test('02: spacing ruler layout and computed whitespace proof', async ({ page }, testInfo) => {
    const optLight = page.locator('[data-testid="theme-option-light"]');
    await optLight.click();

    await scrollToTarget(page, '[data-testid="spacing-ruler"]', 140);

    await probeStyles(page, testInfo, {
      name: 'spacing-ruler',
      probes: [
        {
          selector: '[data-testid="ruler-sample-card"]',
          props: ['padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left'],
        },
        {
          selector: '[data-testid="ruler-card-gap-container"]',
          props: ['gap', 'row-gap'],
        },
        {
          selector: '[data-testid="ruler-lane-1"]',
          props: ['width', 'min-width'],
        },
        {
          selector: '[data-testid="ruler-lane-container"]',
          props: ['gap', 'column-gap'],
        },
        {
          selector: '[data-testid="ruler-list-row"]',
          props: ['height'],
        },
        {
          selector: '[data-testid="ruler-prop-row"]',
          props: ['height'],
        },
      ],
    });

    await annotatedScreenshot(page, testInfo, {
      name: '02-spacing-ruler-light',
      annotations: [
        {
          selector: '[data-testid="ruler-sample-card"]',
          label: 'Sample Card Padding',
          note: '16px 18px',
        },
        {
          selector: '[data-testid="ruler-card-gap-container"]',
          label: 'Card Gap',
          note: '12px',
        },
        {
          selector: '[data-testid="ruler-lane-1"]',
          label: 'Lane Width',
          note: '324px',
        },
        {
          selector: '[data-testid="ruler-lane-container"]',
          label: 'Lane Gutter',
          note: '20px',
        },
        {
          selector: '[data-testid="ruler-list-row"]',
          label: 'List Row',
          note: '46px',
        },
        {
          selector: '[data-testid="ruler-prop-row"]',
          label: 'Property Row',
          note: '38px',
        },
      ],
    });
  });

  test('03: dark theme activation and color swatches', async ({ page }, testInfo) => {
    const optDark = page.locator('[data-testid="theme-option-dark"]');
    await optDark.click();
    await expect(optDark).toHaveAttribute('aria-checked', 'true');

    // Confirm html dataset theme is dark
    const htmlTheme = await page.evaluate(() => document.documentElement.dataset.theme);
    expect(htmlTheme).toBe('dark');

    await scrollToTarget(page, '[data-testid="color-swatches"]', 140);

    await annotatedScreenshot(page, testInfo, {
      name: '03-swatches-dark',
      annotations: [
        {
          selector: '[data-testid="swatch---fg-primary"]',
          label: 'Primary FG Swatch',
          note: '>= 7:1 ratio',
        },
        {
          selector: '[data-testid="swatch---accent-primary"]',
          label: 'Accent Primary Swatch',
          note: '>= 4.5:1 ratio',
        },
        {
          selector: '[data-testid="sticky-swatches-container"]',
          label: 'Sticky Swatches',
          note: 'S8.1 6 tones',
        },
        {
          selector: '[data-testid="theme-option-dark"]',
          label: 'Theme Switcher',
          note: 'Dark active',
        },
      ],
    });
  });

  test('04: base typography, mono key, and focus ring', async ({ page }, testInfo) => {
    const prose = page.locator('[data-testid="typography-prose"]');
    await expect(prose).toBeVisible();

    const monoKey = page.locator('[data-testid="typography-mono-key"]');
    await expect(monoKey).toHaveText('KAN-142');

    // Tab into the theme radiogroup to activate :focus-visible ring
    await page.keyboard.press('Tab');

    await scrollToTarget(page, '[data-testid="typography-prose"]', 140);

    await annotatedScreenshot(page, testInfo, {
      name: '04-typography',
      annotations: [
        {
          selector: '[data-testid="typography-prose"]',
          label: 'Prose Paragraph',
          note: '15px / 26px',
        },
        {
          selector: '[data-testid="typography-mono-key"]',
          label: 'Mono Key',
          note: 'JetBrains Mono, tabular-nums',
        },
        {
          selector: '[data-testid="theme-radiogroup"]',
          label: 'Focus Visible Ring',
          note: '2px solid outline',
        },
      ],
    });
  });
});
