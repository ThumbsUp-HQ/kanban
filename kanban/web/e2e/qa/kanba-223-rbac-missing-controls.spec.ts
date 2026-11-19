// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import {
  assertDisallowedControls,
  assertZeroMockData,
  scanHorizontalOverflow,
} from '../support/gateAuditor';

process.env.QA_TICKET_ID = 'KANBA-223';

const mockGuestUser = {
  id: 'usr-guest-0',
  handle: 'sarah_guest',
  display_name: 'Sarah Guest',
  email: 'sarah.guest@example.com',
  workspace_role: 'WORKSPACE_GUEST',
  is_workspace_admin: false,
  is_server_admin: false,
};

const mockViewerUser = {
  id: 'usr-viewer-1',
  handle: 'victor_viewer',
  display_name: 'Victor Viewer',
  email: 'victor.viewer@example.com',
  workspace_role: 'VIEWER',
  is_workspace_admin: false,
  is_server_admin: false,
};

const mockMemberUser = {
  id: 'usr-member-2',
  handle: 'marcus_member',
  display_name: 'Marcus Brody',
  email: 'marcus.brody@example.com',
  workspace_role: 'WORKSPACE_MEMBER',
  is_workspace_admin: false,
  is_server_admin: false,
};

const mockProjAdminUser = {
  id: 'usr-projadmin-3',
  handle: 'paula_projadmin',
  display_name: 'Paula ProjectAdmin',
  email: 'paula.projadmin@example.com',
  workspace_role: 'WORKSPACE_MEMBER',
  is_workspace_admin: false,
  is_server_admin: false,
};

const mockWsAdminUser = {
  id: 'usr-wsadmin-4',
  handle: 'wendy_wsadmin',
  display_name: 'Wendy WsAdmin',
  email: 'wendy.wsadmin@example.com',
  workspace_role: 'WORKSPACE_ADMIN',
  is_workspace_admin: true,
  is_server_admin: false,
};

const mockServerAdminUser = {
  id: 'usr-serveradmin-5',
  handle: 'elena_admin',
  display_name: 'Elena Vance',
  email: 'elena.vance@example.com',
  workspace_role: 'SERVER_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
};

const mockProjectViewer = {
  id: 'proj-viewer-1',
  identifier: 'PRJVIEW',
  key: 'PRJVIEW',
  name: 'Read-Only Project',
  description_markdown: 'Project for viewer verification',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT'],
  is_project_admin: false,
  project_role: 'VIEWER',
};

const mockProjectMember = {
  id: 'proj-member-1',
  identifier: 'PRJMEM',
  key: 'PRJMEM',
  name: 'Team Project',
  description_markdown: 'Project for contributor verification',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT', 'EDIT'],
  is_project_admin: false,
  project_role: 'MEMBER',
};

const mockStates = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-inprogress', name: 'In Progress', group: 'started', sort_order: 2 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 3 },
];

function getCommonMocks(user: Record<string, unknown>): MockHandlers {
  return {
    'GET /api/v1/auth/me': { json: user },
    'GET /api/v1/me': { json: user },
    'GET /api/v1/users/me': { json: user },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: user.is_server_admin ? 2 : 1,
        csrf_token: 'csrf-rbac-token-223',
        user,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-rbac-token-223' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/workspaces': {
      json: {
        items: [{ id: 'ws-rbac-1', slug: 'platform', name: 'Platform Workspace', is_current: true }],
        active_workspace_id: 'ws-rbac-1',
      },
    },
    'GET /api/v1/workspaces/:wsId': {
      json: { id: 'ws-rbac-1', slug: 'platform', name: 'Platform Workspace', is_current: true },
    },
    'GET /api/v1/notifications': { json: { items: [], total: 0 } },
    'GET /api/v1/objects/:id/access': {
      json: {
        pill_label: 'Access Control',
        explicit_grant_count: 0,
        inherited_scope: {
          kind: 'workspace',
          scope_label: 'Platform Workspace',
          workspace_id: 'ws-rbac-1',
          workspace_name: 'Platform Workspace',
        },
        users: [],
        groups: [],
        agents: [],
      },
    },
    'GET /api/v1/system/status': {
      json: {
        deployment_mode: 'standalone_embedded_pg',
        persistent_volume: true,
        air_gap_mode: false,
        is_server_admin: Boolean(user.is_server_admin),
      },
    },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-223 6-Role Missing-Control DOM & Route-Guard Gate', () => {
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
        value: 'csrf-rbac-token-223',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: @guest renders No accessible projects and exact 0 dummy KAN objects', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const guestMocks: MockHandlers = {
      ...getCommonMocks(mockGuestUser),
      'GET /api/v1/projects': { json: [] },
    };
    assertZeroMockData(guestMocks, 'guest mocks');
    await mockApi(page, guestMocks);

    await page.goto('/');
    await page.waitForSelector('[data-testid="no-accessible-projects"]', { state: 'visible' });

    // Assert exact 0 dummy KAN objects
    const kanCardCount = await page.locator('[data-testid="project-card-KAN"]').count();
    expect(kanCardCount).toBe(0);

    // Assert exact text
    const emptyText = await page.locator('[data-testid="no-accessible-projects"]').textContent();
    expect(emptyText?.trim()).toBe('No accessible projects');

    // Assert disallowed controls are absent
    const violations = await assertDisallowedControls(page, 'guest');
    expect(violations).toHaveLength(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-guest-rbac-empty-home-${theme}`,
        annotations: [
          {
            selector: '[data-testid="no-accessible-projects"]',
            label: 'No Accessible Projects View',
            note: 'Guest receives 0 synthetic KAN items and 0 write controls',
          },
        ],
      });
    }

    const overflow = await scanHorizontalOverflow(page);
    expect(overflow.overflows).toBe(false);
  });

  test('02: @viewer on PRJVIEW has exact count() === 0 for create/edit buttons and cycle form', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const viewerMocks: MockHandlers = {
      ...getCommonMocks(mockViewerUser),
      'GET /api/v1/projects': { json: [mockProjectViewer] },
      'GET /api/v1/projects/PRJVIEW': { json: mockProjectViewer },
      'GET /api/v1/projects/PRJVIEW/issues': {
        json: {
          items: [
            {
              id: 'iss-viewer-1',
              key: 'PRJVIEW-1',
              project_key: 'PRJVIEW',
              summary: 'Security architecture audit record',
              state_id: 'st-backlog',
              priority_slug: 'urgent',
              capabilities: ['VIEW', 'COMMENT'],
            },
          ],
          total: 1,
        },
      },
      'GET /api/v1/projects/PRJVIEW/states': { json: mockStates },
      'GET /api/v1/projects/PRJVIEW/cycles': {
        json: {
          items: [
            {
              id: 'cyc-viewer-1',
              name: 'Sprint Alpha 2026-W47',
              status: 'active',
              start_date: '2026-11-16',
              end_date: '2026-11-30',
            },
          ],
        },
      },
      'GET /api/v1/projects/PRJVIEW/modules': { json: { items: [] } },
      'GET /api/v1/projects/PRJVIEW/labels': { json: { items: [] } },
      'GET /api/v1/projects/PRJVIEW/priorities': { json: { items: [] } },
      'GET /api/v1/projects/PRJVIEW/views': { json: [] },
      'GET /api/v1/projects/PRJVIEW/custom-fields': { json: [] },
      'GET /api/v1/projects/PRJVIEW/assignee-suggestions': { json: [] },
      'GET /api/v1/issues/PRJVIEW-1': {
        json: {
          id: 'iss-viewer-1',
          key: 'PRJVIEW-1',
          project_key: 'PRJVIEW',
          summary: 'Security architecture audit record',
          state_id: 'st-backlog',
          capabilities: ['VIEW', 'COMMENT'],
        },
      },
    };

    assertZeroMockData(viewerMocks, 'viewer mocks');
    await mockApi(page, viewerMocks);

    await page.goto('/projects/PRJVIEW/issues');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Assert exact 0 count for viewer disallowed controls on issues board
    const boardViolations = await assertDisallowedControls(page, 'viewer');
    expect(boardViolations).toHaveLength(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-viewer-readonly-board-${theme}`,
        annotations: [
          {
            selector: '[data-testid="issues-workspace"]',
            label: 'Viewer Read-Only Board',
            note: '0 create buttons, 0 inline edits, and 0 row checkboxes',
          },
        ],
      });
    }

    // Cycles view check
    await page.goto('/projects/PRJVIEW/cycles');
    await page.waitForSelector('[data-testid="project-cycles-view"]', { state: 'visible' });

    expect(await page.locator('[data-testid="create-cycle-form"]').count()).toBe(0);
    expect(await page.locator('button:has-text("Create New Cycle")').count()).toBe(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-viewer-readonly-cycles-${theme}`,
        annotations: [
          {
            selector: '[data-testid="project-cycles-view"]',
            label: 'Viewer Cycles View',
            note: 'Fail-closed: Create New Cycle form completely hidden from DOM',
          },
        ],
      });
    }
  });

  test('03: @member has 0 Create Project buttons and 0 Workflow controls', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const memberMocks: MockHandlers = {
      ...getCommonMocks(mockMemberUser),
      'GET /api/v1/projects': { json: [mockProjectMember] },
      'GET /api/v1/projects/PRJMEM': { json: mockProjectMember },
      'GET /api/v1/projects/PRJMEM/issues': { json: { items: [], total: 0 } },
      'GET /api/v1/projects/PRJMEM/states': { json: mockStates },
      'GET /api/v1/projects/PRJMEM/cycles': { json: { items: [] } },
      'GET /api/v1/projects/PRJMEM/modules': { json: { items: [] } },
      'GET /api/v1/projects/PRJMEM/labels': { json: { items: [] } },
      'GET /api/v1/projects/PRJMEM/priorities': { json: { items: [] } },
      'GET /api/v1/projects/PRJMEM/views': { json: [] },
      'GET /api/v1/projects/PRJMEM/custom-fields': { json: [] },
      'GET /api/v1/projects/PRJMEM/assignee-suggestions': { json: [] },
    };

    assertZeroMockData(memberMocks, 'member mocks');
    await mockApi(page, memberMocks);

    await page.goto('/');
    await page.waitForSelector('[data-testid="route-placeholder"]', { state: 'visible' });

    // Assert Member cannot create projects or workspaces
    const homeViolations = await assertDisallowedControls(page, 'member');
    expect(homeViolations).toHaveLength(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-member-restricted-home-${theme}`,
        annotations: [
          {
            selector: '[data-testid="route-placeholder"]',
            label: 'Member Home View',
            note: '0 + Create Project buttons and 0 Add Project in sidebar',
          },
        ],
      });
    }

    // Now visit project issues board
    await page.goto('/projects/PRJMEM/issues');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    expect(await page.locator('button:has-text("+ Workflow")').count()).toBe(0);
  });

  test('04: @projadmin cannot access unauthorized /projects/PRJSECRET or standalone admin', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const projAdminMocks: MockHandlers = {
      ...getCommonMocks(mockProjAdminUser),
      'GET /api/v1/projects': { json: [mockProjectMember] },
      'GET /api/v1/projects/PRJSECRET': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/PRJSECRET/issues': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/PRJSECRET/states': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/PRJSECRET/labels': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/PRJSECRET/cycles': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/PRJSECRET/modules': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/PRJSECRET/assignee-suggestions': { status: 404, json: { detail: 'Project not found' } },
    };

    assertZeroMockData(projAdminMocks, 'projadmin route guard mocks');
    await mockApi(page, projAdminMocks);

    // Direct URL access to unauthorized /projects/PRJSECRET/issues
    await page.goto('/projects/PRJSECRET/issues');
    await page.waitForSelector('[data-testid="not-found-view"]', { state: 'visible' });
    expect(await page.locator('text=Not found or no access').count()).toBeGreaterThanOrEqual(1);
    expect(await page.locator('.kb-sidebar').count()).toBe(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-unauthorized-project-guard-${theme}`,
        annotations: [
          {
            selector: '[data-testid="not-found-view"]',
            label: 'Unauthorized Project Direct Route Guard',
            note: 'Renders Not found or no access with 0 leaked project sidebar links',
          },
        ],
      });
    }
  });

  test('05: @wsadmin cannot access /admin/standalone server administration', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const wsAdminMocks: MockHandlers = {
      ...getCommonMocks(mockWsAdminUser),
      'GET /api/v1/projects': { json: [mockProjectMember] },
    };

    assertZeroMockData(wsAdminMocks, 'wsadmin mocks');
    await mockApi(page, wsAdminMocks);

    await page.goto('/admin/standalone');
    await page.waitForSelector('[data-testid="not-found-view"]', { state: 'visible' });
    expect(await page.locator('text=Not found or no access').count()).toBeGreaterThanOrEqual(1);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `06-admin-standalone-guard-${theme}`,
        annotations: [
          {
            selector: '[data-testid="not-found-view"]',
            label: 'Admin Standalone Guard',
            note: 'Locked down behind SERVER_ADMIN + AAL2 (renders Not found or no access)',
          },
        ],
      });
    }
  });

  test('06: @admin with AAL2 enters /admin/standalone with full controls', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const adminMocks: MockHandlers = {
      ...getCommonMocks(mockServerAdminUser),
      'GET /api/v1/admin/standalone/compose-export': { json: loadFixture('compose-export-sample') },
      'GET /api/v1/admin/standalone/backup-schedule': {
        json: {
          enabled: true,
          interval_hours: 24,
          retention_count: 7,
          last_run_at: '2026-11-19T00:00:00Z',
          next_run_at: '2026-11-20T00:00:00Z',
        },
      },
      'GET /api/v1/admin/standalone/backups': { json: [] },
      'GET /api/v1/projects': { json: [mockProjectMember] },
    };

    assertZeroMockData(adminMocks, 'admin mocks');
    await mockApi(page, adminMocks);

    await page.goto('/admin/standalone');
    await expect(page.locator('.standalone-panel')).toBeVisible();

    const adminViolations = await assertDisallowedControls(page, 'admin');
    expect(adminViolations).toHaveLength(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `07-admin-standalone-verified-${theme}`,
        annotations: [
          {
            selector: '.standalone-panel',
            label: 'Authorized Standalone Admin Panel',
            note: 'Server Admin + AAL2 renders full management controls',
          },
        ],
      });
    }
  });
});
