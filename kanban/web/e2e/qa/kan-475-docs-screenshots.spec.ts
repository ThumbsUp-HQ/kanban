// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-475';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-475/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    try {
      localStorage.setItem('kb:theme', t);
    } catch {
      // ignore
    }
    document.documentElement.dataset.theme = t;
    document.documentElement.setAttribute('data-theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

async function assertNoHorizontalClipping(page: Page, expectedWidth: number): Promise<void> {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(expectedWidth + 1);

  const headerControls = page.locator('.kb-docs-header button, .kb-docs-header a');
  const count = await headerControls.count();
  for (let i = 0; i < count; i++) {
    const box = await headerControls.nth(i).boundingBox();
    if (box && box.width > 0 && box.height > 0) {
      expect(box.x + box.width).toBeLessThanOrEqual(expectedWidth + 2);
    }
  }
}

const mockAdminUser = {
  id: 'usr-admin-1',
  handle: 'adam_architect',
  display_name: 'Adam Architect',
  email: 'adam@example.com',
  workspace_role: 'WORKSPACE_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

function getDocsMocks(): MockHandlers {
  return {
    'GET /api/v1/me': { json: mockAdminUser },
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/users/me': { json: mockAdminUser },
    'GET /api/v1/auth/session/me': { json: mockAdminUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'csrf-test-token-docs',
        user: mockAdminUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token-docs' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': {
      json: {
        deployment_mode: 'production_multi_container',
        persistent_volume: true,
        data_mount_point: '/var/lib/kanban/data',
        is_server_admin: true,
      },
    },
    'GET /api/v1/system/about': {
      json: {
        platform: '👍kanban',
        slug: 'thumbs-up-kanban',
        tagline: 'The difference between a swarm and an Agile team is a kanban.',
        version: '0.2.1220',
        license_spdx: 'Apache-2.0',
      },
    },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: '01918a22-0000-7000-8000-000000000001',
          name: 'Primary Workspace',
          slug: 'kanban',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/workspaces/current': {
      json: {
        id: '01918a22-0000-7000-8000-000000000001',
        name: 'Primary Workspace',
        slug: 'kanban',
      },
    },
    'GET /api/v1/projects': {
      json: [
        {
          id: 'proj-kan-1',
          identifier: 'KAN',
          name: 'Platform Core',
        },
      ],
    },
    'GET /api/v1/projects/KAN': {
      json: {
        id: 'proj-kan-1',
        identifier: 'KAN',
        name: 'Platform Core',
      },
    },
    'GET /api/v1/notifications': { json: { items: [], total: 0, unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { unread_count: 0 } },
  };
}

test.describe('KAN-475: DocsCenterPage Header De-Clutter Visual Proof', () => {
  test('Capture verified DocsCenter screenshots across Desktop, Tablet, and Mobile in Light and Dark mode', async ({ page }) => {
    test.setTimeout(120000);
    await mockApi(page, getDocsMocks());

    // 1. Desktop Light (1440x900)
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/docs');
    await applyTheme(page, 'light');
    await expect(page.locator('[data-testid="docs-center-page"]')).toBeVisible();
    await expect(page.locator('[data-testid="docs-header-tools"]')).toBeVisible();
    await assertNoHorizontalClipping(page, 1440);
    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'desktop-light-1440x900.png'),
      fullPage: false,
    });

    // 2. Desktop Dark (1440x900)
    await applyTheme(page, 'dark');
    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'desktop-dark-1440x900.png'),
      fullPage: false,
    });

    // 3. Tablet Light (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await applyTheme(page, 'light');
    await expect(page.locator('[data-testid="docs-center-page"]')).toBeVisible();
    await expect(page.locator('[data-testid="docs-header-tools"]')).toBeVisible();
    await assertNoHorizontalClipping(page, 768);
    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'tablet-768x1024.png'),
      fullPage: false,
    });

    // 4. Tablet Dark (768x1024)
    await applyTheme(page, 'dark');
    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'tablet-dark-768x1024.png'),
      fullPage: false,
    });

    // 5. Mobile Light (390x844)
    await page.setViewportSize({ width: 390, height: 844 });
    await applyTheme(page, 'light');
    await expect(page.locator('[data-testid="docs-center-page"]')).toBeVisible();
    await expect(page.locator('[data-testid="docs-header-tools"]')).toBeVisible();
    await assertNoHorizontalClipping(page, 390);

    // Verify touch targets >= 44px on mobile
    const toolsBox = await page.locator('[data-testid="docs-header-tools"]').boundingBox();
    expect(toolsBox).not.toBeNull();
    const llmsBox = await page.locator('[data-testid="docs-llms-txt-link"]').boundingBox();
    expect(llmsBox).not.toBeNull();
    if (llmsBox) {
      expect(llmsBox.height).toBeGreaterThanOrEqual(44);
    }
    const copyBox = await page.locator('[data-testid="docs-copy-agent-prompt-btn"]').boundingBox();
    expect(copyBox).not.toBeNull();
    if (copyBox) {
      expect(copyBox.height).toBeGreaterThanOrEqual(44);
    }

    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'mobile-390x844.png'),
      fullPage: false,
    });

    // 6. Mobile Dark (390x844)
    await applyTheme(page, 'dark');
    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'mobile-dark-390x844.png'),
      fullPage: false,
    });
  });
});
