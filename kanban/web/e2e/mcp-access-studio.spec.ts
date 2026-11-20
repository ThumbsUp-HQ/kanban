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
  '../../../docs/qa/KANBA-140/screenshots',
);

const initialKeys: McpApiKeyItem[] = [
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
    allowed_projects: ['KANBA'],
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
    last_used_at: null,
    revoked_at: null,
  },
  {
    id: 'key-personal-1',
    label: 'Personal Developer Key',
    display_hint: 'a4b4',
    surface: 'agent',
    scope_tier: 'personal_user',
    scopes: ['agent:read'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
    last_used_at: null,
    revoked_at: null,
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

const mockDeviceInfo = {
  user_code: 'WDJB-MJHT',
  client_name: 'Antigravity CLI (Developer Workstation)',
  client_id: 'client_antigravity_cli',
  resource: 'https://kanban.example.com/mcp/agent',
  surface: 'agent',
  requested_scopes: ['agent:read', 'agent:write'],
  allowed_projects: ['KANBA'],
  expires_at: new Date(Date.now() + 600000).toISOString(),
};

async function setupMocks(page: Page, handlers: MockHandlers = {}): Promise<MockRecorder> {
  await page.unroute('**/api/v1/**');
  return mockApi(page, {
    'GET /api/v1/me': { json: loadFixture('me-adam') },
    'GET /api/v1/auth/me': { json: loadFixture('me-adam') },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/project/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    ...handlers,
  });
}

test.describe('MCP Access Studio & Device Flow E2E Proofs (KB-P4-16)', () => {
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

  test('01: MCP Studio tiers and connected apps table with 2-step revocation proof', async ({
    page,
  }, testInfo) => {
    let keys = [...initialKeys];
    let apps = [...initialApps];

    await setupMocks(page, {
      'GET /api/v1/auth/mcp-keys': () => ({ json: { keys } }),
      'DELETE /api/v1/auth/mcp-keys/:keyId': (req) => {
        keys = keys.map((k) =>
          k.id === req.params.keyId ? { ...k, revoked_at: new Date().toISOString() } : k,
        );
        return { status: 204 };
      },
      'GET /api/v1/auth/oauth-grants': () => ({ json: apps }),
      'DELETE /api/v1/auth/oauth-grants/:grantId': (req) => {
        apps = apps.filter((a) => a.id !== req.params.grantId);
        return { status: 204 };
      },
    });

    await page.goto('/settings/mcp');
    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-global"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-workspace"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-project"]')).toBeVisible();
    await expect(page.locator('[data-testid="tier-badge-personal"]')).toBeVisible();
    await expect(page.locator('[data-testid="app-row-grant-1"]')).toBeVisible();

    // Visual proof: 01-mcp-studio-tiers-<viewport>.png
    await annotatedScreenshot(page, testInfo, {
      name: '01-mcp-studio-tiers',
      annotations: [
        {
          selector: '[data-testid="tier-badge-global"]',
          label: 'Scope Tier Badges (Global, Workspace, Project, Personal)',
          note: 'Explicit cryptographic boundaries with semantic emoji hints',
        },
        {
          selector: '[data-testid="connected-apps-section"]',
          label: 'Connected OAuth Apps Section',
          note: 'Active RFC 8628 CLI grants with 2-step inline revocation',
        },
        {
          selector: '[data-testid="mcp-keys-section"]',
          label: 'Breathable --prop-row-h Spacing',
          note: 'S6.1 ergonomics conforming to breathable whitespace tokens',
        },
      ],
    });

    // Test 2-step inline revocation interaction
    const revokeBtn = page.locator('[data-testid="revoke-btn-key-personal-1"]');
    await revokeBtn.click();
    await expect(page.locator('[data-testid="confirm-revoke-bar"]')).toBeVisible();

    const cancelBtn = page.locator('[data-testid="cancel-revoke-btn"]');
    await cancelBtn.click();
    await expect(page.locator('[data-testid="confirm-revoke-bar"]')).toBeHidden();

    // Re-click and confirm
    await page.locator('[data-testid="revoke-btn-key-personal-1"]').click();
    await page.locator('[data-testid="confirm-revoke-btn"]').click();
    await expect(page.locator('[data-testid="confirm-revoke-bar"]')).toBeHidden();
  });

  test('02: Mint key modal and snippet modal with ephemeral plaintext secret', async ({
    page,
  }, testInfo) => {
    await setupMocks(page, {
      'GET /api/v1/auth/mcp-keys': { json: { keys: initialKeys } },
      'POST /api/v1/auth/mcp-keys': (req) => {
        const body = req.body as { label: string; surface: 'agent' | 'docs' | 'admin' };
        const newKey: McpApiKeyItem = {
          id: 'key-newly-minted',
          label: body.label,
          display_hint: '9f8e',
          surface: body.surface,
          scope_tier: 'personal_user',
          scopes: ['agent:read', 'agent:write'],
          allowed_projects: ['KANBA'],
          created_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
          last_used_at: null,
          revoked_at: null,
          raw_key: 'kb_agt_mock_eph_key',
        };
        return { status: 201, json: newKey };
      },
      'GET /api/v1/auth/oauth-grants': { json: initialApps },
    });

    await page.goto('/settings/mcp');
    await expect(page.locator('[data-testid="mint-key-button"]')).toBeVisible();
    await page.locator('[data-testid="mint-key-button"]').click();

    // Fill in mint modal
    await expect(page.locator('[data-testid="mint-label-input"]')).toBeVisible();
    await page.locator('[data-testid="mint-label-input"]').fill('Developer Workstation Key');
    await page.locator('[data-testid="mint-submit-btn"]').click();

    // Snippet modal is opened
    await expect(page.locator('[data-testid="mcp-snippet-modal"]')).toBeVisible();
    await expect(page.locator('[data-testid="raw-key-banner"]')).toBeVisible();
    await expect(page.locator('[data-testid="raw-key-display"]')).toContainText(
      'kb_agt_mock_eph_key',
    );

    // Visual proof: 02-mcp-snippet-modal-<viewport>.png
    await annotatedScreenshot(page, testInfo, {
      name: '02-mcp-snippet-modal',
      annotations: [
        {
          selector: '[data-testid="raw-key-banner"]',
          label: 'One-Time Ephemeral Secret Banner',
          note: 'Volatile in-memory secret wiped upon modal unmount',
        },
        {
          selector: '[data-testid="url-scope-select"]',
          label: 'Global / Workspace / Project URL Scope Selector',
          note: 'Configures client endpoint to appropriate LOD tier',
        },
        {
          selector: '[data-testid="snippet-code-box"]',
          label: '.gemini/settings.json / mcp_config.json Config Snippet',
          note: 'Multi-client tabs with pre-populated credentials',
        },
      ],
    });

    // Close modal and verify secret is wiped from DOM
    await page.locator('[data-testid="done-button"]').click();
    await expect(page.locator('[data-testid="mcp-snippet-modal"]')).toBeHidden();
    const content = await page.content();
    expect(content).not.toContain('kb_agt_mock_eph_key');
  });

  test('03: Device flow /activate consent screen with scope narrowing and approval', async ({
    page,
  }, testInfo) => {
    let activated = false;

    await setupMocks(page, {
      'GET /api/v1/oauth/device/info': { json: mockDeviceInfo },
      'POST /api/v1/oauth/device/activate': () => {
        activated = true;
        return { json: { status: 'approved' } };
      },
    });

    await page.goto('/activate?user_code=wdjbmjht');
    await expect(page.locator('[data-testid="consent-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="verified-code"]')).toHaveText('WDJB-MJHT');
    await expect(page.locator('[data-testid="client-name"]')).toContainText('Antigravity CLI');

    // Visual proof: 03-device-activate-consent-<viewport>.png
    await annotatedScreenshot(page, testInfo, {
      name: '03-device-activate-consent',
      annotations: [
        {
          selector: '[data-testid="verified-code"]',
          label: 'Base-20 Consonant User Code Verification',
          note: 'Formatted as XXXX-XXXX with vowels and ambiguous digits excluded',
        },
        {
          selector: '[data-testid="consent-section"] .kb-device-scopes-group',
          label: 'Scope & Project Narrowing Checkboxes',
          note: 'User can restrict agent permissions prior to granting access',
        },
        {
          selector: '[data-testid="approve-button"]',
          label: '[Approve] / [Deny] Explicit Decisions',
          note: 'Enforces AAL2 gate for administrative surfaces',
        },
      ],
    });

    // Approve the device
    await page.locator('[data-testid="approve-button"]').click();
    await expect(page.locator('[data-testid="completion-approved"]')).toBeVisible();
    expect(activated).toBe(true);
  });
});
