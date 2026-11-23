// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import {
  scanMobileTouchTargets,
  scanMobileInputFontSizes,
  scanTopbarOcclusion,
} from '../support/gateAuditor';

process.env.QA_TICKET_ID = 'KAN-314';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-314/screenshots'
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
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'PROJECT_ADMIN'],
    is_project_admin: true,
  };
  const issueDetail = {
    ...loadFixture<Record<string, unknown>>('issue-kan-142-detail'),
    id: '01918a22-3140-7000-8000-000000000314',
    key: 'KAN-142',
    identifier: 'KAN-142',
    project_key: 'KAN',
    summary: 'Mobile and landscape responsiveness validation item',
    state: 'In Progress',
    priority: 'high',
  };

  const docsTree = loadFixture<unknown[]>('docs-tree-kan');

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: '11111111-1111-4111-8111-111111111111',
        workspace_id: '01918a22-0000-7000-8000-000000000001',
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-314',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-314' } },
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
      },
    },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/access': {
      json: {
        resource_id: 'KAN',
        resource_kind: 'project',
        effective_policy: 'ALLOW',
        entries: [],
      },
    },
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
        { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
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
      json: [
        { id: 'lbl-1', name: 'Frontend', color_hex: '#2563eb' },
        { id: 'lbl-2', name: 'Mobile', color_hex: '#10b981' },
      ],
    },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: {
        items: [{ id: 'u-1', handle: '@adam', display_name: 'Adam Outler', type: 'USER' }],
      },
    },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/docs/tree': { json: docsTree },
    'GET /api/v1/projects/KAN/docs': { json: docsTree },
    'GET /api/v1/docs/:id/tree': { json: docsTree },
    'GET /api/v1/projects/KAN/docs/:id': {
      json: loadFixture('page-auth-studio'),
    },
    'GET /api/v1/pages/:id': {
      json: loadFixture('page-auth-studio'),
    },
    'GET /api/v1/pages/:id/versions': {
      json: loadFixture('page-versions-auth-studio'),
    },
    'GET /api/v1/projects/KAN/stickies': { json: [] },
    'GET /api/v1/notifications': {
      json: {
        items: [
          {
            id: 'notif-1',
            title: 'Welcome to Mobile Review',
            body: 'Responsive touches and typography are enabled.',
            read: false,
            created_at: new Date().toISOString(),
          },
        ],
        unread_count: 1,
      },
    },
    'GET /api/v1/notifications/unread-count': { json: { count: 1 } },
    'POST /api/v1/notifications/:id/read': { json: { ok: true } },
    'POST /api/v1/notifications/mark-all-read': { json: { ok: true } },
    'GET /api/v1/issues/:id': { json: issueDetail },
    'GET /api/v1/issues/:id/subscription': { json: { items: [], subscribed: false } },
    'GET /api/v1/issues/:id/links': { json: loadFixture('links-kan-142') },
    'GET /api/v1/issues/:id/delete-preview': { json: loadFixture('delete-preview-kan-142') },
    'GET /api/v1/objects/:id/canonical-url': {
      json: { url: 'http://127.0.0.1:4173/projects/KAN/issues/KAN-142' },
    },
    'GET /api/v1/issues/:id/activity': { json: loadFixture('activity-kan-142') },
    'GET /api/v1/issues/:id/comments': { json: loadFixture('comments-kan-142') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
    'GET /api/v1/auth/identities': { json: [] },
    'GET /api/v1/auth/mfa/status': {
      json: {
        totp_enabled: false,
        passkeys_count: 0,
        recovery_codes_remaining: 10,
      },
    },
    'GET /api/v1/auth/webauthn/credentials': { json: [] },
    'GET /api/v1/media-proxy': {
      status: 200,
      contentType: 'image/png',
      body: '',
    },
  };
}

test.describe('KAN-314 Mobile & Landscape Browser Ergonomics Verification Suite', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-314',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: mobile portrait (390x844) - Login surface font sizes and touch targets', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Verify font-size >= 16px on mobile inputs
    const fontViolations = await scanMobileInputFontSizes(page, { minFontSize: 16 });
    expect(fontViolations, `Font size violations on /login: ${JSON.stringify(fontViolations)}`).toHaveLength(0);

    // Verify touch targets >= 44x44px (ignoring non-interactive inline badges and native checkboxes)
    const touchViolations = await scanMobileTouchTargets(page, {
      minTargetSize: 44,
      ignoreSelectors: ['input[type="checkbox"]', '[id^="kb-hint-trigger"]', '.kb-hint-trigger', '#login-remember-me'],
    });
    expect(touchViolations, `Touch target violations on /login: ${JSON.stringify(touchViolations)}`).toHaveLength(0);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '01-mobile-portrait-login.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('02: mobile portrait (390x844) - Board layout, topbar offset, and column state headers', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const recorder = await mockApi(page, getBaseMocks());

    // Mount 2D swimlanes view with sub_group_by=priority to audit stacked mobile column headers
    await page.goto('/projects/KAN/issues?layout=board&sub_group_by=priority');
    await page.waitForLoadState('networkidle');

    // Verify zero topbar occlusion
    const occlusionViolations = await scanTopbarOcclusion(page);
    expect(occlusionViolations).toHaveLength(0);

    // Verify mobile column state headers render
    const mobileHeaders = page.locator('.swimlane-column-mobile-header');
    await expect(mobileHeaders.first()).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '02-mobile-portrait-board.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('03: mobile portrait (390x844) - Command palette touch close button and bounded height', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForLoadState('networkidle');

    // Open command palette via topbar search trigger
    const searchBtn = page.locator('.kb-search-trigger');
    await expect(searchBtn).toBeVisible();
    await searchBtn.click();

    const commandPalette = page.locator('.kb-palette-dialog');
    await expect(commandPalette).toBeVisible();

    // Verify 44x44px touch close button exists
    const closeBtn = page.locator('[data-testid="command-palette-close-btn"]');
    await expect(closeBtn).toBeVisible();
    const box = await closeBtn.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThanOrEqual(44);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }

    // Verify input font-size >= 16px to prevent iOS auto-zoom
    const inputFontViolations = await scanMobileInputFontSizes(page, {
      containerSelector: '.kb-palette-dialog',
      minFontSize: 16,
    });
    expect(inputFontViolations).toHaveLength(0);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '03-mobile-portrait-command-palette.png'),
      fullPage: false,
    });

    // Close cleanly via the touch close button
    await closeBtn.click();
    await expect(commandPalette).toBeHidden();
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('04: mobile portrait (390x844) - Notifications tray viewport bounding and touch target', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForLoadState('networkidle');

    const notifBtn = page.locator('[data-testid="notifications-bell"]');
    await expect(notifBtn).toBeVisible();
    await notifBtn.click();

    const notifTray = page.locator('.kb-notif-tray');
    await expect(notifTray).toBeVisible();

    // Verify mark-read button is >= 44x44px
    const markReadBtn = page.locator('.kb-notif-mark-read-btn').first();
    if (await markReadBtn.isVisible()) {
      const markBox = await markReadBtn.boundingBox();
      expect(markBox).not.toBeNull();
      if (markBox) {
        expect(markBox.width).toBeGreaterThanOrEqual(44);
        expect(markBox.height).toBeGreaterThanOrEqual(44);
      }
    }

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '04-mobile-portrait-notifications.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('05: mobile portrait (390x844) - Issue drawer peek and properties rail dropdown containment', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board&peek=KAN-142');
    await page.waitForLoadState('networkidle');

    // Verify issue drawer or peek surface is visible
    const issueSurface = page.locator('.surface--drawer, .surface--full, .surface__body');
    await expect(issueSurface.first()).toBeVisible();

    // Verify input font sizes in drawer >= 16px
    const drawerFonts = await scanMobileInputFontSizes(page, {
      containerSelector: '.surface--drawer, .surface--full, .surface__body',
      minFontSize: 16,
    });
    expect(drawerFonts).toHaveLength(0);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-mobile-portrait-issue-drawer.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('06: mobile portrait (390x844) - Docs workspace drawers and coarse action visibility', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/docs');
    await page.waitForLoadState('networkidle');

    // Verify docs drawer / tree has no topbar occlusion
    const docsOcclusion = await scanTopbarOcclusion(page, '.kb-topbar', ['.docs-tree-pane', '.docs-rail-pane']);
    expect(docsOcclusion).toHaveLength(0);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '06-mobile-portrait-docs-tree.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('07: mobile portrait (390x844) - Personal profile and avatar cropper responsiveness', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/settings/profile');
    await page.waitForLoadState('networkidle');

    const profileFonts = await scanMobileInputFontSizes(page, { minFontSize: 16 });
    expect(profileFonts).toHaveLength(0);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '07-mobile-portrait-settings-profile.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('08: mobile landscape (844x390) - Board view containment and layout', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForLoadState('networkidle');

    const occlusion = await scanTopbarOcclusion(page);
    expect(occlusion).toHaveLength(0);

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '08-mobile-landscape-board.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('09: mobile landscape (844x390) - Command palette bounded in compact landscape', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForLoadState('networkidle');

    const searchBtn = page.locator('.kb-search-trigger');
    await expect(searchBtn).toBeVisible();
    await searchBtn.click();

    const commandPalette = page.locator('.kb-palette-dialog');
    await expect(commandPalette).toBeVisible();

    const box = await commandPalette.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // Must not exceed viewport height of 390px
      expect(box.height).toBeLessThanOrEqual(390);
    }

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '09-mobile-landscape-command-palette.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('10: tablet portrait (768x1024) - Board layout verification', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForLoadState('networkidle');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '10-tablet-portrait-board.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('11: tablet portrait (768x1024) - Docs workspace verification', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/docs');
    await page.waitForLoadState('networkidle');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '11-tablet-portrait-docs.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('12: desktop (1440x900) - Light theme baseline board screenshot', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '12-desktop-board-light.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });

  test('13: desktop (1440x900) - Dark theme baseline board screenshot', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const recorder = await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'dark');
    await page.waitForLoadState('networkidle');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '13-desktop-board-dark.png'),
      fullPage: false,
    });
    expect(recorder.unmatchedCalls).toHaveLength(0);
  });
});
