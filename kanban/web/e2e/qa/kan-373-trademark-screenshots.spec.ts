// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-373';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-373/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

function getBaseMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const rawProject = loadFixture<Record<string, unknown>>('project-kan');
  const projectKan = {
    ...rawProject,
    identifier: 'KAN',
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    is_project_admin: true,
  };

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: { ...me, is_server_admin: true } },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-373',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-373' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: '01918a22-0000-7000-8000-000000000001',
          name: 'Primary Workspace',
          slug: 'kanban',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/workspaces/current': {
      json: {
        id: '01918a22-0000-7000-8000-000000000001',
        name: 'Primary Workspace',
        slug: 'kanban',
        is_current: true,
      },
    },
    'GET /api/v1/admin/workspace-settings': {
      json: {
        id: '01918a22-0000-7000-8000-000000000001',
        name: 'Primary Workspace',
        slug: 'kanban',
        default_project_visibility: 'workspace',
        session_idle_timeout_min: 120,
        session_absolute_timeout_min: 1440,
        trash_retention_days: 30,
        issue_export_enabled: true,
        issue_import_enabled: true,
        issue_export_allowed_roles: ['workspace_admin', 'project_admin'],
      },
    },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/cycles': {
      json: [{ id: 'cycle-1', name: 'Cycle 1', status: 'active' }],
    },
    'GET /api/v1/projects/KAN/modules': {
      json: [{ id: 'mod-1', name: 'Auth Core' }],
    },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
        { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 4 },
      ],
    },
    'GET /api/v1/projects/KAN/issues': { json: loadFixture('issues-kan') },
    'GET /api/v1/projects/KAN/priorities': {
      json: [
        { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
        { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
        { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
        { slug: 'low', label: 'Low', emoji: '💤', sort_order: 4 },
      ],
    },
    'GET /api/v1/projects/KAN/labels': {
      json: [{ id: 'lbl-1', name: 'Frontend', color_hex: '#2563eb' }],
    },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: {
        items: [{ id: 'u-1', handle: '@adam', display_name: 'Adam Outler', type: 'USER' }],
      },
    },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/admin/principals': { json: { items: [], total: 0 } },
    'GET /api/v1/admin/role-bindings': { json: [] },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
  };
}

test.describe('KAN-373 Visual Proofs: Password-Protected ZIP Trademark Removal Across Surfaces', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-373',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: desktop light - Export modal renders Password-Protected ZIP (AES-256) with zero WinZip copy', async ({ page }) => {
    page.on('response', (resp) => {
      console.log('HTTP RESP:', resp.status(), resp.url());
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    // Open export modal
    const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
    await exportBtn.click();

    // Select Password-Protected ZIP option
    const zipRadio = page.locator('[data-testid="export-format-zip"]');
    await zipRadio.click();

    // Enter valid 12+ character password
    const passwordInput = page.locator('[data-testid="export-zip-password-input"]');
    await passwordInput.fill('ExportSecret1234!');

    // Assert trademark-free copy
    await expect(page.locator('strong:has-text("Password-Protected ZIP (AES-256)")')).toBeVisible();
    await expect(page.locator('text=Password meets minimum length')).toBeVisible();

    // Confirm zero WinZip references on screen
    const bodyText = await page.innerText('body');
    expect(bodyText).not.toMatch(/winzip/i);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '01-desktop-light-export-modal.png'),
      fullPage: false,
    });
  });

  test('02: desktop dark - Export modal with Password-Protected ZIP in dark theme', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues');
    await applyTheme(page, 'dark');
    await page.waitForLoadState('networkidle');

    const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
    await exportBtn.click();

    const zipRadio = page.locator('[data-testid="export-format-zip"]');
    await zipRadio.click();

    const passwordInput = page.locator('[data-testid="export-zip-password-input"]');
    await passwordInput.fill('ExportSecretDark123!');

    await expect(page.locator('strong:has-text("Password-Protected ZIP (AES-256)")')).toBeVisible();

    const bodyText = await page.innerText('body');
    expect(bodyText).not.toMatch(/winzip/i);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '02-desktop-dark-export-modal.png'),
      fullPage: false,
    });
  });

  test('03: desktop light - Import tab renders trademark-free ZIP archive guidance', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    const importBtn = page.locator('[data-testid="navigator-import-btn"]');
    await importBtn.click();

    // Verify import guidance copy
    await expect(
      page.locator('text=Import issues from CSV or password-protected ZIP (AES-256) archive'),
    ).toBeVisible();

    const bodyText = await page.innerText('body');
    expect(bodyText).not.toMatch(/winzip/i);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '03-desktop-light-import-modal.png'),
      fullPage: false,
    });
  });

  test('04: desktop light - Workspace settings renders Password-Protected ZIP export and import governance', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/workspaces/settings');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    // Expand Advanced Security & Governance section
    const advToggle = page.locator('[data-testid="workspace-advanced-security-section-toggle"]');
    await advToggle.click();

    // Verify governance toggles have trademark-free copy
    await expect(
      page.locator('text=Enable Issue Export (Allow exporting issues to CSV / Password-Protected ZIP)'),
    ).toBeVisible();
    await expect(
      page.locator('text=Enable Issue Import (Allow importing issues from CSV / Password-Protected ZIP)'),
    ).toBeVisible();

    const bodyText = await page.innerText('body');
    expect(bodyText).not.toMatch(/winzip/i);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '04-desktop-light-workspace-settings.png'),
      fullPage: false,
    });
  });

  test('05: mobile portrait - Export modal responsive rendering on 390x844', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
    await exportBtn.click();

    const zipRadio = page.locator('[data-testid="export-format-zip"]');
    await zipRadio.click();

    await expect(page.locator('strong:has-text("Password-Protected ZIP (AES-256)")')).toBeVisible();

    const bodyText = await page.innerText('body');
    expect(bodyText).not.toMatch(/winzip/i);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-mobile-portrait-export-modal.png'),
      fullPage: false,
    });
  });
});
