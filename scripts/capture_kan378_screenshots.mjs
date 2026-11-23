// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18978;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-378/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-split-view-light',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-52`,
  },
  {
    name: '02-desktop-split-view-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-52`,
  },
  {
    name: '03-tablet-split-view',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-52`,
  },
  {
    name: '04-mobile-landscape-split-view',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-52`,
  },
  {
    name: '05-mobile-portrait-split-view',
    width: 390,
    height: 844,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-52`,
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

    const mockIssueDetail = {
      key: 'KAN-52',
      object_id: '01931234-5678-7000-8000-000000000052',
      project_key: 'KAN',
      project_name: 'Platform Core',
      summary: 'Master-Detail Issue Navigator View',
      description_markdown: '### Pager Test\n\nVerifying drawn SVG vector chevron icons for Prev/Next issue navigation.',
      created_at: '2026-11-20T10:00:00Z',
      updated_at: '2026-11-20T11:00:00Z',
      priority: { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
      state: { id: 'st-inprog', name: 'In Progress', group: 'started' },
      capabilities: ['EDIT', 'TRANSITION', 'COMMENT'],
      assignees: ['@admin'],
      sub_issues: [],
      etag: '"etag-kan-52"',
    };

    const mockIssuesList = {
      items: [
        {
          id: '01931234-5678-7000-8000-000000000051',
          key: 'KAN-51',
          summary: 'Previous Issue in Stream',
          state: { id: 'st-todo', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: 'Medium' },
        },
        {
          id: '01931234-5678-7000-8000-000000000052',
          key: 'KAN-52',
          summary: 'Master-Detail Issue Navigator View',
          state: { id: 'st-inprog', name: 'In Progress', group: 'started' },
          priority: { slug: 'high', label: 'High' },
        },
        {
          id: '01931234-5678-7000-8000-000000000053',
          key: 'KAN-53',
          summary: 'Next Issue in Stream',
          state: { id: 'st-done', name: 'Done', group: 'completed' },
          priority: { slug: 'low', label: 'Low' },
        },
      ],
      total: 3,
      next_cursor: null,
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
            name: 'Platform Core',
            description: 'Core platform repository',
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
            { id: 'st-todo', name: 'Todo', category: 'unstarted', color: '#3b82f6', sort_rank: '1' },
            { id: 'st-inprog', name: 'In Progress', category: 'started', color: '#eab308', sort_rank: '2' },
            { id: 'st-done', name: 'Done', category: 'completed', color: '#22c55e', sort_rank: '3' },
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

      await page.route('**/api/v1/issues/*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockIssueDetail),
        });
      });

      // Default mocks for sub-resources
      await page.route('**/api/v1/projects/KAN/members', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/labels', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/modules', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));

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

      await page.waitForTimeout(1000);

      // Wait for pager or header
      const pager = await page.$('[data-testid="split-pager"], [data-testid="issue-prev-btn"]');
      if (pager) {
        console.log(`Found split pager in ${vp.name}`);
      }

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved screenshot to ${outPath}`);

      await context.close();
    }

    await browser.close();
    console.log('All screenshots captured successfully.');
  } finally {
    previewProc.kill();
  }
}

main().catch((err) => {
  console.error('Error during screenshot capture:', err);
  process.exit(1);
});
