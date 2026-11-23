// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18979;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-379/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-split-view-light',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-379`,
  },
  {
    name: '02-desktop-split-view-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-379`,
  },
  {
    name: '03-tablet-split-view-landscape',
    width: 1024,
    height: 768,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-379`,
  },
  {
    name: '04-mobile-landscape-split-surface',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-379`,
  },
  {
    name: '05-mobile-portrait-split-surface',
    width: 390,
    height: 844,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-379`,
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
      id: 'iss-379',
      key: 'KAN-379',
      project_key: 'KAN',
      project_name: 'Kanban Platform',
      summary: 'Compact Split Issue Header and Relocated Right Sidebar Toolbar',
      description_markdown: 'Compact single-line issue header with edit button and relocated action controls.',
      state_id: 'st-in-prog',
      state: {
        id: 'st-in-prog',
        name: 'In Progress',
        group: 'started',
        color_hex: '#3b82f6',
      },
      priority: 'high',
      assignees: [
        {
          id: 'asg-1',
          kind: 'principal',
          principal: {
            id: 'u-admin',
            handle: 'admin',
            display_name: 'Administrator',
            type: 'USER',
          },
        },
      ],
      capabilities: ['VIEW', 'EDIT', 'ADMIN'],
      created_at: '2026-11-20T10:00:00Z',
      updated_at: '2026-11-23T10:00:00Z',
      start_date: '2026-11-20',
      due_date: '2026-11-30',
      sub_issues: [],
      attachments: [],
    };

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

      // Intercept project
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'p-1',
            identifier: 'KAN',
            name: 'Kanban Platform',
            description: 'Core project',
            modules_enabled: true,
            is_project_admin: true,
          }),
        });
      });

      // Intercept states
      await page.route('**/api/v1/projects/KAN/states**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'st-todo', name: 'Todo', group: 'unstarted', color_hex: '#64748b' },
            { id: 'st-in-prog', name: 'In Progress', group: 'started', color_hex: '#3b82f6' },
            { id: 'st-done', name: 'Done', group: 'completed', color_hex: '#22c55e' },
          ]),
        });
      });

      // Intercept issues list
      await page.route('**/api/v1/projects/KAN/issues**', (route) => {
        const url = route.request().url();
        if (url.includes('/issues/KAN-379')) {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockIssue),
          });
        } else {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([mockIssue]),
          });
        }
      });

      // Intercept access pill / sharing
      await page.route('**/api/v1/objects/**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'obj-379',
            scope: 'project',
            sharing: { users: [], groups: [], agents: [] },
          }),
        });
      });

      await page.goto(vp.url, { waitUntil: 'domcontentloaded' });

      // Apply theme
      if (vp.theme === 'dark') {
        await page.evaluate(() => {
          document.documentElement.classList.add('dark');
          document.documentElement.setAttribute('data-theme', 'dark');
        });
      }

      await page.waitForTimeout(1500);

      const targetPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: targetPath, fullPage: false });
      console.log(`Saved screenshot to ${targetPath}`);
      await context.close();
    }

    await browser.close();
    console.log('All screenshots captured successfully.');
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
