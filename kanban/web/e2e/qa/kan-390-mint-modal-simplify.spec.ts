// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Visual and functional proofs for KAN-390:
 * [KB-MCP-MINT-MODAL-SIMPLIFY] Move Capability Ceiling into Advanced & Merge Key Type + Scope Tier
 * into Single Unified Selector in Mint New MCP Access Key Modal.
 * Plain ASCII hyphens only.
 */

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-390';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-390/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

const mockKeys = [
  {
    id: 'key-global-1',
    label: 'Global Admin Automation Key',
    display_hint: 'g1g1',
    surface: 'admin',
    scope_tier: 'global',
    scopes: ['admin:read', 'admin:write'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 365).toISOString(),
    last_used_at: null,
    revoked_at: null,
  },
  {
    id: 'key-ws-1',
    label: 'Workspace Bot Service Key',
    display_hint: 'w2w2',
    surface: 'agent',
    scope_tier: 'workspace',
    scopes: ['agent:read'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 90).toISOString(),
    last_used_at: null,
    revoked_at: null,
  },
];

const mockApps = [
  {
    id: 'grant-1',
    client_id: 'client_claude_cli',
    client_name: 'Claude Code CLI',
    surface: 'agent',
    scopes: ['agent:read'],
    allowed_projects: ['KAN'],
    created_at: new Date().toISOString(),
    revoked_at: null,
  },
];

function getMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const projectKan = loadFixture<Record<string, unknown>>('project-kan');

  const mintResponse = (req: { body?: unknown }) => {
    const body = req.body as { label?: string; surface?: 'agent' | 'docs' | 'admin' } | undefined;
    return {
      status: 201,
      json: {
        id: 'key-minted-kan-390',
        label: body?.label ?? 'Minted Test Key',
        display_hint: 'm390',
        surface: body?.surface ?? 'agent',
        scope_tier: 'workspace',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
        last_used_at: null,
        revoked_at: null,
        raw_key: 'kb_agt_test_minted_key_390',
      },
    };
  };

  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: { ...me, is_server_admin: true } },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-390',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-390' } },
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
      json: { id: '01918a22-0000-7000-8000-000000000001', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/objects/project/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
    'GET /api/v1/mcp-keys': { json: { keys: mockKeys } },
    'GET /api/v1/auth/mcp-keys': { json: { keys: mockKeys } },
    'GET /api/v1/auth/oauth-grants': { json: mockApps },
    'GET /api/v1/admin/workload-identities': { json: [] },
    'POST /api/v1/mcp-keys': mintResponse,
    'POST /api/v1/auth/mcp-keys': mintResponse,
  };
}

async function setupMocks(page: Page): Promise<void> {
  await page.unroute('**/api/v1/**');
  await mockApi(page, getMocks());
}

test.describe('KAN-390: Simplified Mint MCP Access Key Modal Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-390',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: 1440x900 Desktop Light - 4-question layout, unified selector, collapsed Advanced, live summary', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();

    // Open Mint Key Modal
    const mintBtn = page.locator('[data-testid="mint-key-button"]');
    await expect(mintBtn).toBeVisible();
    await mintBtn.click();

    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    // Verify 4-question layout
    await expect(page.locator('label[for="mint-label-input"]')).toContainText('1. What is the key name?');
    await expect(page.locator('label[for="mint-key-scope-type-select"]')).toContainText('2. Who is this key for & what can it access?');
    await expect(page.locator('.kb-mcp-form-question-heading').filter({ hasText: '3. What can it do?' })).toBeVisible();
    await expect(page.locator('.kb-mcp-form-question-heading').filter({ hasText: '4. Key Summary' })).toBeVisible();

    // Fill label and choose Service Bot - Single Project
    const labelInput = page.locator('[data-testid="mint-label-input"]');
    await labelInput.fill('CI Production Bot');

    const keyScopeSelect = page.locator('[data-testid="mint-key-scope-type-select"]');
    await keyScopeSelect.selectOption('service_bot:project');

    // Allowed Project input is revealed
    const projInput = page.locator('[data-testid="mint-project-input"]');
    await expect(projInput).toBeVisible();
    await projInput.fill('KAN');

    // Verify live summary updates
    const liveSummary = page.locator('[data-testid="mint-key-summary"]');
    await expect(liveSummary).toBeVisible();
    await expect(liveSummary).toHaveText(
      'Key "CI Production Bot" for Service Bot can access Project KAN and use Agent tools (Standard Developer Agent).',
    );

    // Advanced section is collapsed by default
    const advSection = page.locator('[data-testid="advanced-capability-restrictions"]');
    await expect(advSection).not.toHaveAttribute('open', '');

    // Capture screenshot proof
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '01-1440x900-desktop-default-collapsed.png'),
      fullPage: false,
    });
  });

  test('02: 1440x900 Desktop Dark - Expanded Advanced section revealing Capability Ceiling inside', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'dark');

    const mintBtn = page.locator('[data-testid="mint-key-button"]');
    await expect(mintBtn).toBeVisible();
    await mintBtn.click();

    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    const labelInput = page.locator('[data-testid="mint-label-input"]');
    await labelInput.fill('Audit Readonly Key');

    // Expand Advanced Section
    const advToggle = page.locator('[data-testid="advanced-capability-restrictions-toggle"]');
    await expect(advToggle).toBeVisible();
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    // Capability Ceiling select is revealed inside AdvancedSection
    const presetSelect = page.locator('[data-testid="capability-preset-select"]');
    await expect(presetSelect).toBeVisible();
    await presetSelect.selectOption('1'); // Read-Only Agent (1)

    // Verify live summary updates with preset
    const liveSummary = page.locator('[data-testid="mint-key-summary"]');
    await expect(liveSummary).toHaveText(
      'Key "Audit Readonly Key" for Personal User can access This Workspace and use Agent tools (Read-Only Agent).',
    );

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '02-1440x900-desktop-advanced-expanded.png'),
      fullPage: false,
    });
  });

  test('03: 1024x768 Laptop - Compact responsive 4-question modal', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    await page.locator('[data-testid="mint-label-input"]').fill('Laptop Token');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '03-1024x768-laptop-collapsed.png'),
      fullPage: false,
    });
  });

  test('04: 768x1024 Tablet Portrait - Responsive layout and sticky actions', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    await page.locator('[data-testid="mint-label-input"]').fill('Tablet Worker Token');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '04-768x1024-tablet-portrait.png'),
      fullPage: false,
    });
  });

  test('05: 390x844 Mobile Portrait - Single column 4-question touch layout', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    await page.locator('[data-testid="mint-label-input"]').fill('Mobile Agent Token');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-390x844-mobile-portrait.png'),
      fullPage: false,
    });
  });

  test('06: 844x390 Mobile Landscape - Constrained height with scroll and summary', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'dark');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    await page.locator('[data-testid="mint-label-input"]').fill('Landscape Token');

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '06-844x390-mobile-landscape.png'),
      fullPage: false,
    });
  });
});
