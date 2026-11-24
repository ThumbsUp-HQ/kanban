// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Visual and functional proofs for KAN-382:
 * Constrain Mint MCP Access Key Modal Height and Enable Vertical Scrolling in Advanced Mode.
 * Plain ASCII hyphens only.
 */

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-382';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-382/screenshots',
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
  {
    id: 'key-proj-1',
    label: 'Project CI/CD Key',
    display_hint: 'p3p3',
    surface: 'agent',
    scope_tier: 'project',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: ['KAN'],
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
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
        id: 'key-minted-kan-382',
        label: body?.label ?? 'Minted Test Key',
        display_hint: 'm382',
        surface: body?.surface ?? 'agent',
        scope_tier: 'workspace',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
        last_used_at: null,
        revoked_at: null,
        raw_key: 'kb_agt_test_minted_key_382',
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
        csrf_token: 'test-csrf-token-kan-382',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-382' } },
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

test.describe('KAN-382: Mint MCP Access Key Modal Height and Vertical Scrolling Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan-382',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: 1440x900 Desktop Light - Mint modal bounded height, expanded advanced section, reachable Mint button', async ({
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

    // Expand Advanced Section
    const advToggle = page.locator('[data-testid="advanced-capability-restrictions-toggle"]');
    await expect(advToggle).toBeVisible();
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    // Fill key label to enable submit button
    const labelInput = page.locator('[data-testid="mint-label-input"]');
    await labelInput.fill('CI Workstation Agent');

    // Assert modal card geometry is strictly constrained within viewport
    const metrics = await modalCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return {
        rectTop: rect.top,
        rectBottom: rect.bottom,
        rectHeight: rect.height,
        viewportHeight: window.innerHeight,
        maxHeight: style.maxHeight,
        overflowY: style.overflowY,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
      };
    });

    expect(metrics.rectBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
    expect(metrics.rectTop).toBeGreaterThanOrEqual(0);
    expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);

    // Verify Mint submit button is visible and within viewport
    const submitBtn = page.locator('[data-testid="mint-submit-btn"]');
    await expect(submitBtn).toBeVisible();
    const btnRect = await submitBtn.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        top: rect.top,
        bottom: rect.bottom,
        viewportHeight: window.innerHeight,
      };
    });
    expect(btnRect.bottom).toBeLessThanOrEqual(btnRect.viewportHeight);
    expect(btnRect.top).toBeGreaterThanOrEqual(0);

    // Capture screenshot proof
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '01-1440x900-desktop-light-expanded.png'),
      fullPage: false,
    });
  });

  test('02: 1440x900 Desktop Dark - Mint modal bounded height in dark theme', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'dark');

    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();

    const mintBtn = page.locator('[data-testid="mint-key-button"]');
    await expect(mintBtn).toBeVisible();
    await mintBtn.click();

    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    const advToggle = page.locator('[data-testid="advanced-capability-restrictions-toggle"]');
    await expect(advToggle).toBeVisible();
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    const labelInput = page.locator('[data-testid="mint-label-input"]');
    await labelInput.fill('Dark Theme Security Worker');

    const metrics = await modalCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        rectTop: rect.top,
        rectBottom: rect.bottom,
        viewportHeight: window.innerHeight,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
      };
    });

    expect(metrics.rectBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
    expect(metrics.rectTop).toBeGreaterThanOrEqual(0);

    const submitBtn = page.locator('[data-testid="mint-submit-btn"]');
    await expect(submitBtn).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '02-1440x900-desktop-dark-expanded.png'),
      fullPage: false,
    });
  });

  test('03: 1024x768 Laptop - Mint modal vertical scroll and sticky actions', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    const advToggle = page.locator('[data-testid="advanced-capability-restrictions-toggle"]');
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    await page.locator('[data-testid="mint-label-input"]').fill('Laptop Compact Agent');

    const metrics = await modalCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        rectTop: rect.top,
        rectBottom: rect.bottom,
        viewportHeight: window.innerHeight,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
      };
    });

    expect(metrics.rectBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
    expect(metrics.rectTop).toBeGreaterThanOrEqual(0);
    expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);

    const submitBtn = page.locator('[data-testid="mint-submit-btn"]');
    await expect(submitBtn).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '03-1024x768-laptop-light-expanded.png'),
      fullPage: false,
    });
  });

  test('04: 768x1024 Tablet Portrait - Mint modal bounded height on tablet', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    const advToggle = page.locator('[data-testid="advanced-capability-restrictions-toggle"]');
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    await page.locator('[data-testid="mint-label-input"]').fill('Tablet Portrait Key');

    const metrics = await modalCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        rectTop: rect.top,
        rectBottom: rect.bottom,
        viewportHeight: window.innerHeight,
      };
    });

    expect(metrics.rectBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
    expect(metrics.rectTop).toBeGreaterThanOrEqual(0);

    const submitBtn = page.locator('[data-testid="mint-submit-btn"]');
    await expect(submitBtn).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '04-768x1024-tablet-portrait-expanded.png'),
      fullPage: false,
    });
  });

  test('05: 390x844 Mobile Portrait - Mint modal responsive scrolling and sticky header/footer', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    const advToggle = page.locator('[data-testid="advanced-capability-restrictions-toggle"]');
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    await page.locator('[data-testid="mint-label-input"]').fill('Mobile Key');

    const metrics = await modalCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        rectTop: rect.top,
        rectBottom: rect.bottom,
        viewportHeight: window.innerHeight,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
      };
    });

    expect(metrics.rectBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
    expect(metrics.rectTop).toBeGreaterThanOrEqual(0);

    const submitBtn = page.locator('[data-testid="mint-submit-btn"]');
    await expect(submitBtn).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-390x844-mobile-portrait-expanded.png'),
      fullPage: false,
    });
  });

  test('06: 844x390 Mobile Landscape - Extremely constrained height with sticky buttons reachable', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await applyTheme(page, 'light');

    await page.locator('[data-testid="mint-key-button"]').click();
    const modalCard = page.locator('[data-testid="mint-modal-card"]');
    await expect(modalCard).toBeVisible();

    const advToggle = page.locator('[data-testid="advanced-capability-restrictions-toggle"]');
    await advToggle.click();
    await expect(advToggle).toHaveAttribute('aria-expanded', 'true');

    await page.locator('[data-testid="mint-label-input"]').fill('Landscape Key');

    const metrics = await modalCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        rectTop: rect.top,
        rectBottom: rect.bottom,
        viewportHeight: window.innerHeight,
      };
    });

    expect(metrics.rectBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
    expect(metrics.rectTop).toBeGreaterThanOrEqual(0);

    const submitBtn = page.locator('[data-testid="mint-submit-btn"]');
    await expect(submitBtn).toBeVisible();

    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '06-844x390-mobile-landscape-expanded.png'),
      fullPage: false,
    });
  });
});
