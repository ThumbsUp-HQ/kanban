// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18990;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-360/screenshots');

const VIEWPORTS = [
  {
    name: '1440x900-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
    action: async (page) => {
      await page.waitForTimeout(1000);
    },
  },
  {
    name: '1440x900-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=board&peek=KAN-360`,
    action: async (page) => {
      await page.waitForTimeout(1200);
    },
  },
  {
    name: '768x1024-tablet',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
    action: async (page) => {
      await page.waitForTimeout(1000);
    },
  },
  {
    name: '390x844-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board&peek=KAN-360`,
    action: async (page) => {
      await page.waitForTimeout(1000);
    },
  },
  {
    name: '844x390-mobile-landscape',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
    action: async (page) => {
      await page.waitForTimeout(1000);
    },
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

    const mockIssue = {
      id: 'iss-360',
      key: 'KAN-360',
      identifier: 'KAN-360',
      title: 'Comprehensive CSS prefers-reduced-motion Transitions, Flashes, and Particle Animation Clamping',
      description: 'Enforce comprehensive animation and transition clamping under prefers-reduced-motion: reduce across base.css, drawer slide-overs, board drops, and sparkle caret pulses.',
      state_id: 'st-inprog',
      priority: 'urgent',
      project_id: 'p-kan',
      created_at: '2026-11-23T08:00:00Z',
      updated_at: '2026-11-23T08:00:00Z',
      creator: { id: 'u-admin', display_name: 'Administrator', handle: 'admin' },
      assignees: [{ id: 'u-admin', display_name: 'Administrator', handle: 'admin' }],
      labels: [{ id: 'lb-feat', name: 'a11y', color: '#3b82f6' }],
    };

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
        reducedMotion: 'reduce',
      });

      const page = await context.newPage();

      // Intercept auth
      await page.route('**/api/v1/auth/me', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'u-admin',
            handle: 'admin',
            display_name: 'Administrator',
            email: 'admin@kanban.local',
            is_server_admin: true,
            is_workspace_admin: true,
          }),
        });
      });
      await page.route('**/api/v1/user/me', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'u-admin',
            handle: 'admin',
            display_name: 'Administrator',
            email: 'admin@kanban.local',
            is_server_admin: true,
            is_workspace_admin: true,
          }),
        });
      });

      // Project mock endpoints
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'p-kan',
            key: 'KAN',
            name: 'Core Platform',
            description: 'Primary platform repository',
            visibility: 'internal',
            archived: false,
          }),
        });
      });
      await page.route('**/api/v1/projects/KAN/states', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'st-backlog', name: 'Backlog', category: 'backlog', color: '#64748b', sort_rank: '0', soft_wip_limit: null, hard_wip_limit: null },
            { id: 'st-todo', name: 'Todo', category: 'unstarted', color: '#3b82f6', sort_rank: '1', soft_wip_limit: null, hard_wip_limit: null },
            { id: 'st-inprog', name: 'In Progress', category: 'started', color: '#eab308', sort_rank: '2', soft_wip_limit: 5, hard_wip_limit: 10 },
            { id: 'st-done', name: 'Done', category: 'completed', color: '#22c55e', sort_rank: '3', soft_wip_limit: null, hard_wip_limit: null },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/priorities', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'pr-low', level: 1, name: 'Low', color: '#94a3b8', sort_order: 1 },
            { id: 'pr-med', level: 2, name: 'Medium', color: '#3b82f6', sort_order: 2 },
            { id: 'pr-high', level: 3, name: 'High', color: '#f97316', sort_order: 3 },
            { id: 'pr-crit', level: 4, name: 'Urgent', color: '#ef4444', sort_order: 4 },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/labels', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'lb-feat', name: 'a11y', color: '#3b82f6', exclusive_group: 'kind' },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/members', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'pm-1', user_id: 'u-admin', user: { id: 'u-admin', display_name: 'Administrator', handle: 'admin' }, role: 'admin' },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/modules', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/trash', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/workflow-hooks', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/custom-fields', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));

      // Issues mocks
      await page.route('**/api/v1/projects/KAN/issues*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [mockIssue],
            total: 1,
            page: 1,
            size: 50,
          }),
        });
      });
      await page.route('**/api/v1/issues/KAN-360*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockIssue),
        });
      });
      await page.route('**/api/v1/issues/iss-360*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockIssue),
        });
      });

      try {
        await page.goto(vp.url, { waitUntil: 'load', timeout: 15000 });
      } catch (err) {
        console.warn(`Warning navigating to ${vp.url}:`, err.message);
      }

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, vp.theme);

      if (vp.action) {
        try {
          await vp.action(page);
        } catch (e) {
          console.warn(`Action failed for ${vp.name}:`, e.message);
        }
      }

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);
      await context.close();
    }

    await browser.close();
    console.log('Playwright screenshot capture completed successfully.');
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Fatal error during screenshot capture:', err);
  process.exit(1);
});
