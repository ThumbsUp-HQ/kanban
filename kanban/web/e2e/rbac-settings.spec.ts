// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from './support/test';
import { mockApi, type MockHandlers } from './support/mockApi';
import { annotatedScreenshot } from './support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../docs/qa/KANBA-202/screenshots',
);

mkdirSync(SCREENSHOT_DIR, { recursive: true });

const mockAdminUser = {
  id: 'usr-admin-1',
  handle: 'alice_admin',
  display_name: 'Alice Admin',
  email: 'alice@example.com',
  is_server_admin: true,
  is_workspace_admin: true,
  workspace_role: 'SERVER_ADMIN',
  workspace_capabilities: ['ADMIN', 'SETTINGS', 'MANAGE_USERS', 'MANAGE_PROJECTS'],
};

const mockProjectAdmin = {
  id: 'proj-kanba-1',
  identifier: 'KANBA',
  name: 'Platform Engineering',
  description_markdown: 'Core platform engineering and agent framework development.',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'CREATE', 'EDIT', 'TRANSITION', 'DELETE', 'ADMIN'],
  is_project_admin: true,
  project_role: 'PROJECT_ADMIN',
};

const mockProjectMembers = [
  {
    id: 'pm-1',
    principal_id: 'usr-admin-1',
    principal_type: 'USER',
    role: 'PROJECT_ADMIN',
    display_name: 'Alice Admin',
    handle: 'alice_admin',
    email: 'alice@example.com',
  },
  {
    id: 'pm-2',
    principal_id: 'usr-dev-2',
    principal_type: 'USER',
    role: 'MEMBER',
    display_name: 'Bob Builder',
    handle: 'bob_builder',
    email: 'bob@example.com',
  },
];

const mockWorkspaceSettings = {
  id: 'ws-default',
  name: 'Primary Enterprise Workspace',
  slug: 'primary-enterprise',
  default_project_visibility: 'workspace',
  session_idle_timeout_min: 120,
  session_absolute_timeout_min: 1440,
  trash_retention_days: 30,
};

const mockWorkspacePrincipals = [
  {
    id: 'usr-admin-1',
    principal_type: 'USER',
    handle: 'alice_admin',
    display_name: 'Alice Admin',
    email: 'alice@example.com',
  },
  {
    id: 'usr-dev-2',
    principal_type: 'USER',
    handle: 'bob_builder',
    display_name: 'Bob Builder',
    email: 'bob@example.com',
  },
];

async function setupRbacMocks(page: Page, overrides: MockHandlers = {}): Promise<void> {
  await page.unroute('**/api/v1/**');
  await mockApi(page, {
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: 'ws-default',
          name: 'Primary Enterprise Workspace',
          slug: 'primary-enterprise',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/admin/workspace-settings': { json: mockWorkspaceSettings },
    'PATCH /api/v1/admin/workspace-settings': { json: mockWorkspaceSettings },
    'GET /api/v1/admin/principals': { json: mockWorkspacePrincipals },
    'GET /api/v1/projects': {
      json: [mockProjectAdmin],
    },
    'GET /api/v1/projects/KANBA': { json: mockProjectAdmin },
    'PATCH /api/v1/projects/KANBA': { json: mockProjectAdmin },
    'GET /api/v1/projects/KANBA/members': { json: mockProjectMembers },
    'POST /api/v1/projects/KANBA/members': {
      json: {
        id: 'pm-3',
        principal_id: 'usr-charlie',
        principal_type: 'USER',
        role: 'MEMBER',
        display_name: 'Charlie Contributor',
        handle: 'charlie',
        email: 'charlie@example.com',
      },
    },
    'GET /api/v1/system/status': {
      json: {
        standalone: true,
        version: '0.1.0',
        allow_unlimited_mcp_keys: true,
      },
    },
    'GET /api/v1/session/csrf': {
      json: { csrf_token: 'test-csrf-token' },
    },
    'GET /api/v1/setup/status': {
      json: { is_initialized: true, initialized: true, requires_setup: false },
    },
    'GET /api/v1/auth/session': {
      json: { authenticated: true, user: mockAdminUser },
    },
    'GET /api/v1/objects/:objectId/access': {
      json: {
        object_id: 'proj-kanba-1',
        inherited_from: null,
        users: [
          {
            principal_id: 'usr-admin-1',
            display_name: 'Alice Admin',
            handle: 'alice_admin',
            role: 'PROJECT_ADMIN',
            capabilities: ['ADMIN'],
          },
        ],
        groups: [],
        agents: [],
        deny_overrides: [],
      },
    },
    ...overrides,
  });
}

test.describe('KANBA-202: Project and Workspace Settings RBAC Views', () => {
  test('01-project-settings: renders project settings with general and members tabs', async ({ page }, testInfo) => {
    await setupRbacMocks(page);
    await page.goto('/projects/KANBA/settings');

    const pageContainer = page.getByTestId('project-settings-page');
    await expect(pageContainer).toBeVisible();

    const titleHeading = page.getByRole('heading', { name: /Project Settings: Platform Engineering/i });
    await expect(titleHeading).toBeVisible();

    // Take screenshot of General tab
    await annotatedScreenshot(page, testInfo, {
      name: '01-project-settings-general',
      annotations: [
        { selector: '[data-testid="project-settings-page"]', label: 'Project Settings Studio' },
        { selector: '[data-testid="general-form"]', label: 'Project Identity & Retention' },
      ],
    });

    // Switch to Members & Access tab
    const membersTab = page.getByTestId('tab-members');
    await membersTab.click();
    await expect(page.getByTestId('members-section')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-project-settings-members',
      annotations: [
        { selector: '[data-testid="members-section"]', label: 'Members & Access Control' },
        { selector: '[data-testid="add-member-form"]', label: 'Project Role Assignment' },
      ],
    });
  });

  test('03-workspace-settings: renders workspace administration studio', async ({ page }, testInfo) => {
    await setupRbacMocks(page);
    await page.goto('/workspaces/settings');

    const pageContainer = page.getByTestId('workspace-settings-page');
    await expect(pageContainer).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '03-workspace-settings-general',
      annotations: [
        { selector: '[data-testid="workspace-settings-page"]', label: 'Workspace Administration' },
        { selector: '[data-testid="workspace-general-form"]', label: 'Workspace Policy & Identity' },
      ],
    });
  });
});
