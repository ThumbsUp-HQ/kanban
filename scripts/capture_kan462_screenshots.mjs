// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '../kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18462;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-462/screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function waitForServer(url, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 200) return;
    } catch {
      // wait
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`Timeout waiting for preview server at ${url}`);
}

async function setupMockRoutes(page) {
  await page.route('**/*', async (route) => {
    const url = route.request().url();
    if (!url.includes('/api/')) return route.continue();

    if (url.includes('/api/v1/setup/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ initialized: true, is_initialized: true }),
      });
    }

    if (url.includes('/api/v1/users/me') || url.includes('/api/v1/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr_admin',
          email: 'admin@kanban.local',
          username: 'admin',
          display_name: 'Admin User',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'WORKSPACE_ADMIN',
          aal_level: 2,
        }),
      });
    }

    if (url.includes('/api/v1/auth/session')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true, aal_level: 2, principal_id: 'usr_admin' }),
      });
    }

    if (url.includes('/api/v1/projects/KAN/cycles')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'cyc-1',
            name: 'Sprint 1 - Foundation',
            status: 'in_progress',
            start_date: '2026-11-01',
            end_date: '2026-11-15',
          },
          {
            id: 'cyc-2',
            name: 'Sprint 2 - Hardening',
            status: 'planned',
            start_date: '2026-11-16',
            end_date: '2026-11-30',
          },
        ]),
      });
    }

    if (url.includes('/api/v1/projects/KAN')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'p-1',
          identifier: 'KAN',
          name: 'kanban',
          capabilities: ['ADMIN', 'EDIT', 'PROJECT_ADMIN'],
          modules_enabled: true,
        }),
      });
    }

    if (url.includes('/api/v1/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'p-1',
            identifier: 'KAN',
            name: 'kanban',
            capabilities: ['ADMIN', 'EDIT', 'PROJECT_ADMIN'],
          },
        ]),
      });
    }

    if (url.includes('/api/v1/notifications')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, unread_count: 0 }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });
}

async function main() {
  console.log(`Starting preview server on port ${PORT}...`);
  const previewProc = spawn(
    'npx',
    ['vite', 'preview', '--port', String(PORT), '--strictPort', '--host', '127.0.0.1'],
    {
      cwd: path.resolve('kanban/web'),
      stdio: 'ignore',
    }
  );

  const cleanup = () => {
    try {
      previewProc.kill();
    } catch {}
  };
  process.on('exit', cleanup);
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);

  try {
    await waitForServer(`${BASE_URL}/`);
    console.log('Preview server ready. Launching Chrome...');

    const browser = await chromium.launch({
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    });

    const viewports = [
      { name: 'desktop-light-1440x900.png', width: 1440, height: 900, theme: 'light' },
      { name: 'desktop-dark-1440x900.png', width: 1440, height: 900, theme: 'dark' },
      { name: 'tablet-768x1024.png', width: 768, height: 1024, theme: 'light' },
      { name: 'tablet-dark-768x1024.png', width: 768, height: 1024, theme: 'dark' },
      { name: 'mobile-390x844.png', width: 390, height: 844, theme: 'light' },
      { name: 'mobile-dark-390x844.png', width: 390, height: 844, theme: 'dark' },
    ];

    for (const vp of viewports) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: vp.theme,
      });

      const page = await context.newPage();
      await setupMockRoutes(page);

      await page.goto(`${BASE_URL}/projects/KAN/cycles`, { waitUntil: 'networkidle' });
      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, vp.theme);
      await page.waitForTimeout(400);

      const filePath = path.join(OUT_DIR, vp.name);
      await page.screenshot({ path: filePath, fullPage: false });
      console.log('Captured', vp.name);
      await context.close();
    }

    // Popover open viewports
    const popoverViewports = [
      { name: 'popover-open-light-1440x900.png', width: 1440, height: 900, theme: 'light' },
      { name: 'popover-open-dark-1440x900.png', width: 1440, height: 900, theme: 'dark' },
      { name: 'popover-open-mobile-390x844.png', width: 390, height: 844, theme: 'light' },
    ];

    for (const pvp of popoverViewports) {
      const context = await browser.newContext({
        viewport: { width: pvp.width, height: pvp.height },
        colorScheme: pvp.theme,
      });

      const page = await context.newPage();
      await setupMockRoutes(page);

      await page.goto(`${BASE_URL}/projects/KAN/cycles`, { waitUntil: 'networkidle' });
      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, pvp.theme);
      await page.waitForTimeout(300);

      // Focus the start date help hint
      const hint = page.locator('[data-testid="cycle-start-date-help-hint"]');
      await hint.waitFor({ state: 'visible', timeout: 5000 });
      await hint.focus();
      await page.waitForTimeout(400);

      const filePath = path.join(OUT_DIR, pvp.name);
      await page.screenshot({ path: filePath, fullPage: false });
      console.log('Captured', pvp.name);
      await context.close();
    }

    await browser.close();
    console.log('All KAN-462 screenshots captured successfully!');
  } finally {
    cleanup();
  }
}

main().catch((err) => {
  console.error('Error running capture:', err);
  process.exit(1);
});
