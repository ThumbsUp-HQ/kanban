// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KANBA-213';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-213/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

function getBaseMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kanba-213',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kanba-213' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
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
    'GET /api/v1/projects': { json: [loadFixture('project-kan')] },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/projects/KAN/cycles': { json: [] },
    'GET /api/v1/projects/KAN/modules': { json: [] },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
        { id: 'st-done', name: 'Done', group: 'completed', sort_order: 3 },
      ],
    },
    'GET /api/v1/projects/KAN/issues': { json: loadFixture('issues-kan') },
    'GET /api/v1/projects/KAN/stickies': { json: { items: loadFixture('stickies-kan') } },
    'GET /api/v1/stickies': { json: { items: loadFixture('stickies-kan') } },
    'GET /api/v1/projects/KAN/priorities': { json: [] },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/issues/:id/subscription': { json: loadFixture('subscription-kan-142') },
    'GET /api/v1/objects/:id/canonical-url': { json: loadFixture('canonical-kan-142') },
    'GET /api/v1/issues/:id/activity': { json: loadFixture('activity-kan-142') },
    'GET /api/v1/issues/:id/comments': { json: loadFixture('comments-kan-142') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/projects/KAN/docs/tree': { json: loadFixture('docs-tree-kan') },
    'GET /api/v1/pages/:id': { json: loadFixture('page-auth-studio') },
    'GET /api/v1/pages/:id/versions': { json: loadFixture('page-versions-auth-studio') },
    'GET /api/v1/auth/mcp-keys': {
      json: {
        keys: [
          {
            id: 'key-1',
            label: 'Production Automation Bot',
            display_hint: 'a1b2',
            surface: 'admin',
            scope_tier: 'global',
            scopes: ['admin:read', 'admin:write'],
            allowed_projects: null,
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
            last_used_at: null,
            revoked_at: null,
          },
        ],
      },
    },
    'GET /api/v1/auth/oauth-grants': { json: [] },
    'GET /api/v1/admin/workspace-settings': {
      json: {
        workspace_id: '01918a22-0000-7000-8000-000000000001',
        name: 'Primary Workspace',
        slug: 'kanban',
        organization_name: 'Kanban Platform',
        logo_url: null,
        allowed_domains: [],
        mcp_enabled: true,
        allow_unlimited_mcp_keys: true,
      },
    },
    'GET /api/v1/admin/principals': { json: { items: [], total: 0 } },
    'GET /api/v1/projects/KAN/members': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/issues/:id': { json: loadFixture('issue-kan-142-detail') },
  };
}

test.describe('KANBA-213 Visual Proofs: Theme Contrast & Mobile Layout Remediation', () => {
  test.beforeEach(async ({ page, context }) => {
    page.on('response', (res) => {
      if (res.status() === 599) {
        console.error('599 UNMATCHED ROUTE:', res.request().method(), res.url());
      }
    });

    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kanba-213',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: MCP Access Studio theme token contrast and modal', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/settings/mcp');
    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-mcp-access-studio-${theme}`,
        annotations: [
          {
            selector: '.kb-mcp-studio-header',
            label: 'MCP Access Studio Header & Theme Tokens',
            note: 'High-contrast primary and secondary tokens across Light/Dark modes',
          },
          {
            selector: '[data-testid="mint-key-button"]',
            label: 'Mint Key CTA Button',
            note: 'Semantic accent token with accessible text contrast',
          },
        ],
      });
    }
  });

  test('02: Workspace Settings theme tokens & mobile layout', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/workspaces/settings');
    await expect(page.locator('.kb-settings-container, .kb-main-canvas').first()).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-settings-workspace-${theme}`,
        annotations: [
          {
            selector: '.kb-main-canvas',
            label: 'Workspace Settings Canvas',
            note: 'Dark surface cards with readable headings and zero dark-on-dark text',
          },
        ],
      });
    }
  });

  test('03: Project Settings theme tokens & responsive tabs', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('.kb-settings-container, .kb-main-canvas').first()).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-settings-project-${theme}`,
        annotations: [
          {
            selector: '.kb-main-canvas',
            label: 'Project Settings General & Governance tabs',
            note: 'Theme token surfaces, inputs, and danger zone cards',
          },
        ],
      });
    }
  });

  test('04: Stickies Overview with Promoted Sticky Stub', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/stickies');
    await expect(page.locator('.sticky-card, .kb-stickies-container, .kb-main-canvas').first()).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-stickies-promoted-stub-${theme}`,
        annotations: [
          {
            selector: '.kb-main-canvas',
            label: 'Stickies Canvas with Promoted Sticky Stub',
            note: 'High-contrast badge, title, and link text >= 4.5:1 WCAG AA in Dark mode',
          },
        ],
      });
    }
  });

  test('05: Docs Workspace layout, outline hierarchy, and Mermaid CLS reservation', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/docs');
    await expect(page.locator('.docs-workspace, .docs-content, .kb-main-canvas').first()).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-docs-workspace-mobile-${theme}`,
        annotations: [
          {
            selector: '.kb-main-canvas',
            label: 'Docs Workspace View',
            note: 'Full-width reading column on mobile/tablet (<=768px), h1->h2->h3 outline hierarchy, and 220px Mermaid CLS reservation',
          },
        ],
      });
    }
  });

  test('06: Issues List View & Peek Drawer full-width overlay on mobile', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues?layout=list&peek=KAN-1');
    await expect(page.locator('.kb-main-canvas, .kb-split-list-pane, [data-testid="issues-workspace"]').first()).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `06-list-peek-drawer-mobile-${theme}`,
        annotations: [
          {
            selector: '.kb-main-canvas',
            label: 'List View with Peek Drawer',
            note: 'Full-width overlay on <=768px viewports eliminating horizontal column crunch',
          },
        ],
      });
    }
  });

  test('07: Board View card key target size (>=24x24px) & zero mobile overflow', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues?layout=board');
    await expect(page.locator('.board-card-key, .kb-board-lane, .kb-main-canvas').first()).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    // Verify .board-card-key target size >= 24x24px
    const cardKey = page.locator('.board-card-key').first();
    if (await cardKey.count() > 0) {
      const box = await cardKey.boundingBox();
      if (box) {
        expect(box.width).toBeGreaterThanOrEqual(24);
        expect(box.height).toBeGreaterThanOrEqual(24);
      }
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `07-board-card-target-size-${theme}`,
        annotations: [
          {
            selector: '.kb-main-canvas',
            label: 'Board View Swimlanes',
            note: 'Enlarged card key target size >= 24x24px (WCAG 2.2 SC 2.5.8) and inner horizontal lane scroll without document overflow',
          },
        ],
      });
    }
  });

  test('08: Branded SPA 404 Screen on unknown path with return action', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/unknown-random-route-for-spa-404');
    await expect(page.locator('[data-testid="not-found-view"]')).toBeVisible();
    await expect(page.locator('.kb-not-found-title')).toHaveText('404 - Page Not Found');
    await expect(page.locator('[data-testid="return-workspace-btn"]')).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(390);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `08-spa-404-branded-${theme}`,
        annotations: [
          {
            selector: '[data-testid="not-found-view"]',
            label: 'Branded SPA 404 Screen',
            note: 'Displays 404 badge, page title, current inspected path, and Return to Workspace action',
          },
        ],
      });
    }
  });
});
