// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18976;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-376/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900-wide',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues`,
    openDropdown: false,
  },
  {
    name: '02-small-desktop-1024x768-zero-search-overlap',
    width: 1024,
    height: 768,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues`,
    openDropdown: false,
  },
  {
    name: '03-tablet-768x1024-compact-layout',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues`,
    openDropdown: false,
  },
  {
    name: '04-mobile-390x844-open-dropdown-unclipped',
    width: 390,
    height: 844,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues`,
    openDropdown: true,
  },
  {
    name: '05-mobile-landscape-844x390-short-viewport',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues`,
    openDropdown: false,
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

    const mockIssuesList = {
      items: [
        {
          id: '01931234-5678-7000-8000-000000000051',
          key: 'KAN-51',
          summary: 'Fix Mobile Layout Dropdown Clipping Under Content',
          state: { id: 'st-inprog', name: 'In Progress', group: 'started' },
          priority: { slug: 'high', label: 'High' },
        },
        {
          id: '01931234-5678-7000-8000-000000000052',
          key: 'KAN-52',
          summary: 'Small-Desktop LayoutSwitcher Overlapping Search Trigger',
          state: { id: 'st-todo', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: 'Medium' },
        },
      ],
      total: 2,
      next_cursor: null,
    };

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name} (${vp.width}x${vp.height})...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });

      const page = await context.newPage();

      // Auth mocks
      await page.route('**/api/v1/setup/status', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ initialized: true }),
        });
      });

      await page.route('**/api/v1/auth/session', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            authenticated: true,
            mfa_pending: false,
            principal_id: 'u-admin',
            workspace_id: 'w-kanban',
            csrf_token: 'mock-csrf-token',
          }),
        });
      });

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
            identifier: 'KAN',
            name: 'Platform Core',
            description: 'Core platform repository',
            visibility: 'internal',
            archived: false,
            modules_enabled: true,
            capabilities: ['EDIT', 'ADMIN'],
            is_project_admin: true,
          }),
        });
      });

      await page.route('**/api/v1/projects/KAN/states', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'st-todo', name: 'Todo', group: 'unstarted', category: 'unstarted', color: '#3b82f6', sort_rank: '1' },
            { id: 'st-inprog', name: 'In Progress', group: 'started', category: 'started', color: '#eab308', sort_rank: '2' },
            { id: 'st-done', name: 'Done', group: 'completed', category: 'completed', color: '#22c55e', sort_rank: '3' },
          ]),
        });
      });

      await page.route('**/api/v1/projects/KAN/priorities', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'pr-low', level: 1, slug: 'low', name: 'Low', color: '#94a3b8', sort_order: 1 },
            { id: 'pr-med', level: 2, slug: 'medium', name: 'Medium', color: '#3b82f6', sort_order: 2 },
            { id: 'pr-high', level: 3, slug: 'high', name: 'High', color: '#f97316', sort_order: 3 },
          ]),
        });
      });

      await page.route('**/api/v1/projects/KAN/issues*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockIssuesList),
        });
      });

      await page.route('**/api/v1/projects/KAN/members', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/labels', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/modules', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/system/status', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', database: 'connected' }) }));

      try {
        await page.goto(vp.url, { waitUntil: 'load', timeout: 15000 });
      } catch (err) {
        console.warn(`Warning navigating to ${vp.url}:`, err.message);
      }

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('kb_theme', theme);
      }, vp.theme);

      await page.waitForTimeout(800);

      if (vp.openDropdown) {
        console.log(`Opening mobile layout dropdown in ${vp.name}... URL: ${page.url()}`);
        const errMsg = await page.$eval('#app-error-message', el => el.innerText).catch(() => null);
        if (errMsg) console.log('App Error Message:', errMsg);
        const mobileBtn = await page.$('.kb-layout-switcher-mobile-btn');
        if (mobileBtn) {
          await mobileBtn.click();
          await page.waitForTimeout(500);
          console.log(`Dropdown opened successfully.`);
        } else {
          console.warn(`Could not locate .kb-layout-switcher-mobile-btn in ${vp.name}`);
        }
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
