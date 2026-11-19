// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KANBA-219';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-219/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(150);
}

const mockProviders = [
  {
    id: 'prov-openai-1',
    provider_kind: 'openai',
    display_name: 'Production OpenAI Cluster',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o', 'gpt-4o-mini', 'o1', 'o3-mini'],
    residency_tier: 'us-east',
    priority: 10,
    is_enabled: true,
    api_key_set: true,
    settings: {},
  },
  {
    id: 'prov-gemini-1',
    provider_kind: 'gemini',
    display_name: 'Google Gemini Workspace',
    base_url: null,
    model_allowlist: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-3.8-flash-high'],
    residency_tier: 'default',
    priority: 20,
    is_enabled: true,
    api_key_set: true,
    settings: {},
  },
  {
    id: 'prov-ollama-1',
    provider_kind: 'ollama',
    display_name: 'Local Air-Gap Ollama Server',
    base_url: 'http://127.0.0.1:11434',
    model_allowlist: ['llama3.3:70b', 'qwen2.5-coder:32b', 'deepseek-r1:32b'],
    residency_tier: 'local',
    priority: 5,
    is_enabled: true,
    api_key_set: false,
    settings: {},
  },
];

const mockBudgets = [
  {
    period_kind: 'monthly',
    period_start: '2026-11-01T00:00:00Z',
    token_cap: 10000000,
    tokens_used: 4250000,
    tokens_reserved: 120000,
  },
  {
    period_kind: 'daily',
    period_start: '2026-11-18T00:00:00Z',
    token_cap: 500000,
    tokens_used: 125000,
    tokens_reserved: 25000,
  },
];

const mockAgents = [
  {
    id: 'agent-sec',
    slug: 'security-auditor',
    display_name: 'Security Auditor & Threat Modeler',
    project_id: null,
    harness_kind: 'in_app_sdk',
    provider_kind: 'gemini',
    model_id: 'gemini-3.8-flash-high',
    cli_binary_allowlist_id: null,
    cli_args: null,
    remote_runner_pool_slug: null,
    repo_access_mode: 'read_only',
    mcp_allowed_tools: ['read_file', 'grep_code'],
    system_instructions_md: 'Autonomous threat analysis and static boundary verification agent.',
    timeout_ms: 120000,
    created_at: '2026-10-15T00:00:00Z',
    updated_at: '2026-11-10T00:00:00Z',
  },
  {
    id: 'agent-cli',
    slug: 'codebase-investigator',
    display_name: 'Antigravity CLI Codebase Investigator',
    project_id: null,
    harness_kind: 'cli_pipe',
    provider_kind: null,
    model_id: null,
    cli_binary_allowlist_id: 'agy',
    cli_args: ['-p'],
    remote_runner_pool_slug: null,
    repo_access_mode: 'read_only',
    mcp_allowed_tools: [],
    system_instructions_md: 'Fast read-only codebase investigator executing agy -p pipe queries.',
    timeout_ms: 60000,
    created_at: '2026-10-20T00:00:00Z',
    updated_at: '2026-11-12T00:00:00Z',
  },
  {
    id: 'agent-rem',
    slug: 'remote-verifier',
    display_name: 'Remote mTLS Clean-Room Verifier',
    project_id: null,
    harness_kind: 'remote_runner',
    provider_kind: null,
    model_id: null,
    cli_binary_allowlist_id: null,
    cli_args: null,
    remote_runner_pool_slug: 'prod-runners',
    repo_access_mode: 'isolated_clone',
    mcp_allowed_tools: ['build', 'test'],
    system_instructions_md: 'Outbound mTLS worker executing clean-room builds and forensic checks.',
    timeout_ms: 180000,
    created_at: '2026-10-25T00:00:00Z',
    updated_at: '2026-11-14T00:00:00Z',
  },
];

const mockRunners = [
  {
    id: 'run-01',
    workspace_id: 'ws-kanban',
    pool_slug: 'prod-runners',
    hostname: 'runner-node-01.internal.cloud',
    status: 'active',
    client_cert_sha256_hex: '4f8a1c9e8b7d6a5f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f',
    cert_expires_at: '2027-10-01T12:00:00Z',
    capabilities: { docker: true, os: 'linux-x86_64', gpu: true },
    last_heartbeat_at: '2026-11-18T23:25:00Z',
    revoked_at: null,
    created_at: '2026-10-01T12:00:00Z',
  },
  {
    id: 'run-02',
    workspace_id: 'ws-kanban',
    pool_slug: 'default',
    hostname: 'worker-edge-02.dmz.local',
    status: 'offline',
    client_cert_sha256_hex: '9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b',
    cert_expires_at: '2027-10-10T10:00:00Z',
    capabilities: { arch: 'arm64' },
    last_heartbeat_at: '2026-11-18T18:00:00Z',
    revoked_at: null,
    created_at: '2026-10-10T10:00:00Z',
  },
];

function getBaseMocks(): MockHandlers {
  return {
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-qa' } },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KANBA/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: '01918a22-0000-7000-8000-000000000001',
        workspace_id: 'ws-kanban',
        aal_level: 2,
        mfa_pending: false,
        csrf_token: 'test-csrf-token-qa',
        remember_me: true,
        idle_expires_at: '2026-11-25T00:00:00Z',
        absolute_expires_at: '2026-12-18T00:00:00Z',
      },
    },
    'GET /api/v1/users/me': {
      json: {
        id: '01918a22-0000-7000-8000-000000000001',
        handle: '@adam',
        display_name: 'Adam Outler',
        email: 'adam@example.com',
        type: 'USER',
        is_server_admin: true,
        aal_level: 2,
        capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'SERVER_ADMIN'],
      },
    },
    'GET /api/v1/auth/me': {
      json: {
        id: '01918a22-0000-7000-8000-000000000001',
        handle: '@adam',
        display_name: 'Adam Outler',
        email: 'adam@example.com',
        type: 'USER',
        is_server_admin: true,
        aal_level: 2,
        capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'SERVER_ADMIN'],
      },
    },
    'GET /api/v1/me': {
      json: {
        id: '01918a22-0000-7000-8000-000000000001',
        handle: '@adam',
        display_name: 'Adam Outler',
        email: 'adam@example.com',
        type: 'USER',
        is_server_admin: true,
        aal_level: 2,
        capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'SERVER_ADMIN'],
      },
    },
    'GET /api/v1/system/status': {
      json: {
        initialized: true,
        standalone: false,
        is_air_gapped: true,
        version: '0.1.0',
        environment: 'production',
        database: { connected: true, latency_ms: 1.2 },
      },
    },
    'GET /api/v1/workspaces': {
      json: [{ id: 'ws-kanban', name: 'kanban', slug: 'kanban' }],
    },
    'GET /api/v1/workspaces/current': {
      json: { id: 'ws-kanban', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/workspaces/settings': {
      json: {
        air_gap_mode: true,
        token_cap_monthly: 10000000,
      },
    },
    'GET /api/v1/projects': {
      json: [{ id: 'proj-kanba', key: 'KANBA', name: 'Kanban Platform' }],
    },
    'GET /api/v1/projects/KANBA': { json: loadFixture('project-kan') },
    'GET /api/v1/admin/ai/providers': { json: mockProviders },
    'GET /api/v1/admin/ai/providers/:id': { json: mockProviders[0] },
    'GET /api/v1/admin/ai/budgets': { json: mockBudgets },
    'GET /api/v1/admin/agent-definitions': { json: mockAgents },
    'GET /api/v1/admin/agent-runners': { json: mockRunners },
    'POST /api/v1/admin/agent-runners/enrollment-tokens': {
      json: {
        id: 'tok-1',
        pool_slug: 'prod-runners',
        enrollment_token: 'kb_enroll_live_7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c',
        expires_at: '2026-11-19T00:15:00Z',
        created_at: '2026-11-19T00:00:00Z',
      },
    },
    'POST /api/v1/admin/agent-definitions/:id:validate': {
      json: {
        valid: true,
        exit_code: 0,
        status: 'ok',
        command: 'kanban-agent validate-echo',
        latency_ms: 142,
        tokens_in: 32,
        tokens_out: 48,
        rendered_context: 'Sanitized context',
        tool_trace: 'tool:echo',
        report_text: 'SUCCESS: Agent endpoint responded in 142ms. Echo verified.',
      },
    },
  };
}

test.describe('KANBA-219 Visual Proofs - AI Providers, Agent Definitions, and mTLS Runners', () => {
  test.beforeEach(async ({ context, page }) => {
    await page.unroute('**/api/v1/**');
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-qa',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-ai-providers-overview: AI Studio Providers & Air-Gap Banner (Light)', async ({
    page,
  }, testInfo) => {
    page.on('response', (res) => {
      if (res.status() === 599) {
        console.error('599 UNMATCHED ROUTE:', res.request().method(), res.request().url());
      }
    });
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();
    await expect(page.getByTestId('air-gap-active-banner')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-openai-1')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-gemini-1')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-ollama-1')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-ai-providers-overview',
      annotations: [
        {
          selector: '[data-testid="air-gap-active-banner"]',
          label: 'Air-Gap Warning',
          note: 'High-contrast banner warning cloud calls are blocked in air-gap mode',
        },
        {
          selector: '[data-testid="provider-card-prov-openai-1"]',
          label: 'OpenAI Provider',
          note: 'Configured provider with write-only key custody and model allowlist',
        },
        {
          selector: '[data-testid="provider-card-prov-ollama-1"]',
          label: 'Local Ollama',
          note: 'Air-gap compliant local provider with residency metadata',
        },
        {
          selector: '[data-testid="manage-budget-btn-prov-openai-1"]',
          label: 'Token Caps & Ledger',
          note: 'Access to monthly token budgets and usage ledgers',
        },
      ],
    });
  });

  test('02-ai-providers-dark: AI Studio Providers & Air-Gap Banner (Dark)', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'dark');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();
    await expect(page.getByTestId('air-gap-active-banner')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-ai-providers-dark',
      annotations: [
        {
          selector: '[data-testid="air-gap-active-banner"]',
          label: 'Dark Air-Gap Banner',
          note: 'Audited dark mode warning banner meeting WCAG 4.5:1 contrast',
        },
        {
          selector: '[data-testid="provider-card-prov-gemini-1"]',
          label: 'Gemini Provider (Dark)',
          note: 'Dark theme card layout and enabled status toggle',
        },
      ],
    });
  });

  test('03-ai-provider-drawer: Register / Edit AI Provider Drawer', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await page.getByTestId('edit-provider-btn-prov-openai-1').click();
    await expect(page.getByTestId('ai-provider-editor-drawer')).toBeVisible();
    await expect(page.getByTestId('provider-key-input')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '03-ai-provider-drawer',
      annotations: [
        {
          selector: '[data-testid="ai-provider-editor-drawer"]',
          label: 'Provider Drawer',
          note: 'Drawer editor for cloud or local AI providers',
        },
        {
          selector: '[data-testid="provider-key-input"]',
          label: 'Write-Only Custody',
          note: 'Masked placeholder preserving existing secret unless cleared',
        },
        {
          selector: '[data-testid="clear-key-checkbox"]',
          label: 'Clear Key Checkbox',
          note: 'Explicit opt-in to purge secret on save',
        },
      ],
    });
  });

  test('04-ai-budget-modal: Token Caps & Usage Ledger Modal', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await page.getByTestId('manage-budget-btn-prov-openai-1').click();
    await expect(page.getByTestId('ai-budget-modal')).toBeVisible();
    await expect(page.getByTestId('budget-token-cap-input')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '04-ai-budget-modal',
      annotations: [
        {
          selector: '[data-testid="ai-budget-modal"]',
          label: 'Budget Ledger Modal',
          note: 'Monthly token caps, burn rate tracking, and ledger stats',
        },
        {
          selector: '[data-testid="budget-token-cap-input"]',
          label: 'Token Cap Input',
          note: 'Configurable workspace/project token cap limits',
        },
      ],
    });
  });

  test('05-agent-definitions-overview: Autonomous Agent Definitions Studio (Light)', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/agents');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('agent-studio-page')).toBeVisible();
    await expect(page.getByTestId('agent-card-agent-sec')).toBeVisible();
    await expect(page.getByTestId('agent-card-agent-cli')).toBeVisible();
    await expect(page.getByTestId('agent-card-agent-rem')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '05-agent-definitions-overview',
      annotations: [
        {
          selector: '[data-testid="agent-card-agent-sec"]',
          label: 'In-App SDK Agent',
          note: 'Direct SDK agent with model tier high and 120s timeout',
        },
        {
          selector: '[data-testid="agent-card-agent-cli"]',
          label: 'CLI Pipe Agent',
          note: 'Restricted CLI pipe enforcing agy -p prefix and banned flag rejection',
        },
        {
          selector: '[data-testid="agent-card-agent-rem"]',
          label: 'Remote Runner Agent',
          note: 'Dispatches tasks to mTLS worker pool with clean-room isolation',
        },
      ],
    });
  });

  test('06-agent-definitions-dark: Autonomous Agent Definitions Studio (Dark)', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/agents');
    await applyTheme(page, 'dark');

    await expect(page.getByTestId('agent-studio-page')).toBeVisible();
    await expect(page.getByTestId('agent-card-agent-cli')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '06-agent-definitions-dark',
      annotations: [
        {
          selector: '[data-testid="agent-card-agent-cli"]',
          label: 'CLI Pipe (Dark)',
          note: 'Dark theme agent card with badge and capability tags',
        },
      ],
    });
  });

  test('07-agent-validation-modal: Agent Test-Validation Echo Modal', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/agents');
    await applyTheme(page, 'light');

    await page.getByTestId('validate-agent-btn-agent-sec').click();
    await expect(page.getByTestId('agent-validation-modal')).toBeVisible();
    await expect(page.getByTestId('validation-verdict-badge')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '07-agent-validation-modal',
      annotations: [
        {
          selector: '[data-testid="agent-validation-modal"]',
          label: 'Echo Validation Modal',
          note: 'Tests agent endpoint using kanban-agent validate-echo protocol',
        },
        {
          selector: '[data-testid="validation-verdict-badge"]',
          label: 'Success Verdict',
          note: 'Displays latency (142ms), command, and verified response report',
        },
      ],
    });
  });

  test('08-runner-studio-overview: Remote mTLS Runners Studio (Light)', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/agent-runners');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('runner-studio-page')).toBeVisible();
    await expect(page.getByTestId('runner-card-run-01')).toBeVisible();
    await expect(page.getByTestId('runner-card-run-02')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '08-runner-studio-overview',
      annotations: [
        {
          selector: '[data-testid="runner-card-run-01"]',
          label: 'Active mTLS Runner',
          note: 'Active runner node with heartbeat, SHA-256 cert fingerprint, and capabilities',
        },
        {
          selector: '[data-testid="runner-card-run-02"]',
          label: 'Offline Runner',
          note: 'Offline status badge and revocation controls',
        },
        {
          selector: '[data-testid="open-mint-modal-btn"]',
          label: 'Mint Token Button',
          note: 'Opens single-reveal enrollment token generator modal',
        },
      ],
    });
  });

  test('09-runner-studio-dark: Remote mTLS Runners Studio (Dark)', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/agent-runners');
    await applyTheme(page, 'dark');

    await expect(page.getByTestId('runner-studio-page')).toBeVisible();
    await expect(page.getByTestId('runner-card-run-01')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '09-runner-studio-dark',
      annotations: [
        {
          selector: '[data-testid="runner-card-run-01"]',
          label: 'Dark Runner Card',
          note: 'Accessible dark theme runner card with certificate metadata',
        },
      ],
    });
  });

  test('10-runner-mint-token-modal: Single-Reveal Enrollment Token Modal', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/agent-runners');
    await applyTheme(page, 'light');

    await page.getByTestId('open-mint-modal-btn').click();
    await expect(page.getByTestId('mint-enrollment-token-modal')).toBeVisible();

    await page.getByTestId('submit-mint-token-btn').click();
    await expect(page.getByTestId('single-reveal-token-view')).toBeVisible();
    await expect(page.getByTestId('token-plaintext')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '10-runner-mint-token-modal',
      annotations: [
        {
          selector: '[data-testid="single-reveal-warning"]',
          label: 'Single-Reveal Notice',
          note: 'Explicit notice that token is valid for 15m and never retrievable again after closing',
        },
        {
          selector: '[data-testid="token-plaintext"]',
          label: 'Plaintext Token',
          note: 'Freshly minted enrollment token',
        },
        {
          selector: '[data-testid="copy-token-btn"]',
          label: '1-Click Copy',
          note: 'Copies token to clipboard with instant visual feedback',
        },
      ],
    });
  });
});
