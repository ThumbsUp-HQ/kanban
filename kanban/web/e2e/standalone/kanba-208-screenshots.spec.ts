/**
 * Playwright Visual & Accessibility Verification for KANBA-208.
 * Captures Light, Dark, Desktop (1440x900), Tablet (1024x768), and Mobile (390x844)
 * screenshots of /admin/standalone across Health, Backup, Compose tabs and Error Banner scroll.
 */

import { test, expect } from '../support/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KANBA-208/screenshots');

const ADMIN_STATUS_FIXTURE = {
  deployment_mode: 'standalone_embedded_pg',
  persistent_volume: true,
  data_mount_point: '/var/lib/kanban/data',
  data_mount_fstype: 'ext4',
  tier_b_sandbox_available: false,
  air_gap_mode: false,
  local_llm_endpoint_host: 'http://host.docker.internal:11434',
  is_server_admin: true,
};

const SCHEDULE_FIXTURE = {
  enabled: true,
  interval_hours: 24,
  retention_count: 7,
  last_run_at: '2026-11-18T08:00:00Z',
  next_run_at: '2026-11-19T08:00:00Z',
};

const SNAPSHOTS_FIXTURE = [
  {
    filename: 'kanban-backup-20261118-080000.kbbak',
    size_bytes: 4194304,
    created_at: '2026-11-18T08:00:00Z',
  },
];

test.describe('KANBA-208 Studio Modal & Tab Accessibility Screenshots', () => {
  test('Capture visual proof across tabs, dark/light, and error banner scroll', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name; // 'desktop', 'tablet', or 'mobile'

    const mockUser = {
      id: '00000000-0000-0000-0000-000000000001',
      email: 'adam@example.com',
      display_name: 'Adam Outler',
      role: 'SERVER_ADMIN',
      capabilities: ['SERVER_ADMIN', 'WORKSPACE_ADMIN'],
    };

    const mockWorkspace = {
      items: [
        {
          id: '00000000-0000-0000-0000-000000000002',
          slug: 'kanban',
          name: '👍kanban',
        },
      ],
      total: 1,
    };

    const mockProjects = [
      {
        id: '00000000-0000-0000-0000-000000000003',
        key: 'KAN',
        name: 'kanban',
      },
    ];

    await mockApi(page, {
      'GET /api/v1/auth/me': { json: mockUser },
      'GET /api/v1/me': { json: mockUser },
      'GET /api/v1/users/me': { json: mockUser },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: true,
          aal_level: 2,
          csrf_token: 'csrf-test-token',
          user: mockUser,
        },
      },
      'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token' } },
      'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
      'GET /api/v1/workspaces': { json: mockWorkspace },
      'GET /api/v1/workspaces/:wsId': { json: mockWorkspace.items[0] },
      'GET /api/v1/projects': { json: mockProjects },
      'GET /api/v1/projects/KAN': { json: mockProjects[0] },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/issues': { json: loadFixture('issues-kan') },
      'GET /api/v1/system/status': { json: ADMIN_STATUS_FIXTURE },
      'GET /api/v1/admin/standalone/backup-schedule': { json: SCHEDULE_FIXTURE },
      'PUT /api/v1/admin/standalone/backup-schedule': {
        status: 500,
        json: {
          detail:
            'pg_dump: ERROR: permission denied for table alembic_version. Standalone backup failed with correlation tracking.',
          request_id: 'req-pgdump-alembic-500-corr-id-998',
        },
      },
      'GET /api/v1/admin/standalone/backups': { json: SNAPSHOTS_FIXTURE },
      'GET /api/v1/admin/standalone/compose-export': { json: loadFixture('compose-export-sample') },
    });

    // 1. Light Mode - Navigate to /admin/standalone
    await page.goto('/admin/standalone');
    await page.waitForLoadState('networkidle');

    const dialog = page.locator('.standalone-panel');
    await expect(dialog).toBeVisible();

    // Verify Health Tab
    const healthPanel = page.locator('#panel-health');
    await expect(healthPanel).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/01-health-tab-${projectName}-light.png`,
    });

    // 2. Backup Tab
    const backupTabBtn = page.locator('#tab-backup');
    await backupTabBtn.click();
    const backupPanel = page.locator('#panel-backup');
    await expect(backupPanel).toBeVisible();
    await expect(
      page.locator('.standalone-panel__snapshots-table td', {
        hasText: 'kanban-backup-20261118-080000.kbbak',
      }),
    ).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/02-backup-tab-${projectName}-light.png`,
    });

    // 3. Compose Tab
    const composeTabBtn = page.locator('#tab-compose');
    await composeTabBtn.click();
    const composePanel = page.locator('#panel-compose');
    await expect(composePanel).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/03-compose-tab-${projectName}-light.png`,
    });

    // 4. Trigger Error Banner on Backup Tab
    await backupTabBtn.click();
    const saveScheduleBtn = page.locator('button:has-text("Save Schedule")');
    await saveScheduleBtn.click();

    const errorAlert = page.locator('[data-testid="standalone-api-error-alert"]');
    await expect(errorAlert).toBeVisible();
    await expect(page.locator('[data-testid="correlation-id"]')).toHaveText(
      'req-pgdump-alembic-500-corr-id-998',
    );

    // Verify tabs and close button remain visible and unoccluded
    await expect(page.locator('.standalone-panel__tabs')).toBeVisible();
    await expect(page.locator('.standalone-panel__close')).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/04-error-banner-scroll-${projectName}-light.png`,
    });

    // 5. Dark Mode
    await page.evaluate(() => {
      document.documentElement.dataset.theme = 'dark';
    });

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/05-error-banner-scroll-${projectName}-dark.png`,
    });

    // Health Tab in Dark Mode
    const healthTabBtn = page.locator('#tab-health');
    await healthTabBtn.click();
    await expect(healthPanel).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/06-health-tab-${projectName}-dark.png`,
    });

    // Backup Tab in Dark Mode
    await backupTabBtn.click();
    await expect(backupPanel).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/07-backup-tab-${projectName}-dark.png`,
    });

    // Compose Tab in Dark Mode
    await composeTabBtn.click();
    await expect(composePanel).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/08-compose-tab-${projectName}-dark.png`,
    });
  });
});
