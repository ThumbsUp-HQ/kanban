// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-71';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-71/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

const mockIssue = {
  id: '01932e6b-0000-7000-8000-000000000071',
  key: 'KAN-71',
  project_key: 'KAN',
  summary: '[KB-AGENT-WORKPAD-01] Add Silent Per-Issue Agent Workpad Slot, Rework Loop Circuit Breaker, Real BudgetEnforcer Wiring & MCP Rate Limits',
  description_markdown: '### Objective\nAdd Silent Per-Issue Agent Workpad Slot, Rework Loop Circuit Breaker, Real BudgetEnforcer Wiring & MCP Rate Limits',
  state: { id: 'st-in-progress', name: 'In Progress', group: 'started' },
  priority: { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
  rework_tripped_at: '2026-11-22T20:00:00Z',
  rework_rejection_streak: 3,
  workpad: {
    id: '01932e6b-0000-7000-8000-000000000072',
    body_markdown: '# Agent Investigation Notes\n- Verified rework circuit breaker trips at max_rework_attempts=3.\n- Workpad CAS revision increments cleanly (rev 2).\n- Token ledger preserves strict token_cap=100 without expansion.\n- Sliding rate limiter active on /mcp/* tools/call (429 RATE_LIMITED).',
    revision: 2,
    updated_at: '2026-11-22T20:05:00Z',
  },
  assignees: [],
  created_by: '01918a22-0000-7000-8000-000000000002',
  created_at: '2026-11-22T19:00:00Z',
  updated_at: '2026-11-22T20:05:00Z',
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
};

function getMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const rawProject = loadFixture<Record<string, unknown>>('project-kan');
  const projectKan = {
    ...rawProject,
    identifier: 'KAN',
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    is_project_admin: true,
  };
  const baseDetail = loadFixture<Record<string, unknown>>('issue-kan-142-detail');
  const issueWithBreaker = {
    ...baseDetail,
    ...mockIssue,
  };

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-71',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-71' } },
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
    'GET /api/v1/projects/KAN/cycles': {
      json: [{ id: 'cycle-1', name: 'Cycle 1', status: 'active' }],
    },
    'GET /api/v1/projects/KAN/modules': {
      json: [
        { id: 'mod-1', name: 'Auth Core' },
        { id: 'mod-2', name: 'Kanban Board' },
      ],
    },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
        { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 4 },
      ],
    },
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
    'GET /api/v1/projects/KAN/issues': { json: { items: [issueWithBreaker], total: 1 } },
    'GET /api/v1/issues/:id': { json: issueWithBreaker },
    'GET /api/v1/issues/:id/subscription': { json: { items: [], subscribed: false } },
    'GET /api/v1/objects/:id/canonical-url': { json: { url: 'http://127.0.0.1:4173/projects/KAN/issues/KAN-71' } },
    'GET /api/v1/issues/:id/activity': { json: loadFixture('activity-kan-142') },
    'GET /api/v1/issues/:id/comments': { json: loadFixture('comments-kan-142') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/notifications': { json: { items: [], total: 0 } },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'POST /api/v1/issues/:id/reset-rework-breaker': { json: { status: 'ok' } },
  };
}

test.describe('KAN-71 Visual Proofs: Agent Workpad and Rework Circuit Breaker', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-71',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: Desktop 1440x900 Light and Dark', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getMocks());
    await page.goto('/projects/KAN/issues/KAN-71');
    await expect(page.locator('[data-testid="rework-tripped-banner"]')).toBeVisible();

    // Expand collapsible workpad section
    await page.locator('[data-testid="split-section-workpad"] summary').first().click();
    await expect(page.locator('[data-testid="surface-section-workpad"]').first()).toBeVisible();

    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '01-workpad-breaker-desktop-light.png'),
      fullPage: true,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '02-workpad-breaker-desktop-dark.png'),
      fullPage: true,
    });
  });

  test('02: Tablet 768x1024', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await mockApi(page, getMocks());
    await page.goto('/projects/KAN/issues/KAN-71');
    await expect(page.locator('[data-testid="rework-tripped-banner"]')).toBeVisible();

    // Expand collapsible workpad section
    await page.locator('[data-testid="split-section-workpad"] summary').first().click();
    await expect(page.locator('[data-testid="surface-section-workpad"]').first()).toBeVisible();

    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '03-workpad-breaker-tablet.png'),
      fullPage: true,
    });
  });

  test('03: Mobile Portrait 390x844 and Landscape 844x390', async ({ page }) => {
    await mockApi(page, getMocks());

    // Portrait 390x844
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/projects/KAN/issues/KAN-71');
    await expect(page.locator('[data-testid="rework-tripped-banner"]')).toBeVisible();

    // Expand collapsible workpad section
    await page.locator('[data-testid="split-section-workpad"] summary').first().click();
    await expect(page.locator('[data-testid="surface-section-workpad"]').first()).toBeVisible();

    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '04-workpad-breaker-mobile-portrait.png'),
      fullPage: true,
    });

    // Landscape 844x390
    await page.setViewportSize({ width: 844, height: 390 });
    await page.waitForTimeout(100);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-workpad-breaker-mobile-landscape.png'),
      fullPage: true,
    });
  });
});
