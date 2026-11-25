// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Visual verification proofs for KAN-412:
 * Simplify AI Providers, Agents & Remote Runners UI + Backend Wiring.
 * Plain ASCII hyphens only.
 */

import { resolve } from 'node:path';
import { mkdirSync, copyFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-412';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-412/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb:theme', t);
    document.documentElement.dataset.theme = t;
    document.documentElement.setAttribute('data-theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

async function unclipForFullPage(page: Page): Promise<void> {
  await page.evaluate(() => {
    const applyToElements = (selector: string, styles: Record<string, string>) => {
      document.querySelectorAll<HTMLElement>(selector).forEach((el) => {
        for (const [prop, val] of Object.entries(styles)) {
          el.style.setProperty(prop, val, 'important');
        }
      });
    };
    applyToElements('html', {
      position: 'relative',
      height: 'auto',
      'min-height': '100%',
    });
    applyToElements('body', {
      height: 'auto',
      'min-height': '100%',
      overflow: 'visible',
    });
    applyToElements('.kb-app-shell, .kb-main-canvas', {
      height: 'auto',
      'max-height': 'none',
      overflow: 'visible',
    });
    applyToElements('.kb-topbar, header', {
      position: 'static',
    });
    applyToElements(
      '[role="dialog"], .kb-modal, .kb-modal-card, .kb-modal-body, .kb-drawer, form',
      {
        'max-height': 'none',
        height: 'auto',
        overflow: 'visible',
      },
    );
    applyToElements(
      '[class*="backdrop"], [class*="modal-backdrop"], [class*="overlay"]',
      {
        position: 'absolute',
        inset: '0',
        'min-height': '100%',
        height: '100%',
      },
    );
    // Suppress any reconnecting chip or floating toast
    applyToElements('.realtime-status-chip, [data-state="reconnecting"]', {
      display: 'none',
    });
  });
  await page.waitForTimeout(100);
}

const mockProviders = [
  {
    id: 'prov-01',
    provider_kind: 'ollama',
    display_name: 'Local Ollama Runtime',
    base_url: 'http://127.0.0.1:11434',
    model_allowlist: ['llama3.2', 'qwen2.5-coder'],
    priority: 1,
    residency_tier: 'local_only',
    is_active: true,
    has_api_key: false,
    api_key_masked: null,
    settings_json: { timeout_ms: 30000 },
    created_at: '2026-11-25T12:00:00Z',
    updated_at: '2026-11-25T12:00:00Z',
  },
  {
    id: 'prov-02',
    provider_kind: 'openai',
    display_name: 'OpenAI / OpenAI-Compatible',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o', 'gpt-4o-mini'],
    priority: 2,
    residency_tier: 'cloud_standard',
    is_active: true,
    has_api_key: true,
    api_key_masked: 'sk-proj-••••••••••••',
    settings_json: { timeout_ms: 30000 },
    created_at: '2026-11-25T12:00:00Z',
    updated_at: '2026-11-25T12:00:00Z',
  },
];

const mockBudgets = [
  {
    provider_id: 'prov-01',
    token_cap: 0,
    tokens_used: 150000,
    reset_period: 'monthly',
    period_start: '2026-11-01T00:00:00Z',
  },
  {
    provider_id: 'prov-02',
    token_cap: 25000000,
    tokens_used: 1250000,
    reset_period: 'monthly',
    period_start: '2026-11-01T00:00:00Z',
  },
];

const mockAgents = [
  {
    id: 'agt-01',
    slug: 'codebase_investigator',
    display_name: 'Codebase Investigator',
    description: 'Explores the repository topology and architecture.',
    harness_kind: 'cli_pipe',
    cli_binary_allowlist_id: 'agy',
    cli_args: ['-p'],
    repo_access_mode: 'bare_git_tools',
    mcp_allowed_tools: ['read_file', 'search_files'],
    system_prompt: 'You are a senior code architect.',
    is_active: true,
    created_at: '2026-11-25T12:00:00Z',
  },
];

function getMocks(airGapMode = false): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const projectKan = loadFixture<Record<string, unknown>>('project-kan');

  return {
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-412' } },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { count: 0 } },
    'GET /api/v1/me': {
      json: {
        ...me,
        id: '01918a22-0000-7000-8000-000000000001',
        is_server_admin: true,
        is_workspace_admin: true,
        aal_level: 2,
        auth_aal: 'aal2',
      },
    },
    'GET /api/v1/auth/me': {
      json: {
        ...me,
        id: '01918a22-0000-7000-8000-000000000001',
        is_server_admin: true,
        is_workspace_admin: true,
        aal_level: 2,
        auth_aal: 'aal2',
      },
    },
    'GET /api/v1/users/me': {
      json: {
        ...me,
        id: '01918a22-0000-7000-8000-000000000001',
        is_server_admin: true,
        is_workspace_admin: true,
        aal_level: 2,
        auth_aal: 'aal2',
      },
    },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: '01918a22-0000-7000-8000-000000000001',
        workspace_id: 'ws-kanban',
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan-412',
        user: {
          ...me,
          id: '01918a22-0000-7000-8000-000000000001',
          is_server_admin: true,
          is_workspace_admin: true,
          aal_level: 2,
          auth_aal: 'aal2',
        },
      },
    },
    'POST /api/v1/auth/aal2/touch': { json: { ok: true } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/workspaces': {
      json: [{ id: 'ws-kanban', name: 'kanban', slug: 'kanban', is_current: true }],
    },
    'GET /api/v1/workspaces/current': {
      json: { id: 'ws-kanban', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/workspaces/kanban': {
      json: { id: 'ws-kanban', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/workspaces/:workspace/settings': {
      json: {
        air_gap_mode: airGapMode,
        token_cap_monthly: 10000000,
      },
    },
    'GET /api/v1/workspaces/:workspace/ai-providers/settings': {
      json: {
        air_gap_mode: airGapMode,
      },
    },
    'GET /api/v1/workspaces/:workspace/ai-providers': { json: mockProviders },
    'GET /api/v1/workspaces/:workspace/ai-providers/budgets': { json: mockBudgets },
    'GET /api/v1/workspaces/:workspace/agent-definitions': { json: mockAgents },
    'GET /api/v1/admin/ai/providers': { json: mockProviders },
    'GET /api/v1/admin/ai/budgets': { json: mockBudgets },
    'GET /api/v1/admin/agents/definitions': { json: mockAgents },
    'GET /api/v1/admin/runners': { json: [] },
    'GET /api/v1/admin/agent-runners': { json: [] },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KANBA': { json: projectKan },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KANBA/access': { json: loadFixture('access-project-kan') },
  };
}

async function setupPageMocks(page: Page, airGapMode = false): Promise<void> {
  await page.addInitScript(() => {
    class MockWebSocket extends EventTarget {
      readyState = 1;
      url = '';
      onopen: ((ev: Event) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent) => void) | null = null;
      constructor(url: string) {
        super();
        this.url = url;
        setTimeout(() => {
          this.readyState = 1;
          if (this.onopen) this.onopen(new Event('open'));
          this.dispatchEvent(new Event('open'));
        }, 10);
      }
      send(_data?: unknown): void {
        if (_data !== undefined) return;
      }
      close() {
        this.readyState = 3;
        if (this.onclose) this.onclose(new CloseEvent('close'));
        this.dispatchEvent(new CloseEvent('close'));
      }
    }
    // @ts-expect-error MockWebSocket replaces native window.WebSocket for tests
    window.WebSocket = MockWebSocket;

    class MockEventSource extends EventTarget {
      readyState = 1;
      url = '';
      onopen: ((ev: Event) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent) => void) | null = null;
      constructor(url: string) {
        super();
        this.url = url;
        setTimeout(() => {
          this.readyState = 1;
          if (this.onopen) this.onopen(new Event('open'));
          this.dispatchEvent(new Event('open'));
        }, 10);
      }
      close() {
        this.readyState = 2;
      }
    }
    // @ts-expect-error MockEventSource replaces native window.EventSource for tests
    window.EventSource = MockEventSource;
  });
  await mockApi(page, getMocks(airGapMode));
}

test.describe('KAN-412: AI Providers, Agents & Runners Simplification Visual Proofs', () => {
  test('01: 1440x900 Desktop Light - AiProviderEditorDrawer Presets, Promoted Base URL, Zero Password Input', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupPageMocks(page, false);

    await page.goto('/workspaces/settings/ai');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();

    // Verify 100vh app shell layout before unclip
    const initialShellBox = await page.locator('.kb-app-shell').boundingBox();
    expect(initialShellBox?.height).toBeLessThanOrEqual(900);

    // Open Provider Editor Drawer
    await page.getByTestId('register-provider-btn').click();
    await expect(page.getByTestId('ai-provider-editor-drawer')).toBeVisible();

    // Verify Presets are visible
    await expect(page.getByTestId('preset-ollama-btn')).toBeVisible();
    await expect(page.getByTestId('preset-openai-btn')).toBeVisible();
    await expect(page.getByTestId('preset-gemini-btn')).toBeVisible();

    // Verify Promoted Base URL is in primary settings
    await expect(page.getByTestId('provider-base-url-input')).toBeVisible();

    // Verify zero input[type="password"]
    const passwordInputs = await page.locator('input[type="password"]').count();
    expect(passwordInputs).toBe(0);

    // Click Ollama Preset to populate fields
    await page.getByTestId('preset-ollama-btn').click();
    await expect(page.getByTestId('provider-base-url-input')).toHaveValue('http://127.0.0.1:11434');

    // Unclip layout and capture full-page screenshot
    await unclipForFullPage(page);

    const shot1 = resolve(SCREENSHOT_DIR, '01-ai-provider-editor-1440x900-light.png');
    await page.screenshot({ path: shot1, fullPage: true });
    copyFileSync(shot1, resolve(SCREENSHOT_DIR, '1440x900-light.png'));

    // Close drawer via cancel button
    await page.getByTestId('cancel-provider-drawer-btn').click();
    await page.waitForTimeout(200);

    // Click Manage Budget button on prov-01
    await page.getByTestId('manage-budget-btn-prov-01').click();
    await expect(page.getByTestId('ai-budget-modal')).toBeVisible();

    // Verify Mode Toggles and Presets are visible
    await expect(page.getByTestId('cap-mode-enforce-btn')).toBeVisible();
    await expect(page.getByTestId('cap-mode-unlimited-btn')).toBeVisible();
    await expect(page.getByTestId('preset-budget-1m-btn')).toBeVisible();
    await expect(page.getByTestId('preset-budget-0-freeze-btn')).toBeVisible();

    // Click 0 Freeze preset
    await page.getByTestId('preset-budget-0-freeze-btn').click();
    await expect(page.getByTestId('zero-cap-freeze-warning')).toBeVisible();

    // Unclip for budget modal screenshot
    await unclipForFullPage(page);

    const shot2 = resolve(SCREENSHOT_DIR, '02-ai-budget-freeze-1440x900-light.png');
    await page.screenshot({ path: shot2, fullPage: true });
  });

  test('02: 1440x900 Desktop Dark - AgentStudioPage AdminStudioSubnav and AgentDefinitionEditorDrawer', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setupPageMocks(page, false);

    await page.goto('/workspaces/settings/agents');
    await applyTheme(page, 'dark');

    await expect(page.getByTestId('agent-studio-page')).toBeVisible();

    // Verify AdminStudioSubnav is rendered with active agents tab
    await expect(page.getByTestId('tab-admin-agents')).toBeVisible();
    await expect(page.getByTestId('tab-admin-agents')).toHaveClass(/active/);

    // Open Agent Definition Drawer
    await page.getByTestId('register-agent-btn').click();
    await expect(page.getByTestId('agent-editor-drawer')).toBeVisible();

    // Verify Harness Select and Hints
    await expect(page.getByTestId('agent-harness-select')).toBeVisible();
    await expect(page.getByTestId('agent-harness-hint')).toBeVisible();

    await unclipForFullPage(page);

    const shot3 = resolve(SCREENSHOT_DIR, '03-agent-studio-subnav-1440x900-dark.png');
    await page.screenshot({ path: shot3, fullPage: true });
    copyFileSync(shot3, resolve(SCREENSHOT_DIR, '1440x900-dark.png'));
  });

  test('03: 1024x768 Tablet Landscape - Air-Gap Mode Cloud Disabled Controls', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await setupPageMocks(page, true); // Air-gap active

    await page.goto('/workspaces/settings/ai');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();

    // Open Provider Editor Drawer
    await page.getByTestId('register-provider-btn').click();
    await expect(page.getByTestId('ai-provider-editor-drawer')).toBeVisible();

    // Cloud presets disabled
    const openaiBtn = page.getByTestId('preset-openai-btn');
    const geminiBtn = page.getByTestId('preset-gemini-btn');
    await expect(openaiBtn).toBeDisabled();
    await expect(geminiBtn).toBeDisabled();

    // Check kind select options
    const select = page.getByTestId('provider-kind-select');
    await expect(select.locator('option[value="openai"]')).toBeDisabled();
    await expect(select.locator('option[value="gemini"]')).toBeDisabled();

    await unclipForFullPage(page);

    const shot4 = resolve(SCREENSHOT_DIR, '04-ai-airgap-disabled-1024x768.png');
    await page.screenshot({ path: shot4, fullPage: true });
    copyFileSync(shot4, resolve(SCREENSHOT_DIR, '1024x768.png'));
  });

  test('04: 768x1024 Tablet Portrait - AiBudgetModal Unlimited Quota Mode', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await setupPageMocks(page, false);

    await page.goto('/workspaces/settings/ai');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();

    // Open Budget modal
    await page.getByTestId('manage-budget-btn-prov-02').click();
    await expect(page.getByTestId('ai-budget-modal')).toBeVisible();

    // Click Unlimited Quota pill
    await page.getByTestId('cap-mode-unlimited-btn').click();
    await expect(page.getByTestId('budget-unlimited-note')).toBeVisible();

    await unclipForFullPage(page);

    const shot5 = resolve(SCREENSHOT_DIR, '05-ai-budget-unlimited-768x1024.png');
    await page.screenshot({ path: shot5, fullPage: true });
    copyFileSync(shot5, resolve(SCREENSHOT_DIR, '768x1024.png'));
  });

  test('05: 390x844 Mobile Portrait - Responsive Single-Column Stacked Cards and Studio', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupPageMocks(page, false);

    await page.goto('/workspaces/settings/ai');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('ai-studio-page')).toBeVisible();

    // Verify unclipped mobile width
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);

    // Verify stacked cards, subnav, and action buttons are visible without modal open
    await expect(page.getByTestId('provider-card-prov-01')).toBeVisible();
    await expect(page.getByTestId('provider-card-prov-02')).toBeVisible();

    await unclipForFullPage(page);

    const shot6 = resolve(SCREENSHOT_DIR, '06-ai-mobile-responsive-390x844.png');
    await page.screenshot({ path: shot6, fullPage: true });
    copyFileSync(shot6, resolve(SCREENSHOT_DIR, '390x844.png'));
  });
});
