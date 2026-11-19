// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers, type MockRequest } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KANBA-214';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-214/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

function getSettingsMocks(): MockHandlers {
  const me = {
    id: '01918a22-0000-7000-8000-000000000001',
    handle: '@adam',
    display_name: 'Adam Outler',
    email: 'adam@example.com',
    type: 'USER',
    is_server_admin: true,
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'SERVER_ADMIN'],
  };

  const projectKan = {
    id: '01918a22-0000-7000-8000-000000000010',
    identifier: 'KAN',
    key: 'KAN',
    name: 'Kanban Platform',
    description: 'Agent-First, Security-First Kanban & Ticketing Platform',
    description_markdown: 'Agent-First, Security-First Kanban & Ticketing Platform',
    modules_enabled: true,
    default_module_ids: ['mod-1'],
    auto_archive_days: 14,
    is_project_admin: true,
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'PROJECT_ADMIN', 'SERVER_ADMIN'],
  };

  const states = [
    {
      id: '01918a22-0000-7000-8000-000000000101',
      name: 'Backlog',
      group: 'backlog',
      color: '#64748b',
      sort_order: 1,
      is_default: true,
      wip_soft_limit: null,
      wip_hard_limit: null,
    },
    {
      id: '01918a22-0000-7000-8000-000000000102',
      name: 'To Do',
      group: 'unstarted',
      color: '#3b82f6',
      sort_order: 2,
      is_default: false,
      wip_soft_limit: null,
      wip_hard_limit: null,
    },
    {
      id: '01918a22-0000-7000-8000-000000000103',
      name: 'In Progress',
      group: 'started',
      color: '#f59e0b',
      sort_order: 3,
      is_default: false,
      wip_soft_limit: 3,
      wip_hard_limit: 5,
    },
    {
      id: '01918a22-0000-7000-8000-000000000104',
      name: 'Done',
      group: 'completed',
      color: '#10b981',
      sort_order: 4,
      is_default: false,
      wip_soft_limit: null,
      wip_hard_limit: null,
    },
  ];

  const priorities = [
    {
      slug: 'urgent',
      label: 'Urgent',
      emoji: '🔥',
      color: '#dc2626',
      sort_order: 1,
      is_default: false,
    },
    {
      slug: 'high',
      label: 'High',
      emoji: '⚡',
      color: '#ea580c',
      sort_order: 2,
      is_default: false,
    },
    {
      slug: 'medium',
      label: 'Medium',
      emoji: '🔹',
      color: '#2563eb',
      sort_order: 3,
      is_default: true,
    },
    {
      slug: 'low',
      label: 'Low',
      emoji: '💤',
      color: '#64748b',
      sort_order: 4,
      is_default: false,
    },
  ];

  const labels = [
    {
      id: 'lbl-1',
      name: 'security',
      color_hex: '#dc2626',
      exclusive_group: 'domain',
    },
    {
      id: 'lbl-2',
      name: 'frontend',
      color_hex: '#2563eb',
      exclusive_group: 'domain',
    },
    {
      id: 'lbl-3',
      name: 'database',
      color_hex: '#059669',
      exclusive_group: 'domain',
    },
  ];

  const members = [
    {
      id: 'mem-1',
      principal_id: '01918a22-0000-7000-8000-000000000001',
      principal_type: 'USER',
      role: 'PROJECT_ADMIN',
      display_name: 'Adam Outler',
      handle: 'adam',
      avatar_url: null,
    },
    {
      id: 'mem-2',
      principal_id: '01918a22-0000-7000-8000-000000000002',
      principal_type: 'USER',
      role: 'MEMBER',
      display_name: 'Alice Cooper',
      handle: 'alice',
      avatar_url: null,
    },
    {
      id: 'mem-3',
      principal_id: '01918a22-0000-7000-8000-000000000003',
      principal_type: 'AGENT',
      role: 'MEMBER',
      display_name: 'Reality Checker',
      handle: 'reality-checker',
      avatar_url: null,
    },
  ];

  const modules = [
    { id: 'mod-1', name: 'Auth & Identity Core', status: 'active' },
    { id: 'mod-2', name: 'Universal Object Graph', status: 'active' },
    { id: 'mod-3', name: 'Realtime WebSocket Mesh', status: 'planned' },
  ];

  const trashedItems = [
    {
      id: '01918a22-0000-7000-8000-000000000201',
      key: 'KAN-99',
      kind: 'issue',
      title: 'Legacy REST Auth deprecation spike',
      deleted_at: '2026-11-10T12:00:00Z',
      purge_after: '2026-12-10T12:00:00Z',
      remaining_days: 22,
    },
    {
      id: '01918a22-0000-7000-8000-000000000202',
      key: 'cyc-old',
      kind: 'cycle',
      title: 'Sprint 0 Bootstrap Cycle',
      deleted_at: '2026-11-12T14:30:00Z',
      purge_after: '2026-12-12T14:30:00Z',
      remaining_days: 24,
    },
    {
      id: '01918a22-0000-7000-8000-000000000203',
      key: 'mod-legacy',
      kind: 'module',
      title: 'Deprecated Cookie Auth Engine',
      deleted_at: '2026-11-14T09:15:00Z',
      purge_after: '2026-12-14T09:15:00Z',
      remaining_days: 26,
    },
  ];

  const principals = [
    {
      id: '01918a22-0000-7000-8000-000000000004',
      type: 'USER',
      display_name: 'Bob Martin',
      handle: 'bob',
    },
    {
      id: '01918a22-0000-7000-8000-000000000005',
      type: 'GROUP',
      display_name: 'Security Engineers',
      handle: 'sec-team',
    },
    {
      id: '01918a22-0000-7000-8000-000000000006',
      type: 'AGENT',
      display_name: 'Codebase Investigator',
      handle: 'codebase-investigator',
    },
  ];

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kanba-214',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kanba-214' } },
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
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/states': { json: states },
    'GET /api/v1/projects/KAN/priorities': { json: priorities },
    'GET /api/v1/projects/KAN/labels': { json: labels },
    'GET /api/v1/projects/KAN/members': { json: members },
    'GET /api/v1/projects/KAN/modules': { json: modules },
    'GET /api/v1/projects/KAN/module-defaults': { json: { default_module_ids: ['mod-1'] } },
    'GET /api/v1/projects/KAN/trash-items': { json: { items: trashedItems, total: 3 } },
    'GET /api/v1/projects/KAN/trash': { json: { items: trashedItems, total: 3 } },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/principals': { json: { items: principals } },
    'GET /api/v1/admin/principals': { json: { items: principals } },
    'POST /api/v1/admin/destructive:request': (req: MockRequest) => {
      const body = (req.body ?? {}) as { mode?: string };
      const isPurge = body.mode === 'permanent_purge';
      return {
        json: {
          stage: 'requested',
          target: 'KAN',
          target_kind: 'project',
          target_id: '01918a22-0000-7000-8000-000000000010',
          mode: isPurge ? 'permanent_purge' : 'trash',
          blast_summary: {
            issues_count: 142,
            sub_issues_count: 18,
            pages_count: 8,
            stickies_count: 12,
          },
          blast_hash: isPurge ? 'hash-purge-kanba214' : 'hash-trash-kanba214',
          confirm_phrase: isPurge ? 'permanent-purge-kan' : 'trash-project-kan',
          confirmation_token: isPurge ? 'tok-purge-stage2-kanba214' : 'tok-trash-stage2-kanba214',
          expires_in_sec: 300,
        },
      };
    },
    'POST /api/v1/admin/destructive:execute': {
      json: {
        stage: 'executed',
        target: 'KAN',
        target_kind: 'project',
        mode: 'trash',
        status: 'success',
      },
    },
    'POST /api/v1/projects/KAN/trash-blast-radius': {
      json: {
        confirmation_token: 'tok-trash-stage2-kanba214',
        confirm_phrase: 'trash-project-kan',
        expires_at: '2026-11-20T12:00:00Z',
        blast_summary: {
          project_key: 'KAN',
          issues_count: 142,
          cycles_count: 5,
          modules_count: 3,
          stickies_count: 12,
          docs_count: 8,
          mode: 'trash',
        },
      },
    },
    'POST /api/v1/projects/KAN/purge-blast-radius': {
      json: {
        confirmation_token: 'tok-purge-stage2-kanba214',
        confirm_phrase: 'permanent-purge-kan',
        expires_at: '2026-11-20T12:00:00Z',
        blast_summary: {
          project_key: 'KAN',
          issues_count: 142,
          cycles_count: 5,
          modules_count: 3,
          stickies_count: 12,
          docs_count: 8,
          mode: 'permanent_purge',
        },
      },
    },
  };
}

test.describe('KANBA-214 Project Settings & Danger Zone Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kanba-214',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-settings-general: default modules & enable modules configuration', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getSettingsMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('[data-testid="project-settings-page"]')).toBeVisible();

    // Verify General tab is active
    await expect(page.locator('[data-testid="tab-general"]')).toHaveClass(/kb-settings-tab-active/);
    await expect(page.locator('[data-testid="default-modules-select"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-settings-general-default-modules-${theme}`,
        annotations: [
          {
            selector: '[data-testid="tab-general"]',
            label: 'General Tab',
            note: 'Active General Settings tab for Project KAN',
          },
          {
            selector: '[data-testid="default-modules-select"]',
            label: 'Default Modules Selector',
            note: 'Allows configuring default module assignments for newly created issues',
          },
          {
            selector: 'input#enable-modules',
            label: 'Enable Modules Toggle',
            note: 'Enables or disables project-wide module scoping',
          },
        ],
      });
    }
  });

  test('02-settings-workflow-states: states, soft and hard WIP limits', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getSettingsMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('[data-testid="project-settings-page"]')).toBeVisible();

    // Switch to Workflow States tab
    await page.locator('[data-testid="tab-states"]').click();
    await expect(page.locator('[data-testid="state-name-input"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-settings-workflow-states-wip-${theme}`,
        annotations: [
          {
            selector: '[data-testid="tab-states"]',
            label: 'Workflow States Tab',
            note: 'Configures custom project workflow states and WIP limits',
          },
          {
            selector: '[data-testid="state-wip-soft-input"]',
            label: 'Soft WIP Limit',
            note: 'Triggers visual warning indicator on board when exceeded',
          },
          {
            selector: '[data-testid="state-wip-hard-input"]',
            label: 'Hard WIP Limit',
            note: 'Enforces hard snap-back blocking standard members with admin override prompt',
          },
        ],
      });
    }
  });

  test('03-settings-priorities-labels: custom priority emojis and exclusive group labels', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getSettingsMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('[data-testid="project-settings-page"]')).toBeVisible();

    // Switch to Priorities tab
    await page.locator('[data-testid="tab-priorities"]').click();
    await expect(page.locator('[data-testid="priority-slug-input"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-settings-priorities-labels-${theme}`,
        annotations: [
          {
            selector: '[data-testid="tab-priorities"]',
            label: 'Priorities Management',
            note: 'Custom priority keys, labels, emojis, colors, and order CRUD',
          },
          {
            selector: '[data-testid="priority-emoji-input"]',
            label: 'Priority Emoji',
            note: 'Semantic emoji representation with hover elaboration',
          },
        ],
      });
    }
  });

  test('04-settings-members: searchable principal picker', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getSettingsMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('[data-testid="project-settings-page"]')).toBeVisible();

    // Switch to Members & Access tab
    await page.locator('[data-testid="tab-members"]').click();
    await expect(page.locator('[data-testid="member-principal-id-input"]')).toBeVisible();

    // Type in principal search to open dropdown
    await page.locator('[data-testid="member-principal-id-input"]').fill('Bob');
    await expect(page.locator('[data-testid="principal-picker-dropdown"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-settings-members-principal-picker-${theme}`,
        annotations: [
          {
            selector: '[data-testid="tab-members"]',
            label: 'Members Tab',
            note: 'Role-based access control for Project KAN',
          },
          {
            selector: '[data-testid="member-principal-id-input"]',
            label: 'Principal Search Input',
            note: 'Search Users, Groups, and Agents by name or @handle instead of raw UUIDs',
          },
          {
            selector: '[data-testid="principal-picker-dropdown"]',
            label: 'Principal Search Dropdown',
            note: 'Live filtered results showing identity icon, display name, handle, and UUID',
          },
        ],
      });
    }
  });

  test('05-settings-trash: retention days and 1-click restore', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getSettingsMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('[data-testid="project-settings-page"]')).toBeVisible();

    // Switch to Trash & Retention tab
    await page.locator('[data-testid="tab-trash"]').click();
    await expect(page.locator('[data-testid="trash-filter-all"]')).toBeVisible();
    await expect(page.locator('[data-testid="trash-items-table"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-settings-trash-retention-restore-${theme}`,
        annotations: [
          {
            selector: '[data-testid="tab-trash"]',
            label: 'Trash & Retention Tab',
            note: 'Lists soft-deleted issues, cycles, modules, stickies, and docs',
          },
          {
            selector: '[data-testid="trash-filter-all"]',
            label: 'Kind Filter',
            note: 'Filters soft-deleted items across all object types',
          },
          {
            selector: '[data-testid="trash-items-table"]',
            label: 'Trashed Items Table',
            note: 'Shows soft-deleted items with remaining retention days and 1-click Restore',
          },
        ],
      });
    }
  });

  test('06-danger-zone-move-to-trash: stage 2 blast radius & confirmation dialog', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getSettingsMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('[data-testid="project-settings-page"]')).toBeVisible();

    // Switch to Danger Zone tab
    await page.locator('[data-testid="tab-danger"]').click();
    await expect(page.locator('[data-testid="request-delete-btn"]')).toBeVisible();

    // Click Move Project to Trash...
    await page.locator('[data-testid="request-delete-btn"]').click();
    await expect(page.locator('[data-testid="danger-confirm-card"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `06-danger-zone-move-to-trash-${theme}`,
        annotations: [
          {
            selector: '[data-testid="danger-confirm-card"]',
            label: 'Stage 2 Blast Radius Summary',
            note: 'Displays exact affected item counts before soft-delete confirmation',
          },
          {
            selector: '[data-testid="confirm-phrase-input"]',
            label: 'Confirmation Phrase Input',
            note: 'Fixes 422 by sending mode: "trash" with explicit phrase confirmation',
          },
        ],
      });
    }
  });

  test('07-danger-zone-permanent-purge: server admin irreversible purge dialog', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getSettingsMocks());
    await page.goto('/projects/KAN/settings');
    await expect(page.locator('[data-testid="project-settings-page"]')).toBeVisible();

    // Switch to Danger Zone tab
    await page.locator('[data-testid="tab-danger"]').click();
    await expect(page.locator('[data-testid="request-purge-btn"]')).toBeVisible();

    // Click Permanently Purge Project...
    await page.locator('[data-testid="request-purge-btn"]').click();
    await expect(page.locator('[data-testid="danger-confirm-card"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `07-danger-zone-permanent-purge-${theme}`,
        annotations: [
          {
            selector: '[data-testid="danger-confirm-card"]',
            label: 'Permanent Purge Blast Radius',
            note: 'SERVER_ADMIN-only irreversible destruction summary and phrase confirmation',
          },
          {
            selector: '[data-testid="confirm-phrase-input"]',
            label: 'Purge Confirmation Input',
            note: 'Requires exact confirmation phrase match for permanent purge execution',
          },
        ],
      });
    }
  });
});
