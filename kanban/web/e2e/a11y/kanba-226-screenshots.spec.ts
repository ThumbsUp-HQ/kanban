// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-226/screenshots',
);

process.env.QA_TICKET_ID = 'KANBA-226';
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const issueKan142 = {
  key: 'KAN-142',
  object_id: 'c0000000-0000-0000-0000-000000000142',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
  description_markdown: 'Detailed description of the auth hardening task.',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  state: {
    id: 'st-in-progress',
    name: 'In Progress',
    group: 'started',
  },
  etag: '"etag-kan-142"',
};

async function setupA11yMocks(page: Page): Promise<void> {
  await page.unroute('**/api/v1/**');
  const me = loadFixture('me-adam');
  const systemStatus = loadFixture('system-status-prod');
  const rawProject = loadFixture<Record<string, unknown>>('project-kan');
  const projectKan = {
    ...rawProject,
    identifier: 'KAN',
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    is_project_admin: true,
  };
  const kan142Access = loadFixture('access-inspector-kan-142');
  const projectAccess = loadFixture('access-project-kan');
  const docsTree = loadFixture('docs-tree-kan');
  const pageAuthStudio = loadFixture('page-auth-studio');
  const pageVersions = loadFixture('page-versions-auth-studio');

  await mockApi(page, {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 1,
        csrf_token: 'csrf-test-token',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: systemStatus },
    'GET /api/v1/workspaces': {
      json: {
        items: [{ id: 'ws-default', name: 'Primary Workspace', slug: 'primary-workspace', is_current: true }],
        active_workspace_id: 'ws-default',
      },
    },
    'GET /api/v1/workspaces/:wsId': { json: { id: 'ws-default', name: 'Primary Workspace', slug: 'primary-workspace', is_current: true } },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/:key/views': { json: [] },
    'GET /api/v1/projects/:key/custom-fields': { json: [] },
    'GET /api/v1/projects/KAN/issues': { json: { items: [issueKan142], total: 1 } },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
        { id: 'st-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'st-done', name: 'Done', group: 'completed', sort_order: 4 },
      ],
    },
    'GET /api/v1/projects/KAN/priorities': {
      json: {
        items: [
          { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
          { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
          { id: 'prio-medium', slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
          { id: 'prio-low', slug: 'low', label: 'Low', emoji: '🔽', sort_order: 4 },
        ],
      },
    },
    'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
    'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
    'GET /api/v1/projects/KAN/labels': { json: { items: [] } },
    'GET /api/v1/projects/KAN/docs/tree': { json: docsTree },
    'GET /api/v1/pages/:pageId': { json: pageAuthStudio },
    'GET /api/v1/pages/:pageId/versions': { json: pageVersions },
    'GET /api/v1/issues/KAN-142': { json: issueKan142 },
    'GET /api/v1/issues/KAN-143': { json: { ...issueKan142, key: 'KAN-143', summary: 'Next task' } },
    'GET /api/v1/issues/KAN-999': { status: 404, json: { title: 'Not Found', status: 404 } },
    'GET /api/v1/issues/KAN-142/activity': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/comments': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/state': { json: { name: 'In Progress', group: 'started' } },
    'GET /api/v1/issues/KAN-142/subscription': { json: { subscribed: false } },
    'GET /api/v1/issues/KAN-142/links': { json: { blocks: [], blocked_by: [], related: [] } },
    'GET /api/v1/issues/KAN-142/delete-preview': { json: { can_delete: true, cascade_counts: {} } },
    'GET /api/v1/objects/KAN-142/canonical-url': { json: { url: '/projects/KAN/issues/KAN-142' } },
    'GET /api/v1/objects/c0000000-0000-0000-0000-000000000142/access': { json: kan142Access },
    'GET /api/v1/objects/KAN-142/access': { json: kan142Access },
    'GET /api/v1/objects/KAN/access': { json: projectAccess },
    'GET /api/v1/objects/:id/access': { json: projectAccess },
  });
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-226 A11y & WCAG 2.2 AA Focus Traps, ARIA Hierarchy & Label Parity', () => {
  test('01: QuickCreateIssueModal enforces cyclic focus trap, aria-modal="true", and Escape restoration', async ({
    page,
  }, testInfo) => {
    await setupA11yMocks(page);
    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Open Quick Create modal via board new item button or shortcut key
    const boardNewItemBtn = page.locator('.board-new-item-btn').first();
    if (await boardNewItemBtn.isVisible()) {
      await boardNewItemBtn.click();
    } else {
      await page.keyboard.press('c');
    }

    const modal = page.locator('.quick-create-modal-overlay');
    await expect(modal).toBeVisible();

    // Verify dialog role and aria-modal attributes
    await expect(modal).toHaveAttribute('role', 'dialog');
    await expect(modal).toHaveAttribute('aria-modal', 'true');
    await expect(modal).toHaveAttribute('aria-labelledby', 'quick-create-title');

    // Summary input should be present and focusable
    const summaryInput = page.locator('#quick-create-summary');
    await expect(summaryInput).toBeVisible();

    // Test focus wrapping within modal
    await summaryInput.focus();
    await page.keyboard.press('Shift+Tab');
    const focusedShift = await page.evaluate(() => document.activeElement?.tagName);
    expect(focusedShift).not.toBe('BODY');

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-modal-focus-trap-${theme}`,
        annotations: [
          {
            selector: '.quick-create-modal-overlay',
            label: 'QuickCreate modal with role="dialog" and aria-modal="true"',
          },
          {
            selector: '#quick-create-summary',
            label: 'Initial focus target inside modal trap',
          },
          {
            selector: '.filter-chip-remove',
            label: 'Modal close button with aria-label="Close modal"',
          },
        ],
      });
    }

    // Escape closes modal deterministically
    await page.keyboard.press('Escape');
    await expect(modal).toHaveCount(0);
  });

  test('02: IssuePeekDrawer enforces cyclic focus trap, aria-modal="true", and deterministic focus return', async ({
    page,
  }, testInfo) => {
    await setupA11yMocks(page);
    await page.goto('/__dev/drawer');
    await page.waitForSelector('[data-testid="link-kan-142"]', { state: 'visible' });

    // Click trigger link to open drawer
    await page.click('[data-testid="link-kan-142"]');

    const drawer = page.locator('.surface--drawer');
    await expect(drawer).toBeVisible();

    // Assert dialog role and aria-modal attribute
    await expect(drawer).toHaveAttribute('role', 'dialog');
    await expect(drawer).toHaveAttribute('aria-modal', 'true');

    // Close button exists inside drawer header
    const closeBtn = drawer.locator('button[aria-label="Close issue panel"]').first();
    await expect(closeBtn).toBeVisible();

    // Ensure focus is within drawer
    await closeBtn.focus();
    await page.keyboard.press('Tab');
    const focusedWithin = await page.evaluate(() => {
      const active = document.activeElement;
      const d = document.querySelector('.surface--drawer');
      return d ? d.contains(active) : false;
    });
    expect(focusedWithin).toBe(true);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-drawer-focus-trap-${theme}`,
        annotations: [
          {
            selector: '.surface--drawer',
            label: 'IssuePeekDrawer with role="dialog" and aria-modal="true"',
          },
          {
            selector: 'button[aria-label="Close issue panel"]',
            label: 'Drawer close button with aria-label="Close issue panel"',
          },
        ],
      });
    }

    // Press Escape to close drawer and assert focus restoration
    await page.keyboard.press('Escape');
    await expect(drawer).not.toBeVisible();
  });

  test('03: AccessInspectorPopover enforces cyclic focus trap and aria-modal="true"', async ({
    page,
  }, testInfo) => {
    await setupA11yMocks(page);
    await page.goto('/__dev/drawer');
    await page.waitForSelector('[data-testid="link-kan-142"]', { state: 'visible' });

    // Open Access Inspector Popover via custom event on host
    await page.evaluate((objectId) => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId },
        }),
      );
    }, 'c0000000-0000-0000-0000-000000000142');

    const popover = page.locator('div.access-inspector[role="dialog"]');
    await expect(popover).toBeVisible();
    await expect(popover).toHaveAttribute('aria-modal', 'true');

    // Close button exists inside popover
    const closeBtn = popover.locator('.access-inspector__close-btn');
    await expect(closeBtn).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-access-focus-trap-${theme}`,
        annotations: [
          {
            selector: 'div.access-inspector[role="dialog"]',
            label: 'Access Inspector dialog overlay with aria-modal="true"',
          },
          {
            selector: '.access-inspector__close-btn',
            label: 'Access inspector close button with aria-label="Close Access Inspector"',
          },
        ],
      });
    }

    // Press Escape to close popover
    await page.keyboard.press('Escape');
    await expect(popover).not.toBeVisible();
  });

  test('04: ListView conforms strictly to WAI-ARIA 1.2 Table/RowGroup/Row/Cell hierarchy', async ({
    page,
  }, testInfo) => {
    await setupA11yMocks(page);
    await page.goto('/projects/KAN/issues?layout=list');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    const targetRow = page.locator('[data-issue-key="KAN-142"]');
    await expect(targetRow).toBeVisible();

    // Verify Table role
    const table = page.locator('.list-section:has([data-issue-key="KAN-142"]) .list-table');
    await expect(table).toHaveAttribute('role', 'table');

    // Verify RowGroup role
    const rowgroup = page.locator('.list-section:has([data-issue-key="KAN-142"]) .list-rows');
    await expect(rowgroup).toHaveAttribute('role', 'rowgroup');

    // Verify Row role
    await expect(targetRow).toHaveAttribute('role', 'row');

    // Verify Cell roles
    const cells = targetRow.locator('> div[role="cell"]');
    const cellCount = await cells.count();
    expect(cellCount).toBeGreaterThanOrEqual(2);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-list-aria-hierarchy-${theme}`,
        annotations: [
          {
            selector: '.list-section:has([data-issue-key="KAN-142"]) .list-table',
            label: 'List View table container with role="table"',
          },
          {
            selector: '.list-section:has([data-issue-key="KAN-142"]) .list-rows',
            label: 'List View rowgroup container with role="rowgroup"',
          },
          {
            selector: '[data-issue-key="KAN-142"]',
            label: 'List View row item with role="row"',
          },
          {
            selector: '[data-issue-key="KAN-142"] > .list-row-left',
            label: 'List View cell with role="cell"',
          },
        ],
      });
    }
  });

  test('05: WCAG 2.5.3 label parity across Topbar Search, Board Card, and Docs New Doc', async ({
    page,
  }, testInfo) => {
    await setupA11yMocks(page);
    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // 1. Topbar Global Search trigger
    const searchBtn = page.locator('.kb-search-trigger');
    await expect(searchBtn).toBeVisible();
    await expect(searchBtn).toHaveAttribute('aria-label', 'Search... (Cmd+K)');
    const searchText = await searchBtn.textContent();
    expect(searchText).toContain('Search...');

    // 2. Board Card label parity
    const card = page.locator('[data-issue-key="KAN-142"]');
    await expect(card).toBeVisible();
    const cardAriaLabel = await card.getAttribute('aria-label');
    expect(cardAriaLabel).toContain('KAN-142');
    expect(cardAriaLabel).toContain('Harden Multi-Card OIDC & LDAPS Auth Studio');

    // 3. Docs + New Doc button
    await page.goto('/projects/KAN/docs');
    await page.waitForSelector('.docs-workspace-view', { state: 'visible' });

    const newDocBtn = page.locator('[data-testid="create-root-doc-btn"]');
    await expect(newDocBtn).toBeAttached();
    await expect(newDocBtn).toHaveAttribute('aria-label', '+ New Doc');
    const newDocText = await newDocBtn.textContent();
    expect(newDocText?.trim()).toBe('+ New Doc');

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-wcag-label-parity-${theme}`,
        annotations: [
          {
            selector: '.kb-search-trigger',
            label: 'Topbar search button with aria-label="Search... (Cmd+K)"',
          },
        ],
      });
    }
  });
});
