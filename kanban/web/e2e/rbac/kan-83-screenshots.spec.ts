// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, type MockHandlers } from '../support/mockApi';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-83/screenshots',
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
  name: 'Platform Engineering',
  slug: 'platform-engineering',
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
];

const mockRoles = [
  {
    id: 'role-sysadmin',
    workspace_id: 'ws-main-1',
    slug: 'system-admin',
    name: 'system-admin',
    color_hex: '#dc2626',
    description: 'Full system administration capabilities',
    is_system: true,
    system_role: 'system-admin',
    scope_tier: 'system',
    permissions: [
      'workspace:create', 'workspace:edit_settings', 'workspace:delete',
      'workspace:manage_members', 'workspace:manage_billing', 'workspace:export_data',
      'workspace:manage_integrations', 'workspace:view_audit_log',
      'issue:create', 'issue:view', 'issue:edit', 'issue:delete',
      'issue:transition', 'issue:assign', 'issue:comment', 'issue:move',
      'issue:archive', 'issue:link',
      'field:title', 'field:description', 'field:state', 'field:priority',
      'field:assignees', 'field:dates', 'field:cycle_id', 'field:modules',
      'field:custom_fields', 'field:subtasks', 'field:attach_files', 'field:estimate_sp',
    ],
  },
  {
    id: 'role-wsadmin',
    workspace_id: 'ws-main-1',
    slug: 'workspace-admin',
    name: 'workspace-admin',
    color_hex: '#ea580c',
    description: 'Workspace administration and issue governance',
    is_system: true,
    system_role: 'workspace-admin',
    scope_tier: 'workspace',
    permissions: [
      'workspace:edit_settings', 'workspace:manage_members', 'workspace:export_data',
      'issue:create', 'issue:view', 'issue:edit', 'issue:delete',
      'issue:transition', 'issue:assign', 'issue:comment', 'issue:move',
      'issue:archive', 'issue:link',
      'field:title', 'field:description', 'field:state', 'field:priority',
      'field:assignees', 'field:dates', 'field:cycle_id', 'field:modules',
      'field:custom_fields', 'field:subtasks', 'field:attach_files', 'field:estimate_sp',
    ],
  },
  {
    id: 'role-projadmin',
    workspace_id: 'ws-main-1',
    slug: 'project-admin',
    name: 'project-admin',
    color_hex: '#f59e0b',
    description: 'Project configuration and workflow administration',
    is_system: true,
    system_role: 'project-admin',
    scope_tier: 'project',
    permissions: [
      'issue:create', 'issue:view', 'issue:edit', 'issue:delete',
      'issue:transition', 'issue:assign', 'issue:comment', 'issue:move',
      'issue:archive', 'issue:link',
      'field:title', 'field:description', 'field:state', 'field:priority',
      'field:assignees', 'field:dates', 'field:cycle_id', 'field:modules',
      'field:custom_fields', 'field:subtasks', 'field:attach_files', 'field:estimate_sp',
    ],
  },
  {
    id: 'role-users',
    workspace_id: 'ws-main-1',
    slug: 'users',
    name: 'users',
    color_hex: '#10b981',
    description: 'Standard contributor role with issue authoring rights',
    is_system: true,
    system_role: 'users',
    scope_tier: 'workspace',
    permissions: [
      'issue:create', 'issue:view', 'issue:edit', 'issue:transition',
      'issue:assign', 'issue:comment', 'issue:link',
      'field:title', 'field:description', 'field:state', 'field:priority',
      'field:assignees', 'field:dates', 'field:custom_fields', 'field:attach_files',
    ],
  },
  {
    id: 'role-viewer',
    workspace_id: 'ws-main-1',
    slug: 'viewer',
    name: 'viewer',
    color_hex: '#3b82f6',
    description: 'Read-only access to issues with commenting capability',
    is_system: true,
    system_role: 'viewer',
    scope_tier: 'workspace',
    permissions: ['issue:view', 'issue:comment'],
  },
  {
    id: 'role-guest',
    workspace_id: 'ws-main-1',
    slug: 'guest',
    name: 'guest',
    color_hex: '#6b7280',
    description: 'Minimal read-only access to assigned issues only',
    is_system: true,
    system_role: 'guest',
    scope_tier: 'workspace',
    permissions: ['issue:view'],
  },
];

function getMocks(): MockHandlers {
  return {
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/system/status': {
      json: {
        initialized: true,
        air_gap_mode: false,
        build_id: 'kan-83-verified',
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
        csrf_token: 'csrf-valid-token-kan-83',
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
        workspace_id: 'ws-main-1',
        name: 'Platform Engineering',
        slug: 'platform-engineering',
        display_name: 'Platform Engineering',
        default_project_visibility: 'workspace',
        session_idle_timeout_min: 120,
        session_absolute_timeout_min: 1440,
        trash_retention_days: 30,
        mcp_key_max_ttl_days: 90,
        air_gap_mode: false,
      },
    },
    'GET /api/v1/admin/principals': { json: mockPrincipals },
    'GET /api/v1/admin/rbac/roles': { json: mockRoles },
    'GET /api/v1/admin/rbac/roles?workspace_id=ws-main-1': { json: mockRoles },
    'GET /api/v1/admin/principals/usr-alice-1/role-labels': { json: [] },
    'GET /api/v1/admin/principals/usr-bob-1/role-labels': { json: [] },
    'GET /api/v1/projects': { json: [] },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/objects/:id/access': { json: { object_id: 'ws-main-1' } },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KAN-83 RbacPolicyBuilder Responsive Screenshots Suite', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'csrf-valid-token-kan-83',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('captures all 5 responsive screenshots for RbacPolicyBuilder', async ({ page }) => {
    await mockApi(page, getMocks());

    await page.goto('/workspaces/settings#tab-roles');
    await expect(page.locator('[data-testid="tab-roles"]')).toBeVisible();
    await page.locator('[data-testid="tab-roles"]').click();
    await expect(page.locator('[data-testid="rbac-policy-builder"]')).toBeVisible();

    // 1. Desktop Light (1440x900)
    await page.setViewportSize({ width: 1440, height: 900 });
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'rbac-policy-builder-1440x900-light.png'),
      fullPage: false,
    });

    // 2. Desktop Dark (1440x900)
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'rbac-policy-builder-1440x900-dark.png'),
      fullPage: false,
    });

    // Reset to light theme for responsive viewports
    await applyTheme(page, 'light');

    // 3. Tablet Portrait (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'rbac-policy-builder-768x1024.png'),
      fullPage: false,
    });

    // 4. Mobile Portrait (390x844)
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'rbac-policy-builder-390x844.png'),
      fullPage: false,
    });

    // 5. Mobile Landscape (844x390)
    await page.setViewportSize({ width: 844, height: 390 });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'rbac-policy-builder-844x390.png'),
      fullPage: false,
    });
  });
});
