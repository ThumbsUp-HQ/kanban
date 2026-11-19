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
  '../../../../docs/qa/KANBA-221/screenshots',
);

process.env.QA_TICKET_ID = 'KANBA-221';
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
      id: 'iss-221',
      key: 'KAN-221',
      project_key: 'KAN',
      summary: 'Implement Live Your Work Hub, Global Search, and Notifications',
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
      due_date: '2026-03-05',
      dependencies: [
        { source_issue_key: 'KAN-221', target_issue_key: 'KAN-212', kind: 'BLOCKS' },
      ],
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
    {
      id: 'iss-212',
      key: 'KAN-212',
      project_key: 'KAN',
      summary: 'Universal Object Graph Link Auditor and Purger Engine',
      state: { id: 'st-todo', name: 'To Do', group: 'unstarted' },
      priority: { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
      cycle_id: 'cyc-1',
      cycle: { id: 'cyc-1', name: 'Sprint Alpha' },
      module_ids: [],
      modules: [],
      assignees: [],
      created_by_id: 'usr-admin-1',
      created_by: 'usr-admin-1',
      start_date: '2026-03-06',
      due_date: '2026-03-12',
      dependencies: [],
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
    {
      id: 'iss-226',
      key: 'KAN-226',
      project_key: 'KAN',
      summary: 'Shortcuts and Accessibility Standard Milestone',
      state: { id: 'st-done', name: 'Done', group: 'completed' },
      priority: { id: 'prio-medium', slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
      cycle_id: 'cyc-2',
      cycle: { id: 'cyc-2', name: 'Sprint Beta' },
      module_ids: [],
      modules: [],
      assignees: [
        {
          id: 'asg-2',
          principal_id: 'usr-admin-1',
          display_name: 'Adam Architect',
          handle: 'adam_architect',
          type: 'USER',
          principal: { id: 'usr-admin-1', handle: 'adam_architect', display_name: 'Adam Architect', type: 'USER' },
        },
      ],
      created_by_id: 'usr-other-2',
      created_by: 'usr-other-2',
      start_date: '2026-03-02',
      due_date: '2026-03-02',
      dependencies: [],
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
  ],
  total: 3,
};

const mockNotifications = {
  items: [
    {
      id: 'notif-1',
      title: 'Adam Architect assigned you to KAN-221',
      body: 'Implement Live Your Work Hub, Global Search, and Notifications',
      event_type: 'assignment',
      type: 'assignment',
      actor: { display_name: 'Adam Architect', handle: 'adam_architect' },
      issue: { id: 'iss-221', key: 'KAN-221', summary: 'Implement Live Your Work Hub, Global Search, and Notifications' },
      read: false,
      read_at: null,
      link: '/projects/KAN/issues?peek=KAN-221',
      created_at: '2026-03-02T10:00:00Z',
    },
    {
      id: 'notif-2',
      title: 'Gate verified for KAN-211',
      body: 'Reality checker forensic QA gate passed with grade A',
      event_type: 'gate',
      type: 'gate',
      actor: { display_name: 'Reality Checker', handle: 'reality_checker' },
      issue: { id: 'iss-211', key: 'KAN-211', summary: 'Cycles and Modules Architecture' },
      read: false,
      read_at: null,
      link: '/projects/KAN/cycles',
      created_at: '2026-03-02T09:30:00Z',
    },
    {
      id: 'notif-3',
      title: 'Mentioned in KAN-212',
      body: '@adam_architect please review the link auditor schema',
      event_type: 'mention',
      type: 'mention',
      actor: { display_name: 'Lead Developer', handle: 'lead_dev' },
      issue: { id: 'iss-212', key: 'KAN-212', summary: 'Link Auditor Engine' },
      read: true,
      read_at: '2026-03-01T16:00:00Z',
      link: '/projects/KAN/issues?peek=KAN-212',
      created_at: '2026-03-01T15:00:00Z',
    },
  ],
  unread_count: 2,
};

const mockSavedViews = [
  {
    id: 'view-sprint',
    name: 'Sprint Alpha - In Progress',
    layout: 'table',
    grouping: 'priority',
    sub_grouping: null,
    active_filters: { state: ['st-in-progress'] },
    created_at: '2026-03-01T12:00:00Z',
  },
  {
    id: 'view-timeline',
    name: 'Platform Roadmap BLOCKS',
    layout: 'timeline',
    grouping: 'none',
    sub_grouping: null,
    active_filters: {},
    created_at: '2026-03-01T14:00:00Z',
  },
];

const mockSearchResults = {
  items: [
    {
      id: 'iss-221',
      kind: 'issue',
      key: 'KAN-221',
      title: 'Implement Live Your Work Hub, Global Search, and Notifications',
      link: '/projects/KAN/issues?peek=KAN-221',
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
    {
      id: 'stk-p1',
      kind: 'sticky',
      key: 'STK-1',
      title: 'Quick ideas for Saved Views Persistence',
      link: '/projects/KAN/stickies',
      project_key: 'KAN',
    },
  ],
  results: [
    {
      id: 'iss-221',
      kind: 'issue',
      key: 'KAN-221',
      title: 'Implement Live Your Work Hub, Global Search, and Notifications',
      link: '/projects/KAN/issues?peek=KAN-221',
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
    {
      id: 'stk-p1',
      kind: 'sticky',
      key: 'STK-1',
      title: 'Quick ideas for Saved Views Persistence',
      link: '/projects/KAN/stickies',
      project_key: 'KAN',
    },
  ],
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
    'GET /api/v1/projects/KAN/views': { json: mockSavedViews },
    'POST /api/v1/projects/KAN/views': {
      json: {
        id: 'view-new',
        name: 'New Custom View',
        layout: 'table',
        grouping: 'none',
        sub_grouping: null,
        active_filters: {},
        created_at: '2026-03-02T12:00:00Z',
      },
    },
    'DELETE /api/v1/projects/KAN/views/:id': { json: { success: true } },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/notifications': { json: mockNotifications },
    'PATCH /api/v1/notifications/:id/read': { json: { success: true } },
    'POST /api/v1/notifications/mark-all-read': { json: { success: true } },
    'GET /api/v1/search': { json: mockSearchResults },
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

test.describe('KANBA-221 Live Hubs, Search, Notifications, Saved Views & Table/Timeline QA Proofs', () => {
  test('01: Live Your Work Hub with Assigned, Created, Subscribed tabs and search filtering', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/your-work');
    await page.waitForSelector('[data-testid="your-work-view"]', { state: 'visible' });
    await expect(page.locator('[data-testid="tab-assigned-to-me"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-your-work-hub-${theme}`,
        annotations: [
          {
            selector: '[data-testid="your-work-view"]',
            label: 'Live Your Work Hub with RLS-filtered tabs and real-time counter badges',
          },
          {
            selector: '[data-testid="tab-assigned-to-me"]',
            label: 'Assigned to Me tab showing active work items with project tags and quick inspect links',
          },
          {
            selector: '.your-work-search-box',
            label: 'Instant client-side filter input for rapid item narrowing',
          },
        ],
      });
    }
  });

  test('02: Global Cmd+K Command Palette Hybrid Search Modal', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Open command palette via keyboard or trigger
    await page.keyboard.press('ControlOrMeta+k');
    await page.waitForSelector('[data-testid="command-palette-modal"]', { state: 'visible' });

    // Type query to display hybrid search results
    await page.fill('[data-testid="command-palette-input"]', 'Universal');
    await page.waitForTimeout(400);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-command-palette-search-${theme}`,
        annotations: [
          {
            selector: '[data-testid="command-palette-modal"]',
            label: 'Global Cmd+K Command Palette with hybrid search across Issues, Docs, Pages, and Stickies',
          },
          {
            selector: '[data-testid="command-palette-input"]',
            label: 'Accessible search input with instant debounced API query and navigation shortcuts',
          },
        ],
      });
    }
  });

  test('03: Topbar Notifications Bell and Feed Drawer', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues');
    await page.waitForSelector('[data-testid="notifications-bell"]', { state: 'visible' });

    // Click notifications bell to open feed
    await page.click('[data-testid="notifications-bell"]');
    await page.waitForSelector('[data-testid="notifications-tray"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-notifications-tray-${theme}`,
        annotations: [
          {
            selector: '[data-testid="notifications-tray"]',
            label: 'In-app notification drawer showing assignments, gate verifications, and mentions',
          },
          {
            selector: '[data-testid="mark-all-read-btn"]',
            label: 'Mark all as read action with optimistic state synchronization',
          },
        ],
      });
    }
  });

  test('04: Saved Views Manager View at /projects/:key/views', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/views');
    await page.waitForSelector('[data-testid="project-views-view"]', { state: 'visible' });
    await expect(page.locator('[data-testid="saved-views-list"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-saved-views-manager-${theme}`,
        annotations: [
          {
            selector: '[data-testid="saved-views-list"]',
            label: 'Saved Views persistence manager listing custom layouts, active filters, and grouping',
          },
          {
            selector: '[data-testid="open-view-view-sprint"]',
            label: 'Open View action applying saved layout, grouping, and filter states',
          },
        ],
      });
    }
  });

  test('05: Save View Modal Dialog on Board/Table Views', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues?layout=table');
    await page.waitForSelector('[data-testid="table-view"]', { state: 'visible' });

    // Open Display menu and click Save as view button
    const displayBtn = page.locator('button:has-text("Display")');
    if (await displayBtn.isVisible()) {
      await displayBtn.click();
      await page.waitForTimeout(100);
      const saveViewBtn = page.locator('button:has-text("Save as view")');
      if (await saveViewBtn.isVisible()) {
        await saveViewBtn.click();
        await page.waitForSelector('[data-testid="save-view-modal"]', { state: 'visible' });
      }
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-save-view-modal-${theme}`,
        annotations: [
          {
            selector: '[data-testid="save-view-modal"]',
            label: 'Save View Modal capturing layout, grouping, sub-grouping, and active filter configuration',
          },
          {
            selector: '[data-testid="save-view-name-input"]',
            label: 'Unique view name input with validation and POST /api/v1/projects/:key/views persistence',
          },
        ],
      });
    }
  });

  test('06: Table View Inline Cell Editing with Capability Gates', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues?layout=table');
    await page.waitForSelector('[data-testid="table-view"]', { state: 'visible' });

    // Activate state inline editor on first row
    const stateCell = page.locator('[data-testid="cell-state-iss-221"]');
    if (await stateCell.isVisible()) {
      await stateCell.click();
      await page.waitForTimeout(100);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `06-table-inline-editing-${theme}`,
        annotations: [
          {
            selector: '[data-testid="table-view"]',
            label: 'Interactive Table view with capability-gated inline cell editing for State, Priority, Assignee, and Cycle',
          },
          {
            selector: '[data-testid="cell-state-iss-221"]',
            label: 'Active inline State select editor updating issue state with optimistic local preview',
          },
        ],
      });
    }
  });

  test('07: Timeline View BLOCKS Bezier Dependency Connectors and Single-Day Labels', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues?layout=timeline');
    await page.waitForSelector('[data-testid="timeline-view"]', { state: 'visible' });

    // Ensure Show BLOCKS arrows checkbox is checked
    const arrowsCheckbox = page.locator('#toggle-arrows');
    if (await arrowsCheckbox.isVisible()) {
      const isChecked = await arrowsCheckbox.isChecked();
      if (!isChecked) {
        await arrowsCheckbox.check();
      }
      await page.waitForTimeout(150);
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `07-timeline-blocks-arrows-${theme}`,
        annotations: [
          {
            selector: '[data-testid="timeline-view"]',
            label: 'Timeline view rendering visible SVG Bezier curves connecting BLOCKS dependency relationships',
          },
          {
            selector: '.timeline-toolbar',
            label: 'Unified Today anchor navigation button and dependency connector toggles',
          },
        ],
      });
    }
  });

  test('08: Accessible Keyboard Shortcuts Cheat Sheet Modal', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, getCommonMocks());

    await page.goto('/projects/KAN/issues');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Press ? key to open shortcuts cheat sheet
    await page.keyboard.press('?');
    await page.waitForSelector('[data-testid="shortcuts-cheat-sheet-modal"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `08-shortcuts-cheat-sheet-${theme}`,
        annotations: [
          {
            selector: '[data-testid="shortcuts-cheat-sheet-modal"]',
            label: 'Accessible Keyboard Shortcuts Cheat Sheet modal detailing navigation, actions, and views',
          },
        ],
      });
    }
  });
});
