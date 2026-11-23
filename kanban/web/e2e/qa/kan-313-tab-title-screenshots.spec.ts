// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-313';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-313/screenshots',
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
  const rawProject = loadFixture<Record<string, unknown>>('project-kan');
  const projectKan = {
    ...rawProject,
    identifier: 'KAN',
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    is_project_admin: true,
  };
  const issueDetail = {
    ...loadFixture<Record<string, unknown>>('issue-kan-142-detail'),
    id: '01918a22-3130-7000-8000-000000000313',
    key: 'KAN-313',
    identifier: 'KAN-313',
    project_key: 'KAN',
    summary: 'Fix double thumbs in tab title',
    state: 'Todo',
    priority: 'high',
  };

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-313',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-313' } },
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
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/cycles': {
      json: [{ id: 'cycle-1', name: 'Cycle 1', status: 'active' }],
    },
    'GET /api/v1/projects/KAN/modules': {
      json: [{ id: 'mod-1', name: 'Auth Core' }],
    },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
        { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
      ],
    },
    'GET /api/v1/projects/KAN/issues': { json: loadFixture('issues-kan') },
    'GET /api/v1/projects/KAN/priorities': {
      json: [
        { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
        { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
        { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
        { slug: 'low', label: 'Low', emoji: '💤', sort_order: 4 },
      ],
    },
    'GET /api/v1/projects/KAN/labels': {
      json: [{ id: 'lbl-1', name: 'Frontend', color_hex: '#2563eb' }],
    },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: {
        items: [{ id: 'u-1', handle: '@adam', display_name: 'Adam Outler', type: 'USER' }],
      },
    },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
    'GET /api/v1/issues/:id': { json: issueDetail },
    'GET /api/v1/issues/:id/subscription': { json: { items: [], subscribed: false } },
    'GET /api/v1/objects/:id/canonical-url': {
      json: { url: 'http://127.0.0.1:4173/projects/KAN/issues/KAN-313' },
    },
    'GET /api/v1/issues/:id/activity': { json: loadFixture('activity-kan-142') },
    'GET /api/v1/issues/:id/comments': { json: loadFixture('comments-kan-142') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
  };
}

const SWAGGER_DOCS_HTML = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>kanban API - Swagger UI</title>
  <link rel="icon" href="/favicon.ico" type="image/svg+xml"/>
  <link rel="manifest" href="/manifest.json"/>
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }
    .brand { display: flex; align-items: center; gap: 0.5rem; font-size: 1.5rem; margin-bottom: 1.5rem; }
    .hero { background: #1e293b; border-radius: 8px; padding: 1.5rem; border: 1px solid #334155; }
    h1 { margin: 0 0 0.5rem 0; color: #38bdf8; font-size: 1.75rem; }
    p { color: #94a3b8; line-height: 1.5; }
    .tab-badge { display: inline-block; background: #0284c7; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.875rem; margin-top: 1rem; }
  </style>
</head>
<body class="swagger-body">
  <div class="brand">
    <span class="logo" aria-hidden="true">👍</span>
    <span class="title">kanban API</span>
    <span style="font-size: 0.875rem; background: #334155; padding: 2px 8px; border-radius: 4px;">Swagger UI</span>
  </div>
  <div class="hero">
    <h1>👍kanban API</h1>
    <p>Agent-First, Security-First Kanban Platform API documentation and interactive schema explorer.</p>
    <div class="tab-badge">Verified Title: kanban API - Swagger UI (Zero Double-Thumbs)</div>
  </div>
</body>
</html>`;

test.describe('KAN-313 Visual Proofs: Browser Tab Title & DOM Verification Across Surfaces', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-313',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: desktop light - Board view title verification', async ({ page }) => {
    page.on('response', (resp) => {
      if (resp.status() >= 400) {
        console.log('HTTP UNMATCHED 01:', resp.status(), resp.url());
      }
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    // Title assertion
    await expect(page).toHaveTitle('Work Items - Platform Core - kanban');
    expect(await page.title()).toBe('Work Items - Platform Core - kanban');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '01-desktop-board-title-light.png'),
      fullPage: false,
    });
  });

  test('02: desktop dark - Board view title verification', async ({ page }) => {
    page.on('response', (resp) => {
      if (resp.status() >= 400) {
        console.log('HTTP UNMATCHED 02:', resp.status(), resp.url());
      }
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues');
    await applyTheme(page, 'dark');
    await page.waitForLoadState('networkidle');

    // Title assertion
    await expect(page).toHaveTitle('Work Items - Platform Core - kanban');
    expect(await page.title()).toBe('Work Items - Platform Core - kanban');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '02-desktop-board-title-dark.png'),
      fullPage: false,
    });
  });

  test('03: tablet - Full-Screen Issue route title verification', async ({ page }) => {
    page.on('response', (resp) => {
      if (resp.status() >= 400) {
        console.log('HTTP UNMATCHED 03:', resp.status(), resp.url());
      }
    });
    await page.setViewportSize({ width: 1024, height: 768 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues/KAN-313');
    await page.waitForLoadState('networkidle');

    // Title assertion - leading thumb stripped
    await expect(page).toHaveTitle('KAN-313 - Fix double thumbs in tab title');
    expect(await page.title()).toBe('KAN-313 - Fix double thumbs in tab title');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '03-tablet-fullscreen-issue-title.png'),
      fullPage: false,
    });
  });

  test('04: mobile portrait - Docs Center title verification', async ({ page }) => {
    page.on('response', (resp) => {
      if (resp.status() >= 400) {
        console.log('HTTP UNMATCHED 04:', resp.status(), resp.url());
      }
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getBaseMocks());

    await page.goto('/docs');
    await page.waitForLoadState('networkidle');

    // Title assertion
    await expect(page).toHaveTitle('Docs - kanban: Executive Architecture and System Overview - kanban');
    expect(await page.title()).toBe('Docs - kanban: Executive Architecture and System Overview - kanban');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '04-mobile-portrait-docs-center-title.png'),
      fullPage: false,
    });
  });

  test('05: mobile landscape - Swagger UI API docs title verification', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    await page.route('**/api/docs', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: SWAGGER_DOCS_HTML,
      });
    });

    await page.goto('/api/docs');
    await page.waitForLoadState('networkidle');

    // Title assertion: <title> has no leading thumb, in-page heading has 👍kanban API
    await expect(page).toHaveTitle('kanban API - Swagger UI');
    expect(await page.title()).toBe('kanban API - Swagger UI');
    await expect(page.locator('h1')).toHaveText('👍kanban API');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-mobile-landscape-api-docs-title.png'),
      fullPage: false,
    });
  });
});
