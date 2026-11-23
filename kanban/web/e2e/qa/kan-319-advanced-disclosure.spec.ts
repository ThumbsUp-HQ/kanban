// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Visual and functional proofs for KAN-319:
 * Progressive Disclosure Audit, shared AdvancedSection component,
 * and refactored AuthCardEditorDrawer with clean progressive disclosure.
 * Plain ASCII hyphens only.
 */

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-319';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-319/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

function getBaseAuthMocks(): MockHandlers {
  const meAdmin = {
    ...loadFixture<Record<string, unknown>>('me-admin-auth'),
    is_server_admin: true,
    is_workspace_admin: true,
    workspace_role: 'WORKSPACE_ADMIN',
    aal_level: 2,
    auth_aal: 'aal2',
  };

  return {
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: 'admin-uuid-0001',
        workspace_id: 'ws-default',
        aal_level: 2,
        mfa_pending: false,
        csrf_token: 'test-csrf-token-kan-319',
        remember_me: true,
        idle_expires_at: '2026-11-25T23:00:00Z',
        absolute_expires_at: '2026-12-18T23:00:00Z',
        user: meAdmin,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-319' } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/workspaces': {
      json: {
        items: [{ id: 'ws-default', slug: 'kanban', name: '👍kanban Workspace' }],
        active_workspace_id: 'ws-default',
      },
    },
    'GET /api/v1/workspaces/current': {
      json: { id: 'ws-default', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/projects': {
      json: [
        { id: 'proj-kan', key: 'KAN', name: 'Platform Core' },
      ],
    },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/users/me': { json: meAdmin },
    'GET /api/v1/me': { json: meAdmin },
    'GET /api/v1/auth/me': { json: meAdmin },
    'GET /api/v1/admin/auth-cards': { json: loadFixture('admin-auth-cards') },
    'GET /api/v1/admin/principals': { json: [] },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
  };
}

test.describe('KAN-319: Progressive Disclosure & AdvancedSection E2E Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-319',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: 1440x900 Light - Desktop collapsed default disclosure', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseAuthMocks());

    await page.goto('/admin/auth');
    await applyTheme(page, 'light');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    // Open Okta SSO edit drawer
    const editButton = page.locator('.auth-card-row').first().locator('button:has-text("Edit")');
    await expect(editButton).toBeVisible();
    await editButton.click();

    // Verify drawer opened
    const drawer = page.locator('.auth-editor-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.locator('.auth-editor-title')).toHaveText('Edit Okta SSO');

    // Primary connection fields must be visible in default flow
    await expect(page.locator('#card-display-name')).toBeVisible();
    await expect(page.locator('#card-issuer-url')).toBeVisible();
    await expect(page.locator('#card-client-id')).toBeVisible();
    await expect(page.locator('#card-secret')).toBeVisible();

    // Advanced section must be present and collapsed by default
    const advancedToggle = page.locator('.kb-advanced-summary');
    await expect(advancedToggle).toBeVisible();
    await expect(advancedToggle).toHaveAttribute('aria-expanded', 'false');

    // Advanced fields should NOT be visible when collapsed
    await expect(page.locator('#card-slug')).not.toBeVisible();

    // Capture screenshot: 1440x900-desktop-light-collapsed.png
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '1440x900-desktop-light-collapsed.png'),
      fullPage: false,
    });
  });

  test('02: 1440x900 Dark - Desktop expanded with active overrides badge', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseAuthMocks());

    await page.goto('/admin/auth');
    await applyTheme(page, 'dark');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    // Open Okta SSO edit drawer
    const editButton = page.locator('.auth-card-row').first().locator('button:has-text("Edit")');
    await expect(editButton).toBeVisible();
    await editButton.click();

    const drawer = page.locator('.auth-editor-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.locator('.auth-editor-title')).toHaveText('Edit Okta SSO');

    // Toggle Advanced section to expand
    const advancedToggle = page.locator('.kb-advanced-summary');
    await expect(advancedToggle).toBeVisible();
    await advancedToggle.click();
    await expect(advancedToggle).toHaveAttribute('aria-expanded', 'true');

    // Advanced fields are now visible
    await expect(page.locator('#card-slug')).toBeVisible();
    await expect(page.locator('#card-subtext')).toBeVisible();
    await expect(page.locator('#card-icon-preset')).toBeVisible();
    await expect(page.locator('#card-email-domains')).toBeVisible();

    // Capture screenshot: 1440x900-desktop-dark-expanded.png
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '1440x900-desktop-dark-expanded.png'),
      fullPage: false,
    });
  });

  test('03: 768x1024 - Tablet collapsed disclosure', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await mockApi(page, getBaseAuthMocks());

    await page.goto('/admin/auth');
    await applyTheme(page, 'light');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    const editButton = page.locator('.auth-card-row').first().locator('button:has-text("Edit")');
    await expect(editButton).toBeVisible();
    await editButton.click();

    const drawer = page.locator('.auth-editor-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.locator('.auth-editor-title')).toHaveText('Edit Okta SSO');

    const advancedToggle = page.locator('.kb-advanced-summary');
    await expect(advancedToggle).toBeVisible();
    await expect(advancedToggle).toHaveAttribute('aria-expanded', 'false');

    // Capture screenshot: 768x1024-tablet-collapsed.png
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '768x1024-tablet-collapsed.png'),
      fullPage: false,
    });
  });

  test('04: 390x844 - Mobile portrait expanded disclosure', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getBaseAuthMocks());

    await page.goto('/admin/auth');
    await applyTheme(page, 'light');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    const editButton = page.locator('.auth-card-row').first().locator('button:has-text("Edit")');
    await expect(editButton).toBeVisible();
    await editButton.click();

    const drawer = page.locator('.auth-editor-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.locator('.auth-editor-title')).toHaveText('Edit Okta SSO');

    const advancedToggle = page.locator('.kb-advanced-summary');
    await expect(advancedToggle).toBeVisible();
    await advancedToggle.click();
    await expect(advancedToggle).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('#card-slug')).toBeVisible();

    // Capture screenshot: 390x844-mobile-portrait-expanded.png
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '390x844-mobile-portrait-expanded.png'),
      fullPage: false,
    });
  });

  test('05: 844x390 - Mobile landscape collapsed disclosure', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    await mockApi(page, getBaseAuthMocks());

    await page.goto('/admin/auth');
    await applyTheme(page, 'light');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    const editButton = page.locator('.auth-card-row').first().locator('button:has-text("Edit")');
    await expect(editButton).toBeVisible();
    await editButton.click();

    const drawer = page.locator('.auth-editor-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.locator('.auth-editor-title')).toHaveText('Edit Okta SSO');

    const advancedToggle = page.locator('.kb-advanced-summary');
    await expect(advancedToggle).toBeVisible();
    await expect(advancedToggle).toHaveAttribute('aria-expanded', 'false');

    // Capture screenshot: 844x390-mobile-landscape-collapsed.png
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '844x390-mobile-landscape-collapsed.png'),
      fullPage: false,
    });
  });
});
