/**
 * Playwright Visual & QA Proof Verification for KAN-10.
 * Captures Desktop (1440x900) and Mobile (390x844) in Light and Dark themes.
 * Plain ASCII hyphens only. Zero em-dashes or en-dashes.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KAN-10/screenshots');
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

const mockUser = {
  id: '01918a22-0000-7000-8000-000000000001',
  principal_id: '01918a22-0000-7000-8000-000000000001',
  handle: '@architect',
  display_name: 'Security Architect',
  username: 'architect',
  email: 'architect@thumbsup.org',
  timezone: 'UTC',
  avatar_url: null,
  roles: ['admin'],
  is_server_admin: true,
  is_workspace_admin: true,
  is_project_admin: true,
  aal_level: 2,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'],
};

const projectKan = {
  id: '01918a22-0000-7000-8000-000000000010',
  identifier: 'KAN',
  key: 'KAN',
  name: 'Platform Core',
  description: 'Agent-First, Security-First Kanban Platform',
  description_markdown: 'Agent-First, Security-First Kanban Platform',
  modules_enabled: true,
  default_module_ids: ['mod-1'],
  auto_archive_days: 14,
  is_project_admin: true,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'PROJECT_ADMIN', 'SERVER_ADMIN'],
};

const states = [
  { id: 'state-backlog', name: 'Backlog', group: 'backlog', color: '#64748b', sort_order: 1, is_default: true },
  { id: 'state-todo', name: 'Todo', group: 'unstarted', color: '#3b82f6', sort_order: 2, is_default: false },
  { id: 'state-in-progress', name: 'In Progress', group: 'started', color: '#f59e0b', sort_order: 3, is_default: false },
  { id: 'state-done', name: 'Done', group: 'completed', color: '#10b981', sort_order: 4, is_default: false },
];

const mockCustomFields = [
  {
    id: 'f-cvss',
    slug: 'cvss-score',
    name: 'CVSS Score',
    tier: 'wasm',
    output_format: 'severity_pill',
    output_format_metadata: { critical_min: 9.0, high_min: 7.0 },
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
    is_enabled: true,
    approval_status: 'APPROVED',
    script_source: 'return 8.8;',
  },
];

const mockRepoBindings = [
  {
    id: 'repo-binding-1',
    workspace_id: '01918a22-0000-7000-8000-000000000001',
    project_id: '01918a22-0000-7000-8000-000000000010',
    slug: 'core-engine',
    remote_url: 'https://github.com/ThumbsUp-HQ/kanban.git',
    default_ref: 'main',
    access_mode: 'ro_vfs_mount',
    last_fetched_commit: '0123456789abcdef0123456789abcdef01234567',
    last_fetched_at: '2026-11-19T12:00:00Z',
    last_fetch_error: null,
    created_at: '2026-11-19T10:00:00Z',
  },
];

const defaultWorkflowRules = [
  {
    from_state: 'In Progress',
    to_state: 'Done',
    active_hook_count: 1,
    hooks: [
      {
        id: 'hook-1',
        name: 'ci-guardrail-check',
        from_state: 'In Progress',
        to_state: 'Done',
        hook_kind: 'sync_validator',
        sort_rank: '0000000000000001',
        failure_policy: 'fail_closed',
        manifest_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
        is_enabled: true,
        target_latency_budget: '<2ms',
        description: 'Verify CI checks and test results prior to Done state.',
      },
    ],
  },
];

function getCommonMocks(): MockHandlers {
  return {
    'GET /api/v1/me': { json: mockUser },
    'GET /api/v1/auth/me': { json: mockUser },
    'GET /api/v1/users/me': { json: mockUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan10',
        user: mockUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan10' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
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
    'GET /api/v1/projects/KAN/priorities': { json: [] },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/projects/KAN/members': { json: [] },
    'GET /api/v1/projects/KAN/cycles': { json: [] },
    'GET /api/v1/projects/KAN/modules': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: mockCustomFields },
    'GET /api/v1/custom-fields/f-cvss/approvals': { json: [] },
    'GET /api/v1/projects/KAN/workflow-hooks': { json: defaultWorkflowRules },
    'GET /api/v1/projects/KAN/repo-bindings': { json: mockRepoBindings },
    'GET /api/v1/workspaces/:ws/agent-definitions': { json: [] },
    'GET /api/v1/workspaces/kanban/agent-definitions': { json: [] },
    'GET /api/v1/projects/KAN/approved-wasm-modules': { json: [] },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
  };
}

test.describe('KAN-10: Playwright Screenshots Verification', () => {
  test('01: Custom Field Editor Dual-Control Banner on WORKSPACE Scope', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, getCommonMocks());
    await page.goto('/projects/KAN/settings/custom-fields');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="custom-fields-editor-layout"]')).toBeVisible();

    // Fill sample values on Basic tab
    const nameInput = page.locator('[data-testid="field-name-input"]');
    await nameInput.fill('Target Environment');

    const slugInput = page.locator('[data-testid="field-slug-input"]');
    await slugInput.fill('target-env');

    // Switch to Advanced tab to configure target scope
    const advTab = page.locator('[data-testid="custom-fields-advanced-tab"]');
    await advTab.click();

    // Select WORKSPACE scope
    const scopeSelect = page.locator('[data-testid="target-scope-select"]');
    await scopeSelect.selectOption('WORKSPACE');

    // Verify immediate dual-control banner
    const banner = page.locator('[data-testid="dual-control-explanation-banner"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Dual-Control Policy');

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-custom-fields-dual-control-workspace-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-custom-fields-dual-control-workspace-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('02: Custom Field Editor Dual-Control Banner on SERVER Scope', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, getCommonMocks());
    await page.goto('/projects/KAN/settings/custom-fields');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="custom-fields-editor-layout"]')).toBeVisible();

    const nameInput = page.locator('[data-testid="field-name-input"]');
    await nameInput.fill('Global Compliance Check');

    const slugInput = page.locator('[data-testid="field-slug-input"]');
    await slugInput.fill('global-compliance');

    // Switch to Advanced tab
    const advTab = page.locator('[data-testid="custom-fields-advanced-tab"]');
    await advTab.click();

    // Select SERVER scope
    const scopeSelect = page.locator('[data-testid="target-scope-select"]');
    await scopeSelect.selectOption('SERVER');

    // Verify immediate dual-control banner
    const banner = page.locator('[data-testid="dual-control-explanation-banner"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Dual-Control Policy');

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-custom-fields-dual-control-server-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-custom-fields-dual-control-server-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('03: Workflow Studio Git Repo Binding Modal', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, getCommonMocks());
    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForLoadState('networkidle');

    // Open Git Repo Binding Modal
    const bindBtn = page.locator('button[aria-label="Bind Git Repository"]');
    await expect(bindBtn).toBeVisible();
    await bindBtn.click();

    // Verify modal is open
    const modal = page.locator('div[role="dialog"][aria-labelledby="bind-repo-title"]');
    await expect(modal).toBeVisible();

    // Fill form fields
    const slugInput = page.locator('#repo-slug-input');
    await slugInput.fill('core-engine');

    const urlInput = page.locator('#repo-url-input');
    await urlInput.fill('https://github.com/ThumbsUp-HQ/kanban.git');

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-workflow-git-repo-binding-modal-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-workflow-git-repo-binding-modal-dark-${projectName}.png`),
      fullPage: true,
    });
  });
});
