// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Visual verification proofs for KAN-433:
 * Persist system_instructions_md in Agent Definitions API and Stop Infinite
 * /api/v1/auth/session Request Storm on /workspaces/settings/agents.
 * Plain ASCII hyphens only.
 */

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-433';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-433/screenshots',
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

const customSystemPrompt =
  '# Reality Checker Directives\n\n' +
  '- Passive forensic audits only.\n' +
  '- Strict verification proof packets.\n' +
  '- Zero-tolerance quality gate.';

const mockAgents = [
  {
    id: 'agent-01',
    workspace_id: 'ws-kanban',
    principal_id: 'prin-01',
    slug: 'reality-checker',
    display_name: 'Reality Checker QA',
    harness_kind: 'in_app_sdk',
    provider_kind: 'gemini',
    model_id: 'gemini-2.5-flash',
    cli_binary_allowlist_id: null,
    cli_args: [],
    remote_runner_pool_slug: null,
    repo_access_mode: 'bare_git_tools',
    mcp_allowed_tools: ['search_tickets', 'read_ticket'],
    system_instructions_md: customSystemPrompt,
    timeout_ms: 45000,
  },
  {
    id: 'agent-02',
    workspace_id: 'ws-kanban',
    principal_id: 'prin-02',
    slug: 'agy-reviewer',
    display_name: 'Antigravity CLI Pipe',
    harness_kind: 'cli_pipe',
    provider_kind: null,
    model_id: null,
    cli_binary_allowlist_id: 'agy',
    cli_args: ['-p'],
    remote_runner_pool_slug: null,
    repo_access_mode: 'none',
    mcp_allowed_tools: ['search_knowledge', 'read_doc'],
    system_instructions_md: '# Sandboxed CLI runner.',
    timeout_ms: 60000,
  },
];

function getMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const projectKan = loadFixture<Record<string, unknown>>('project-kan');

  const adminUser = {
    ...me,
    id: '01918a22-0000-7000-8000-000000000001',
    is_server_admin: true,
    is_workspace_admin: true,
    workspace_role: 'WORKSPACE_ADMIN',
    aal_level: 2,
    auth_aal: 'aal2',
  };

  return {
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan-433' } },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/me': { json: adminUser },
    'GET /api/v1/users/me': { json: adminUser },
    'GET /api/v1/auth/me': { json: adminUser },
    'GET /api/v1/auth/session': {
      headers: {
        'x-kb-aal2-expires-at': '2026-11-26T16:00:00Z',
      },
      json: {
        authenticated: true,
        aal2_active: true,
        aal2_expires_at: '2026-11-26T16:00:00Z',
        user: adminUser,
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
        air_gap_mode: false,
        token_cap_monthly: 10000000,
      },
    },
    'GET /api/v1/workspaces/:workspace/ai-providers/settings': {
      json: {
        air_gap_mode: false,
      },
    },
    'GET /api/v1/workspaces/:workspace/agent-definitions': { json: mockAgents },
    'GET /api/v1/workspaces/:workspace/ai-providers': { json: [] },
    'GET /api/v1/workspaces/:workspace/ai-providers/budgets': { json: [] },
    'GET /api/v1/agent-definitions/:agent': { json: mockAgents[0] },
    'GET /api/v1/admin/ai/providers': { json: [] },
    'GET /api/v1/admin/ai/budgets': { json: [] },
    'GET /api/v1/admin/agent-definitions': { json: mockAgents },
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

async function setupPageMocks(page: Page): Promise<{ getSessionCallCount: () => number }> {
  let sessionCallCount = 0;

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

  await mockApi(page, getMocks());

  page.on('request', (req) => {
    if (req.url().includes('/api/v1/auth/session')) {
      sessionCallCount++;
    }
  });

  return {
    getSessionCallCount: () => sessionCallCount,
  };
}

test.describe('KAN-433: Agent Instructions Persistence and Zero Session Storm Visual Proofs', () => {
  test('01: 1440x900 Desktop Light - Edit Agent Drawer displays preserved custom system instructions', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const tracker = await setupPageMocks(page);

    await page.goto('/workspaces/settings/agents');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('agent-studio-page')).toBeVisible();

    // Verify AdminStudioSubnav is rendered with active tab
    await expect(page.getByTestId('tab-admin-agents')).toBeVisible();

    const countBeforeDrawer = tracker.getSessionCallCount();

    // Open Edit Drawer for reality-checker
    await page.getByTestId('edit-agent-btn-agent-01').click();
    await expect(page.getByTestId('agent-editor-drawer')).toBeVisible();

    // Expand Advanced Section to show instructions textarea
    const toggle = page.getByTestId('advanced-model-harness-config-toggle');
    const isExpanded = await toggle.getAttribute('aria-expanded');
    if (isExpanded !== 'true') {
      await toggle.click();
    }

    const textarea = page.getByTestId('agent-instructions-textarea');
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveValue(customSystemPrompt);

    // Wait 400ms to verify zero session request storm occurs
    await page.waitForTimeout(400);
    const countAfterDrawer = tracker.getSessionCallCount();
    expect(countAfterDrawer - countBeforeDrawer).toBe(0);
    expect(countAfterDrawer).toBeLessThanOrEqual(3);

    await unclipForFullPage(page);

    const shot = resolve(SCREENSHOT_DIR, 'desktop-light-1440x900.png');
    await page.screenshot({ path: shot, fullPage: true });
  });

  test('02: 1440x900 Desktop Dark - Preserved instructions displayed in dark theme', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const tracker = await setupPageMocks(page);

    await page.goto('/workspaces/settings/agents');
    await applyTheme(page, 'dark');

    await expect(page.getByTestId('agent-studio-page')).toBeVisible();

    const countBeforeDrawer = tracker.getSessionCallCount();

    // Open Edit Drawer for reality-checker
    await page.getByTestId('edit-agent-btn-agent-01').click();
    await expect(page.getByTestId('agent-editor-drawer')).toBeVisible();

    // Expand Advanced Section
    const toggle = page.getByTestId('advanced-model-harness-config-toggle');
    const isExpanded = await toggle.getAttribute('aria-expanded');
    if (isExpanded !== 'true') {
      await toggle.click();
    }

    const textarea = page.getByTestId('agent-instructions-textarea');
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveValue(customSystemPrompt);

    await page.waitForTimeout(400);
    const countAfterDrawer = tracker.getSessionCallCount();
    expect(countAfterDrawer - countBeforeDrawer).toBe(0);
    expect(countAfterDrawer).toBeLessThanOrEqual(3);

    await unclipForFullPage(page);

    const shot = resolve(SCREENSHOT_DIR, 'desktop-dark-1440x900.png');
    await page.screenshot({ path: shot, fullPage: true });
  });

  test('03: 768x1024 Tablet Portrait - Responsive drawer with custom instructions', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    const tracker = await setupPageMocks(page);

    await page.goto('/workspaces/settings/agents');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('agent-studio-page')).toBeVisible();

    const countBeforeDrawer = tracker.getSessionCallCount();

    // Open Edit Drawer for reality-checker
    await page.getByTestId('edit-agent-btn-agent-01').click();
    await expect(page.getByTestId('agent-editor-drawer')).toBeVisible();

    // Expand Advanced Section
    const toggle = page.getByTestId('advanced-model-harness-config-toggle');
    const isExpanded = await toggle.getAttribute('aria-expanded');
    if (isExpanded !== 'true') {
      await toggle.click();
    }

    const textarea = page.getByTestId('agent-instructions-textarea');
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveValue(customSystemPrompt);

    await page.waitForTimeout(400);
    const countAfterDrawer = tracker.getSessionCallCount();
    expect(countAfterDrawer - countBeforeDrawer).toBe(0);
    expect(countAfterDrawer).toBeLessThanOrEqual(3);

    await unclipForFullPage(page);

    const shot = resolve(SCREENSHOT_DIR, 'tablet-768x1024.png');
    await page.screenshot({ path: shot, fullPage: true });
  });

  test('04: 390x844 Mobile - Responsive stacked drawer with custom instructions', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const tracker = await setupPageMocks(page);

    await page.goto('/workspaces/settings/agents');
    await applyTheme(page, 'light');

    await expect(page.getByTestId('agent-studio-page')).toBeVisible();

    const countBeforeDrawer = tracker.getSessionCallCount();

    // Open Edit Drawer for reality-checker
    await page.getByTestId('edit-agent-btn-agent-01').click();
    await expect(page.getByTestId('agent-editor-drawer')).toBeVisible();

    // Expand Advanced Section
    const toggle = page.getByTestId('advanced-model-harness-config-toggle');
    const isExpanded = await toggle.getAttribute('aria-expanded');
    if (isExpanded !== 'true') {
      await toggle.click();
    }

    const textarea = page.getByTestId('agent-instructions-textarea');
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveValue(customSystemPrompt);

    await page.waitForTimeout(400);
    const countAfterDrawer = tracker.getSessionCallCount();
    expect(countAfterDrawer - countBeforeDrawer).toBe(0);
    expect(countAfterDrawer).toBeLessThanOrEqual(3);

    await unclipForFullPage(page);

    const shot = resolve(SCREENSHOT_DIR, 'mobile-390x844.png');
    await page.screenshot({ path: shot, fullPage: true });
  });
});
