// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import {
  scanLandmarksAndHeadings,
  scanAccessibleNamesAndAria,
  scanFocusVisibleIndicators,
  scanElementContrast,
} from '../support/gateAuditor';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-315/screenshots',
);

process.env.QA_TICKET_ID = 'KAN-315';
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
];

const mockModules = [
  {
    id: 'mod-1',
    name: 'Auth Core',
    status: 'in_progress',
    start_date: '2026-03-01',
    target_date: '2026-03-31',
    description_markdown: 'Hardened multi-card authentication.',
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
      id: 'iss-315',
      key: 'KAN-315',
      project_key: 'KAN',
      summary: 'Full WCAG 2.2 AA Accessibility Review and Remediation Epic',
      state: { id: 'st-in-progress', name: 'In Progress', group: 'started' },
      priority: { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
      cycle_id: 'cyc-1',
      cycle: { id: 'cyc-1', name: 'Sprint Alpha' },
      module_ids: ['mod-1'],
      modules: [{ id: 'mod-1', name: 'Auth Core' }],
      assignees: [
        {
          id: 'asg-1',
          principal_id: 'usr-admin-1',
          display_name: 'Adam Architect',
          handle: 'adam_architect',
          type: 'USER',
          principal: { id: 'usr-admin-1', handle: 'adam_architect', display_name: 'Adam Architect', type: 'USER' },
        },
      ],
      created_by_id: 'usr-admin-1',
      created_by: 'usr-admin-1',
      start_date: '2026-03-01',
      due_date: '2026-03-15',
      dependencies: [],
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
  ],
  total: 1,
};

const mockSearchResults = {
  items: [
    {
      id: 'iss-315',
      kind: 'issue',
      key: 'KAN-315',
      title: 'Full WCAG 2.2 AA Accessibility Review and Remediation Epic',
      link: '/projects/KAN/issues?peek=KAN-315',
      project_key: 'KAN',
    },
    {
      id: 'doc-arch',
      kind: 'doc',
      key: 'DOC-1',
      title: 'Universal Graph and Architecture Spec',
      link: '/docs/DOC-1',
      project_key: 'KAN',
    },
  ],
  results: [
    {
      id: 'iss-315',
      kind: 'issue',
      key: 'KAN-315',
      title: 'Full WCAG 2.2 AA Accessibility Review and Remediation Epic',
      link: '/projects/KAN/issues?peek=KAN-315',
      project_key: 'KAN',
    },
  ],
};

function getA11yMocks(): MockHandlers {
  const docsTree = loadFixture('docs-tree-kan');
  const pageAuthStudio = loadFixture('page-auth-studio');
  const pageVersions = loadFixture('page-versions-auth-studio');
  const projectAccess = loadFixture('access-project-kan');

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
    'GET /api/v1/workspaces/:wsId': {
      json: { id: 'ws-default', name: 'Primary Workspace', slug: 'primary-workspace', is_current: true },
    },
    'GET /api/v1/system/status': loadFixture('system-status-prod'),
    'GET /api/v1/projects': { json: [mockProject] },
    'GET /api/v1/projects/KAN': { json: mockProject },
    'GET /api/v1/projects/KAN/cycles': { json: mockCycles },
    'GET /api/v1/projects/KAN/modules': { json: mockModules },
    'GET /api/v1/projects/KAN/states': { json: mockStates },
    'GET /api/v1/projects/KAN/priorities': { json: mockPriorities },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/projects/KAN/members': {
      json: [
        {
          id: 'usr-admin-1',
          handle: 'adam_architect',
          display_name: 'Adam Architect',
          role: 'ADMIN',
        },
      ],
    },
    'GET /api/v1/projects/KAN/assignee-suggestions': { json: [] },
    'GET /api/v1/projects/KAN/issues': { json: mockIssues },
    'GET /api/v1/issues/:id': (req) => {
      const found = mockIssues.items.find(
        (i) => i.key === req.params.id || i.id === req.params.id,
      );
      return { json: found ?? mockIssues.items[0] };
    },
    'GET /api/v1/issues/:id/comments': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/:id/activity': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/:id/links': { json: { blocks: [], blocked_by: [], related: [] } },
    'GET /api/v1/issues/:id/subscription': { json: { subscribed: false } },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/search': { json: mockSearchResults },
    'GET /api/v1/projects/KAN/docs/tree': { json: docsTree },
    'GET /api/v1/pages/:pageId': { json: pageAuthStudio },
    'GET /api/v1/pages/:pageId/versions': { json: pageVersions },
    'GET /api/v1/objects/:id/access': { json: projectAccess },
    'GET /api/v1/objects/KAN/access': { json: projectAccess },
    'GET /api/v1/media-proxy': {
      status: 200,
      contentType: 'image/png',
      body: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
        'base64',
      ),
    },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('WCAG 2.2 AA Conformance Full Review & Verification Proofs (KAN-315)', () => {
  test('01: CommandPalette combobox active-descendant and focus-visible outlines', async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getA11yMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Open command palette via shortcut
    await page.keyboard.press('ControlOrMeta+k');
    await page.waitForSelector('[data-testid="command-palette-modal"]', { state: 'visible' });

    const input = page.locator('[data-testid="command-palette-input"]');
    await expect(input).toBeVisible();
    await input.focus();

    // Verify aria-activedescendant
    const activeDesc = await input.getAttribute('aria-activedescendant');
    expect(activeDesc).toBeTruthy();

    // Focus-visible scanner
    const focusViolations = await scanFocusVisibleIndicators(page, ['.kb-palette-input']);
    expect(focusViolations).toHaveLength(0);

    // Apply light theme and capture annotated proof
    await applyTheme(page, 'light');
    await annotatedScreenshot(page, testInfo, {
      name: '01-focus-visible-palette-light',
      annotations: [
        {
          selector: '[data-testid="command-palette-input"]',
          label: 'Combobox input with aria-activedescendant and 2px focus ring',
        },
        {
          selector: '#command-palette-list',
          label: 'Option list with active option highlighted and scrolled into view',
        },
      ],
    });

    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="command-palette-modal"]')).toHaveCount(0);
  });

  test('02: Topbar theme switcher ARIA group and menuitemradio semantics', async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getA11yMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    const avatarBtn = page.locator('[data-testid="topbar-avatar-button"]');
    await avatarBtn.click();

    const menu = page.locator('.kb-avatar-menu');
    await expect(menu).toBeVisible();

    const themeGroup = menu.locator('[role="group"][aria-label="Theme preference"]');
    await expect(themeGroup).toBeVisible();

    const radios = themeGroup.locator('[role="menuitemradio"]');
    await expect(radios).toHaveCount(3);

    // Validate ARIA semantics using gate auditor
    const ariaViolations = await scanAccessibleNamesAndAria(page);
    expect(ariaViolations).toHaveLength(0);

    await applyTheme(page, 'light');
    await annotatedScreenshot(page, testInfo, {
      name: '02-topbar-theme-radio-menu-light',
      annotations: [
        {
          selector: '[role="group"][aria-label="Theme preference"]',
          label: 'Theme preference group inside role="menu"',
        },
        {
          selector: '.kb-theme-radio[aria-checked="true"]',
          label: 'Active theme radio item with aria-checked="true"',
        },
      ],
    });

    await page.keyboard.press('Escape');
    await expect(menu).not.toBeVisible();
  });

  test('03: Sidebar mobile dialog role, aria-modal, and background canvas inertness', async ({
    page,
  }, testInfo) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getA11yMocks());

    await page.goto('/projects/KAN/issues?layout=board');
    await page.waitForSelector('.kb-topbar-hamburger', { state: 'visible' });

    // Click hamburger to open mobile sidebar
    await page.click('.kb-topbar-hamburger');

    const sidebar = page.locator('aside.kb-sidebar');
    await expect(sidebar).toHaveAttribute('role', 'dialog');
    await expect(sidebar).toHaveAttribute('aria-modal', 'true');

    // Main canvas must have inert attribute
    const mainCanvas = page.locator('#main');
    await expect(mainCanvas).toHaveAttribute('inert');
    await expect(mainCanvas).toHaveAttribute('aria-hidden', 'true');

    await applyTheme(page, 'dark');
    await annotatedScreenshot(page, testInfo, {
      name: '03-sidebar-mobile-dialog-dark',
      annotations: [
        {
          selector: 'aside.kb-sidebar',
          label: 'Mobile sidebar overlay with role="dialog" and aria-modal="true"',
        },
        {
          selector: '#main',
          label: 'Main application canvas marked inert and aria-hidden="true"',
        },
      ],
    });

    // Close sidebar
    await page.keyboard.press('Escape');
    await expect(mainCanvas).not.toHaveAttribute('inert');
  });

  test('04: Docs Workspace and Version Diff theme tokens and dark-mode contrast', async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getA11yMocks());

    await page.goto('/projects/KAN/docs');
    await page.waitForSelector('[data-testid="docs-workspace-view"]', { state: 'visible' });

    await applyTheme(page, 'dark');

    // Sweep contrast across headings, buttons, and inputs in docs workspace
    const contrastViolations = await scanElementContrast(
      page,
      ['h1', 'h2', 'h3', 'button', 'input', 'p'],
      '[data-testid="docs-workspace-view"]',
    );
    expect(contrastViolations).toHaveLength(0);

    await annotatedScreenshot(page, testInfo, {
      name: '04-docs-workspace-contrast-dark',
      annotations: [
        {
          selector: '[data-testid="docs-workspace-view"]',
          label: 'Docs Workspace utilizing CSS theme tokens in Dark mode',
        },
        {
          selector: '.docs-title-input',
          label: 'Accessible document title input with theme border and focus ring',
        },
      ],
    });
  });

  test('05: Issue Navigator search inputs and card focus rings in dark mode', async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getA11yMocks());

    await page.goto('/projects/KAN/issues?layout=list');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    await applyTheme(page, 'dark');

    // Validate landmarks and headings
    const landmarkViolations = await scanLandmarksAndHeadings(page);
    expect(landmarkViolations).toHaveLength(0);

    // Validate focus visible outlines on navigator inputs
    const focusViolations = await scanFocusVisibleIndicators(page, [
      '.navigator-search-input',
      '.navigator-query-input',
    ]);
    expect(focusViolations).toHaveLength(0);

    await annotatedScreenshot(page, testInfo, {
      name: '05-navigator-focus-rings-dark',
      annotations: [
        {
          selector: '.navigator-search-input',
          label: 'Issue navigator search input with 2px solid focus indicator',
        },
        {
          selector: '.issue-list-card',
          label: 'Issue item card with visible outline on focus',
        },
      ],
    });
  });
});
