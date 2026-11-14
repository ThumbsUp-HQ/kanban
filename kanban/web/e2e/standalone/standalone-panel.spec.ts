/**
 * Playwright E2E & Visual Verification for Standalone Status Panel (KB-P3-52 / KANBA-117).
 * Tests volume persistence, sandbox disclosure, encrypted backup, and compose export across viewports.
 * Captures 3 annotated screenshots and probes computed styles.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';
import { mockApi, loadFixture } from '../support/mockApi';

/**
 * Robustly opens the standalone panel across desktop (direct click) and mobile/tablet (touch popover action).
 */
async function openStandalonePanel(page: Page): Promise<void> {
  const warnPill = page.locator('.emoji-hint', { hasText: '⚠️' }).first();
  await expect(warnPill).toBeVisible();
  await warnPill.click();

  const actionBtn = page.locator('.emoji-hint-action-btn');
  if (await actionBtn.isVisible({ timeout: 500 }).catch(() => false)) {
    await actionBtn.click();
  }
}

test.describe('Standalone Status Panel E2E (KB-P3-52 / KANBA-117)', () => {
  test('01: ephemeral storage warning, sandbox status, backup trigger and style probes', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/system/status': { json: loadFixture('standalone-detail-ephemeral') },
      'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/issues': { json: loadFixture('issues-kan') },
      'GET /api/v1/users/me': { json: loadFixture('me-adam') },
      'GET /api/v1/admin/standalone/compose-export': { json: loadFixture('compose-export-sample') },
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 1. Open standalone status panel
    await openStandalonePanel(page);

    const dialog = page.locator('.standalone-panel');
    await expect(dialog).toBeVisible();
    await expect(page.locator('.standalone-panel__warn-banner')).toBeVisible();
    await expect(page.locator('.standalone-panel__backup-form')).toBeVisible();

    // 2. Probe computed styles (dialog 24px padding, 24px gap, 24x24 pill, warn colors)
    await probeStyles(page, testInfo, {
      name: 'standalone-panel',
      probes: [
        {
          selector: '.standalone-panel',
          props: [
            'padding',
            'padding-top',
            'padding-right',
            'padding-bottom',
            'padding-left',
            'gap',
            'width',
            'max-height',
            'border-radius',
            'background-color',
            'color',
          ],
        },
        {
          selector: '.standalone-panel__warn-banner',
          props: [
            'background-color',
            'color',
            'padding',
            'gap',
            'border-radius',
            'font-size',
            'line-height',
          ],
        },
        {
          selector: '.emoji-hint',
          props: ['width', 'height', 'display', 'align-items', 'justify-content'],
        },
      ],
    });

    // 3. Capture screenshot 01: ephemeral admin
    await annotatedScreenshot(page, testInfo, {
      name: '01-standalone-ephemeral-admin',
      annotations: [
        {
          selector: '.emoji-hint:has-text("⚠️")',
          label: '⚠️ Header Pill',
          note: '24x24px warning trigger in topbar',
        },
        {
          selector: '.standalone-panel__warn-banner',
          label: 'Ephemeral Storage Warning',
          note: 'overlayfs detected; copyable docker run command',
        },
        {
          selector: '.standalone-panel__sandbox-row',
          label: 'Sandbox Status',
          note: 'SANDBOX_UNAVAILABLE_IN_STANDALONE disclosure',
        },
        {
          selector: '.standalone-panel__backup-form',
          label: 'Encrypted Database Backup',
          note: 'AES-256-GCM .kbkp export trigger with min 16-char passphrase',
        },
      ],
    });
  });

  test('02: compose export tab and PostgreSQL 16 promotion checklist', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/system/status': { json: loadFixture('standalone-detail-ephemeral') },
      'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/issues': { json: loadFixture('issues-kan') },
      'GET /api/v1/users/me': { json: loadFixture('me-adam') },
      'GET /api/v1/admin/standalone/compose-export': { json: loadFixture('compose-export-sample') },
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await openStandalonePanel(page);

    const composeSection = page.locator('.standalone-panel__compose-container');
    await expect(composeSection).toBeVisible();

    const downloadBtn = page.locator('button:has-text("Download docker-compose.yml")');
    await expect(downloadBtn).toBeVisible();

    const checklist = page.locator('.standalone-panel__checklist-card');
    await expect(checklist).toBeVisible();

    // Capture screenshot 02: compose export section
    await annotatedScreenshot(page, testInfo, {
      name: '02-standalone-compose-export',
      annotations: [
        {
          selector: 'button:has-text("Download docker-compose.yml")',
          label: 'Download Compose',
          note: '1-click production docker-compose.yml export',
        },
        {
          selector: '.standalone-panel__checklist-card',
          label: 'Promotion Runbook',
          note: '4-step PostgreSQL 16 migration runbook preview',
        },
      ],
    });
  });

  test('03: persistent volume verified status and non-admin redaction', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/system/status': { json: loadFixture('standalone-detail-persistent') },
      'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/issues': { json: loadFixture('issues-kan') },
      'GET /api/v1/users/me': { json: loadFixture('me-adam') },
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await openStandalonePanel(page);

    const dialog = page.locator('.standalone-panel');
    await expect(dialog).toBeVisible();

    // Verify calm persistent badge
    const persistentBadge = page.locator('.standalone-panel__persistent-badge');
    await expect(persistentBadge).toBeVisible();
    await expect(page.locator('.standalone-panel__badge-detail')).toHaveText('Persistent volume verified');

    // Verify non-admin notice and absence of backup form and compose buttons
    const notice = page.locator('.standalone-panel__member-notice');
    await expect(notice).toBeVisible();
    await expect(page.locator('.standalone-panel__backup-form')).toHaveCount(0);
    await expect(page.locator('button:has-text("Download docker-compose.yml")')).toHaveCount(0);

    // Capture screenshot 03: persistent member
    await annotatedScreenshot(page, testInfo, {
      name: '03-standalone-persistent-member',
      annotations: [
        {
          selector: '.standalone-panel__persistent-badge',
          label: 'Persistent Storage Badge',
          note: 'Persistent volume verified status without host topology disclosure',
        },
        {
          selector: '.standalone-panel__member-notice',
          label: 'Member Notice',
          note: 'Backup export and compose promotion hidden for non-server-admin',
        },
      ],
    });
  });
});
