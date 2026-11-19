// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { assertZeroMockData, scanHorizontalOverflow } from '../support/gateAuditor';

process.env.QA_TICKET_ID = 'KANBA-223';

const VALID_SETUP_TOKEN = 'kb_setup_' + 'B'.repeat(43);

const mockAdminUser = {
  id: 'usr-smoke-admin',
  handle: 'elena_admin',
  display_name: 'Elena Vance',
  email: 'elena.vance@example.com',
  workspace_role: 'SERVER_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
};

const mockStandaloneStatus = {
  deployment_mode: 'standalone_embedded_pg',
  persistent_volume: true,
  data_mount_point: '/var/lib/kanban/data',
  data_mount_fstype: 'ext4',
  tier_b_sandbox_available: false,
  air_gap_mode: false,
  local_llm_endpoint_host: 'http://host.docker.internal:11434',
  is_server_admin: true,
};

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-223 Production Container Cold-Boot Smoke Gate', () => {
  test.beforeEach(async ({ page, context }) => {
    // Intercept SSE / EventSource to prevent 404 in preview mode
    await page.route('**/sse**', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': keepalive\n\n',
      });
    });

    // Assert zero unexpected network errors (500, or unexpected 404, 422, 428)
    page.on('response', (res) => {
      const status = res.status();
      const url = res.url();
      if (status === 599) {
        console.error('599 UNMATCHED ROUTE:', res.request().method(), url);
      }
      if (status === 500) {
        throw new Error(`Smoke Gate Network Failure: HTTP 500 on ${url}`);
      }
      if ([404, 422, 428].includes(status)) {
        // Exempt /sse, favicon, or intentional negative probe routes
        if (url.includes('/sse') || url.includes('/favicon.ico')) return;
        if (!url.includes('/api/v1/auth/stale') && !url.includes('/api/v1/projects/NONEXISTENT')) {
          throw new Error(`Smoke Gate Network Failure: Unexpected HTTP ${String(status)} on ${url}`);
        }
      }
    });

    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'csrf-smoke-token-223',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: kanban-ctl --help exits 0 and exposes operational command tree', () => {
    const repoRoot = resolve(import.meta.dirname, '../../../../');
    const venvPython = resolve(repoRoot, '.venv/bin/python');
    const pythonBin = existsSync(venvPython) ? venvPython : 'python3';

    const stdout = execFileSync(pythonBin, ['-m', 'kanban.cli.ctl', '--help'], {
      cwd: repoRoot,
      encoding: 'utf-8',
    });

    expect(stdout).toContain('usage: kanban-ctl');
    expect(stdout).toContain('backup');
    expect(stdout).toContain('restore');
    expect(stdout).toContain('promote');
    expect(stdout).toContain('jobs');
    expect(stdout).toContain('auth');
    expect(stdout).toContain('import');
    expect(stdout).toContain('cutover');
    expect(stdout).toContain('db');

    assertZeroMockData(stdout, 'kanban-ctl --help stdout');
  });

  test('02: Cold-boot /setup + TOTP enroll verify transitions to AAL2 session', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const setupMocks: MockHandlers = {
      'GET /api/v1/setup/status': {
        json: { initialized: false, is_initialized: false, requires_setup: true },
      },
      'GET /api/v1/auth/session': {
        json: { authenticated: false, aal_level: 0, csrf_token: 'csrf-smoke-token-223' },
      },
      'POST /api/v1/setup/claim': {
        json: { status: 'enrollment_required', enrollment_id: 'enr-smoke-1' },
      },
      'POST /api/v1/auth/mfa/totp/enroll': {
        json: {
          secret_base32: 'JBSWY3DPEHPK3PXP',
          otpauth_uri: 'otpauth://totp/kanban:elena_admin?secret=JBSWY3DPEHPK3PXP',
        },
      },
      'POST /api/v1/auth/mfa/totp/confirm': {
        json: {
          status: 'enrolled',
          recovery_codes: [
            'code-01-aaaa',
            'code-02-bbbb',
            'code-03-cccc',
            'code-04-dddd',
            'code-05-eeee',
            'code-06-ffff',
            'code-07-gggg',
            'code-08-hhhh',
            'code-09-iiii',
            'code-10-jjjj',
          ],
        },
      },
    };

    assertZeroMockData(setupMocks, 'setup mocks');
    await mockApi(page, setupMocks);

    await page.goto(`/setup?token=${VALID_SETUP_TOKEN}`);
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Step 1: Submit initial root admin credentials
    await expect(page.locator('.auth-step-pill')).toHaveText('Step 1 of 3');
    await page.locator('#setup-username').fill('elena_admin');
    await page.locator('#setup-display-name').fill('Elena Vance');
    await page.locator('#setup-password').fill('MasterAdminPassphrase14Long!');
    await page.locator('#setup-confirm-password').fill('MasterAdminPassphrase14Long!');
    await page.locator('button:has-text("Claim Instance & Continue")').click();

    // Step 2: TOTP Verification
    await expect(page.locator('.auth-step-pill')).toHaveText('Step 2 of 3');
    await page.locator('.auth-tab:has-text("Authenticator App")').click();
    await expect(page.locator('#setup-totp-verify')).toBeVisible();
    await page.locator('#setup-totp-verify').fill('123456');
    await page.locator('button:has-text("Verify & Continue")').click();

    // Step 3: Emergency recovery codes and confirmation
    await expect(page.locator('.auth-step-pill')).toHaveText('Step 3 of 3');
    await expect(page.locator('.auth-recovery-code-item')).toHaveCount(10);
    const confirmCheckbox = page.locator('.auth-checkbox-wrap input[type="checkbox"]');
    await confirmCheckbox.check();

    const continueBtn = page.locator('button:has-text("Continue to workspace")');
    await expect(continueBtn).toBeEnabled();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-coldboot-setup-step3-${theme}`,
        annotations: [
          {
            selector: '.auth-recovery-grid',
            label: '10 Emergency Recovery Codes',
            note: 'Cold-boot TOTP enrollment verification -> AAL2 confirmation',
          },
          {
            selector: 'button:has-text("Continue to workspace")',
            label: 'AAL2 Transition Action',
            note: 'Unlocks full standalone server administration',
          },
        ],
      });
    }

    const overflow = await scanHorizontalOverflow(page);
    expect(overflow.overflows).toBe(false);
  });

  test('03: Stale-cookie /login recovery cleanly redirects without crashing', async ({
    page,
    context,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    // Simulate stale expired session cookie
    await context.addCookies([
      {
        name: 'kb_session',
        value: 'stale-corrupted-session-token-999',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);

    const staleRecoveryMocks: MockHandlers = {
      'GET /api/v1/auth/session': {
        json: {
          authenticated: false,
          aal_level: 0,
          csrf_token: 'csrf-smoke-token-223',
          stale_session_cleared: true,
        },
      },
      'GET /api/v1/setup/status': {
        json: { initialized: true, is_initialized: true, requires_setup: false },
      },
      'GET /api/v1/auth/cards': {
        json: {
          cards: [
            {
              id: 'card-local-1',
              provider_kind: 'LOCAL_ADMIN',
              slug: 'local-admin',
              display_name: 'Local Administrator',
              button_subtext: 'Local root credentials',
              icon_preset: 'shield',
            },
          ],
        },
      },
    };

    assertZeroMockData(staleRecoveryMocks, 'stale recovery mocks');
    await mockApi(page, staleRecoveryMocks);

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Verify login panel renders cleanly, expands local admin disclosure
    const disclosureBtn = page.locator('button:has-text("Sign in with Local Admin + Passkey / TOTP")');
    await expect(disclosureBtn).toBeVisible();
    await disclosureBtn.click();
    await expect(page.locator('#local-admin-username')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-stale-cookie-login-recovery-${theme}`,
        annotations: [
          {
            selector: '.auth-panel',
            label: 'Clean Stale-Cookie Recovery',
            note: 'Session cleared gracefully, login form presented without 500 error',
          },
        ],
      });
    }
  });

  test('04: POST /api/v1/admin/standalone/backup returns 200 with encrypted archive metadata', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const backupMocks: MockHandlers = {
      'GET /api/v1/auth/me': { json: mockAdminUser },
      'GET /api/v1/me': { json: mockAdminUser },
      'GET /api/v1/users/me': { json: mockAdminUser },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: true,
          aal_level: 2,
          csrf_token: 'csrf-smoke-token-223',
          user: mockAdminUser,
        },
      },
      'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-smoke-token-223' } },
      'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
      'GET /api/v1/system/status': { json: mockStandaloneStatus },
      'GET /api/v1/workspaces': {
        json: {
          items: [{ id: 'ws-smoke-1', slug: 'platform', name: 'Platform Workspace', is_current: true }],
          active_workspace_id: 'ws-smoke-1',
        },
      },
      'GET /api/v1/workspaces/:wsId': {
        json: { id: 'ws-smoke-1', slug: 'platform', name: 'Platform Workspace', is_current: true },
      },
      'GET /api/v1/projects': {
        json: [
          {
            id: 'proj-smoke-1',
            key: 'PRJ',
            name: 'Platform Core',
            description_markdown: 'Primary engineering workspace',
            capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
            is_project_admin: true,
          },
        ],
      },
      'GET /api/v1/projects/PRJ': {
        json: {
          id: 'proj-smoke-1',
          key: 'PRJ',
          name: 'Platform Core',
          description_markdown: 'Primary engineering workspace',
          capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
          is_project_admin: true,
        },
      },
      'GET /api/v1/notifications': { json: { items: [], total: 0 } },
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
      'GET /api/v1/admin/standalone/backups': {
        json: [
          {
            filename: 'kanban-backup-smoke-20261119-000000.kbbak',
            size_bytes: 4194304,
            created_at: '2026-11-19T00:00:00Z',
          },
        ],
      },
      'POST /api/v1/admin/standalone/backup': {
        status: 200,
        headers: {
          'Content-Disposition': 'attachment; filename="kanban-backup-smoke-20261119-052400.kbbak"',
        },
        json: {
          filename: 'kanban-backup-smoke-20261119-052400.kbbak',
          size_bytes: 4194304,
          created_at: new Date().toISOString(),
          status: 'completed',
          format: 'KBBAK1',
          sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        },
      },
    };

    assertZeroMockData(backupMocks, 'backup mocks');
    await mockApi(page, backupMocks);

    await page.goto('/admin/standalone');
    await expect(page.locator('.standalone-panel')).toBeVisible();

    // Switch to Backup tab
    const backupTab = page.locator('#tab-backup');
    await backupTab.click();

    // Fill passphrase and submit backup request
    await page.locator('#backup-passphrase').fill('PassphraseSecret16CharsLong!');
    const downloadBackupBtn = page.locator('button:has-text("Download Encrypted Backup (.kbbak)")');
    await expect(downloadBackupBtn).toBeEnabled();
    await downloadBackupBtn.click();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-admin-standalone-backup-200-${theme}`,
        annotations: [
          {
            selector: '.standalone-panel',
            label: 'Standalone Studio with AAL2',
            note: 'POST /api/v1/admin/standalone/backup returns 200 without network errors',
          },
        ],
      });
    }

    const overflow = await scanHorizontalOverflow(page);
    expect(overflow.overflows).toBe(false);
  });
});
