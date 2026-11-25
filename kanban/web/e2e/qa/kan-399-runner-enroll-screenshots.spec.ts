// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Visual and functional proofs for KAN-399:
 * Remote runner enroll CLI and token reveal UX hardening.
 * Plain ASCII hyphens only.
 */

import { resolve } from 'node:path';
import { mkdirSync, copyFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-399';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-399/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

const mockRunners = [
  {
    id: 'run-01',
    workspace_id: 'ws-kanban',
    pool_slug: 'prod-runners',
    hostname: 'runner-node-01.internal.cloud',
    status: 'active',
    client_cert_sha256_hex: '4f8a1c9e8b7d6a5f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f',
    cert_expires_at: '2027-10-01T12:00:00Z',
    capabilities: { docker: true, os: 'linux-x86_64', gpu: true },
    last_heartbeat_at: '2026-11-25T00:30:00Z',
    revoked_at: null,
    created_at: '2026-10-01T12:00:00Z',
  },
  {
    id: 'run-02',
    workspace_id: 'ws-kanban',
    pool_slug: 'default',
    hostname: 'worker-edge-02.dmz.local',
    status: 'offline',
    client_cert_sha256_hex: '9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b',
    cert_expires_at: '2027-10-10T10:00:00Z',
    capabilities: { arch: 'arm64' },
    last_heartbeat_at: '2026-11-24T18:00:00Z',
    revoked_at: null,
    created_at: '2026-10-10T10:00:00Z',
  },
];

function getMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const projectKan = loadFixture<Record<string, unknown>>('project-kan');

  return {
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-399' } },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
    'GET /api/v1/me': {
      json: {
        ...me,
        id: '01918a22-0000-7000-8000-000000000001',
        is_server_admin: true,
        is_workspace_admin: true,
        aal_level: 2,
        auth_aal: 'aal2',
      },
    },
    'GET /api/v1/auth/me': {
      json: {
        ...me,
        id: '01918a22-0000-7000-8000-000000000001',
        is_server_admin: true,
        is_workspace_admin: true,
        aal_level: 2,
        auth_aal: 'aal2',
      },
    },
    'GET /api/v1/users/me': {
      json: {
        ...me,
        id: '01918a22-0000-7000-8000-000000000001',
        is_server_admin: true,
        is_workspace_admin: true,
        aal_level: 2,
        auth_aal: 'aal2',
      },
    },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: '01918a22-0000-7000-8000-000000000001',
        workspace_id: 'ws-kanban',
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-399',
        user: {
          ...me,
          id: '01918a22-0000-7000-8000-000000000001',
          is_server_admin: true,
          is_workspace_admin: true,
          aal_level: 2,
          auth_aal: 'aal2',
        },
      },
    },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/workspaces': {
      json: [{ id: 'ws-kanban', name: 'kanban', slug: 'kanban', is_current: true }],
    },
    'GET /api/v1/workspaces/current': {
      json: { id: 'ws-kanban', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/workspaces/settings': {
      json: {
        air_gap_mode: true,
        token_cap_monthly: 10000000,
      },
    },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KANBA': { json: projectKan },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KANBA/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/admin/agent-runners': { json: mockRunners },
    'POST /api/v1/admin/agent-runners/enrollment-tokens': {
      json: {
        id: 'tok-kan399',
        pool_slug: 'prod-runners',
        enrollment_token: 'kb_enroll_live_7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c',
        expires_at: '2026-11-25T02:00:00Z',
        created_at: '2026-11-25T01:45:00Z',
      },
    },
  };
}

async function setupMocks(page: Page): Promise<void> {
  await page.unroute('**/api/v1/**');
  await mockApi(page, getMocks());
}

test.describe('KAN-399: Runner Enrollment Modal Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-399',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: 1440x900 Desktop Light - Mint modal single-reveal view with --server-url, Copy CLI Command, and Done', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupMocks(page);

    await page.goto('/admin/agent-runners');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('runner-studio-page')).toBeVisible();

    // Open mint modal
    await page.getByTestId('open-mint-modal-btn').click();
    await expect(page.getByTestId('mint-enrollment-token-modal')).toBeVisible();

    // Submit mint form
    await page.getByTestId('submit-mint-token-btn').click();

    // Single-reveal view checks
    const singleReveal = page.getByTestId('single-reveal-token-view');
    await expect(singleReveal).toBeVisible();
    await expect(page.getByTestId('token-plaintext')).toBeVisible();

    // Verify canonical --server-url in pre block
    const cliPre = page.getByTestId('runner-cli-command');
    await expect(cliPre).toBeVisible();
    await expect(cliPre).toContainText('--server-url');

    // Verify Copy CLI Command button
    const copyCliBtn = page.getByTestId('copy-runner-cli-btn');
    await expect(copyCliBtn).toBeVisible();
    await expect(copyCliBtn).toHaveText('Copy CLI Command');

    // Verify Done dismiss button
    const doneBtn = page.getByTestId('dismiss-mint-modal-btn');
    await expect(doneBtn).toBeVisible();
    await expect(doneBtn).toHaveText('Done');

    // Capture screenshot
    const shotPath = resolve(SCREENSHOT_DIR, 'runner-mint-modal-reveal-1440x900-light.png');
    await page.screenshot({ path: shotPath, fullPage: false });
    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '1440x900-light.png'));

    // Click Copy CLI Command and capture feedback state
    await copyCliBtn.click();
    await expect(copyCliBtn).toHaveText('✓ Copied!');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, 'runner-mint-modal-cli-copied-feedback.png'),
      fullPage: false,
    });
  });

  test('02: 1440x900 Desktop Dark - Mint modal single-reveal view in dark theme', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupMocks(page);

    await page.goto('/admin/agent-runners');
    await applyTheme(page, 'dark');

    await expect(page.getByTestId('runner-studio-page')).toBeVisible();

    // Open mint modal and submit
    await page.getByTestId('open-mint-modal-btn').click();
    await expect(page.getByTestId('mint-enrollment-token-modal')).toBeVisible();
    await page.getByTestId('submit-mint-token-btn').click();

    await expect(page.getByTestId('single-reveal-token-view')).toBeVisible();
    await expect(page.getByTestId('runner-cli-command')).toContainText('--server-url');
    await expect(page.getByTestId('copy-runner-cli-btn')).toHaveText('Copy CLI Command');
    await expect(page.getByTestId('dismiss-mint-modal-btn')).toHaveText('Done');

    const shotPath = resolve(SCREENSHOT_DIR, 'runner-mint-modal-reveal-1440x900-dark.png');
    await page.screenshot({ path: shotPath, fullPage: false });
    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '1440x900-dark.png'));
  });

  test('03: 768x1024 Tablet Portrait - Responsive layout with visible CLI snippet and buttons', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await setupMocks(page);

    await page.goto('/admin/agent-runners');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('runner-studio-page')).toBeVisible();

    await page.getByTestId('open-mint-modal-btn').click();
    await expect(page.getByTestId('mint-enrollment-token-modal')).toBeVisible();
    await page.getByTestId('submit-mint-token-btn').click();

    await expect(page.getByTestId('single-reveal-token-view')).toBeVisible();
    await expect(page.getByTestId('runner-cli-command')).toContainText('--server-url');
    await expect(page.getByTestId('copy-runner-cli-btn')).toBeVisible();
    await expect(page.getByTestId('dismiss-mint-modal-btn')).toHaveText('Done');

    const shotPath = resolve(SCREENSHOT_DIR, 'runner-mint-modal-reveal-768x1024.png');
    await page.screenshot({ path: shotPath, fullPage: false });
    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '768x1024.png'));
  });

  test('04: 390x844 Mobile Portrait - Single-column responsive modal layout', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMocks(page);

    await page.goto('/admin/agent-runners');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('runner-studio-page')).toBeVisible();

    await page.getByTestId('open-mint-modal-btn').click();
    await expect(page.getByTestId('mint-enrollment-token-modal')).toBeVisible();
    await page.getByTestId('submit-mint-token-btn').click();

    await expect(page.getByTestId('single-reveal-token-view')).toBeVisible();
    await expect(page.getByTestId('runner-cli-command')).toContainText('--server-url');
    await expect(page.getByTestId('copy-runner-cli-btn')).toBeVisible();
    await expect(page.getByTestId('dismiss-mint-modal-btn')).toHaveText('Done');

    const shotPath = resolve(SCREENSHOT_DIR, 'runner-mint-modal-reveal-390x844.png');
    await page.screenshot({ path: shotPath, fullPage: false });
    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '390x844.png'));
  });
});
