// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-211/screenshots',
);

process.env.QA_TICKET_ID = 'KANBA-211';
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const mockAdminUser = {
  id: 'usr-admin-1',
  handle: 'adam_architect',
  display_name: 'Adam Architect',
  email: 'adam@example.com',
  workspace_role: 'WORKSPACE_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
};

const mockProject = {
  id: 'proj-kan-1',
  identifier: 'KAN',
  name: 'Platform Core',
  description_markdown: 'Core platform engineering workspace',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'PROJECT_ADMIN'],
  is_project_admin: true,
  project_role: 'ADMIN',
};

const mockWorkspaces = [
  {
    id: 'ws-default',
    name: 'Primary Workspace',
    slug: 'primary-workspace',
    is_current: true,
  },
];

const mockCycles = [
  {
    id: 'cyc-1',
    name: 'Sprint Alpha',
    status: 'in_progress',
    start_date: '2026-03-01',
    end_date: '2026-03-14',
  },
  {
    id: 'cyc-2',
    name: 'Sprint Beta',
    status: 'upcoming',
    start_date: '2026-03-15',
    end_date: '2026-03-28',
  },
  {
    id: 'cyc-0',
    name: 'Sprint Foundation',
    status: 'completed',
    start_date: '2026-02-15',
    end_date: '2026-02-28',
  },
];

const mockModules = [
  {
    id: 'mod-1',
    name: 'Auth Core',
    status: 'in_progress',
    start_date: '2026-03-01',
    target_date: '2026-03-31',
    description_markdown: 'Hardened multi-card authentication and session management subsystem.',
  },
  {
    id: 'mod-2',
    name: 'Universal Graph',
    status: 'in_progress',
    start_date: '2026-03-05',
    target_date: '2026-04-15',
    description_markdown: 'Universal object model, object links, and link audit engine.',
  },
  {
    id: 'mod-3',
    name: 'UI System',
    status: 'planned',
    start_date: '2026-03-15',
    target_date: '2026-04-30',
    description_markdown: 'Breathable layout tokens, WCAG AA contrast, and mobile responsive shell.',
  },
  {
    id: 'mod-4',
    name: 'Agent Engine',
    status: 'planned',
    start_date: '2026-04-01',
    target_date: '2026-05-15',
    description_markdown: 'Native LLM integrations and forensic proof verification harnesses.',
  },
];

const mockStates = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 4 },
];

const mockPriorities = {
  items: [
    { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
    { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
    { id: 'prio-medium', slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
    { id: 'prio-low', slug: 'low', label: 'Low', emoji: '🔽', sort_order: 4 },
  ],
};

const mockIssues = {
  items: [
    {
      id: 'iss-1',
      key: 'KAN-211',
      project_key: 'KAN',
      summary: 'Fix Cycles and Modules End-to-End Persistence and Lifecycle Actions',
      state: { id: 'st-in-progress', name: 'In Progress', group: 'started' },
      priority: { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
      cycle_id: 'cyc-1',
      cycle: { id: 'cyc-1', name: 'Sprint Alpha' },
      module_ids: ['mod-1', 'mod-3'],
      modules: [
        { id: 'mod-1', name: 'Auth Core' },
        { id: 'mod-3', name: 'UI System' },
      ],
      due_date: '2026-03-14',
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
    {
      id: 'iss-2',
      key: 'KAN-212',
      project_key: 'KAN',
      summary: 'Universal Object Graph Link Auditor and Purger Engine',
      state: { id: 'st-todo', name: 'To Do', group: 'unstarted' },
      priority: { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
      cycle_id: 'cyc-2',
      cycle: { id: 'cyc-2', name: 'Sprint Beta' },
      module_ids: ['mod-2'],
      modules: [{ id: 'mod-2', name: 'Universal Graph' }],
      due_date: '2026-03-28',
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
    {
      id: 'iss-3',
      key: 'KAN-213',
      project_key: 'KAN',
      summary: 'Mobile Viewport 390x844 Responsive Stacking Guard',
      state: { id: 'st-backlog', name: 'Backlog', group: 'backlog' },
      priority: { id: 'prio-medium', slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
      cycle_id: null,
      cycle: null,
      module_ids: [],
      modules: [],
      due_date: null,
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
  ],
  total: 3,
};

function getCommonMocks(): MockHandlers {
  return {
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/me': { json: mockAdminUser },
    'GET /api/v1/users/me': { json: mockAdminUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'csrf-test-token',
        user: mockAdminUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/workspaces': { json: mockWorkspaces },
    'GET /api/v1/workspaces/current': {
      json: { id: 'ws-default', name: 'Primary Workspace', slug: 'primary-workspace' },
    },
    'GET /api/v1/system/status': loadFixture('system-status-prod'),
    'GET /api/v1/projects': { json: [mockProject] },
    'GET /api/v1/projects/KAN': { json: mockProject },
    'GET /api/v1/projects/KAN/cycles': { json: mockCycles },
    'GET /api/v1/projects/KAN/modules': { json: mockModules },
    'GET /api/v1/projects/KAN/states': { json: mockStates },
    'GET /api/v1/projects/KAN/priorities': { json: mockPriorities },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/projects/KAN/members': { json: [] },
    'GET /api/v1/projects/KAN/issues': { json: mockIssues },
    'GET /api/v1/issues/:id': (req) => {
      const found = mockIssues.items.find(
        (i) => i.key === req.params.id || i.id === req.params.id,
      );
      return { json: found ?? mockIssues.items[0] };
    },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-211 Cycles and Modules Visual Proofs', () => {
  test('01: Cycles Page with explicit formatted dates, status pills, and lifecycle actions', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/cycles');
    await page.waitForSelector('[data-testid="project-cycles-view"]', { state: 'visible' });
    await expect(page.locator('[data-testid="cycles-list"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-cycles-page-desktop-${theme}`,
        annotations: [
          {
            selector: '[data-testid="cycles-list"]',
            label: 'Cycles list showing explicit Start/End dates (Start -> End), styled status pills (In Progress, Upcoming, Completed), and Edit/Complete/Delete controls',
          },
          {
            selector: '[data-testid="create-cycle-form"]',
            label: 'Create New Cycle form with unified background tokens and accessible date inputs',
          },
        ],
      });
    }
  });

  test('02: Modules Page with 4-column cards and explicit Start/Target dates on desktop', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/modules');
    await page.waitForSelector('[data-testid="project-modules-view"]', { state: 'visible' });
    await expect(page.locator('[data-testid="modules-list"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-modules-page-desktop-${theme}`,
        annotations: [
          {
            selector: '[data-testid="modules-list"]',
            label: 'Modules list displaying 4-column cards with formatted Start/Target dates, status badges, and Edit/Delete controls',
          },
          {
            selector: '[data-testid="create-module-form"]',
            label: 'Create Module form with name, status select, start date, target date, and description fields',
          },
        ],
      });
    }
  });

  test('03: Modules Page single-column stacking at 390x844 mobile viewport with zero horizontal overflow', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/modules');
    await page.waitForSelector('[data-testid="project-modules-view"]', { state: 'visible' });
    await expect(page.locator('[data-testid="modules-list"]')).toBeVisible();

    // Verify no horizontal scrolling on mobile canvas
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-modules-mobile-390x844-${theme}`,
        annotations: [
          {
            selector: '[data-testid="modules-list"]',
            label: 'Modules cards stacked in a single column at 390x844 mobile with zero horizontal scroll overflow',
          },
        ],
      });
    }
  });

  test('04: Edit Cycle Modal with human-readable date validation error banner', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/cycles');
    await page.waitForSelector('[data-testid="project-cycles-view"]', { state: 'visible' });

    // Open Edit modal for Sprint Alpha
    await page.click('[data-testid="edit-cycle-btn-cyc-1"]');
    await page.waitForSelector('[data-testid="edit-cycle-modal"]', { state: 'visible' });

    // Trigger validation error: end date earlier than start date
    await page.fill('[data-testid="edit-cycle-start-input"]', '2026-03-20');
    await page.fill('[data-testid="edit-cycle-end-input"]', '2026-03-10');
    await page.click('[data-testid="save-edit-cycle-btn"]');
    await page.waitForSelector('[data-testid="edit-cycle-error"]', { state: 'visible' });
    await expect(page.locator('[data-testid="edit-cycle-error"]')).toContainText('End date cannot be earlier than start date');

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-edit-cycle-modal-validation-${theme}`,
        annotations: [
          {
            selector: '[data-testid="edit-cycle-modal"]',
            label: 'Edit Cycle modal with human-readable date order validation error banner (End date cannot be earlier than start date)',
          },
        ],
      });
    }
  });

  test('05: Complete Cycle Modal with Unfinished-Issue Rollover target cycle selector', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/cycles');
    await page.waitForSelector('[data-testid="project-cycles-view"]', { state: 'visible' });

    // Open Complete modal for Sprint Alpha
    await page.click('[data-testid="complete-cycle-btn-cyc-1"]');
    await page.waitForSelector('[data-testid="complete-cycle-modal"]', { state: 'visible' });
    await expect(page.locator('[data-testid="rollover-target-select"]')).toBeVisible();

    // Select Sprint Beta as rollover target
    await page.selectOption('[data-testid="rollover-target-select"]', 'cyc-2');

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-complete-cycle-rollover-modal-${theme}`,
        annotations: [
          {
            selector: '[data-testid="complete-cycle-modal"]',
            label: 'Complete Cycle modal with Unfinished-Issue Rollover target cycle dropdown selector populated with eligible future cycles',
          },
        ],
      });
    }
  });

  test('06: Board Grouped by Cycle with dynamic Sprint Alpha, Sprint Beta, and No Cycle columns', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues?layout=board&groupBy=cycle');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `06-board-grouped-by-cycle-${theme}`,
        annotations: [
          {
            selector: '[data-testid="issues-workspace"]',
            label: 'Board view grouped by Cycle rendering actual project sprint columns (Sprint Alpha, Sprint Beta, No Cycle) instead of State columns',
          },
        ],
      });
    }
  });

  test('07: List View rendering real assigned cycle names and real module pills', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues?layout=list');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });
    await expect(page.locator('.list-row').first()).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `07-list-real-pills-${theme}`,
        annotations: [
          {
            selector: '[data-testid="issues-workspace"]',
            label: 'List View rows rendering real assigned cycle name (Sprint Alpha) and real module pills (Auth Core, UI System) instead of static placeholders',
          },
        ],
      });
    }
  });
});
