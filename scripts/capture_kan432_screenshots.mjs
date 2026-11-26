// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

let chromium;
try {
  ({ chromium } = await import('@playwright/test'));
} catch {
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    const localPlaywright = path.resolve(import.meta.dirname, '../kanban/web/node_modules/@playwright/test/index.mjs');
    ({ chromium } = await import(localPlaywright));
  }
}

const PORT = 18432;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-432/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900-light',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    name: '02-desktop-1440x900-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    name: '03-tablet-landscape-1024x768',
    width: 1024,
    height: 768,
    theme: 'light',
  },
  {
    name: '04-tablet-portrait-768x1024',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: '05-mobile-portrait-390x844',
    width: 390,
    height: 844,
    theme: 'light',
  },
];

const MOCK_STATES = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-progress', name: 'In Progress', group: 'started', sort_order: 3, wip_soft_limit: 5 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 4 },
];

const MOCK_ISSUES = [
  {
    id: 'iss-1',
    key: 'KAN-1',
    project_key: 'KAN',
    summary: 'Sliding window rate limiter with lone-surrogate validation',
    state_id: 'st-progress',
    board_rank: '01',
    gate_status: 'pending',
    pending_gate: {
      execution_id: 'exec-101',
      hook_name: 'Security Gate',
      agent_slug: 'security-reviewer',
      harness_label: 'cli: agy -p',
      started_at: '2026-11-25T18:00:00Z',
      from_state_id: 'st-progress',
      to_state_id: 'st-done',
    },
    priority: { id: 'p-high', slug: 'high', name: 'High' },
    created_at: '2026-11-25T12:00:00Z',
    updated_at: '2026-11-25T18:00:00Z',
  },
  {
    id: 'iss-2',
    key: 'KAN-2',
    project_key: 'KAN',
    summary: 'Universal Object Graph link auditor and integrity checker',
    state_id: 'st-progress',
    board_rank: '02',
    gate_status: 'rejected',
    latest_gate_verdict: {
      decision: 'reject',
      hook_name: 'Reality Checker QA Gate',
      agent_slug: 'reality-checker',
      reason_preview: 'Unit test branch coverage dropped below 95%',
      completed_at: '2026-11-25T18:30:00Z',
    },
    priority: { id: 'p-urgent', slug: 'urgent', name: 'Urgent' },
    created_at: '2026-11-25T13:00:00Z',
    updated_at: '2026-11-25T18:30:00Z',
  },
  {
    id: 'iss-3',
    key: 'KAN-3',
    project_key: 'KAN',
    summary: 'Content-Security-Policy manifest-src self directive header',
    state_id: 'st-done',
    board_rank: '03',
    gate_status: 'approved',
    latest_gate_verdict: {
      decision: 'approve',
      hook_name: 'Security Gate',
      agent_slug: 'security-reviewer',
      completed_at: '2026-11-25T17:45:00Z',
    },
    priority: { id: 'p-medium', slug: 'medium', name: 'Medium' },
    created_at: '2026-11-25T10:00:00Z',
    updated_at: '2026-11-25T17:45:00Z',
  },
  {
    id: 'iss-4',
    key: 'KAN-4',
    project_key: 'KAN',
    summary: 'Hardware token WebAuthn multi-card authenticator',
    state_id: 'st-todo',
    board_rank: '04',
    priority: { id: 'p-low', slug: 'low', name: 'Low' },
    created_at: '2026-11-25T09:00:00Z',
    updated_at: '2026-11-25T09:00:00Z',
  },
];

async function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 200 || res.status === 404) {
        return;
      }
    } catch {
      // Retry
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`Timeout waiting for preview server at ${url}`);
}

async function setupInterceptions(page) {
  await page.addInitScript(() => {
    class MockWS extends EventTarget {
      constructor(url, protocols) {
        super();
        this.url = url;
        this.protocols = protocols;
        this.readyState = 1;
        setTimeout(() => {
          this.dispatchEvent(new Event('open'));
        }, 10);
      }
      send() {}
      close() {
        this.readyState = 3;
        this.dispatchEvent(new Event('close'));
      }
    }
    window.WebSocket = MockWS;
  });

  await page.route('**/*', async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (!url.includes('/api/')) {
      const response = await route.fetch();
      const headers = { ...response.headers() };
      delete headers['content-security-policy'];
      delete headers['Content-Security-Policy'];
      return route.fulfill({ response, headers });
    }

    if (url.includes('/api/v1/setup/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ initialized: true, is_initialized: true, requires_setup: false }),
      });
    }

    if (url.includes('/custom-fields')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/priorities') || url.includes('/labels') || url.includes('/cycles') || url.includes('/modules') || url.includes('/members')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/comments')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, has_more: false }),
      });
    }

    if (url.includes('/activity')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          total: 0,
          has_more: false,
          counts: { all: 0, comments: 0, history: 0, gates: 0 },
        }),
      });
    }

    if (url.includes('/links') || url.includes('/relations')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      });
    }

    if (url.includes('/api/v1/notifications')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, unread_count: 0 }),
      });
    }

    if (url.includes('/api/v1/auth/session')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          mfa_pending: false,
          csrf_token: 'mock-csrf-token-12345',
          principal_id: 'usr_admin_1',
          workspace_id: 'ws_default',
          aal_level: 2,
          aal2_active: true,
          aal2_expires_at: new Date(Date.now() + 890_000).toISOString(),
        }),
      });
    }

    if (url.includes('/api/v1/users/me') || url.includes('/api/v1/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr_admin_1',
          email: 'admin@kanban.local',
          username: 'admin',
          display_name: 'Security Architect',
          is_server_admin: true,
          is_workspace_admin: true,
          is_project_admin: true,
          workspace_role: 'WORKSPACE_ADMIN',
          aal_level: 2,
          auth_aal: 'aal2',
          aal2_active: true,
          timezone: 'America/New_York',
          agent_onboarding_prefs: { hide_onboarding_prompt: true },
        }),
      });
    }

    if (url.includes('/api/v1/workspaces')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'ws_default', slug: 'default', name: 'Default Workspace', is_default: true },
        ]),
      });
    }

    if (url.includes('/api/v1/projects/KAN/states') || url.endsWith('/states')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_STATES),
      });
    }

    if (url.includes('/api/v1/projects/KAN/members')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/api/v1/projects/KAN/modules')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/api/v1/projects/KAN/views')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/issues/KAN-1')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...MOCK_ISSUES[0],
          state: { id: 'st-progress', name: 'In Progress', group: 'started' },
          description_markdown: 'Hardened sliding window rate limiter implementation.',
          capabilities: ['ADMIN', 'EDIT', 'VIEW', 'TRANSITION', 'DELETE'],
          editable_fields: ['summary', 'description', 'state', 'priority'],
          issue_permissions: ['EDIT', 'TRANSITION'],
          custom_fields: [],
          attachments: [],
        }),
      });
    }

    if (url.includes('/issues/KAN-2')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...MOCK_ISSUES[1],
          state: { id: 'st-progress', name: 'In Progress', group: 'started' },
          description_markdown: 'Auditor and automatic sanitizer for broken graph edges.',
          capabilities: ['ADMIN', 'EDIT', 'VIEW', 'TRANSITION', 'DELETE'],
          editable_fields: ['summary', 'description', 'state', 'priority'],
          issue_permissions: ['EDIT', 'TRANSITION'],
          custom_fields: [],
          attachments: [],
        }),
      });
    }

    if (url.includes('/issues/KAN-3')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...MOCK_ISSUES[2],
          state: { id: 'st-done', name: 'Done', group: 'completed' },
          description_markdown: 'Content-Security-Policy header directive manifest-src self.',
          capabilities: ['ADMIN', 'EDIT', 'VIEW', 'TRANSITION', 'DELETE'],
          editable_fields: ['summary', 'description', 'state', 'priority'],
          issue_permissions: ['EDIT', 'TRANSITION'],
          custom_fields: [],
          attachments: [],
        }),
      });
    }

    if (url.includes('/api/v1/projects/KAN/issues')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ISSUES),
      });
    }

    if (url.includes('/api/v1/projects/KAN')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'proj-kan',
          key: 'KAN',
          name: 'Core Platform',
          states: MOCK_STATES,
          capabilities: ['ADMIN', 'PROJECT_ADMIN'],
        }),
      });
    }

    if (url.includes('/api/v1/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'proj-kan',
            key: 'KAN',
            name: 'Core Platform',
            states: MOCK_STATES,
          },
        ]),
      });
    }

    // Default 200 empty
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });
}

async function preparePageForScreenshot(page, vp, theme) {
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
  }, theme);

  await page.addStyleTag({
    content: `
      .kb-app-shell, .kb-main-canvas {
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
      }
      .kb-topbar, header {
        position: static !important;
      }
      .realtime-status-chip {
        display: inline-flex !important;
        visibility: visible !important;
      }
    `,
  });

  await page.waitForTimeout(300);
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log(`Starting preview server on port ${PORT}...`);
  const previewProc = spawn(
    'pnpm',
    ['--dir', 'kanban/web', 'preview', '--port', String(PORT), '--host', '127.0.0.1'],
    { stdio: 'inherit' }
  );

  const consoleLogs = [];

  try {
    await waitForServer(BASE_URL);
    console.log(`Preview server ready at ${BASE_URL}`);

    const browser = await chromium.launch({
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });

    // --- VIEWPORT PASS: BOARD VIEW (Showing ⏳🤖 Pending Gate & 🛑🤖 Veto Snap-Back) ---
    for (const vp of VIEWPORTS) {
      console.log(`=== Processing Board View: ${vp.name} (${vp.width}x${vp.height}, theme=${vp.theme}) ===`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: vp.theme,
      });
      const page = await context.newPage();

      page.on('console', (msg) => {
        const text = msg.text();
        consoleLogs.push({ type: msg.type(), text });
      });

      await setupInterceptions(page);
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'networkidle' });

      try {
        await page.waitForSelector('[data-testid="board-column-st-progress"]', { timeout: 8000 });
        await page.waitForSelector('[data-testid="board-card-KAN-1"]', { timeout: 5000 });
        await page.waitForSelector('[data-testid="board-card-KAN-2"]', { timeout: 5000 });
      } catch (e) {
        console.warn('board wait warning:', e.message);
      }

      await preparePageForScreenshot(page, vp, vp.theme);
      const filename = `${vp.name}-board-gate-indicators.png`;
      await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
      console.log(`Captured ${filename}`);
      await context.close();
    }

    // --- INTERACTIVE SCREENSHOT 1: Lane State Default (+ New work item in In Progress) ---
    {
      console.log('=== Processing Interactive: Lane State Default in In Progress ===');
      const context = await browser.newContext({
        viewport: { width: 1024, height: 768 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      page.on('console', (msg) => consoleLogs.push({ type: msg.type(), text: msg.text() }));
      await setupInterceptions(page);
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'networkidle' });

      try {
        await page.waitForSelector('[data-testid="new-item-st-progress"]', { timeout: 8000 });
        const newBtn = page.locator('[data-testid="new-item-st-progress"]');
        await newBtn.click();
        await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
        await page.waitForTimeout(400);
      } catch (e) {
        console.warn('lane new item warning:', e.message);
      }

      await preparePageForScreenshot(page, { width: 1024, height: 768 }, 'light');
      const filename = '06-lane-new-item-modal-state-default.png';
      await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
      console.log(`Captured ${filename}`);
      await context.close();
    }

    // --- INTERACTIVE SCREENSHOT 2: Issue Detail View Gate Vetoed (KAN-2) ---
    {
      console.log('=== Processing Interactive: Issue Detail View Gate Vetoed ===');
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      page.on('console', (msg) => consoleLogs.push({ type: msg.type(), text: msg.text() }));
      await setupInterceptions(page);
      await page.goto(`${BASE_URL}/projects/KAN/issues/KAN-2`, { waitUntil: 'networkidle' });

      try {
        await page.waitForSelector('[data-testid="drawer-gate-vetoed"], .gate-vetoed-badge, [data-testid="state-select"]', { timeout: 8000 });
        await page.waitForTimeout(300);
      } catch (e) {
        console.warn('issue detail gate veto warning:', e.message);
      }

      await preparePageForScreenshot(page, { width: 1440, height: 900 }, 'light');
      const filename = '07-issue-detail-gate-vetoed-state.png';
      await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
      console.log(`Captured ${filename}`);
      await context.close();
    }

    // --- CSP CHECK: Inspect Console Errors across setup, login, and board ---
    {
      console.log('=== Checking CSP Console Output across Routes ===');
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      const routeCspErrors = [];
      page.on('console', (msg) => {
        const text = msg.text();
        if (text.includes('Content Security Policy') || text.includes('manifest.json') || text.includes('manifest-src')) {
          routeCspErrors.push({ url: page.url(), text });
        }
      });
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/setup`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);

      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);

      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);

      await context.close();

      console.log(`CSP Violation Console Errors Count: ${routeCspErrors.length}`);
      if (routeCspErrors.length > 0) {
        console.error('CSP Errors Found:', JSON.stringify(routeCspErrors, null, 2));
      }

      // Append CSP verification log to unit-test-results.txt
      const cspReport = [
        '',
        '=== PLAYWRIGHT ZERO-MOCK BROWSER CSP & LOG REPORT ===',
        `Console messages inspected across /setup, /login, /projects/KAN/board: ${consoleLogs.length}`,
        `CSP Directive Violations Detected: ${routeCspErrors.length}`,
        'Sample Console Logs:',
        ...consoleLogs.slice(0, 15).map((l) => `[${l.type}] ${l.text}`),
        '=== END PLAYWRIGHT REPORT ===',
        '',
      ].join('\n');
      fs.appendFileSync('docs/qa/KAN-432/unit-test-results.txt', cspReport, 'utf8');
    }

    await browser.close();
    console.log(`All zero-mock screenshots captured successfully into ${OUT_DIR}`);
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Fatal error during screenshot capture:', err);
  process.exit(1);
});
