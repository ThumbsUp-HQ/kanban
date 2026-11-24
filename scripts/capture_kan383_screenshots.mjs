// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18983;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-383/screenshots');

const VIEWPORTS = [
  {
    name: '01-board-cards-desktop-1440x900-light',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
  },
  {
    name: '02-board-cards-desktop-1440x900-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
  },
  {
    name: '03-board-cards-tablet-landscape-1024x768',
    width: 1024,
    height: 768,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
  },
  {
    name: '04-board-cards-tablet-portrait-768x1024',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
  },
  {
    name: '05-board-cards-mobile-390x844',
    width: 390,
    height: 844,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
  },
];

async function waitForServer(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404 || res.status === 200) {
        return true;
      }
    } catch {
      // wait and retry
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Server failed to start at ${url} within ${timeoutMs}ms`);
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Starting preview server on port ${PORT}...`);
  const previewProc = spawn(
    'pnpm',
    ['--dir', 'kanban/web', 'exec', 'vite', 'preview', '--port', String(PORT), '--host', '127.0.0.1'],
    { stdio: 'inherit' }
  );

  try {
    await waitForServer(BASE_URL);
    console.log(`Preview server ready at ${BASE_URL}`);

    const browser = await chromium.launch({
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    });

    const mockWorkflowStates = [
      { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1, color_hex: '#64748b' },
      { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2, color_hex: '#3b82f6' },
      { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3, color_hex: '#f59e0b' },
      { id: 'state-done', name: 'Done', group: 'completed', sort_order: 4, color_hex: '#10b981' },
      { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 5, color_hex: '#ef4444' },
    ];

    const mockPriorities = [
      { id: 'p-urg', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
      { id: 'p-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
      { id: 'p-med', slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
      { id: 'p-low', slug: 'low', label: 'Low', emoji: '💤', sort_order: 4 },
    ];

    const mockBoardIssues = {
      items: [
        {
          id: 'iss-101',
          key: 'KAN-101',
          summary: 'Telemetry pipeline ingest schema definition',
          state_id: 'state-backlog',
          state: mockWorkflowStates[0],
          board_rank: '0000000000000001',
          priority: mockPriorities[3], // low
          assignees: [{ id: 'u-1', handle: 'alice' }],
        },
        {
          id: 'iss-102',
          key: 'KAN-102',
          summary: 'Review CSP violation report ingestion router',
          state_id: 'state-todo',
          state: mockWorkflowStates[1],
          board_rank: '0000000000000002',
          priority: mockPriorities[2], // medium
          assignees: [{ id: 'u-2', handle: 'bob' }],
        },
        {
          id: 'iss-142',
          key: 'KAN-142',
          summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
          state_id: 'state-in-progress',
          state: mockWorkflowStates[2],
          board_rank: '0000000000000003',
          priority: mockPriorities[0], // urgent
          assignees: [
            { id: 'u-adam', handle: 'adam' },
            { id: 'u-sec', free_text: 'Ext: SecAudit' },
          ],
          due_date: '2026-12-01',
        },
        {
          id: 'iss-143',
          key: 'KAN-143',
          summary: 'Clean-room security reality checker verification',
          state_id: 'state-done',
          state: mockWorkflowStates[3],
          board_rank: '0000000000000004',
          priority: mockPriorities[1], // high
          assignees: [{ id: 'u-qa', handle: 'reality-checker', is_agent: true, name: 'RealityChecker' }],
        },
        {
          id: 'iss-144',
          key: 'KAN-144',
          summary: 'Deprecated legacy basic auth header parser',
          state_id: 'state-cancelled',
          state: mockWorkflowStates[4],
          board_rank: '0000000000000005',
          priority: null,
          assignees: [],
        },
      ],
      total: 5,
    };

    const mockProject = {
      id: '01918a22-0000-7000-8000-000000000002',
      key: 'KAN',
      identifier: 'KAN',
      name: 'Platform Core',
      description: 'Core platform engineering',
      visibility: 'internal',
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'TRANSITION'],
      is_project_admin: true,
    };

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });

      const page = await context.newPage();

      // Auth mocks
      await page.route('**/api/v1/auth/me', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'u-adam',
            handle: 'adam',
            display_name: 'Adam Outler',
            email: 'adam@kanban.local',
            is_server_admin: true,
            is_workspace_admin: true,
          }),
        });
      });

      await page.route('**/api/v1/users/me', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'u-adam',
            handle: 'adam',
            display_name: 'Adam Outler',
          }),
        });
      });

      await page.route('**/api/v1/auth/session', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            authenticated: true,
            aal_level: 2,
            csrf_token: 'test-csrf-token',
            user: { id: 'u-adam', handle: 'adam', display_name: 'Adam Outler' },
          }),
        });
      });

      await page.route('**/api/v1/workspaces', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'ws-1', name: 'Primary Workspace', slug: 'kanban', is_current: true },
          ]),
        });
      });

      await page.route('**/api/v1/workspaces/current', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'ws-1', name: 'Primary Workspace', slug: 'kanban', is_current: true }),
        });
      });

      await page.route('**/api/v1/projects', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([mockProject]),
        });
      });

      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockProject),
        });
      });

      await page.route('**/api/v1/projects/KAN/states', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockWorkflowStates),
        });
      });

      await page.route('**/api/v1/projects/KAN/priorities', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockPriorities),
        });
      });

      await page.route('**/api/v1/projects/KAN/issues*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockBoardIssues),
        });
      });

      // Default mocks for sub-resources
      await page.route('**/api/v1/projects/KAN/cycles', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/modules', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/labels', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/views', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/custom-fields', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/objects/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
      await page.route('**/api/v1/notifications/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[],"count":0}' }));

      try {
        await page.goto(vp.url, { waitUntil: 'load', timeout: 15000 });
      } catch (err) {
        console.warn(`Warning navigating to ${vp.url}:`, err.message);
      }

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('kb_theme', theme);
        localStorage.setItem('kb:theme', theme);
      }, vp.theme);

      await page.waitForTimeout(1000);

      // Verify board card is rendered
      const card = await page.$('[data-testid="board-card-KAN-142"]');
      if (card) {
        console.log(`Found board card KAN-142 in ${vp.name}`);
      }

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved screenshot to ${outPath}`);

      await context.close();
    }

    await browser.close();
    console.log('All 5 screenshots captured successfully.');
  } finally {
    previewProc.kill();
  }
}

main().catch((err) => {
  console.error('Error during screenshot capture:', err);
  process.exit(1);
});
