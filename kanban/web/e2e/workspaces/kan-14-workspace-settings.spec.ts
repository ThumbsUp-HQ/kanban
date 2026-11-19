// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import { test, expect } from '../support/test';
import { mockApi, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KAN-14';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-14/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const mockAdminUser = {
  id: 'usr-admin-1',
  handle: '@admin',
  display_name: 'Admin User',
  email: 'admin@example.com',
  workspace_role: 'WORKSPACE_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
};

const mockWorkspace = {
  id: 'ws-main-1',
  name: 'Primary Workspace',
  slug: 'primary-workspace',
  is_current: true,
};

const mockPrincipals = [
  {
    id: 'usr-alice-1',
    principal: '@alice',
    display_name: 'Alice Developer',
    type: 'USER',
    email: 'alice@example.com',
    role: 'WORKSPACE_ADMIN',
  },
  {
    id: 'usr-bob-1',
    principal: '@bob',
    display_name: 'Bob Operator',
    type: 'USER',
    email: 'bob@example.com',
    role: 'WORKSPACE_MEMBER',
  },
  {
    id: 'grp-platform-1',
    principal: '@platform-team',
    display_name: 'Platform Engineering',
    type: 'GROUP',
    role: 'WORKSPACE_MEMBER',
  },
];

const mockGroupMembers = [
  {
    id: 'usr-alice-1',
    principal: '@alice',
    display_name: 'Alice Developer',
    type: 'USER',
    email: 'alice@example.com',
  },
];

const pngPixel = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

function getMocks(): MockHandlers {
  return {
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/system/status': {
      json: {
        initialized: true,
        air_gap_mode: false,
        build_id: 'kan-14-verified',
        version: '0.1.0',
      },
    },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: 'usr-admin-1',
        workspace_id: 'ws-main-1',
        aal_level: 2,
        mfa_pending: false,
        csrf_token: 'csrf-valid-token-kan-14',
      },
    },
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/users/me': { json: mockAdminUser },
    'GET /api/v1/workspaces': { json: [mockWorkspace] },
    'GET /api/v1/workspaces/current': { json: mockWorkspace },
    'GET /api/v1/workspaces/ws-main-1': { json: mockWorkspace },
    'GET /api/v1/admin/workspace-settings': {
      json: {
        id: 'ws-main-1',
        name: 'Primary Workspace',
        slug: 'primary-workspace',
        display_name: 'Primary Workspace',
        default_project_visibility: 'workspace',
        session_idle_timeout_min: 120,
        session_absolute_timeout_min: 1440,
        trash_retention_days: 30,
        mcp_key_max_ttl_days: 90,
        air_gap_mode: false,
      },
    },
    'GET /api/v1/admin/principals': { json: mockPrincipals },
    'GET /api/v1/admin/groups/grp-platform-1/members': { json: mockGroupMembers },
    'GET /api/v1/projects': { json: [] },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/objects/:id/access': { json: { object_id: 'ws-main-1' } },
    'GET /api/v1/users/:id/avatar': {
      status: 200,
      contentType: 'image/png',
      body: pngPixel,
    },
  };
}

test.describe('KAN-14 /workspaces/settings live principals and autofill keydown resilience', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'csrf-valid-token-kan-14',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-members-tab-autofill-keydown: mounts inputs, dispatches autofill keydown, renders live principals', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getMocks());

    await page.goto('/workspaces/settings');
    const membersTab = page.locator('[data-testid="tab-members"]');
    await membersTab.click();
    await expect(page.locator('[data-testid="workspace-members-section"]')).toBeVisible();

    // Verify email and password inputs are present
    const emailInput = page.locator('[data-testid="new-user-email"]');
    const passwordInput = page.locator('[data-testid="new-user-password"]');
    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();

    // Dispatch synthetic autofill keydown event with event.key === undefined
    await page.evaluate(() => {
      const emailEl = document.querySelector('[data-testid="new-user-email"]');
      if (emailEl) {
        emailEl.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
      }
      const passEl = document.querySelector('[data-testid="new-user-password"]');
      if (passEl) {
        passEl.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
      }
      window.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
    });

    // Verify UI did not crash and live principal payloads rendered
    await expect(page.locator('[data-testid="member-name-usr-alice-1"]')).toHaveText('Alice Developer');
    await expect(page.locator('[data-testid="member-handle-usr-alice-1"]')).toHaveText('@alice');
    await expect(page.locator('[data-testid="member-name-usr-bob-1"]')).toHaveText('Bob Operator');
    await expect(page.locator('[data-testid="member-handle-usr-bob-1"]')).toHaveText('@bob');

    await annotatedScreenshot(page, testInfo, {
      name: '01-members-tab-autofill-keydown',
      annotations: [
        {
          selector: '[data-testid="create-user-form"]',
          label: 'Autofill-Resilient User Creation Form',
          note: 'Synthetic keydown with undefined key does not crash shortcut handler.',
        },
        {
          selector: '[data-testid="workspace-users-table"]',
          label: 'Live Principals Table with p.principal Resolution',
          note: 'Handles live API principal payloads without handle attribute.',
        },
      ],
    });
  });

  test('02-members-tab-dark-mode: renders members tab in dark mode', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getMocks());

    await page.goto('/workspaces/settings');
    await page.locator('[data-testid="tab-members"]').click();
    await expect(page.locator('[data-testid="workspace-members-section"]')).toBeVisible();

    await page.evaluate(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.classList.add('dark');
    });

    await annotatedScreenshot(page, testInfo, {
      name: '02-members-tab-dark-mode',
      annotations: [
        {
          selector: '[data-testid="workspace-members-section"]',
          label: 'Dark Mode Members Section',
          note: 'High-contrast accessible theme styles for workspace members.',
        },
      ],
    });
  });

  test('03-groups-tab-principal-payload: renders groups tab with live group handle and members', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getMocks());

    await page.goto('/workspaces/settings');
    const groupsTab = page.locator('[data-testid="tab-groups"]');
    await groupsTab.click();
    await expect(page.locator('[data-testid="workspace-groups-section"]')).toBeVisible();

    // Select group
    const groupItem = page.locator('[data-testid="group-item-grp-platform-1"]');
    await groupItem.click();
    await expect(page.locator('[data-testid="group-detail-pane"]')).toBeVisible();

    // Dispatch synthetic autofill keydown
    await page.evaluate(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
    });

    await expect(page.locator('[data-testid="selected-group-name"]')).toHaveText('Platform Engineering');
    await expect(page.locator('[data-testid="selected-group-handle"]')).toHaveText('@platform-team');
    await expect(page.locator('[data-testid="group-members-table"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '03-groups-tab-principal-payload',
      annotations: [
        {
          selector: '[data-testid="group-detail-pane"]',
          label: 'Group Detail with Live Principal Resolution',
          note: 'Resolves group handle and nested members from principal field.',
        },
      ],
    });
  });

  test('04-groups-tab-dark-mode: renders groups tab in dark mode', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getMocks());

    await page.goto('/workspaces/settings');
    await page.locator('[data-testid="tab-groups"]').click();
    await page.locator('[data-testid="group-item-grp-platform-1"]').click();
    await expect(page.locator('[data-testid="group-detail-pane"]')).toBeVisible();

    await page.evaluate(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.classList.add('dark');
    });

    await annotatedScreenshot(page, testInfo, {
      name: '04-groups-tab-dark-mode',
      annotations: [
        {
          selector: '[data-testid="workspace-groups-section"]',
          label: 'Dark Mode Groups Section',
          note: 'Hierarchy and membership drilldown in dark mode.',
        },
      ],
    });
  });
});
