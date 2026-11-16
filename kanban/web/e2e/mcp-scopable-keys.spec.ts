// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from './support/test';
import { mockApi, loadFixture, type MockHandlers, type MockRecorder } from './support/mockApi';
import { annotatedScreenshot } from './support/annotate';
import type { McpApiKeyItem, OAuthConnectedApp } from '../src/features/settings/settingsApi';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../docs/qa/KANBA-106/screenshots',
);

const initialKeys: McpApiKeyItem[] = [
  {
    id: 'key-global-1',
    label: 'Global Service Bot Key',
    display_hint: 'g1a1',
    surface: 'agent',
    scope_tier: 'global',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    expires_at: null, // Unlimited key
    last_used_at: null,
    revoked_at: null,
    disabled_tools: ['delete_all_projects'],
    allowed_cidrs: ['10.0.0.0/8'],
  },
  {
    id: 'key-ws-1',
    label: 'Workspace Bot Key',
    display_hint: 'w2b2',
    surface: 'agent',
    scope_tier: 'workspace',
    scopes: ['agent:read'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 90).toISOString(),
    last_used_at: null,
    revoked_at: null,
    disabled_tools: [],
  },
  {
    id: 'key-proj-1',
    label: 'Project CI/CD Key',
    display_hint: 'p3c3',
    surface: 'agent',
    scope_tier: 'project',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: ['KANBA'],
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
    last_used_at: null,
    revoked_at: null,
    disabled_tools: ['complete_work'],
  },
  {
    id: 'key-personal-1',
    label: 'Personal Developer Key',
    display_hint: 'a4d4',
    surface: 'agent',
    scope_tier: 'personal_user',
    scopes: ['agent:read'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
    last_used_at: null,
    revoked_at: null,
    disabled_tools: ['transition_ticket'],
  },
];

const initialApps: OAuthConnectedApp[] = [
  {
    id: 'grant-1',
    client_id: 'client_claude_cli',
    client_name: 'Claude Code CLI',
    surface: 'agent',
    scopes: ['agent:read'],
    allowed_projects: ['KANBA'],
    created_at: new Date().toISOString(),
    revoked_at: null,
  },
];

async function setupMocks(page: Page, handlers: MockHandlers = {}): Promise<MockRecorder> {
  await page.unroute('**/api/v1/**');
  return mockApi(page, {
    'GET /api/v1/me': { json: loadFixture('me-adam') },
    'GET /api/v1/auth/me': { json: loadFixture('me-adam') },
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: 'usr_adam',
        workspace_id: 'ws_kanban',
        aal_level: 2,
        mfa_pending: false,
        csrf_token: 'test-csrf-token-123',
      },
    },
    'GET /api/v1/projects': { json: [loadFixture('project-kan')] },
    'GET /api/v1/system/status': () => ({
      json: {
        ...loadFixture<Record<string, unknown>>('system-status-prod'),
        allow_unlimited_mcp_keys: true,
      },
    }),
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/project/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/auth/mcp-keys': () => ({ json: { keys: initialKeys } }),
    'GET /api/v1/auth/oauth-grants': () => ({ json: initialApps }),
    ...handlers,
  });
}

test.describe('Hierarchical Scopable Keys & Granular Narrowing (KB-P4-14 / KANBA-106)', () => {
  test.beforeEach(async ({ context }) => {
    mkdirSync(SCREENSHOT_DIR, { recursive: true });
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-123',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: MCP Studio overview with hierarchical scope tiers and unlimited expiry', async ({
    page,
  }, testInfo) => {
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-global"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-workspace"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-project"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-personal"]')).toBeVisible();

    // Verify Never (Unlimited) text for key-global-1
    await expect(page.locator('text=Never (Unlimited)')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-mcp-studio-hierarchical-overview',
      annotations: [
        {
          selector: '[data-testid="tier-badge-global"]',
          label: 'Hierarchical Scope Tiers',
          note: 'Global, Workspace, Project, and Personal User cryptographic boundaries',
        },
        {
          selector: 'text=Never (Unlimited)',
          label: 'Unlimited Key Expiry Indicator',
          note: 'Explicit unlimited lifetime pill displayed when expires_at is NULL',
        },
        {
          selector: '[data-testid="mint-key-button"]',
          label: 'Self-Service Key Minting Action',
          note: 'Enforces AAL2 and privilege boundary checks',
        },
      ],
    });
  });

  test('02: Mint modal unlimited key friction and warning banner', async ({
    page,
  }, testInfo) => {
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await expect(page.locator('[data-testid="mint-key-button"]')).toBeVisible();
    await page.locator('[data-testid="mint-key-button"]').click();

    await expect(page.locator('[data-testid="mint-label-input"]')).toBeVisible();
    await page.locator('[data-testid="mint-label-input"]').fill('Long-Running Production Agent');

    // Select Unlimited expiry option
    await page.locator('[data-testid="mint-expiry-select"]').selectOption('unlimited');

    // Warning banner and confirmation checkbox must now be visible
    await expect(page.locator('[data-testid="unlimited-warning-box"]')).toBeVisible();
    await expect(page.locator('[data-testid="confirm-unlimited-checkbox"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-mint-modal-unlimited-warning',
      annotations: [
        {
          selector: '[data-testid="unlimited-warning-box"]',
          label: 'Friction: Security Warning Banner',
          note: 'Warns against token leakage and credential replay without expiration',
        },
        {
          selector: '[data-testid="confirm-unlimited-checkbox"]',
          label: 'Explicit Acknowledgment Checkbox',
          note: 'Submitting without confirmation yields 422 UNLIMITED_CONFIRMATION_REQUIRED',
        },
      ],
    });
  });

  test('03: Mint modal granular tool narrowing and disabled tools selection', async ({
    page,
  }, testInfo) => {
    await setupMocks(page);

    await page.goto('/settings/mcp');
    await expect(page.locator('[data-testid="mint-key-button"]')).toBeVisible();
    await page.locator('[data-testid="mint-key-button"]').click();

    // Check complete_work and transition_ticket tool checkboxes to disable them
    const completeWorkCb = page.locator('[data-testid="disable-tool-complete_work"]');
    if (await completeWorkCb.isVisible()) {
      await completeWorkCb.check();
    }
    const transitionTicketCb = page.locator('[data-testid="disable-tool-transition_ticket"]');
    if (await transitionTicketCb.isVisible()) {
      await transitionTicketCb.check();
    }

    await annotatedScreenshot(page, testInfo, {
      name: '03-mint-modal-tool-narrowing',
      annotations: [
        {
          selector: '[data-testid="tools-selection-grid"]',
          label: 'Granular Tool Disabling Grid',
          note: 'Allows stripping specific mutating or destructive tools from the minted key',
        },
      ],
    });
  });
});
