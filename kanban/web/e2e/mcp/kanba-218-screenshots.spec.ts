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
  '../../../../docs/qa/KANBA-218/screenshots',
);

process.env.QA_TICKET_ID = 'KANBA-218';
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const mockAdminUser = {
  id: 'usr-admin-1',
  handle: 'adam_architect',
  display_name: 'Adam Architect',
  email: 'adam@example.com',
  workspace_role: 'WORKSPACE_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
};

const mockProject = {
  id: 'proj-qaadm-1',
  identifier: 'QAADM',
  name: 'QA Administration',
  modules_enabled: true,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'PROJECT_ADMIN'],
  is_project_admin: true,
  project_role: 'ADMIN',
};

const mockMcpKeys = [
  {
    id: 'key-qaadm-1',
    label: 'QAADM Bot Runner Key',
    display_hint: '9f2a',
    surface: 'agent',
    scope_tier: 'project',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: ['QAADM'],
    created_at: '2026-03-01T10:00:00Z',
    expires_at: null,
    last_used_at: '2026-03-02T14:30:00Z',
    revoked_at: null,
  },
  {
    id: 'key-ws-1',
    label: 'Workspace Agent Key',
    display_hint: '4b1c',
    surface: 'docs',
    scope_tier: 'workspace',
    scopes: ['docs:read', 'docs:write'],
    allowed_projects: null,
    created_at: '2026-03-01T11:00:00Z',
    expires_at: '2026-06-01T11:00:00Z',
    last_used_at: null,
    revoked_at: null,
  },
];

const mockConnectedApps = [
  {
    id: 'grant-claude-1',
    client_id: 'client_claude_code',
    client_name: 'Claude Code Agent',
    surface: 'agent',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: ['QAADM'],
    created_at: '2026-03-01T12:00:00Z',
    revoked_at: null,
  },
];

const mockOAuthClients = [
  {
    client_id: 'client_cursor_ide',
    client_name: 'Cursor IDE Assistant',
    client_type: 'confidential',
    redirect_uris: ['https://cursor.com/callback', 'http://127.0.0.1:4567/callback'],
    status: 'active',
    created_at: '2026-02-15T08:00:00Z',
    updated_at: '2026-02-15T08:00:00Z',
  },
  {
    client_id: 'client_claude_cli',
    client_name: 'Claude Code CLI',
    client_type: 'public',
    redirect_uris: ['http://127.0.0.1:8920/oauth/callback'],
    status: 'suspended',
    created_at: '2026-02-20T10:00:00Z',
    updated_at: '2026-02-20T10:00:00Z',
  },
  {
    client_id: 'client_codex_cli',
    client_name: 'OpenAI Codex Headless Runner',
    client_type: 'public',
    redirect_uris: ['http://127.0.0.1:9099/callback'],
    status: 'active',
    created_at: '2026-02-25T14:00:00Z',
    updated_at: '2026-02-25T14:00:00Z',
  },
];

const mockImportReport = {
  to_create: 14,
  to_update: 2,
  unchanged: 1,
  sequence_high_water_mark: 17,
  unmapped_members: ['plane-usr-legacy-99'],
  rewritten_attachments: 3,
  invalid_link_count: 0,
  warnings: [
    'Attachment files proxied through local storage directory.',
    'State "Done" mapped to canonical state group "completed".',
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
    'GET /api/v1/system/status': { json: { allow_unlimited_mcp_keys: true } },
    'GET /api/v1/workspaces': {
      json: [{ id: 'ws-default', name: 'Primary Workspace', slug: 'kanban', is_current: true }],
    },
    'GET /api/v1/workspaces/current': {
      json: { id: 'ws-default', name: 'Primary Workspace', slug: 'kanban' },
    },
    'GET /api/v1/projects': { json: [mockProject] },
    'GET /api/v1/projects/QAADM': { json: mockProject },
    'GET /api/v1/projects/KAN': { json: mockProject },
    'GET /api/v1/notifications': { json: [] },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/auth/mcp-keys': { json: mockMcpKeys },
    'POST /api/v1/auth/mcp-keys': {
      json: {
        id: 'key-newly-minted',
        label: 'Ephemeral Agent Mint',
        display_hint: 'e1a2',
        surface: 'agent',
        scope_tier: 'project',
        scopes: ['agent:read', 'agent:write'],
        allowed_projects: ['QAADM'],
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
        raw_key: 'kb_agt_ephemeral_plaintext_token_test_123',
      },
    },
    'GET /api/v1/admin/mcp-keys': { json: mockMcpKeys },
    'GET /api/v1/auth/oauth-grants': { json: mockConnectedApps },
    'GET /api/v1/admin/oauth-clients': { json: mockOAuthClients },
    'POST /api/v1/admin/imports/plane': { json: mockImportReport },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-218 MCP Key Project Scope Badge, Client Snippets, OAuth Governance & Plane Import Studio QA Proofs', () => {
  test('01: MCP Access Studio with Fixed Project Scope Badge (Project: QAADM)', async ({ page }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/settings/mcp');
    await page.waitForSelector('[data-testid="mcp-access-studio"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-mcp-access-studio-scope-badge-${theme}`,
        annotations: [
          {
            selector: '[data-testid="tier-badge-project"]',
            label: 'Fixed MCP Project Scope Badge showing Project: QAADM (fixing hardcoded KANBA bug)',
          },
          {
            selector: '[data-testid="mcp-keys-table"]',
            label: 'Active MCP Keys table displaying scope tiers, hints, and one-click revocation',
          },
          {
            selector: '[data-testid="connected-apps-section"]',
            label: 'Connected OAuth Applications section with clean user revocation',
          },
        ],
      });
    }
  });

  test('02: Aligned MCP Mint & Client Config Snippet Modal (Claude, Cursor, Gemini, Antigravity, Codex)', async ({ page }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/settings/mcp');
    await page.waitForSelector('[data-testid="mcp-access-studio"]', { state: 'visible' });

    // Open mint modal and mint key
    await page.click('[data-testid="mint-key-button"]');
    await page.waitForSelector('[data-testid="mint-modal-card"]', { state: 'visible' });
    await page.fill('[data-testid="mint-label-input"]', 'Ephemeral Agent Mint');
    await page.click('[data-testid="mint-submit-btn"]');

    // Wait for snippet modal to open
    await page.waitForSelector('[data-testid="mcp-snippet-modal"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-mcp-mint-client-snippets-${theme}`,
        annotations: [
          {
            selector: '[data-testid="mcp-snippet-modal"]',
            label: 'Aligned MCP Client Config Snippet Modal displaying ephemeral secret',
          },
          {
            selector: '[data-testid="tab-cursor"]',
            label: 'Cursor IDE configuration snippet tab with command line and JSON schema',
          },
          {
            selector: '[data-testid="tab-codex"]',
            label: 'OpenAI Codex headless agent runner configuration tab',
          },
        ],
      });
    }
  });

  test('03: Admin OAuth 2.1 + PKCE Client Governance Studio (/admin/oauth)', async ({ page }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/admin/oauth');
    await page.waitForSelector('[data-testid="oauth-client-governance-studio"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-oauth-client-governance-studio-${theme}`,
        annotations: [
          {
            selector: '[data-testid="oauth-clients-section"]',
            label: 'Registered OAuth 2.1 clients table with client IDs, types, and redirect URIs',
          },
          {
            selector: '[data-testid="status-badge-active"]',
            label: 'Status indicators with Activate, Suspend, and Revoke controls',
          },
          {
            selector: '[data-testid="tab-admin-oauth"]',
            label: 'Integrated Admin Subnav linking Bot API Keys, OAuth 2.1 Clients, and Plane Imports',
          },
        ],
      });
    }
  });

  test('04: Admin Plane Migration Import Studio (/admin/imports) - Step 1 Bundle Input', async ({ page }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/admin/imports');
    await page.waitForSelector('[data-testid="plane-import-studio"]', { state: 'visible' });

    // Switch to paste mode and paste sample Plane bundle
    await page.click('[data-testid="mode-paste-btn"]');
    await page.fill(
      '[data-testid="paste-textarea"]',
      JSON.stringify(
        {
          projects: [{ id: 'p1', name: 'Plane Export Project' }],
          states: [{ id: 's1', name: 'In Progress' }],
          issues: [{ id: 'i1', sequence_id: 1, name: 'Sample Issue' }],
          cycles: [{ id: 'c1', name: 'Sprint 1' }],
          modules: [{ id: 'm1', name: 'Auth Module' }],
          issue_comments: [{ id: 'cm1' }],
          members: [{ id: 'u1' }],
        },
        null,
        2,
      ),
    );

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-plane-migration-studio-step1-${theme}`,
        annotations: [
          {
            selector: '[data-testid="paste-textarea"]',
            label: 'Plane export JSON bundle input with real-time format validation',
          },
          {
            selector: '[data-testid="entity-metrics-preview"]',
            label: 'Detected Plane entity metrics cards (Projects, States, Issues, Cycles, Modules)',
          },
          {
            selector: '[data-testid="run-dry-run-btn"]',
            label: 'Stage 1 Dry-Run Simulation trigger button',
          },
        ],
      });
    }
  });

  test('05: Admin Plane Migration Import Studio (/admin/imports) - Stage 1 Dry-Run Preview', async ({ page }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/admin/imports');
    await page.waitForSelector('[data-testid="plane-import-studio"]', { state: 'visible' });

    // Paste sample bundle and trigger dry run
    await page.click('[data-testid="mode-paste-btn"]');
    await page.fill(
      '[data-testid="paste-textarea"]',
      JSON.stringify({ projects: [{ id: 'p1' }], issues: [{ id: 'i1' }] }),
    );
    await page.click('[data-testid="run-dry-run-btn"]');

    // Wait for preview section
    await page.waitForSelector('[data-testid="dry-run-preview-section"]', { state: 'visible' });

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-plane-migration-studio-dry-run-${theme}`,
        annotations: [
          {
            selector: '[data-testid="dry-run-preview-section"]',
            label: 'Stage 1 Dry-Run Simulation Preview with zero database mutations',
          },
          {
            selector: '[data-testid="diff-to-create"]',
            label: 'Diff impact cards showing issues to create, update, and sequence watermark',
          },
          {
            selector: '[data-testid="warnings-box"]',
            label: 'Forensic warnings report detailing state mappings and attachment rewrites',
          },
          {
            selector: '[data-testid="execute-import-btn"]',
            label: 'Stage 2: Execute Live Import button with transactional database execution',
          },
        ],
      });
    }
  });
});
