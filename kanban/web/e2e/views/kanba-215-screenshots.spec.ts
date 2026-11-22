// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-215/screenshots',
);

process.env.QA_TICKET_ID = 'KANBA-215';
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

const mockIssues = {
  items: [
    {
      id: 'iss-1',
      key: 'KAN-215',
      project_key: 'KAN',
      summary: 'Fix Workflow Transition Studio Presets & Agent-Definitions 404',
      state: { id: 'st-in-review', name: 'In Review', group: 'started' },
      priority: { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    },
  ],
  total: 1,
};

const mockWorkflowHooks = [
  {
    from_state: 'In Review',
    to_state: 'Done',
    active_hook_count: 3,
    hooks: [
      {
        id: 'hook-qa',
        name: 'qa-proof-validator',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'sync_validator',
        harness_kind: 'wasm_component',
        wasm_module_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
        failure_policy: 'fail_closed',
        is_enabled: true,
        sort_rank: '0|hzzzzz:',
      },
      {
        id: 'hook-sec',
        name: 'security-invariant-validator',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'sync_validator',
        harness_kind: 'wasm_component',
        wasm_module_sha256: '7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874',
        failure_policy: 'fail_closed',
        is_enabled: true,
        sort_rank: '0|i00000:',
      },
      {
        id: 'hook-label',
        name: 'auto-label-mutator',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'sync_mutator',
        harness_kind: 'wasm_component',
        wasm_module_sha256: '2e7db622992707370042a3c5e15eda145d995048ef4f69f6c746f33dc43f93e9',
        failure_policy: 'fail_open',
        is_enabled: true,
        sort_rank: '0|i00001:',
        allowed_mutable_fields: ['labels', 'priority'],
      },
    ],
  },
];

const mockApprovedWasm = [
  {
    sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
    name: 'qa-proof-validator',
    description: 'Ensures description or comments include docs/qa/ proof bundle',
    target_latency_budget: '<2ms',
  },
  {
    sha256: '7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874',
    name: 'security-invariant-validator',
    description: 'Checks zero new dependencies and strict security tokens',
    target_latency_budget: '<25ms',
  },
  {
    sha256: '2e7db622992707370042a3c5e15eda145d995048ef4f69f6c746f33dc43f93e9',
    name: 'auto-label-mutator',
    description: 'Mutates labels on transition based on issue type',
    target_latency_budget: '<5ms',
  },
];

const mockRepoBindings = [
  {
    id: 'repo-1',
    workspace_id: 'ws-default',
    project_id: 'proj-kan-1',
    slug: 'kanban-core',
    remote_url: 'https://github.com/ThumbsUp-HQ/kanban.git',
    default_ref: 'main',
    access_mode: 'ro_vfs_mount',
    last_fetched_commit: '92d31f66098dd8194837346df091aace6d7db8ef',
    last_fetched_at: '2026-11-18T22:30:00Z',
    created_by: 'usr-admin-1',
    created_at: '2026-11-18T20:00:00Z',
  },
  {
    id: 'repo-2',
    workspace_id: 'ws-default',
    project_id: 'proj-kan-1',
    slug: 'kanban-docs',
    remote_url: 'git@github.com:adamoutler/kanban-docs.git',
    default_ref: 'master',
    access_mode: 'bare_git_tools',
    last_fetched_commit: '7982de041f00a867a3f839e6172865450d0159fa',
    last_fetched_at: '2026-11-18T22:45:00Z',
    created_by: 'usr-admin-1',
    created_at: '2026-11-18T20:15:00Z',
  },
];

const mockDryRunSuccess = {
  would_commit: true,
  steps: [
    {
      order: 1,
      name: 'qa-proof-validator',
      hook_kind: 'sync_validator',
      result: 'allow',
      reason: 'docs/qa/ proof bundle verified in issue description',
      duration_us: 1200,
    },
    {
      order: 2,
      name: 'security-invariant-validator',
      hook_kind: 'sync_validator',
      result: 'allow',
      reason: 'Zero new dependencies and token boundaries satisfied',
      duration_us: 3400,
    },
    {
      order: 3,
      name: 'auto-label-mutator',
      hook_kind: 'sync_mutator',
      result: 'mutate',
      field_updates: { labels: ['qa-certified', 'security-approved'] },
      duration_us: 2100,
    },
    {
      order: 4,
      name: 'code-review-agent',
      hook_kind: 'agent_interceptor',
      result: 'skipped_async',
      duration_us: 500,
    },
  ],
};

function getWorkflowMocks(agentDefs: unknown[] = []): MockHandlers {
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
        workspace_id: 'primary-workspace',
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/workspaces': { json: mockWorkspaces },
    'GET /api/v1/workspaces/current': { json: mockWorkspaces[0] },
    'GET /api/v1/projects': { json: [mockProject] },
    'GET /api/v1/projects/KAN': { json: mockProject },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
        { id: 'st-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'st-in-review', name: 'In Review', group: 'started', sort_order: 4 },
        { id: 'st-done', name: 'Done', group: 'completed', sort_order: 5 },
      ],
    },
    'GET /api/v1/projects/KAN/workflow-hooks': { json: mockWorkflowHooks },
    'GET /api/v1/projects/KAN/workflows/hooks': { json: mockWorkflowHooks },
    'GET /api/v1/projects/KAN/approved-wasm-modules': { json: mockApprovedWasm },
    'GET /api/v1/projects/KAN/repo-bindings': { json: mockRepoBindings },
    'GET /api/v1/workspaces/primary-workspace/agent-definitions': { json: agentDefs },
    'GET /api/v1/workspaces/current/agent-definitions': { json: agentDefs },
    'GET /api/v1/workspaces/kanban/agent-definitions': { json: agentDefs },
    'GET /api/v1/system/status': loadFixture('system-status-prod'),
    'GET /api/v1/projects/KAN/cycles': { json: [] },
    'GET /api/v1/projects/KAN/modules': { json: [] },
    'GET /api/v1/projects/KAN/priorities': { json: { items: [] } },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/projects/KAN/members': { json: [] },
    'GET /api/v1/projects/KAN/issues': { json: mockIssues },
    'GET /api/v1/issues/:id': { json: mockIssues.items[0] },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'PATCH /api/v1/notifications/:id/read': { json: { success: true } },
    'POST /api/v1/notifications/mark-all-read': { json: { success: true } },
    'POST /api/v1/projects/KAN/workflow-hooks/dry-run': { json: mockDryRunSuccess },
    'POST /api/v1/projects/KAN/workflows/dry-run': { json: mockDryRunSuccess },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-215 Workflow Transition Studio & Repo Bindings Visual Proofs', () => {
  test('01: Workflow Studio Desktop Light and Dark Viewports (1440x900)', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getWorkflowMocks());

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForSelector('[data-testid="workflow-studio-page"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-workflow-studio-desktop-${theme}`,
        annotations: [
          {
            selector: '.workflow-studio-header',
            label: 'Workflow Studio Header with Add Transition Rule Action',
            note: 'Canonical project-scoped transition rules and interceptor pipeline.',
          },
          {
            selector: '.transition-rule-card',
            label: 'Transition Rule Card (In Review -> Done)',
            note: 'Ordered pipeline with 3 active hooks (2 Wasm validators, 1 mutator).',
          },
          {
            selector: '.repo-bindings-section',
            label: 'Git Repository Bindings (:ro Bare Mirrors)',
            note: 'Project-scoped read-only mirror management with status badges.',
          },
        ],
      });
    }
  });

  test('02: Workflow Studio Mobile 390x844 Responsive Stacking Viewport', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, getWorkflowMocks());

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForSelector('[data-testid="workflow-studio-page"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-workflow-studio-mobile-${theme}`,
        annotations: [
          {
            selector: '.workflow-studio-title',
            label: 'Responsive Studio Header on 390x844',
            note: 'Clean wrapping without clipping or horizontal overflow.',
          },
          {
            selector: '.repo-bindings-section',
            label: 'Responsive Repo Bindings List',
            note: 'Stacked cards with touch targets conforming to >= 44px standard.',
          },
        ],
      });
    }
  });

  test('03: Attach Hook Dialog Unclipped Layout on Desktop and Mobile', async ({ page }, testInfo) => {
    await mockApi(page, getWorkflowMocks());

    // Desktop 1440x900
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/projects/KAN/settings/workflows?attach=1&to_state=Done');
    await page.waitForSelector('.workflow-dialog', { state: 'visible' });

    await annotatedScreenshot(page, testInfo, {
      name: '03-attach-hook-dialog-desktop',
      annotations: [
        {
          selector: '.workflow-dialog-header',
          label: 'Unclipped Dialog Header',
          note: 'Fixed header with clear modal title.',
        },
        {
          selector: '.workflow-dialog-actions',
          label: 'Sticky Modal Actions Footer',
          note: 'Fully unclipped Cancel and Attach Hook action buttons.',
        },
      ],
    });

    // Mobile 390x844
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(200);

    await annotatedScreenshot(page, testInfo, {
      name: '04-attach-hook-dialog-mobile',
      annotations: [
        {
          selector: '.workflow-dialog',
          label: 'Mobile Dialog Modal on 390x844',
          note: 'Contained scrollable body with sticky footer buttons (>= 44px touch targets).',
        },
        {
          selector: '.workflow-dialog-actions',
          label: 'Unclipped Sticky Action Buttons',
          note: 'Cancel and Attach Hook fit inside viewport without clipping.',
        },
      ],
    });
  });

  test('05: Agent Definitions Graceful Empty Callout', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Empty agent definitions returned
    await mockApi(page, getWorkflowMocks([]));

    await page.goto('/projects/KAN/settings/workflows?attach=1&to_state=Done');
    await page.waitForSelector('.workflow-dialog', { state: 'visible' });

    // Switch to Agent Interceptor radio
    await page.getByLabel('Agent Interceptor').check();
    await page.waitForSelector('[data-testid="no-agents-warning"]', { state: 'visible' });

    await annotatedScreenshot(page, testInfo, {
      name: '05-agent-definitions-empty-callout',
      annotations: [
        {
          selector: '[data-testid="no-agents-warning"]',
          label: 'Graceful Agent Definitions Empty-State Callout',
          note: 'Explains missing definitions with inline navigation link to Workspace Settings.',
        },
        {
          selector: '.workflow-dialog-actions button[type="submit"]',
          label: 'Disabled Attach Hook Button',
          note: 'Prevents saving interceptor when zero agent definitions exist in workspace.',
        },
      ],
    });
  });

  test('06: Dry-Run Drawer with Sample Ticket and CLI Snippet', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getWorkflowMocks());

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForSelector('[data-testid="workflow-studio-page"]', { state: 'visible' });

    // Click Dry-Run
    await page.getByLabel(/Dry-run against sample ticket/i).click();
    await page.waitForSelector('.dry-run-drawer', { state: 'visible' });

    // Click Run Dry-Run
    await page.getByRole('button', { name: /Run Dry-Run/i }).click();
    await page.waitForSelector('.dry-run-summary-banner', { state: 'visible' });

    await annotatedScreenshot(page, testInfo, {
      name: '06-dry-run-drawer-simulation',
      annotations: [
        {
          selector: '.dry-run-summary-banner',
          label: 'Dry-Run Simulation Verdict',
          note: 'Simulates transition execution against sample ticket payload without DB mutation.',
        },
        {
          selector: '.dry-run-copyable-cli',
          label: 'Copyable CLI Validation Snippet',
          note: 'kanban-agent validate-transition command for headless CLI reproduction.',
        },
      ],
    });
  });

  test('07: Bind Git Repository Modal with Live URL Validation', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockApi(page, getWorkflowMocks());

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForSelector('[data-testid="workflow-studio-page"]', { state: 'visible' });

    // Open Bind Git Repository modal
    await page.getByLabel('Bind Git Repository').click();
    await page.waitForSelector('#bind-repo-title', { state: 'visible' });

    // Type valid URL
    await page.fill('#repo-slug-input', 'core-engine');
    await page.fill('#repo-url-input', 'https://github.com/adamoutler/kanban.git');
    await page.waitForSelector('.repo-url-valid', { state: 'visible' });

    await annotatedScreenshot(page, testInfo, {
      name: '07-bind-git-repository-modal',
      annotations: [
        {
          selector: '.workflow-dialog',
          label: 'Bind Git Repository Modal Dialog',
          note: 'Read-only mirror creation with slug, ref, and access mode parameters.',
        },
        {
          selector: '.repo-url-valid',
          label: 'Live Remote URL Security Validation Check',
          note: 'Enforces HTTPS/SSH and rejects SSRF, loopback, and private network ranges.',
        },
      ],
    });
  });
});
