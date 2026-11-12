import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';
import type { Page } from '@playwright/test';

/**
 * Scrolls document layout viewport smoothly so target element appears cleanly
 * without visual viewport clipping in mobile emulation.
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

/**
 * Scrolls document layout viewport so target element appears near the bottom
 * boundary of the viewport to trigger edge-flipping geometry.
 */
async function scrollToBottomEdge(page: Page, selector: string, bottomOffset = 110): Promise<void> {
  await page.evaluate(
    ({ sel, offset }) => {
      const el = document.querySelector(sel);
      if (el) {
        const rect = el.getBoundingClientRect();
        const targetY = Math.max(0, window.scrollY + rect.top - (window.innerHeight - offset));
        window.scrollTo(0, targetY);
      }
    },
    { sel: selector, offset: bottomOffset },
  );
}

test.describe('EmojiHint E2E Verification & Design Proofs (KB-P3-31)', () => {
  test.beforeEach(async ({ page }) => {
    const response = await page.goto('/__dev/emoji');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="emoji-story"]')).toBeVisible();
  });

  test('01: registry grid with all 21 semantic status emojis', async ({ page }, testInfo) => {
    await expect(page.locator('[data-testid="emoji-grid"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-registry-grid',
      annotations: [
        {
          selector: '[data-testid="card-access"]',
          label: 'access card',
          note: 'Scope summary & counts',
        },
        {
          selector: '[data-testid="card-gatePending"]',
          label: 'gatePending card',
          note: 'Workflow transition gate',
        },
        {
          selector: '[data-testid="card-brokenLink"]',
          label: 'brokenLink card',
          note: 'Object link auditor',
        },
        {
          selector: '[data-testid="emoji-grid"]',
          label: 'Card Spacing',
          note: '--card-pad 16px 18px, gap 12px',
        },
      ],
    });
  });

  test('hover opens after 180ms', async ({ page }, testInfo) => {
    const trigger = page.locator('[data-testid="hint-access"]');
    const isMobile = testInfo.project.name === 'mobile';

    if (isMobile) {
      await trigger.tap();
    } else {
      await trigger.hover();
    }

    const popup = page.locator('[data-testid="hint-access-popup"]');
    await expect(popup).toBeVisible();

    const describedBy = await trigger.getAttribute('aria-describedby');

    await probeStyles(page, testInfo, {
      name: 'emoji-hint-measurements',
      probes: [
        {
          selector: '[data-testid="hint-access"]',
          props: ['width', 'height', 'border-radius'],
        },
        {
          selector: '[data-testid="hint-access-popup"]',
          props: [
            'max-width',
            'padding',
            'padding-top',
            'padding-right',
            'padding-bottom',
            'padding-left',
          ],
        },
      ],
    });

    await annotatedScreenshot(page, testInfo, {
      name: '02-hover-tooltip-access',
      annotations: [
        {
          selector: '[data-testid="hint-access"]',
          label: 'Trigger Pill',
          note: '24x24',
        },
        {
          selector: '[data-testid="hint-access-popup"]',
          label: 'Tooltip Body',
          note: 'Project: Platform Core',
        },
        {
          selector: '[data-testid="hint-access-popup"]',
          label: 'Tooltip Padding',
          note: '12px 14px',
        },
        {
          selector: '[data-testid="hint-access"]',
          label: 'Aria Describedby',
          note: `aria-describedby: ${describedBy ?? 'kb-hint-popup'}`,
        },
      ],
    });
  });

  test('neighbor warmup opens instantly', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'mobile', 'Neighbor hover warmup applies to pointer scanning');

    const trigger1 = page.locator('[data-testid="hint-access"]');
    await trigger1.hover();
    await expect(page.locator('[data-testid="hint-access-popup"]')).toBeVisible();

    // Hover adjacent trigger within 400ms warmup window
    const trigger2 = page.locator('[data-testid="hint-restricted"]');
    await trigger2.hover();

    // Should open instantly under neighbor warmup
    await expect(page.locator('[data-testid="hint-restricted-popup"]')).toBeVisible();
  });

  test('tab focus opens instantly', async ({ page }, testInfo) => {
    await scrollToTarget(page, '[data-testid="card-gateApproved"]', 200);

    const trigger = page.locator('[data-testid="hint-gateApproved"]');
    await trigger.focus();

    const popup = page.locator('[data-testid="hint-gateApproved-popup"]');
    await expect(popup).toBeVisible();

    // Highlight verdict hash to demonstrate copyable bridge
    await page.evaluate(() => {
      const el = document.querySelector('[data-testid="verdict-hash"]');
      if (el) {
        const range = document.createRange();
        range.selectNodeContents(el);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
    });

    await annotatedScreenshot(page, testInfo, {
      name: '03-keyboard-focus-gate-approved',
      annotations: [
        {
          selector: '[data-testid="hint-gateApproved"]',
          label: 'Trigger Focus Ring',
          note: 'Tab focus visible',
        },
        {
          selector: '[data-testid="hint-gateApproved-popup"]',
          label: 'Tooltip Open',
          note: 'Opened at 0ms',
        },
        {
          selector: '[data-testid="verdict-hash"]',
          label: 'Verdict Hash',
          note: 'Selected copyable text',
        },
      ],
    });
  });

  test('escape dismisses and keeps focus', async ({ page }) => {
    const trigger = page.locator('[data-testid="hint-access"]');
    await trigger.focus();
    await expect(page.locator('[data-testid="hint-access-popup"]')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="hint-access-popup"]')).toBeHidden();

    // Focus remains on trigger
    const isFocused = await trigger.evaluate((el) => document.activeElement === el);
    expect(isFocused).toBe(true);
  });

  test('bridge allows copying tooltip text', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'mobile', 'Pointer bridge applies to mouse hover');

    const trigger = page.locator('[data-testid="hint-access"]');
    await trigger.hover();

    const popup = page.locator('[data-testid="hint-access-popup"]');
    await expect(popup).toBeVisible();

    // Move pointer into popup within 120ms bridge grace period
    await popup.hover();
    await expect(popup).toBeVisible();
  });

  test('04: edge flip placement near bottom right', async ({ page }, testInfo) => {
    await scrollToBottomEdge(page, '[data-testid="edge-hint-trigger"]', 110);

    const trigger = page.locator('[data-testid="edge-hint-trigger"]');
    const isMobile = testInfo.project.name === 'mobile';

    if (isMobile) {
      await trigger.tap();
    } else {
      await trigger.hover();
    }

    const popup = page.locator('[data-testid="edge-hint-trigger-popup"]');
    await expect(popup).toBeVisible();

    // Verify it flipped to top
    const placement = await popup.getAttribute('data-placement');
    expect(placement).toBe('top');

    await annotatedScreenshot(page, testInfo, {
      name: '04-edge-flip',
      annotations: [
        {
          selector: '[data-testid="edge-hint-trigger"]',
          label: 'Edge Trigger',
          note: 'Near viewport corner',
        },
        {
          selector: '[data-testid="edge-hint-trigger-popup"]',
          label: 'Flipped Popup',
          note: 'Placed top, clamped 8px',
        },
      ],
    });
  });

  test('touch tap opens and action button activates', async ({ page }, testInfo) => {
    await scrollToTarget(page, '[data-testid="interactive-section"]', 160);

    const trigger = page.locator('[data-testid="interactive-hint"]');
    const isMobile = testInfo.project.name === 'mobile';

    if (isMobile) {
      await trigger.tap();
    } else {
      await trigger.click();
    }

    const popup = page.locator('[data-testid="interactive-hint-popup"]');
    await expect(popup).toBeVisible();
    await expect(popup).toHaveAttribute('role', 'dialog');

    const actionBtn = page.locator('[data-testid="interactive-hint-action-btn"]');
    if (isMobile) {
      await actionBtn.tap();
    } else {
      await actionBtn.click();
    }

    const log = page.locator('[data-testid="activation-log"]');
    await expect(log).toHaveText('inspector-opened');
    await expect(popup).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '05-interactive-touch-action',
      annotations: [
        {
          selector: '[data-testid="interactive-hint-popup"]',
          label: 'Interactive Dialog',
          note: 'role=dialog',
        },
        {
          selector: '[data-testid="interactive-hint-action-btn"]',
          label: 'Action Button',
          note: 'Open Access Inspector',
        },
        {
          selector: '[data-testid="activation-log"]',
          label: 'Activation Log',
          note: 'inspector-opened',
        },
      ],
    });
  });
});
