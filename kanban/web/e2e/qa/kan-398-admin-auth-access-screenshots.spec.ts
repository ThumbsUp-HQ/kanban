// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-398';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-398/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb:theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

const mockDiagnostics = {
  status: 'healthy',
  runtime_and_container: {
    deployment_mode: 'production_multi_container',
    in_container: true,
    container_runtime: 'docker',
    container_id_short: 'c116ba38',
    os_platform: 'Linux-6.6.137',
    python_version: '3.12.7',
    process_uid: 1000,
    process_gid: 1000,
    is_non_root: true,
    uptime_seconds: 3600.0,
    cgroup_version: 'v2',
    memory_limit_bytes: 4294967296,
    memory_current_bytes: 524288000,
    cpu_quota: 'max',
    pids_limit: 4096,
    pids_current: 42,
  },
  storage: {
    persistent_volume: true,
    data_mount_point: '/var/lib/kanban/data',
    data_mount_fstype: 'ext4',
    attachments_backend: 'local',
    sri_manifest_present: true,
    directories: [
      {
        name: 'attachments',
        path: '/var/lib/kanban/data/attachments',
        exists: true,
        writable: true,
        free_bytes: 107374182400,
        total_bytes: 536870912000,
      },
    ],
  },
  database: {
    connected: true,
    latency_ms: 1.25,
    server_version: 'PostgreSQL 16.2',
    active_role_non_bypass: true,
    force_rls_verified: true,
    alembic_head_current: true,
    code_heads: ['p6_17_server_admin_role_access'],
    db_heads: ['p6_17_server_admin_role_access'],
    pool: {
      size: 10,
      checked_in: 9,
      checked_out: 1,
      overflow: 0,
    },
    sanitized_dsn_target: {
      dialect: 'postgresql',
      host: '127.0.0.1',
      port: 5432,
      database: 'kanban',
      is_unix_socket: false,
    },
  },
  realtime: {
    ws_enabled: true,
    ws_paths: ['/ws', '/api/v1/ws'],
    sse_enabled: true,
    sse_path: '/sse',
    hub_running: true,
    hub_draining: false,
    broker_kind: 'pg_notify',
    broker_listener_connected: true,
    broker_publisher_connected: true,
    outbox_relay_running: true,
    outbox_pending_count: 0,
    outbox_dead_letter_count: 0,
    active_connections_total: 8,
    workspace_connections: { 'ws-01': 8 },
    ws_connections: 6,
    sse_connections: 2,
    heartbeat_interval_s: 25.0,
    session_recheck_interval_s: 60.0,
    replay_retention_minutes: 60,
    background_tasks: {
      listener_alive: true,
      ping_alive: true,
      session_check_alive: true,
    },
  },
  request_proxy_check: {
    detected_scheme: 'https',
    is_https: true,
    resolved_client_ip: '127.0.0.1',
    forwarded_proto_present: true,
  },
  config: [],
  subsystems: {},
};

const mockServerAdmin = {
  id: 'usr-admin-1',
  handle: 'server_admin',
  display_name: 'Server Admin',
  email: 'admin@example.com',
  is_server_admin: true,
  is_workspace_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

const mockWorkspaceAdmin = {
  id: 'usr-ws-admin-1',
  handle: 'ws_admin',
  display_name: 'Workspace Admin',
  email: 'ws-admin@example.com',
  workspace_role: 'WORKSPACE_ADMIN',
  is_server_admin: false,
  is_workspace_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

function getBaseShellMocks(): MockHandlers {
  return {
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/projects': { json: [loadFixture('project-kan')] },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/auth/session': { json: { csrf_token: 'mock-csrf-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/notifications': { json: { items: [], total: 0, unread_count: 0 } },
    'GET /api/v1/workspaces/current': {
      json: {
        id: '01a1f1aa-7d7a-782f-a996-6a87f9e9e667',
        name: 'Platform Engineering',
        slug: 'platform-engineering',
        is_current: true,
      },
    },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: '01a1f1aa-7d7a-782f-a996-6a87f9e9e667',
          name: 'Platform Engineering',
          slug: 'platform-engineering',
          is_current: true,
        },
      ],
    },
  };
}

function getMfaRequiredMocks(): MockHandlers {
  return {
    ...getBaseShellMocks(),
    'GET /api/v1/auth/me': { json: mockServerAdmin },
    'GET /api/v1/users/me': { json: mockServerAdmin },
    'GET /api/v1/admin/auth-cards': {
      status: 403,
      json: {
        code: 'MFA_ENROLLMENT_REQUIRED',
        title: 'Two-Factor Authentication Required',
        detail: 'Administrative operations require MFA enrollment. Please configure a second factor in your profile settings.',
      },
    },
    'GET /api/v1/admin/principals': {
      status: 403,
      json: {
        code: 'MFA_ENROLLMENT_REQUIRED',
        title: 'Two-Factor Authentication Required',
        detail: 'Administrative operations require MFA enrollment. Please configure a second factor in your profile settings.',
      },
    },
  };
}

function getServerAdminHealthyMocks(): MockHandlers {
  return {
    ...getBaseShellMocks(),
    'GET /api/v1/auth/me': { json: mockServerAdmin },
    'GET /api/v1/users/me': { json: mockServerAdmin },
    'GET /api/v1/admin/auth-cards': { json: loadFixture('admin-auth-cards') },
    'GET /api/v1/admin/principals': { json: [] },
  };
}

function getWorkspaceAdminMocks(): MockHandlers {
  return {
    ...getBaseShellMocks(),
    'GET /api/v1/auth/me': { json: mockWorkspaceAdmin },
    'GET /api/v1/users/me': { json: mockWorkspaceAdmin },
    'GET /api/v1/admin/diagnostics': { json: mockDiagnostics },
  };
}

test.describe('KAN-398 Visual Verification: Admin Auth Access and MFA Banner', () => {
  test.beforeEach(async ({ context, page }) => {
    page.on('response', (res) => {
      if (res.status() === 599) {
        console.error('599_UNMATCHED:', res.request().method(), res.url());
      }
    });
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-398',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-mfa-enrollment-banner: captures light and dark across viewports', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    await mockApi(page, getMfaRequiredMocks());
    await page.goto('/admin/auth');

    const banner = page.getByTestId('mfa-enrollment-required-banner');
    await expect(banner).toBeVisible({ timeout: 10000 });
    await expect(banner).toContainText('Two-Factor Authentication Required');
    const profileLink = banner.getByRole('link', { name: /profile settings/i });
    await expect(profileLink).toHaveAttribute('href', '/settings/profile');

    // Light screenshot
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-mfa-enrollment-banner-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark screenshot
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-mfa-enrollment-banner-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('02-subnav-server-admin: captures all 8 tabs visible for server admin', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    await mockApi(page, getServerAdminHealthyMocks());
    await page.goto('/admin/auth');

    await expect(page.getByTestId('tab-admin-auth')).toBeVisible();
    await expect(page.getByTestId('tab-admin-ai')).toBeVisible();
    await expect(page.getByTestId('tab-admin-runners')).toBeVisible();
    await expect(page.getByTestId('tab-admin-mcp')).toBeVisible();
    await expect(page.getByTestId('tab-admin-oauth')).toBeVisible();
    await expect(page.getByTestId('tab-admin-imports')).toBeVisible();
    await expect(page.getByTestId('tab-admin-standalone')).toBeVisible();
    await expect(page.getByTestId('tab-admin-diagnostics')).toBeVisible();

    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-subnav-server-admin-light-${projectName}.png`),
      fullPage: true,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-subnav-server-admin-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('03-subnav-workspace-admin: captures server tabs filtered out for non-server admin', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    await mockApi(page, getWorkspaceAdminMocks());
    await page.goto('/admin/diagnostics');

    await expect(page.getByTestId('tab-admin-diagnostics')).toBeVisible();
    await expect(page.getByTestId('tab-admin-auth')).toBeHidden();
    await expect(page.getByTestId('tab-admin-ai')).toBeHidden();
    await expect(page.getByTestId('tab-admin-runners')).toBeHidden();
    await expect(page.getByTestId('tab-admin-mcp')).toBeHidden();
    await expect(page.getByTestId('tab-admin-oauth')).toBeHidden();
    await expect(page.getByTestId('tab-admin-imports')).toBeHidden();
    await expect(page.getByTestId('tab-admin-standalone')).toBeHidden();

    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-subnav-workspace-admin-light-${projectName}.png`),
      fullPage: true,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-subnav-workspace-admin-dark-${projectName}.png`),
      fullPage: true,
    });
  });
});
