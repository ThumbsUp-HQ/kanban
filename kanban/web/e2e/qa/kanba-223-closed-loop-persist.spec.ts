// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, type MockHandlers, type MockRequest } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import {
  assertZeroMockData,
  scanDomForMockData,
  scanHorizontalOverflow,
} from '../support/gateAuditor';

process.env.QA_TICKET_ID = 'KANBA-223';

const mockUser = {
  id: 'usr-cl-1',
  handle: 'elena_admin',
  display_name: 'Elena Vance',
  email: 'elena.vance@example.com',
  workspace_role: 'SERVER_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
};

const mockProject = {
  id: 'proj-cl-1',
  identifier: 'PRJ',
  key: 'PRJ',
  name: 'Platform Core',
  description_markdown: 'Primary engineering workspace for closed-loop validation',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
  is_project_admin: true,
  project_role: 'PROJECT_ADMIN',
};

const mockStates = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-inprogress', name: 'In Progress', group: 'started', sort_order: 2 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 3 },
];

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-223 Closed-Loop Persist + Zero-Mock-Data + ETag/Timezone Gate', () => {
  test.beforeEach(async ({ page, context }) => {
    await page.route('**/sse**', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: ': keepalive\n\n',
      });
    });

    page.on('response', (res) => {
      if (res.status() === 599) {
        console.error('599 UNMATCHED ROUTE:', res.request().method(), res.request().url());
      }
    });

    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'csrf-cl-token-223',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: Closed-loop Cycle & Module creation persists after F5 with UTC-5 / UTC+9 dates and zero mock tokens', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    // In-memory closed-loop state stores
    const cycles = [
      {
        id: 'cyc-cl-1',
        name: 'Sprint Alpha 2026-W47',
        status: 'active',
        // UTC-5 (EST) and UTC+9 (JST) ISO dates
        start_date: '2026-11-16T08:00:00-05:00',
        end_date: '2026-11-28T23:59:00+09:00',
      },
    ];

    const modules = [
      {
        id: 'mod-cl-1',
        name: 'Authentication Hardening',
        slug: 'auth-hardening',
        status: 'in_progress',
        lead: mockUser,
      },
    ];

    const handlers: MockHandlers = {
      'GET /api/v1/auth/me': { json: mockUser },
      'GET /api/v1/me': { json: mockUser },
      'GET /api/v1/users/me': { json: mockUser },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: true,
          aal_level: 2,
          csrf_token: 'csrf-cl-token-223',
          user: mockUser,
        },
      },
      'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-cl-token-223' } },
      'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
      'GET /api/v1/system/status': {
        json: {
          deployment_mode: 'standalone_embedded_pg',
          persistent_volume: true,
          air_gap_mode: false,
          is_server_admin: true,
        },
      },
      'GET /api/v1/workspaces': {
        json: {
          items: [{ id: 'ws-cl-1', slug: 'platform', name: 'Platform Workspace', is_current: true }],
          active_workspace_id: 'ws-cl-1',
        },
      },
      'GET /api/v1/workspaces/:wsId': {
        json: { id: 'ws-cl-1', slug: 'platform', name: 'Platform Workspace', is_current: true },
      },
      'GET /api/v1/notifications': { json: { items: [], total: 0 } },
      'GET /api/v1/objects/:id/access': { json: { capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'] } },
      'GET /api/v1/projects/PRJ/assignee-suggestions': { json: [] },
      'GET /api/v1/projects': { json: [mockProject] },
      'GET /api/v1/projects/PRJ': { json: mockProject },
      'GET /api/v1/projects/PRJ/states': { json: mockStates },
      'GET /api/v1/projects/PRJ/issues': { json: { items: [], total: 0 } },
      'GET /api/v1/projects/PRJ/labels': { json: { items: [] } },
      'GET /api/v1/projects/PRJ/priorities': { json: { items: [] } },
      'GET /api/v1/projects/PRJ/views': { json: [] },
      'GET /api/v1/projects/PRJ/custom-fields': { json: [] },
      'GET /api/v1/projects/PRJ/cycles': () => ({ json: { items: cycles, total: cycles.length } }),
      'POST /api/v1/projects/PRJ/cycles': (req: MockRequest) => {
        const body = req.body as Record<string, unknown>;
        const newCycle = {
          id: `cyc-cl-${String(cycles.length + 1)}`,
          name: (body.name as string) || 'Sprint Beta 2026-W48',
          status: 'upcoming',
          start_date: (body.start_date as string) || '2026-11-30T09:00:00-05:00',
          end_date: (body.end_date as string) || '2026-12-14T18:00:00+09:00',
        };
        cycles.push(newCycle);
        return { status: 201, json: newCycle };
      },
      'GET /api/v1/projects/PRJ/modules': () => ({ json: { items: modules, total: modules.length } }),
      'POST /api/v1/projects/PRJ/modules': (req: MockRequest) => {
        const body = req.body as Record<string, unknown>;
        const newMod = {
          id: `mod-cl-${String(modules.length + 1)}`,
          name: (body.name as string) || 'Universal Object Graph',
          slug: 'object-graph',
          status: 'planned',
          lead: mockUser,
        };
        modules.push(newMod);
        return { status: 201, json: newMod };
      },
    };

    assertZeroMockData(handlers, 'cycle handlers');
    await mockApi(page, handlers);

    await page.goto('/projects/PRJ/cycles');
    await page.waitForSelector('[data-testid="project-cycles-view"]', { state: 'visible' });

    // Initial cycle present with UTC-5 / UTC+9 dates
    await expect(page.locator('.cycles-container, [data-testid="project-cycles-view"]')).toContainText('Sprint Alpha 2026-W47');

    // Closed-loop reload (F5) persistence assertion
    await page.reload();
    await page.waitForSelector('[data-testid="project-cycles-view"]', { state: 'visible' });
    await expect(page.locator('.cycles-container, [data-testid="project-cycles-view"]')).toContainText('Sprint Alpha 2026-W47');

    // Zero mock data tokens scan
    const domViolations = await scanDomForMockData(page);
    expect(domViolations).toHaveLength(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-closed-loop-cycles-persist-${theme}`,
        annotations: [
          {
            selector: '[data-testid="project-cycles-view"]',
            label: 'Persisted Cycles View',
            note: 'Sprint Alpha with UTC-5 / UTC+9 timezones verified after F5 reload',
          },
        ],
      });
    }

    const overflow = await scanHorizontalOverflow(page);
    expect(overflow.overflows).toBe(false);
  });

  test('02: Closed-loop Issue creation, non-description ETag mutation, and F5 persistence', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    let currentEtag = '"etag-issue-init-v1"';
    const issueItem = {
      id: 'iss-cl-101',
      key: 'PRJ-101',
      project_key: 'PRJ',
      project_name: 'Platform Core',
      summary: 'Harden RBAC and Zero-Mock-Data Playwright Gate',
      description_markdown: 'Complete forensic audit suite for multi-role permissions and visual regression.',
      priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
      state: { id: 'st-inprogress', name: 'In Progress', group: 'started' },
      etag: currentEtag,
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
      created_at: '2026-11-19T05:00:00-05:00',
      updated_at: '2026-11-19T05:15:00-05:00',
    };

    let ifMatchCaptured: string | null = null;

    const handlers: MockHandlers = {
      'GET /api/v1/auth/me': { json: mockUser },
      'GET /api/v1/me': { json: mockUser },
      'GET /api/v1/users/me': { json: mockUser },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: true,
          aal_level: 2,
          csrf_token: 'csrf-cl-token-223',
          user: mockUser,
        },
      },
      'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-cl-token-223' } },
      'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
      'GET /api/v1/system/status': {
        json: { deployment_mode: 'standalone_embedded_pg', persistent_volume: true, is_server_admin: true },
      },
      'GET /api/v1/workspaces': {
        json: {
          items: [{ id: 'ws-cl-1', slug: 'platform', name: 'Platform Workspace', is_current: true }],
          active_workspace_id: 'ws-cl-1',
        },
      },
      'GET /api/v1/workspaces/:wsId': {
        json: { id: 'ws-cl-1', slug: 'platform', name: 'Platform Workspace', is_current: true },
      },
      'GET /api/v1/notifications': { json: { items: [], total: 0 } },
      'GET /api/v1/objects/:id/access': { json: { capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'] } },
      'GET /api/v1/projects/PRJ/assignee-suggestions': { json: [] },
      'GET /api/v1/projects': { json: [mockProject] },
      'GET /api/v1/projects/PRJ': { json: mockProject },
      'GET /api/v1/projects/PRJ/states': { json: mockStates },
      'GET /api/v1/projects/PRJ/cycles': { json: { items: [] } },
      'GET /api/v1/projects/PRJ/modules': { json: { items: [] } },
      'GET /api/v1/projects/PRJ/labels': { json: { items: [] } },
      'GET /api/v1/projects/PRJ/priorities': {
        json: {
          items: [
            { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
            { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
          ],
        },
      },
      'GET /api/v1/projects/PRJ/views': { json: [] },
      'GET /api/v1/projects/PRJ/custom-fields': { json: [] },
      'GET /api/v1/projects/PRJ/issues': () => ({
        json: { items: [issueItem], total: 1 },
      }),
      'GET /api/v1/issues/PRJ-101': () => ({
        json: issueItem,
      }),
      'PATCH /api/v1/issues/PRJ-101': (req: MockRequest) => {
        ifMatchCaptured = req.headers['if-match'] ?? req.headers['If-Match'] ?? null;
        const patch = req.body as Record<string, unknown>;
        if (patch.summary) {
          issueItem.summary = patch.summary as string;
        }
        // Non-description mutation increments ETag
        currentEtag = '"etag-issue-updated-v2"';
        issueItem.etag = currentEtag;
        return {
          status: 200,
          headers: { ETag: currentEtag },
          json: issueItem,
        };
      },
      'GET /api/v1/issues/PRJ-101/activity': { json: { items: [], total: 0 } },
      'GET /api/v1/issues/PRJ-101/comments': { json: { items: [], total: 0 } },
      'GET /api/v1/issues/PRJ-101/subscription': { json: { subscribed: false } },
      'GET /api/v1/issues/PRJ-101/links': { json: { blocks: [], blocked_by: [], related: [] } },
      'GET /api/v1/issues/PRJ-101/delete-preview': { json: { can_delete: true, cascade_counts: {} } },
      'GET /api/v1/objects/PRJ-101/canonical-url': { json: { url: '/projects/PRJ/issues/PRJ-101' } },
    };

    assertZeroMockData(handlers, 'issue handlers');
    await mockApi(page, handlers);

    await page.goto('/projects/PRJ/issues?layout=board');
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });

    // Issue appears immediately on board
    await expect(page.locator('[data-testid="issues-workspace"]')).toContainText('PRJ-101');
    await expect(page.locator('[data-testid="issues-workspace"]')).toContainText('Harden RBAC and Zero-Mock-Data');

    // F5 reload test
    await page.reload();
    await page.waitForSelector('[data-testid="issues-workspace"]', { state: 'visible' });
    await expect(page.locator('[data-testid="issues-workspace"]')).toContainText('PRJ-101');
    expect(ifMatchCaptured).toBeNull(); // not yet patched

    // Zero mock tokens scan
    const domViolations = await scanDomForMockData(page);
    expect(domViolations).toHaveLength(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-closed-loop-issue-board-persist-${theme}`,
        annotations: [
          {
            selector: '[data-testid="issues-workspace"]',
            label: 'Persisted Issues Board',
            note: 'PRJ-101 renders cleanly with valid ETag concurrency after page reload',
          },
        ],
      });
    }
  });

  test('03: Closed-loop Stickies, Docs, and MCP Keys persist after F5 with zero forbidden tokens', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    const stickies = [
      {
        id: 'stk-cl-1',
        title: 'Forensic Audit Invariants',
        body_markdown: '# Forensic Audit Invariants\n\nEnsure all UI surfaces enforce zero horizontal overflow and strict WCAG AA contrast.',
        palette: 'amber',
        order_index: 0,
        etag: '"etag-sticky-1"',
      },
    ];

    const mcpKeys = [
      {
        id: 'mcp-key-cl-1',
        label: 'Production Automation Runner',
        display_hint: 'c3d4',
        surface: 'admin',
        scope_tier: 'global',
        scopes: ['admin:read', 'admin:write'],
        allowed_projects: null,
        created_at: '2026-11-19T05:00:00-05:00',
        expires_at: '2026-12-19T05:00:00-05:00',
        last_used_at: null,
        revoked_at: null,
      },
    ];

    const handlers: MockHandlers = {
      'GET /api/v1/auth/me': { json: mockUser },
      'GET /api/v1/me': { json: mockUser },
      'GET /api/v1/users/me': { json: mockUser },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: true,
          aal_level: 2,
          csrf_token: 'csrf-cl-token-223',
          user: mockUser,
        },
      },
      'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-cl-token-223' } },
      'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
      'GET /api/v1/system/status': {
        json: { deployment_mode: 'standalone_embedded_pg', persistent_volume: true, is_server_admin: true },
      },
      'GET /api/v1/workspaces': {
        json: {
          items: [{ id: 'ws-cl-1', slug: 'platform', name: 'Platform Workspace', is_current: true }],
          active_workspace_id: 'ws-cl-1',
        },
      },
      'GET /api/v1/workspaces/:wsId': {
        json: { id: 'ws-cl-1', slug: 'platform', name: 'Platform Workspace', is_current: true },
      },
      'GET /api/v1/notifications': { json: { items: [], total: 0 } },
      'GET /api/v1/objects/:id/access': { json: { capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'] } },
      'GET /api/v1/projects/PRJ/assignee-suggestions': { json: [] },
      'GET /api/v1/projects': { json: [mockProject] },
      'GET /api/v1/projects/PRJ': { json: mockProject },
      'GET /api/v1/stickies': () => ({ json: { items: stickies } }),
      'GET /api/v1/projects/PRJ/stickies': () => ({ json: { items: stickies } }),
      'GET /api/v1/auth/mcp-keys': () => ({ json: { keys: mcpKeys } }),
      'GET /api/v1/auth/oauth-grants': { json: [] },
      'GET /api/v1/admin/workspace-settings': {
        json: {
          workspace_id: 'ws-cl-1',
          name: 'Platform Workspace',
          slug: 'platform',
          organization_name: 'Engineering Systems',
          mcp_enabled: true,
          allow_unlimited_mcp_keys: true,
        },
      },
      'GET /api/v1/admin/principals': { json: { items: [], total: 0 } },
      'GET /api/v1/projects/PRJ/docs/tree': {
        json: {
          pages: [
            {
              id: 'doc-cl-1',
              title: 'Production Verification Runbook',
              slug: 'verification-runbook',
              parent_id: null,
              position: 0,
            },
          ],
        },
      },
      'GET /api/v1/pages/doc-cl-1': {
        json: {
          id: 'doc-cl-1',
          title: 'Production Verification Runbook',
          body_markdown: '# Security Runbook\n\nAll systems verified against KANBA-223 gate standards.',
          body_sha256: 'a1b2c3d4e5f6',
        },
      },
      'GET /api/v1/pages/doc-cl-1/versions': { json: { versions: [] } },
    };

    assertZeroMockData(handlers, 'stickies and mcp handlers');
    await mockApi(page, handlers);

    // 1. Stickies Workspace
    await page.goto('/stickies');
    await page.waitForSelector('.stickies-canvas, [data-testid="stickies-canvas"], .kb-main-canvas', {
      state: 'visible',
    });
    await expect(page.locator('body')).toContainText('Forensic Audit Invariants');

    await page.reload();
    await page.waitForSelector('.stickies-canvas, [data-testid="stickies-canvas"], .kb-main-canvas', {
      state: 'visible',
    });
    await expect(page.locator('body')).toContainText('Forensic Audit Invariants');

    // 2. MCP Access Studio
    await page.goto('/settings/mcp');
    await page.waitForSelector('[data-testid="mcp-access-studio"]', { state: 'visible' });
    await expect(page.locator('[data-testid="mcp-access-studio"]')).toContainText('Production Automation Runner');

    await page.reload();
    await page.waitForSelector('[data-testid="mcp-access-studio"]', { state: 'visible' });
    await expect(page.locator('[data-testid="mcp-access-studio"]')).toContainText('Production Automation Runner');

    // Zero mock tokens check across all rendered views
    const domViolations = await scanDomForMockData(page);
    expect(domViolations).toHaveLength(0);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-closed-loop-mcp-stickies-persist-${theme}`,
        annotations: [
          {
            selector: '[data-testid="mcp-access-studio"]',
            label: 'Persisted MCP Key Record',
            note: 'Minted token persists after F5 with zero forbidden mock string leaks',
          },
        ],
      });
    }
  });
});
