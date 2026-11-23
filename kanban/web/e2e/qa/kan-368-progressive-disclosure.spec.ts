// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Visual and functional proofs for KAN-368:
 * Issue Creation Modal and Properties Rail Progressive Disclosure.
 * Plain ASCII hyphens only.
 */

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-368';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-368/screenshots',
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
  const issueDetail = loadFixture<Record<string, unknown>>('issue-kan-142-detail');

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-368',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-368' } },
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
      json: { id: '01918a22-0000-7000-8000-000000000001', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/views/default': { json: { id: 'view-default', layout: 'board' } },
    'GET /api/v1/projects/KAN/cycles': {
      json: [
        { id: 'cycle-1', name: 'Sprint 1', status: 'active' },
      ],
    },
    'GET /api/v1/projects/KAN/modules': {
      json: [
        { id: 'mod-1', name: 'Core Engine' },
        { id: 'mod-2', name: 'User Experience' },
      ],
    },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
        { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
        { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 6 },
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
        { id: 'lbl-1', name: 'Database', color_hex: '#2563eb' },
        { id: 'lbl-2', name: 'Security', color_hex: '#dc2626' },
      ],
    },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: {
        items: [
          { id: 'u-1', handle: '@alice', display_name: 'Alice Cooper', type: 'USER' },
          { id: 'u-2', handle: '@adam', display_name: 'Adam Outler', type: 'USER' },
        ],
      },
    },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/issues/:id': { json: issueDetail },
    'GET /api/v1/issues/:id/subscription': { json: { items: [], subscribed: false } },
    'GET /api/v1/objects/:id/canonical-url': { json: { url: 'http://127.0.0.1:4173/projects/KAN/issues/KAN-142' } },
    'GET /api/v1/issues/:id/activity': { json: loadFixture('activity-kan-142') },
    'GET /api/v1/issues/:id/comments': { json: loadFixture('comments-kan-142') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
  };
}

test.describe('KAN-368: Issue Creation and Properties Rail Progressive Disclosure E2E Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-368',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: 1440x900 Light - QuickCreateModal default collapsed disclosure', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');

    // Trigger Quick Create Issue modal using shortcut 'c'
    await page.keyboard.press('c');
    const modal = page.locator('[data-testid="quick-create-modal"]');
    await expect(modal).toBeVisible();

    // Verify primary fields are visible
    await expect(page.locator('#quick-create-summary')).toBeVisible();
    await expect(page.locator('#quick-create-description')).toBeVisible();
    await expect(page.locator('#quick-create-state')).toBeVisible();
    await expect(page.locator('#quick-create-priority')).toBeVisible();

    // Verify AdvancedSection is collapsed by default
    const advToggle = page.locator('[data-testid="quick-create-advanced-toggle"]');
    await expect(advToggle).toBeVisible();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'false');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '1440x900-desktop-light-collapsed.png'),
      fullPage: false,
    });
  });

  test('02: 1440x900 Dark - QuickCreateModal expanded with advanced fields', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'dark');

    // Open Quick Create modal
    await page.keyboard.press('c');
    const modal = page.locator('[data-testid="quick-create-modal"]');
    await expect(modal).toBeVisible();

    // Expand AdvancedSection
    const advToggle = page.locator('[data-testid="quick-create-advanced-toggle"]');
    await expect(advToggle).toBeVisible();
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    // Secondary fields are visible
    await expect(page.locator('#quick-create-module')).toBeVisible();
    await expect(page.locator('#quick-create-due-date')).toBeVisible();
    await expect(page.locator('#quick-create-parent')).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '1440x900-desktop-dark-expanded.png'),
      fullPage: false,
    });
  });

  test('03: 768x1024 Tablet - QuickCreateModal collapsed on tablet', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');

    await page.keyboard.press('c');
    const modal = page.locator('[data-testid="quick-create-modal"]');
    await expect(modal).toBeVisible();

    const advToggle = page.locator('[data-testid="quick-create-advanced-toggle"]');
    await expect(advToggle).toBeVisible();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'false');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '768x1024-tablet-collapsed.png'),
      fullPage: false,
    });
  });

  test('04: 390x844 Mobile Portrait - QuickCreateModal expanded mobile view', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');

    await page.keyboard.press('c');
    const modal = page.locator('[data-testid="quick-create-modal"]');
    await expect(modal).toBeVisible();

    const advToggle = page.locator('[data-testid="quick-create-advanced-toggle"]');
    await expect(advToggle).toBeVisible();
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '390x844-mobile-portrait-expanded.png'),
      fullPage: false,
    });
  });

  test('05: 844x390 Mobile Landscape - QuickCreateModal collapsed landscape view', async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');

    await page.keyboard.press('c');
    const modal = page.locator('[data-testid="quick-create-modal"]');
    await expect(modal).toBeVisible();

    const advToggle = page.locator('[data-testid="quick-create-advanced-toggle"]');
    await expect(advToggle).toBeVisible();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'false');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '844x390-mobile-landscape-collapsed.png'),
      fullPage: false,
    });
  });
});
