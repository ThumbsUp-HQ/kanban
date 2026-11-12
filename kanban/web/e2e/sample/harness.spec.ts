import { test, expect } from '../support/test';
import { PRODUCTION_CSP } from '../support/csp';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

test.describe('E2E Harness Smoke and Guard Proofs', () => {
  test('01: loads app root, validates production CSP, captures screenshot and probes styles', async ({
    page,
  }, testInfo) => {
    const response = await page.goto('/');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);

    const cspHeader = response?.headers()['content-security-policy'] ?? '';
    expect(cspHeader).toBe(PRODUCTION_CSP);

    await expect(page).toHaveTitle('Kanban');
    const appRoot = page.locator('[data-testid="app-root"]');
    await expect(appRoot).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-harness-smoke',
      annotations: [
        {
          selector: '[data-testid="app-root"]',
          label: 'App Root',
          note: 'CSP enforced, mock API active',
        },
      ],
    });

    await probeStyles(page, testInfo, {
      name: 'app-root',
      probes: [
        {
          selector: 'body',
          props: ['font-family', 'font-size', 'line-height'],
        },
      ],
    });
  });

  test('02: negative guard proof - unmatched API call fails test', async ({ page }) => {
    test.fail(true, 'Expected failure: unmatched API route triggers test guard failure');
    await page.goto('/');
    await page.evaluate(async () => {
      await fetch('/api/v1/does-not-exist');
    });
  });

  test('03: negative guard proof - inline style CSP violation fails test', async ({ page }) => {
    test.fail(true, 'Expected failure: inline style tag violates CSP and triggers test guard failure');
    await page.goto('/');
    await page.evaluate(() => {
      document.head.appendChild(
        Object.assign(document.createElement('style'), { textContent: 'body{}' }),
      );
    });
  });
});
