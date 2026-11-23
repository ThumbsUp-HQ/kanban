// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18994;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-374/screenshots');

const VIEWPORTS = [
  {
    name: '1440x900-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
      if (await exportBtn.count() > 0) {
        await exportBtn.first().click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '1440x900-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
      if (await exportBtn.count() > 0) {
        await exportBtn.first().click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '768x1024-tablet',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
      if (await exportBtn.count() > 0) {
        await exportBtn.first().click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '390x844-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
      if (await exportBtn.count() > 0) {
        await exportBtn.first().click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '844x390-mobile-landscape',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const exportBtn = page.locator('[data-testid="navigator-export-btn"]');
      if (await exportBtn.count() > 0) {
        await exportBtn.first().click();
        await page.waitForTimeout(400);
      }
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

    const mockIssues = [
      {
        id: 'iss-374',
        key: 'KAN-374',
        identifier: 'KAN-374',
        summary: 'Consolidate Duplicate Search Bar Export Buttons into Single Export Button with 3 Options',
        description_markdown: 'Consolidated single Export dropdown with CSV, Password-Protected ZIP, and Report Template.',
        state: { id: 'st-inprog', name: 'In Progress', group: 'started', color_hex: '#3b82f6' },
        state_id: 'st-inprog',
        priority: { id: 'p-high', slug: 'high', label: 'High' },
        project_id: 'p-kan',
        created_at: '2026-11-23T08:00:00Z',
        updated_at: '2026-11-23T08:00:00Z',
        creator: { id: 'u-admin', display_name: 'Administrator', handle: 'admin' },
        assignees: [{ id: 'u-admin', display_name: 'Administrator', handle: 'admin', kind: 'principal', principal: { handle: 'admin', display_name: 'Administrator' } }],
        labels: [{ id: 'lb-feat', name: 'export', color: '#3b82f6' }],
      },
      {
        id: 'iss-373',
        key: 'KAN-373',
        identifier: 'KAN-373',
        summary: 'Replace WinZip Trademark Copy with Password-Protected ZIP (AES-256)',
        description_markdown: 'Trademark copy sanitization.',
        state: { id: 'st-todo', name: 'To Do', group: 'unstarted', color_hex: '#64748b' },
        state_id: 'st-todo',
        priority: { id: 'p-med', slug: 'medium', label: 'Medium' },
        project_id: 'p-kan',
        created_at: '2026-11-23T08:00:00Z',
        updated_at: '2026-11-23T08:00:00Z',
        creator: { id: 'u-admin', display_name: 'Administrator', handle: 'admin' },
        assignees: [],
        labels: [],
      },
    ];

    const mockStates = [
      { id: 'st-backlog', name: 'Backlog', group: 'backlog', color_hex: '#94a3b8' },
      { id: 'st-todo', name: 'To Do', group: 'unstarted', color_hex: '#64748b' },
      { id: 'st-inprog', name: 'In Progress', group: 'started', color_hex: '#3b82f6' },
      { id: 'st-done', name: 'Done', group: 'completed', color_hex: '#10b981' },
      { id: 'st-cancelled', name: 'Cancelled', group: 'cancelled', color_hex: '#ef4444' },
    ];

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
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

      // Intercept projects and workspaces
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'p-kan',
            key: 'KAN',
            name: 'Core Platform',
            description: 'Core platform issues board',
            visibility: 'internal',
            archived: false,
          }),
        });
      });
      await page.route('**/api/v1/projects/KAN/states', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockStates),
        });
      });
      await page.route('**/api/v1/projects/KAN/issues*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: mockIssues,
            total: mockIssues.length,
            next_cursor: null,
          }),
        });
      });
      await page.route('**/api/v1/projects/KAN/saved-views*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });
      await page.route('**/api/v1/workspaces*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'ws-1', slug: 'default', name: 'Default Workspace' },
          ]),
        });
      });

      await page.goto(vp.url, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1000);

      if (vp.theme === 'dark') {
        await page.evaluate(() => {
          document.documentElement.setAttribute('data-theme', 'dark');
          document.documentElement.classList.add('dark');
        });
        await page.waitForTimeout(300);
      }

      if (vp.action) {
        await vp.action(page);
      }

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved screenshot: ${outPath}`);
      await context.close();
    }

    await browser.close();
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
