// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import {
  assertZeroMockData,
  scanHorizontalOverflow,
  scanModalFooterVisibility,
  scanElementContrast,
} from '../support/gateAuditor';

process.env.QA_TICKET_ID = 'KANBA-223';

const mockUser = {
  id: 'usr-sweep-1',
  handle: 'elena_admin',
  display_name: 'Elena Vance',
  email: 'elena.vance@example.com',
  workspace_role: 'SERVER_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
};

const mockProject = {
  id: 'proj-sweep-1',
  identifier: 'PRJ',
  key: 'PRJ',
  name: 'Platform Core',
  description_markdown: 'Primary engineering workspace for visual contrast and responsive sweep',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
  is_project_admin: true,
  project_role: 'PROJECT_ADMIN',
};

const mockStates = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-inprogress', name: 'In Progress', group: 'started', sort_order: 2 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 3 },
];

function getStudioMocks(): MockHandlers {
  return {
    'GET /api/v1/auth/me': { json: mockUser },
    'GET /api/v1/me': { json: mockUser },
    'GET /api/v1/users/me': { json: mockUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'csrf-sweep-token-223',
        user: mockUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-sweep-token-223' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': {
      json: {
        deployment_mode: 'standalone_embedded_pg',
        persistent_volume: true,
        air_gap_mode: false,
        is_server_admin: true,
      },
    },
    'GET /api/v1/workspaces': {
      json: {
        items: [{ id: 'ws-sweep-1', slug: 'platform', name: 'Platform Workspace', is_current: true }],
        active_workspace_id: 'ws-sweep-1',
      },
    },
    'GET /api/v1/workspaces/:wsId': {
      json: { id: 'ws-sweep-1', slug: 'platform', name: 'Platform Workspace', is_current: true },
    },
    'GET /api/v1/notifications': { json: { items: [], total: 0 } },
    'GET /api/v1/projects/PRJ/assignee-suggestions': { json: [] },
    'GET /api/v1/projects': { json: [mockProject] },
    'GET /api/v1/projects/PRJ': { json: mockProject },
    'GET /api/v1/projects/PRJ/states': { json: mockStates },
    'GET /api/v1/projects/PRJ/cycles': {
      json: {
        items: [
          {
            id: 'cyc-sweep-1',
            name: 'Sprint Alpha 2026-W47',
            status: 'active',
            start_date: '2026-11-16',
            end_date: '2026-11-30',
          },
        ],
      },
    },
    'GET /api/v1/projects/PRJ/modules': { json: { items: [] } },
    'GET /api/v1/projects/PRJ/labels': { json: { items: [] } },
    'GET /api/v1/projects/PRJ/priorities': {
      json: {
        items: [
          { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
          { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
        ],
      },
    },
    'GET /api/v1/projects/PRJ/views': { json: [] },
    'GET /api/v1/projects/PRJ/custom-fields': { json: [] },
    'GET /api/v1/projects/PRJ/issues': {
      json: {
        items: [
          {
            id: 'iss-sweep-1',
            key: 'PRJ-1',
            project_key: 'PRJ',
            project_name: 'Platform Core',
            summary: 'Visual contrast and responsive shell audit',
            state: { id: 'st-inprogress', name: 'In Progress', group: 'started' },
            priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
            capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
          },
        ],
        total: 1,
      },
    },
    'GET /api/v1/issues/PRJ-1': {
      json: {
        id: 'iss-sweep-1',
        key: 'PRJ-1',
        project_key: 'PRJ',
        summary: 'Visual contrast and responsive shell audit',
        capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
      },
    },
    'GET /api/v1/stickies': {
      json: {
        items: [
          {
            id: 'stk-sweep-1',
            title: 'Design Invariants',
            body_markdown: 'WCAG AA 4.5:1 ratio and zero mobile overflow.',
            palette: 'emerald',
            order_index: 0,
          },
        ],
      },
    },
    'GET /api/v1/projects/PRJ/stickies': {
      json: {
        items: [
          {
            id: 'stk-sweep-1',
            title: 'Design Invariants',
            body_markdown: 'WCAG AA 4.5:1 ratio and zero mobile overflow.',
            palette: 'emerald',
            order_index: 0,
          },
        ],
      },
    },
    'GET /api/v1/projects/PRJ/docs/tree': {
      json: {
        pages: [
          {
            id: 'doc-sweep-1',
            title: 'Audit Standards Guide',
            slug: 'audit-standards',
            parent_id: null,
            position: 0,
          },
        ],
      },
    },
    'GET /api/v1/pages/doc-sweep-1': {
      json: {
        id: 'doc-sweep-1',
        title: 'Audit Standards Guide',
        body_markdown: '# Contrast Standards\n\nAll elements enforce WCAG AA minimum 4.5:1 contrast.',
        body_sha256: 'deadbeef1234',
      },
    },
    'GET /api/v1/pages/doc-sweep-1/versions': { json: { versions: [] } },
    'GET /api/v1/auth/mcp-keys': {
      json: {
        keys: [
          {
            id: 'mcp-key-sweep-1',
            label: 'Audit Inspector Runner',
            display_hint: 'e5f6',
            surface: 'admin',
            scope_tier: 'global',
            scopes: ['admin:read'],
            allowed_projects: null,
            created_at: '2026-11-19T05:00:00Z',
            expires_at: '2026-12-19T05:00:00Z',
            last_used_at: null,
            revoked_at: null,
          },
        ],
      },
    },
    'GET /api/v1/auth/oauth-grants': { json: [] },
    'GET /api/v1/admin/workspace-settings': {
      json: {
        workspace_id: 'ws-sweep-1',
        name: 'Platform Workspace',
        slug: 'platform',
        organization_name: 'Platform Team',
        mcp_enabled: true,
        allow_unlimited_mcp_keys: true,
      },
    },
    'GET /api/v1/admin/principals': { json: { items: [], total: 0 } },
    'GET /api/v1/admin/standalone/backup-schedule': {
      json: {
        enabled: true,
        interval_hours: 24,
        retention_count: 7,
        last_run_at: '2026-11-19T00:00:00Z',
        next_run_at: '2026-11-20T00:00:00Z',
      },
    },
    'GET /api/v1/admin/standalone/compose-export': { json: loadFixture('compose-export-sample') },
    'GET /api/v1/admin/standalone/backups': { json: [] },
    'GET /api/v1/objects/:id/access': { json: { capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'] } },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.setAttribute('data-theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-223 Light/Dark Contrast & 390x844 Mobile Overflow Gate', () => {
  test.beforeEach(async ({ page, context }) => {
    await page.route('**/sse**', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': keepalive\n\n',
      });
    });

    page.on('response', (res) => {
      if (res.status() === 599) {
        console.error('599 UNMATCHED ROUTE:', res.request().method(), res.request().url());
      }
    });

    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'csrf-sweep-token-223',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: User Studios sweep (Issues, Cycles, Stickies) across Light and Dark themes', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');
    const mocks = getStudioMocks();
    assertZeroMockData(mocks, 'user studio mocks');
    await mockApi(page, mocks);

    const routesToSweep = [
      { route: '/projects/PRJ/issues', name: 'user-issues-board', selector: '[data-testid="issues-workspace"]' },
      { route: '/projects/PRJ/cycles', name: 'user-cycles-view', selector: '[data-testid="project-cycles-view"]' },
      { route: '/stickies', name: 'user-stickies-canvas', selector: '.stickies-canvas, [data-testid="stickies-canvas"], .kb-main-canvas' },
    ];

    for (const target of routesToSweep) {
      await page.goto(target.route);
      await page.waitForSelector(target.selector, { state: 'visible' });

      for (const theme of ['light', 'dark'] as const) {
        await applyTheme(page, theme);

        // 1. Mobile overflow check
        const overflow = await scanHorizontalOverflow(page);
        expect(overflow.overflows).toBe(false);

        // 2. Contrast evaluation
        const contrastViolations = await scanElementContrast(page, ['h1', 'h2', 'button', 'a', '.badge'], target.selector);
        expect(contrastViolations).toHaveLength(0);

        // 3. Modal footer visibility if any modal present
        const modalViolations = await scanModalFooterVisibility(page);
        expect(modalViolations).toHaveLength(0);

        await annotatedScreenshot(page, testInfo, {
          name: `01-${target.name}-${theme}`,
          annotations: [
            {
              selector: target.selector,
              label: `${target.name} Surface`,
              note: `0 contrast failures, scrollWidth <= innerWidth (${String(overflow.scrollWidth)}px)`,
            },
          ],
        });
      }
    }
  });

  test('02: Admin Studios sweep (Standalone, MCP, Workspace Settings) across Light and Dark themes', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');
    const mocks = getStudioMocks();
    assertZeroMockData(mocks, 'admin studio mocks');
    await mockApi(page, mocks);

    const adminRoutes = [
      { route: '/admin/standalone', name: 'admin-standalone-panel', selector: '.standalone-panel' },
      { route: '/settings/mcp', name: 'admin-mcp-access-studio', selector: '[data-testid="mcp-access-studio"]' },
      { route: '/workspaces/settings', name: 'admin-workspace-settings', selector: '.kb-settings-container, .kb-main-canvas' },
    ];

    for (const target of adminRoutes) {
      await page.goto(target.route);
      await page.waitForSelector(target.selector, { state: 'visible' });

      for (const theme of ['light', 'dark'] as const) {
        await applyTheme(page, theme);

        // 1. Mobile overflow check
        const overflow = await scanHorizontalOverflow(page);
        expect(overflow.overflows).toBe(false);

        // 2. Contrast evaluation
        const contrastViolations = await scanElementContrast(page, ['h1', 'h2', 'button', 'a', '.badge'], target.selector);
        expect(contrastViolations).toHaveLength(0);

        // 3. Modal footer visibility check
        const modalViolations = await scanModalFooterVisibility(page);
        expect(modalViolations).toHaveLength(0);

        await annotatedScreenshot(page, testInfo, {
          name: `02-${target.name}-${theme}`,
          annotations: [
            {
              selector: target.selector,
              label: `${target.name} Canvas`,
              note: `0 contrast failures, 0 clipped footer buttons, scrollWidth <= innerWidth (${String(overflow.scrollWidth)}px)`,
            },
          ],
        });
      }
    }
  });
});
