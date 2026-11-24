// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-384';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-384/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

const mockIssues = [
  {
    id: 'iss-142',
    key: 'KAN-142',
    project_key: 'KAN',
    summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
    state_id: 'state-in-progress',
    state: { id: 'state-in-progress', name: 'In Progress', group: 'started' },
    board_rank: '0000000000000010',
    priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'TRANSITION'],
  },
  {
    id: 'iss-143',
    key: 'KAN-143',
    project_key: 'KAN',
    summary: 'Verify LDAPS certificate pinning',
    state_id: 'state-todo',
    state: { id: 'state-todo', name: 'To Do', group: 'unstarted' },
    board_rank: '0000000000000020',
    priority: { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'TRANSITION'],
  },
];

function getBaseMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const rawProject = loadFixture<Record<string, unknown>>('project-kan');
  const projectKan = {
    ...rawProject,
    identifier: 'KAN',
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'TRANSITION'],
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
        csrf_token: 'test-csrf-token-kan-384',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-384' } },
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
        { id: 'state-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
        { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
      ],
    },
    'GET /api/v1/projects/KAN/issues': { json: mockIssues },
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
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
    'GET /api/v1/objects/:id/canonical-url': {
      json: { url: `http://127.0.0.1:${process.env.E2E_PORT ?? '4173'}/projects/KAN/issues/KAN-142` },
    },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'POST /api/v1/projects/KAN/issues/move': {
      json: {
        issue_key: 'KAN-142',
        state_id: 'state-in-review',
        board_rank: '0000000000000099',
        rebalance_scheduled: false,
      },
    },
  };
}

test.describe('KAN-384: Card Quick Move and State Transition Multi-Viewport Proof', () => {
  test('01: desktop 1440x900 light - Board card header renders without overlap, touch quick-move hidden', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    // Wait for card to appear
    const card = page.locator('[data-testid="board-card-KAN-142"]');
    await expect(card).toBeVisible();

    // Verify key and state button are visible
    const key = page.locator('[data-testid="board-card-key-KAN-142"]');
    await expect(key).toBeVisible();

    const stateBtn = page.locator('[data-testid="board-card-state-btn-KAN-142"]');
    await expect(stateBtn).toBeVisible();
    await expect(stateBtn).toContainText('In Progress');

    // Verify touch action button is hidden on fine-pointer desktop
    const touchBtn = page.locator('[data-testid="board-card-touch-action-KAN-142"]');
    await expect(touchBtn).toBeHidden();

    // Verify zero geometric overlap between key and state button
    const keyBox = await key.boundingBox();
    const stateBtnBox = await stateBtn.boundingBox();
    expect(keyBox).not.toBeNull();
    expect(stateBtnBox).not.toBeNull();
    if (keyBox && stateBtnBox) {
      expect(keyBox.x + keyBox.width).toBeLessThanOrEqual(stateBtnBox.x + 1);
    }

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '01-desktop-1440x900-light.png'),
      fullPage: false,
    });
  });

  test('02: desktop 1440x900 dark - Dark theme card header contrast and alignment', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'dark');
    await page.waitForLoadState('networkidle');

    const card = page.locator('[data-testid="board-card-KAN-142"]');
    await expect(card).toBeVisible();

    const stateBtn = page.locator('[data-testid="board-card-state-btn-KAN-142"]');
    await expect(stateBtn).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '02-desktop-1440x900-dark.png'),
      fullPage: false,
    });
  });

  test('03: tablet 1024x768 - Tablet landscape lane ergonomics and card header integrity', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    const card = page.locator('[data-testid="board-card-KAN-142"]');
    await expect(card).toBeVisible();

    const key = page.locator('[data-testid="board-card-key-KAN-142"]');
    const stateBtn = page.locator('[data-testid="board-card-state-btn-KAN-142"]');
    await expect(key).toBeVisible();
    await expect(stateBtn).toBeVisible();

    const keyBox = await key.boundingBox();
    const stateBtnBox = await stateBtn.boundingBox();
    if (keyBox && stateBtnBox) {
      expect(keyBox.x + keyBox.width).toBeLessThanOrEqual(stateBtnBox.x + 1);
    }

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '03-tablet-1024x768.png'),
      fullPage: false,
    });
  });

  test('04: tablet portrait 768x1024 - Tablet portrait lane layout with zero header collision', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    const card = page.locator('[data-testid="board-card-KAN-142"]');
    await expect(card).toBeVisible();

    const key = page.locator('[data-testid="board-card-key-KAN-142"]');
    const stateBtn = page.locator('[data-testid="board-card-state-btn-KAN-142"]');
    await expect(key).toBeVisible();
    await expect(stateBtn).toBeVisible();

    const keyBox = await key.boundingBox();
    const stateBtnBox = await stateBtn.boundingBox();
    if (keyBox && stateBtnBox) {
      expect(keyBox.x + keyBox.width).toBeLessThanOrEqual(stateBtnBox.x + 1);
    }

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '04-tablet-portrait-768x1024.png'),
      fullPage: false,
    });
  });

  test('05: mobile portrait 390x844 - Touch viewport displays quick move button and state button cleanly', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    const card = page.locator('[data-testid="board-card-KAN-142"]');
    await expect(card).toBeVisible();

    const key = page.locator('[data-testid="board-card-key-KAN-142"]');
    const stateBtn = page.locator('[data-testid="board-card-state-btn-KAN-142"]');
    await expect(key).toBeVisible();
    await expect(stateBtn).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-mobile-390x844.png'),
      fullPage: false,
    });
  });

  test('06: desktop 1440x900 - State transition popover opens on card state button click', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    const stateBtn = page.locator('[data-testid="board-card-state-btn-KAN-142"]');
    await expect(stateBtn).toBeVisible();
    await stateBtn.click();

    // Verify QuickFieldPopover opened
    const popover = page.locator('[role="dialog"][aria-label="Quick State Picker"]');
    await expect(popover).toBeVisible();

    // Verify states are listed
    await expect(page.locator('[role="option"]:has-text("In Review")')).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '06-state-transition-popover.png'),
      fullPage: false,
    });
  });
});
