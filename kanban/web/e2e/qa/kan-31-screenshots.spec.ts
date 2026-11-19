/**
 * Playwright Visual & QA Proof Verification for KAN-31.
 * Captures Desktop (1440x900) and Mobile (390x844) in Light and Dark themes.
 * Plain ASCII hyphens only. Zero em-dashes or en-dashes.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KAN-31/screenshots');

const mockUser = {
  principal_id: '11111111-1111-4111-8111-111111111111',
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Security Architect',
  username: 'architect',
  email: 'architect@thumbsup.org',
  timezone: 'UTC',
  avatar_url: null,
  roles: ['admin'],
  is_server_admin: true,
  is_workspace_admin: true,
  is_project_admin: true,
  capabilities: ['SERVER_ADMIN', 'WORKSPACE_ADMIN'],
};

const mockKeys = [
  {
    id: 'key-dev-001',
    label: 'Personal Developer CLI Key',
    display_hint: 'a1b2',
    surface: 'agent',
    scope_tier: 'personal_user',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: null,
    created_at: '2026-11-19T08:00:00Z',
    expires_at: '2026-12-19T08:00:00Z',
    last_used_at: '2026-11-19T11:45:00Z',
    revoked_at: null,
  },
  {
    id: 'key-proj-002',
    label: 'KANBA Automation Bot Key',
    display_hint: 'c3d4',
    surface: 'agent',
    scope_tier: 'project',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: ['KANBA'],
    created_at: '2026-11-18T10:00:00Z',
    expires_at: null,
    last_used_at: '2026-11-19T12:00:00Z',
    revoked_at: null,
  },
  {
    id: 'key-ws-003',
    label: 'Workspace Shared CI Bot',
    display_hint: 'e5f6',
    surface: 'agent',
    scope_tier: 'workspace',
    scopes: ['agent:read'],
    allowed_projects: null,
    created_at: '2026-11-15T09:00:00Z',
    expires_at: '2027-11-15T09:00:00Z',
    last_used_at: null,
    revoked_at: null,
  },
  {
    id: 'key-srv-004',
    label: 'Server Administrative Bot',
    display_hint: 'g7h8',
    surface: 'admin',
    scope_tier: 'global',
    scopes: ['admin:read'],
    allowed_projects: null,
    created_at: '2026-11-10T08:30:00Z',
    expires_at: null,
    last_used_at: null,
    revoked_at: null,
  },
];

const mockConnectedApps = [
  {
    id: 'app-grant-001',
    client_id: 'client-claude-desktop',
    client_name: 'Claude Desktop Integration',
    surface: 'agent',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: null,
    created_at: '2026-11-17T14:00:00Z',
    revoked_at: null,
  },
];

const baseMocks = {
  'GET /api/v1/setup/status': { json: { initialized: true } },
  'GET /api/v1/auth/session': {
    json: {
      authenticated: true,
      principal_id: mockUser.id,
      workspace_id: '22222222-2222-2222-2222-222222222222',
      aal_level: 2,
      mfa_pending: false,
      csrf_token: 'test-csrf-token-kan31',
      remember_me: true,
    },
  },
  'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
  'GET /api/v1/workspaces': {
    json: [{ id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' }],
  },
  'GET /api/v1/workspaces/current': {
    json: { id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' },
  },
  'GET /api/v1/projects': {
    json: [
      { id: '33333333-3333-3333-3333-333333333333', key: 'KANBA', identifier: 'KANBA', name: 'kanban' },
      { id: '44444444-4444-4444-4444-444444444444', key: 'QAADM', identifier: 'QAADM', name: 'QA Admin' },
    ],
  },
  'GET /api/v1/projects/KANBA': { json: loadFixture('project-kan') },
  'GET /api/v1/projects/KANBA/views': { json: [] },
  'GET /api/v1/projects/KANBA/issues': { json: [] },
  'GET /api/v1/projects/KANBA/cycles': { json: { items: [] } },
  'GET /api/v1/projects/KANBA/modules': { json: { items: [] } },
  'GET /api/v1/projects/KANBA/states': { json: { items: [] } },
  'GET /api/v1/projects/KANBA/priorities': { json: { items: [] } },
  'GET /api/v1/projects/KANBA/labels': { json: { items: [] } },
  'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
  'GET /api/v1/notifications': { json: { items: [] } },
  'GET /api/v1/users/me': { json: mockUser },
  'GET /api/v1/auth/me': { json: mockUser },
  'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
  'GET /api/v1/auth/mcp-keys': { json: { keys: mockKeys } },
  'GET /api/v1/mcp-keys': { json: mockKeys },
  'GET /api/v1/auth/oauth-grants': { json: mockConnectedApps },
};

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(150);
}

test.describe('KAN-31 Visual Verification & Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan31',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: /settings/mcp My Keys view with scope pills and architecture explainer', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, baseMocks);
    await page.goto('/settings/mcp');

    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();
    await expect(page.locator('[data-testid="mcp-scope-explainer"]')).toBeVisible();
    await expect(page.locator('[data-testid="scope-pill-all"]')).toBeVisible();
    await expect(page.locator('[data-testid="admin-view-toggle"]')).toBeVisible();
    await expect(page.locator('[data-testid="key-row-key-dev-001"]')).toBeVisible();

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-settings-mcp-my-keys-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-settings-mcp-my-keys-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('02: /settings/mcp?view=governance Governance view with scoped keys', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, baseMocks);
    await page.goto('/settings/mcp?view=governance');

    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();
    await expect(page.locator('[data-testid="view-governance-btn"]')).toHaveClass(/kb-mcp-view-btn-active/);
    await expect(page.locator('[data-testid="studio-title"]')).toContainText('MCP Key Governance');

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-settings-mcp-governance-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-settings-mcp-governance-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('03: /settings/mcp?scope=project Project scope active with project selector', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, baseMocks);
    await page.goto('/settings/mcp?scope=project&project=KANBA');

    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();
    await expect(page.locator('[data-testid="scope-pill-project"]')).toHaveClass(/kb-mcp-filter-pill-active/);
    await expect(page.locator('[data-testid="scope-project-select"]')).toBeVisible();
    await expect(page.locator('[data-testid="key-row-key-proj-002"]')).toBeVisible();

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-settings-mcp-project-scope-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-settings-mcp-project-scope-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('04: Topbar avatar dropdown menu with unified MCP Studio link', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, baseMocks);
    await page.goto('/settings/mcp');

    const avatarBtn = page.locator('[data-testid="topbar-avatar-button"]');
    await expect(avatarBtn).toBeVisible();
    await avatarBtn.click();

    const mcpLink = page.locator('[data-testid="topbar-mcp-studio-link"]');
    await expect(mcpLink).toBeVisible();
    await expect(mcpLink).toHaveText(/MCP Keys & OAuth Apps/);

    // Verify old duplicate links are NOT present in avatar menu
    const menu = page.locator('.kb-avatar-menu');
    await expect(menu.getByText('Personal MCP Keys')).toHaveCount(0);
    await expect(menu.getByText('Workspace MCP Keys')).toHaveCount(0);
    await expect(menu.getByText('Admin MCP Keys')).toHaveCount(0);

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `04-topbar-menu-mcp-studio-light-${projectName}.png`),
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    if (!(await mcpLink.isVisible())) {
      await avatarBtn.click();
    }
    await expect(mcpLink).toBeVisible();
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `04-topbar-menu-mcp-studio-dark-${projectName}.png`),
    });
  });
});
