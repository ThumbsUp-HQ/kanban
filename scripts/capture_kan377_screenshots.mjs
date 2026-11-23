// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18977;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-377/screenshots');

const mockIssue = {
  id: 'iss-377',
  key: 'KAN-377',
  identifier: 'KAN-377',
  title: 'Add 3 Space-Preserving Search Header Modes',
  summary: 'Add 3 Space-Preserving Search Header Modes (Search Only 1-Col, Basic 2-Col, Advanced 2-Col 1-Line)',
  description: 'Add the 3 space-preserving search header modes: Search only 1-col docked inside list pane, Basic 2-col, and Advanced 2-col 1-line.',
  description_markdown: 'Add the 3 space-preserving search header modes: Search only 1-col docked inside list pane, Basic 2-col, and Advanced 2-col 1-line.',
  state_id: 'st-inprog',
  state: { id: 'st-inprog', name: 'In Progress', group: 'started', color_hex: '#eab308' },
  priority: { slug: 'high', label: 'High' },
  project_id: 'p-kan',
  project_key: 'KAN',
  created_at: '2026-11-23T08:00:00Z',
  updated_at: '2026-11-23T08:00:00Z',
  creator: { id: 'u-admin', display_name: 'Administrator', handle: 'admin' },
  assignees: [{ id: 'u-admin', display_name: 'Administrator', handle: 'admin', kind: 'principal', principal: { id: 'u-admin', handle: 'admin', display_name: 'Administrator' } }],
  labels: [{ id: 'lb-feat', name: 'ux', color_hex: '#3b82f6' }],
};

const VIEWPORTS = [
  {
    name: '01-1col-desktop-split-view-risen',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-377`,
    action: async (page) => {
      // 1-Col mode is default; ensure button is active
      const btn = page.locator('[data-testid="header-mode-1col-btn"]');
      if (await btn.isVisible()) {
        await btn.click().catch(() => {});
      }
      await page.waitForTimeout(300);
    },
  },
  {
    name: '02-basic-2col-desktop',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-377`,
    action: async (page) => {
      await page.locator('[data-testid="header-mode-basic-2col-btn"]').click();
      await page.waitForTimeout(400);
    },
  },
  {
    name: '03-advanced-1line-desktop',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-377`,
    action: async (page) => {
      await page.locator('[data-testid="header-mode-advanced-1line-btn"]').click();
      await page.waitForTimeout(400);
    },
  },
  {
    name: '04-1col-tablet',
    width: 768,
    height: 1024,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-377`,
    action: async (page) => {
      await page.waitForTimeout(300);
    },
  },
  {
    name: '05-1col-mobile',
    width: 390,
    height: 844,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list`,
    action: async (page) => {
      await page.waitForTimeout(300);
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

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
        colorScheme: vp.theme,
      });

      const page = await context.newPage();

      // Intercept auth
      await page.route('**/api/v1/auth/**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            authenticated: true,
            aal_level: 2,
            csrf_token: 'test-csrf-token',
            principal_id: 'u-admin',
            user: { id: 'u-admin', handle: 'admin', display_name: 'Administrator' },
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
      await page.route('**/api/v1/setup/status', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ initialized: true, is_initialized: true, requires_setup: false }),
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
            identifier: 'KAN',
            name: 'Core Platform',
            description: 'Primary platform repository',
            visibility: 'internal',
            archived: false,
            capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
            is_project_admin: true,
            modules_enabled: true,
          }),
        });
      });

      // Specific mock for issues
      await page.route('**/api/v1/projects/KAN/issues*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [
              mockIssue,
              {
                id: 'iss-376',
                key: 'KAN-376',
                identifier: 'KAN-376',
                summary: 'Refactor Layout Controls',
                state_id: 'st-todo',
                state: { id: 'st-todo', name: 'Todo', group: 'unstarted', color_hex: '#3b82f6' },
                priority: { slug: 'medium', label: 'Medium' },
                project_id: 'p-kan',
                project_key: 'KAN',
                assignees: [],
                labels: [],
              },
            ],
            total: 2,
            page: 1,
            size: 50,
          }),
        });
      });

      // Catch-all for remaining project and issue sub-resources
      await page.route('**/api/v1/projects/KAN/**', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });
      await page.route('**/api/v1/issues/**', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockIssue) });
      });

      try {
        await page.goto(vp.url, { waitUntil: 'domcontentloaded', timeout: 15000 });
      } catch (err) {
        console.warn(`Warning navigating to ${vp.url}:`, err.message);
      }

      await page.waitForSelector('[data-testid="issue-navigator-bar"]', { timeout: 10000 });

      // Apply theme
      await page.evaluate((theme) => {
        try {
          localStorage.setItem('theme', theme);
          document.documentElement.setAttribute('data-theme', theme);
          document.documentElement.dataset.theme = theme;
        } catch {
          // ignore
        }
      }, vp.theme);

      // Perform mode switch action
      if (vp.action) {
        await vp.action(page);
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
