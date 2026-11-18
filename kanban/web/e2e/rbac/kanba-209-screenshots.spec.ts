// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-209/screenshots',
);

process.env.QA_TICKET_ID = 'KANBA-209';
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const mockGuestUser = {
  id: 'usr-guest-1',
  handle: 'guest_user',
  display_name: 'Guest User',
  email: 'guest@example.com',
  workspace_role: 'WORKSPACE_GUEST',
  is_workspace_admin: false,
  is_server_admin: false,
};

const mockViewerUser = {
  id: 'usr-viewer-1',
  handle: 'vicki_viewer',
  display_name: 'Vicki Viewer',
  email: 'viewer@example.com',
  workspace_role: 'VIEWER',
  is_workspace_admin: false,
  is_server_admin: false,
};

const mockMemberUser = {
  id: 'usr-member-1',
  handle: 'mike_member',
  display_name: 'Mike Member',
  email: 'member@example.com',
  workspace_role: 'WORKSPACE_MEMBER',
  is_workspace_admin: false,
  is_server_admin: false,
};

const mockProjectViewer = {
  id: 'proj-qaview-1',
  identifier: 'QAVIEW',
  name: 'QA Viewer Project',
  description_markdown: 'Read-only project for QA inspection and verification.',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT'],
  is_project_admin: false,
  project_role: 'VIEWER',
};

const mockProjectMember = {
  id: 'proj-qamem-1',
  identifier: 'QAMEM',
  name: 'QA Member Project',
  description_markdown: 'Member project with standard contributor capabilities.',
  modules_enabled: false,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT', 'EDIT'],
  is_project_admin: false,
  project_role: 'MEMBER',
};

const mockWorkspaces = [
  {
    id: 'ws-default',
    name: 'Primary Workspace',
    slug: 'primary-workspace',
    is_current: true,
  },
];

const mockStates = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 3 },
];

const mockIssuesViewer = {
  items: [
    {
      id: 'iss-1',
      key: 'QAVIEW-1',
      project_key: 'QAVIEW',
      summary: 'Read-only security assessment ticket',
      state_id: 'st-backlog',
      priority_slug: 'urgent',
      capabilities: ['VIEW', 'COMMENT'],
    },
  ],
  total: 1,
};

const mockCyclesViewer = [
  {
    id: 'cyc-1',
    name: 'Sprint 1',
    status: 'active',
    start_date: '2026-03-01',
    end_date: '2026-03-15',
  },
];

function getCommonMocks(user: Record<string, unknown>): MockHandlers {
  return {
    'GET /api/v1/auth/me': { json: user },
    'GET /api/v1/me': { json: user },
    'GET /api/v1/users/me': { json: user },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 1,
        csrf_token: 'csrf-test-token',
        user,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/workspaces': { json: mockWorkspaces },
    'GET /api/v1/system/status': loadFixture('system-status-prod'),
    'GET /api/v1/objects/:id/access': loadFixture('access-project-kan'),
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-209 RBAC Route Guards and UI Controls Forensic Audit', () => {
  test('1. Guest empty home renders No accessible projects and 0 dummy KAN cards', async ({ page }, testInfo) => {
    await mockApi(page, {
      ...getCommonMocks(mockGuestUser),
      'GET /api/v1/projects': { json: [] },
    });

    await page.goto('/');
    await page.waitForSelector('[data-testid="no-accessible-projects"]', { state: 'visible' });

    // Assert zero dummy KAN cards and exact "No accessible projects" text
    const kanCards = await page.locator('[data-testid="project-card-KAN"]').count();
    expect(kanCards).toBe(0);

    const emptyText = await page.locator('[data-testid="no-accessible-projects"]').textContent();
    expect(emptyText?.trim()).toBe('No accessible projects');

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-guest-empty-home-${theme}`,
        annotations: [
          {
            selector: '[data-testid="no-accessible-projects"]',
            label: 'No accessible projects rendered for Guest (0 KAN dummy cards)',
          },
        ],
      });
    }
  });

  test('2. Viewer QAVIEW omits create/edit controls and hides Create New Cycle form', async ({ page }, testInfo) => {
    await mockApi(page, {
      ...getCommonMocks(mockViewerUser),
      'GET /api/v1/projects': { json: [mockProjectViewer] },
      'GET /api/v1/projects/QAVIEW': { json: mockProjectViewer },
      'GET /api/v1/projects/QAVIEW/issues': { json: mockIssuesViewer },
      'GET /api/v1/projects/QAVIEW/states': { json: mockStates },
      'GET /api/v1/projects/QAVIEW/cycles': { json: mockCyclesViewer },
      'GET /api/v1/issues/QAVIEW-1': { json: mockIssuesViewer.items[0] },
      'GET /api/v1/issues/QAVIEW-1/activity': { json: [] },
      'GET /api/v1/issues/QAVIEW-1/comments': { json: [] },
    });

    await page.goto('/projects/QAVIEW/issues');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Assert 0 create buttons
    expect(await page.locator('[data-testid="home-create-issue-btn"]').count()).toBe(0);
    expect(await page.locator('[data-testid="view-empty-create-btn"]').count()).toBe(0);
    expect(await page.locator('[data-testid="list-new-btn"]').count()).toBe(0);
    expect(await page.locator('.kb-new-item-btn').count()).toBe(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-viewer-readonly-board-${theme}`,
        annotations: [
          {
            selector: '[data-testid="issues-workspace"]',
            label: 'Viewer read-only board with 0 new work item buttons and 0 row checkboxes',
          },
        ],
      });
    }

    // Now visit cycles view
    await page.goto('/projects/QAVIEW/cycles');
    await page.waitForSelector('[data-testid="project-cycles-view"]', { state: 'visible' });

    // Assert 0 Create New Cycle form
    expect(await page.locator('[data-testid="create-cycle-form"]').count()).toBe(0);
    expect(await page.locator('text=Create New Cycle').count()).toBe(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-viewer-readonly-cycles-${theme}`,
        annotations: [
          {
            selector: '[data-testid="project-cycles-view"]',
            label: 'Viewer read-only cycles view with 0 Create New Cycle form (FAIL-CLOSED)',
          },
        ],
      });
    }
  });

  test('3. Member omits Create Project and Workflow management controls', async ({ page }, testInfo) => {
    await mockApi(page, {
      ...getCommonMocks(mockMemberUser),
      'GET /api/v1/projects': { json: [mockProjectMember] },
      'GET /api/v1/projects/QAMEM': { json: mockProjectMember },
      'GET /api/v1/projects/QAMEM/issues': { json: { items: [], total: 0 } },
      'GET /api/v1/projects/QAMEM/states': { json: mockStates },
    });

    await page.goto('/');
    await page.waitForSelector('[data-testid="route-placeholder"]', { state: 'visible' });

    // Assert Member cannot create projects or workspaces
    expect(await page.locator('[data-testid="home-create-project-btn"]').count()).toBe(0);
    expect(await page.locator('[data-testid="sidebar-add-project-btn"]').count()).toBe(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-member-restricted-home-${theme}`,
        annotations: [
          {
            selector: '[data-testid="route-placeholder"]',
            label: 'Member Home with 0 + Create Project buttons and 0 Add Project in sidebar',
          },
        ],
      });
    }

    // Now visit project issues view
    await page.goto('/projects/QAMEM/issues');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Assert Workflow button hidden for non-admin
    expect(await page.locator('text=+ Workflow').count()).toBe(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-member-restricted-board-${theme}`,
        annotations: [
          {
            selector: '[data-testid="issues-workspace"]',
            label: 'Member project board with 0 + Workflow management headers',
          },
        ],
      });
    }
  });

  test('4. Strict Route Guards render Not found or no access for /admin/standalone and unauthorized projects', async ({ page }, testInfo) => {
    await mockApi(page, {
      ...getCommonMocks(mockMemberUser),
      'GET /api/v1/projects': { json: [mockProjectMember] },
      'GET /api/v1/projects/QAADM': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/QAADM/issues': { status: 404, json: { detail: 'Project not found' } },
      'GET /api/v1/projects/QAADM/states': { status: 404, json: { detail: 'Project not found' } },
    });

    // 1. /admin/standalone
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
            label: 'Admin standalone locked down behind SERVER_ADMIN + AAL2 (renders Not found)',
          },
        ],
      });
    }

    // 2. Direct URL access to unauthorized /projects/QAADM/issues
    await page.goto('/projects/QAADM/issues');
    await page.waitForSelector('[data-testid="not-found-view"]', { state: 'visible' });
    expect(await page.locator('text=Not found or no access').count()).toBeGreaterThanOrEqual(1);
    expect(await page.locator('.kb-sidebar').count()).toBe(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `07-unauthorized-project-guard-${theme}`,
        annotations: [
          {
            selector: '[data-testid="not-found-view"]',
            label: 'Direct access to unauthorized project renders Not found with 0 sidebar links',
          },
        ],
      });
    }
  });
});
