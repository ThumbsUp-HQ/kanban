/**
 * Playwright Visual Verification for KAN-7.
 * Captures Light, Dark, Desktop (1440x900), and Mobile (390x844) screenshots
 * of Setup Claim (/setup) and SecondFactorStep recovery code login.
 * Plain ASCII hyphens only. Zero em-dashes or en-dashes.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KAN-7/screenshots');

mkdirSync(SCREENSHOT_DIR, { recursive: true });

const VALID_SETUP_TOKEN = 'kb_setup_' + 'A'.repeat(43);

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KAN-7 Visual Verification & Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan7',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('Capture /setup claim page screenshots', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, {
      'GET /api/v1/setup/status': { json: { initialized: false } },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: false,
          mfa_pending: false,
          csrf_token: 'test-csrf-token-kan7',
        },
      },
    });

    await page.goto(`/setup?token=${VALID_SETUP_TOKEN}`);
    await expect(page.locator('#setup-username')).toBeVisible();

    // Fill sample values for clear visual demonstration
    await page.fill('#setup-display-name', 'Admin User');
    await page.fill('#setup-username', 'admin');
    await page.fill('#setup-email', 'admin@example.com');

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-7-setup-claim-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-7-setup-claim-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('Capture SecondFactorStep recovery code login screenshots', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, {
      'GET /api/v1/setup/status': { json: { initialized: true } },
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: true,
          principal_id: '11111111-1111-4111-8111-111111111111',
          session_id: 'session-mfa-kan7',
          aal_level: 1,
          mfa_pending: true,
          csrf_token: 'test-csrf-token-kan7',
        },
      },
    });

    await page.goto('/login');
    await expect(page.locator('[data-testid="second-factor-step"]')).toBeVisible();

    // Click Recovery code tab
    await page.click('button[role="tab"]:has-text("Recovery code")');
    await expect(page.locator('#recovery-code-input')).toBeVisible();

    // Enter a sample recovery code format
    await page.fill('#recovery-code-input', 'AAAA-1111-BBBB-2222');

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-7-second-factor-recovery-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-7-second-factor-recovery-dark-${projectName}.png`),
      fullPage: true,
    });
  });
});
