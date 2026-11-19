// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KAN-22';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-22/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(150);
}

const mock5Providers = [
  {
    id: 'prov-1-ollama',
    provider_kind: 'ollama',
    display_name: 'Primary Ollama Engine',
    base_url: 'http://127.0.0.1:11434',
    model_allowlist: ['qwen2.5-coder:32b', 'llama3.3:70b'],
    residency_tier: 'local_only',
    priority: 10,
    is_enabled: true,
    api_key_set: false,
    settings: {},
  },
  {
    id: 'prov-2-ollama',
    provider_kind: 'ollama',
    display_name: 'Secondary Ollama Cluster',
    base_url: 'http://192.168.1.50:11434',
    model_allowlist: ['deepseek-r1:32b', 'mistral-small:24b'],
    residency_tier: 'local_only',
    priority: 20,
    is_enabled: true,
    api_key_set: false,
    settings: {},
  },
  {
    id: 'prov-3-openai-local',
    provider_kind: 'openai',
    display_name: 'Local vLLM OpenAI Engine',
    base_url: 'http://127.0.0.1:8000/v1',
    model_allowlist: ['meta-llama/Llama-3.1-8B-Instruct'],
    residency_tier: 'local_only',
    priority: 30,
    is_enabled: true,
    api_key_set: false,
    settings: {},
  },
  {
    id: 'prov-4-gemini',
    provider_kind: 'gemini',
    display_name: 'Google Gemini Pro Cloud',
    base_url: 'https://generativelanguage.googleapis.com',
    model_allowlist: ['gemini-2.5-pro', 'gemini-2.5-flash'],
    residency_tier: 'cloud_standard',
    priority: 40,
    is_enabled: true,
    api_key_set: true,
    settings: {},
  },
  {
    id: 'prov-5-openai',
    provider_kind: 'openai',
    display_name: 'Enterprise OpenAI Cloud',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o', 'o3-mini'],
    residency_tier: 'cloud_standard',
    priority: 50,
    is_enabled: true,
    api_key_set: true,
    settings: {},
  },
];

function getBaseMocks(): MockHandlers {
  return {
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-qa' } },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
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
        is_air_gapped: false,
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
        air_gap_mode: false,
      },
    },
    'GET /api/v1/admin/workspace-settings': {
      json: {
        air_gap_mode: false,
      },
    },
    'GET /api/v1/projects': {
      json: [{ id: 'proj-kanba', key: 'KANBA', name: 'Kanban Platform' }],
    },
    'GET /api/v1/projects/KANBA': { json: loadFixture('project-kan') },
    'GET /api/v1/admin/ai/providers': { json: mock5Providers },
    'GET /api/v1/admin/ai/providers/:id': { json: mock5Providers[0] },
    'GET /api/v1/admin/ai/budgets': { json: [] },
    'POST /api/v1/admin/ai/providers/:id/test-connection': {
      json: {
        ok: true,
        latency_ms: 42.1,
        models: ['qwen2.5-coder:32b', 'llama3.3:70b'],
        model_count: 2,
        message: 'Connected in 42ms',
      },
    },
    'POST /api/v1/admin/ai/providers/test-connection': {
      json: {
        ok: true,
        latency_ms: 38.6,
        models: ['qwen2.5-coder:32b'],
        model_count: 1,
      },
    },
    'POST /api/v1/admin/ai/providers/:id/probe-models': {
      json: {
        ok: true,
        latency_ms: 55.0,
        models: ['llama3.3:70b', 'qwen2.5-coder:32b', 'deepseek-r1:32b', 'mistral-small:24b', 'phi4:14b'],
        model_count: 5,
      },
    },
    'POST /api/v1/admin/ai/providers/probe-models': {
      json: {
        ok: true,
        latency_ms: 55.0,
        models: ['llama3.3:70b', 'qwen2.5-coder:32b', 'deepseek-r1:32b', 'mistral-small:24b', 'phi4:14b'],
        model_count: 5,
      },
    },
    'PUT /api/v1/admin/ai/providers/order': {
      json: mock5Providers,
    },
  };
}

test.describe('KAN-22 Visual QA Proofs - AI Studio 5-Provider Failover Stack & Probe Models', () => {
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

  test('01-failover-stack-light: 5-Provider Priority Stack (Light Theme)', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-1-ollama')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-2-ollama')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-3-openai-local')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-4-gemini')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-5-openai')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-failover-stack-light',
      annotations: [
        {
          selector: '[data-testid="provider-rank-prov-1-ollama"]',
          label: '#1 Primary Ollama',
          note: 'First-priority local Ollama zero-egress runtime',
        },
        {
          selector: '[data-testid="key-status-prov-1-ollama"]',
          label: 'Local Key Badge',
          note: 'No Key Required (Local) badge on loopback Ollama endpoint',
        },
        {
          selector: '[data-testid="provider-rank-prov-3-openai-local"]',
          label: '#3 Local vLLM Engine',
          note: 'OpenAI-compatible local runtime targeting 127.0.0.1:8000',
        },
        {
          selector: '[data-testid="provider-rank-prov-4-gemini"]',
          label: '#4 Google Gemini Cloud',
          note: 'Cloud failover tier with write-only key custody',
        },
        {
          selector: '[data-testid="provider-rank-prov-5-openai"]',
          label: '#5 Enterprise OpenAI',
          note: 'Final failover tier in priority stack',
        },
      ],
    });
  });

  test('02-failover-stack-dark: 5-Provider Priority Stack (Dark Theme)', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'dark');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-1-ollama')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-5-openai')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-failover-stack-dark',
      annotations: [
        {
          selector: '[data-testid="providers-stack"]',
          label: 'Dark Mode Stack',
          note: 'Numbered 1..5 failover priority stack in high-contrast dark theme',
        },
        {
          selector: '[data-testid="residency-badge-prov-1-ollama"]',
          label: 'Local Badge (Dark)',
          note: 'Audited dark token contrast for Local / Zero-Egress badge',
        },
        {
          selector: '[data-testid="residency-badge-prov-5-openai"]',
          label: 'Cloud Badge (Dark)',
          note: 'Subtle Cloud residency badge on dark theme',
        },
      ],
    });
  });

  test('03-test-connection-card: Inline Test Connection Results on Card', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('test-connection-btn-prov-1-ollama')).toBeVisible();
    await page.getByTestId('test-connection-btn-prov-1-ollama').click();

    await expect(page.getByTestId('test-status-prov-1-ollama')).toBeVisible();
    await expect(page.getByTestId('test-status-prov-1-ollama')).toContainText('Connected in 42ms');

    await annotatedScreenshot(page, testInfo, {
      name: '03-test-connection-card',
      annotations: [
        {
          selector: '[data-testid="test-status-prov-1-ollama"]',
          label: 'Inline Connection Status',
          note: 'Live round-trip latency and available model count displayed inline',
        },
      ],
    });
  });

  test('04-probe-models-chips: Probe Models Live Chip Picker in Drawer', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await page.getByTestId('edit-provider-btn-prov-1-ollama').click();
    await expect(page.getByTestId('ai-provider-editor-drawer')).toBeVisible();

    await page.getByTestId('probe-models-btn').click();
    await expect(page.getByTestId('probed-models-picker')).toBeVisible();
    await expect(page.getByTestId('probe-chip-qwen2.5-coder:32b')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '04-probe-models-chips',
      annotations: [
        {
          selector: '[data-testid="probe-models-btn"]',
          label: 'Probe Models Button',
          note: 'Queries upstream provider endpoint for live authorized models',
        },
        {
          selector: '[data-testid="probed-models-picker"]',
          label: 'Interactive Model Chips',
          note: 'Selectable chips with filter search and Select All / Clear controls',
        },
      ],
    });
  });

  test('05-advanced-settings-collapsed: Collapsed Advanced Settings in Drawer', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await page.getByTestId('register-provider-btn').click();
    await expect(page.getByTestId('ai-provider-editor-drawer')).toBeVisible();
    await expect(page.getByTestId('advanced-settings-details')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '05-advanced-settings-collapsed',
      annotations: [
        {
          selector: '[data-testid="advanced-settings-details"]',
          label: 'Collapsed Advanced Settings',
          note: 'Tidy details disclosure keeping advanced residency overrides tucked away',
        },
      ],
    });
  });

  test('06-advanced-settings-expanded: Expanded Advanced Settings with Residency Tier Override', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await page.getByTestId('register-provider-btn').click();
    await expect(page.getByTestId('ai-provider-editor-drawer')).toBeVisible();

    // Click details summary to expand
    await page.locator('[data-testid="advanced-settings-details"] summary').click();
    await expect(page.getByTestId('provider-residency-select')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '06-advanced-settings-expanded',
      annotations: [
        {
          selector: '[data-testid="provider-residency-select"]',
          label: 'Residency Tier Override',
          note: 'Manual data residency selector with auto-inferred protocol guidance',
        },
      ],
    });
  });

  test('07-drawer-test-connection: Drawer Test Connection Button & Result', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/admin/ai');
    await applyTheme(page, 'light');

    await page.getByTestId('edit-provider-btn-prov-1-ollama').click();
    await expect(page.getByTestId('ai-provider-editor-drawer')).toBeVisible();

    await page.getByTestId('drawer-test-connection-btn').click();
    await expect(page.getByTestId('drawer-test-status')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '07-drawer-test-connection',
      annotations: [
        {
          selector: '[data-testid="drawer-test-connection-btn"]',
          label: 'Drawer Test Connection',
          note: 'Validates credentials and endpoint connectivity before saving',
        },
        {
          selector: '[data-testid="drawer-test-status"]',
          label: 'Test Result Message',
          note: 'Inline confirmation of round-trip latency and discovered models',
        },
      ],
    });
  });
});
