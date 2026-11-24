// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync, copyFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KAN-383';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-383/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(150);
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

  const workflowStates = [
    { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1, color_hex: '#64748b' },
    { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2, color_hex: '#3b82f6' },
    { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3, color_hex: '#f59e0b' },
    { id: 'state-done', name: 'Done', group: 'completed', sort_order: 4, color_hex: '#10b981' },
    { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 5, color_hex: '#ef4444' },
  ];

  const boardIssues = {
    items: [
      {
        id: 'iss-101',
        key: 'KAN-101',
        summary: 'Backlog telemetry pipeline ingest schema',
        state_id: 'state-backlog',
        state: workflowStates[0],
        board_rank: '0000000000000001',
        priority: { id: 'p-low', label: 'Low', slug: 'low' },
        assignees: [{ id: 'u-1', handle: 'alice' }],
      },
      {
        id: 'iss-102',
        key: 'KAN-102',
        summary: 'Review CSP violation report ingestion router',
        state_id: 'state-todo',
        state: workflowStates[1],
        board_rank: '0000000000000002',
        priority: { id: 'p-med', label: 'Medium', slug: 'medium' },
        assignees: [{ id: 'u-2', handle: 'bob' }],
      },
      {
        id: 'iss-142',
        key: 'KAN-142',
        summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
        state_id: 'state-in-progress',
        state: workflowStates[2],
        board_rank: '0000000000000003',
        priority: { id: 'p-urg', label: 'Urgent', slug: 'urgent' },
        assignees: [{ id: 'u-adam', handle: 'adam' }, { id: 'u-sec', free_text: 'Ext: SecAudit' }],
        due_date: '2026-12-01',
      },
      {
        id: 'iss-143',
        key: 'KAN-143',
        summary: 'Clean-room security reality checker verification',
        state_id: 'state-done',
        state: workflowStates[3],
        board_rank: '0000000000000004',
        priority: { id: 'p-high', label: 'High', slug: 'high' },
        assignees: [{ id: 'u-qa', handle: 'reality-checker', is_agent: true, name: 'RealityChecker' }],
      },
      {
        id: 'iss-144',
        key: 'KAN-144',
        summary: 'Deprecated legacy basic auth header parser',
        state_id: 'state-cancelled',
        state: workflowStates[4],
        board_rank: '0000000000000005',
        priority: null,
      },
    ],
    total: 5,
  };

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: { ...me, is_server_admin: true } },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-383',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-383' } },
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
    'GET /api/v1/projects/KAN/cycles': { json: [] },
    'GET /api/v1/projects/KAN/modules': { json: [] },
    'GET /api/v1/projects/KAN/states': { json: workflowStates },
    'GET /api/v1/projects/KAN/issues': { json: boardIssues },
    'GET /api/v1/projects/KAN/priorities': {
      json: [
        { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
        { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
        { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
        { slug: 'low', label: 'Low', emoji: '💤', sort_order: 4 },
      ],
    },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: { items: [{ id: 'u-1', handle: '@adam', display_name: 'Adam Outler', type: 'USER' }] },
    },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
  };
}

test.describe('KAN-383 Visual Proofs: Workflow State & Priority Color Coding on Kanban Cards', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-383',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: desktop 1440x900 light - Cards render left accent bars and priority color pills', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="board-card-KAN-142"]')).toBeVisible();

    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: '01-board-cards-desktop-1440x900-light',
      annotations: [
        {
          selector: '[data-testid="board-card-KAN-142"]',
          label: 'Card Left Color Accent Bar',
          note: '3.5px solid var(--card-state-accent) matching started (#f59e0b)',
        },
        {
          selector: '[data-testid="board-card-state-btn-KAN-142"] .board-card-state-btn-dot',
          label: 'State Status Dot Indicator',
          note: 'Colored circle indicator matching state accent color',
        },
        {
          selector: '[data-testid="priority-pill-KAN-142"]',
          label: 'Priority Urgent Color Pill',
          note: 'board-card-priority-pill--urgent in .board-card-meta',
        },
      ],
    });

    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '01-board-cards-desktop-1440x900-light.png'));
  });

  test('02: desktop 1440x900 dark - High contrast state accent bars and priority pills in dark mode', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'dark');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="board-card-KAN-142"]')).toBeVisible();

    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: '02-board-cards-desktop-1440x900-dark',
      annotations: [
        {
          selector: '[data-testid="board-card-KAN-142"]',
          label: 'Dark Theme Card Accent',
          note: 'Vibrant amber border-left accent bar against dark surface',
        },
        {
          selector: '[data-testid="board-card-KAN-143"]',
          label: 'Completed State Accent',
          note: 'Emerald green border-left accent bar on done cards',
        },
      ],
    });

    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '02-board-cards-desktop-1440x900-dark.png'));
  });

  test('03: tablet landscape 1024x768 - Clean card layout and visible status accents', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="board-card-KAN-142"]')).toBeVisible();

    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: '03-board-cards-tablet-landscape-1024x768',
      annotations: [
        {
          selector: '[data-testid="board-card-KAN-142"]',
          label: 'Tablet Landscape Board Card',
          note: 'Uncluttered card header and distinct state accent bar',
        },
      ],
    });

    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '03-board-cards-tablet-landscape-1024x768.png'));
  });

  test('04: tablet portrait 768x1024 - Responsive board cards with color coding', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="board-card-KAN-142"]')).toBeVisible();

    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: '04-board-cards-tablet-portrait-768x1024',
      annotations: [
        {
          selector: '[data-testid="board-card-KAN-142"]',
          label: 'Tablet Portrait Card',
          note: 'Clear visual state and priority cues',
        },
      ],
    });

    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '04-board-cards-tablet-portrait-768x1024.png'));
  });

  test('05: mobile 390x844 - Mobile touch board cards with state and priority indicators', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getBaseMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await applyTheme(page, 'light');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="board-card-KAN-142"]')).toBeVisible();

    const shotPath = await annotatedScreenshot(page, testInfo, {
      name: '05-board-cards-mobile-390x844',
      annotations: [
        {
          selector: '[data-testid="board-card-KAN-142"]',
          label: 'Mobile Card Accent',
          note: 'State accent bar and priority pill visible in mobile viewport',
        },
      ],
    });

    copyFileSync(shotPath, resolve(SCREENSHOT_DIR, '05-board-cards-mobile-390x844.png'));
  });
});
