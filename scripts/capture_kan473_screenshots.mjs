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
    ({ chromium } = await import('/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs'));
  } catch {
    ({ chromium } = await import('playwright'));
  }
}

const PORT = 18473;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-473/screenshots');

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
      static OPEN = 1;
      static CONNECTING = 0;
      static CLOSING = 2;
      static CLOSED = 3;
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

  const mockUser = {
    id: 'usr_admin_1',
    email: 'admin@kanban.local',
    username: 'admin',
    display_name: 'Adam Architect',
    is_server_admin: true,
    is_workspace_admin: true,
    workspace_role: 'WORKSPACE_ADMIN',
    aal_level: 2,
    auth_aal: 'aal2',
    aal2_active: true,
  };

  const mockProject = {
    id: 'proj_kan',
    key: 'KAN',
    identifier: 'KAN',
    name: 'Core Platform',
    capabilities: ['ADMIN', 'PROJECT_ADMIN'],
    is_project_admin: true,
  };

  await page.route('**/*', async (route) => {
    const url = route.request().url();

    if (url.includes('/api/v1/setup/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ initialized: true, is_initialized: true, requires_setup: false }),
      });
    }

    if (url.includes('/api/v1/auth/session') || url.includes('/api/v1/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          is_authenticated: true,
          user: mockUser,
        }),
      });
    }

    if (url.includes('/api/v1/workspaces/current')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'ws_default',
          name: 'Platform Engineering',
          slug: 'kanban',
          is_current: true,
        }),
      });
    }

    if (url.includes('/api/v1/workspaces')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'ws_default', slug: 'kanban', name: 'Platform Engineering' },
        ]),
      });
    }

    if (url.includes('/api/v1/projects/current') || url.includes('/api/v1/projects/KAN')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockProject),
      });
    }

    if (url.includes('/api/v1/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([mockProject]),
      });
    }

    if (url.includes('/api/v1/search')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'issue-473',
              kind: 'issue',
              key: 'KAN-473',
              title: 'Command Palette Persistent Footer Legend',
              summary: 'Persistent keyboard shortcut hints for navigate, select, and dismiss',
              match_reason: 'Title & Summary Match',
            },
          ],
        }),
      });
    }

    if (url.includes('/api/v1/issues')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'iss-1',
            key: 'KAN-473',
            title: 'Command Palette Persistent Footer Legend',
            summary: 'Command Palette Persistent Footer Legend',
            state: 'in_progress',
          },
        ]),
      });
    }

    return route.continue();
  });
}

async function capture() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log(`Starting preview server on port ${PORT}...`);
  const previewProc = spawn(
    'pnpm',
    ['--dir', 'kanban/web', 'preview', '--port', String(PORT), '--host', '127.0.0.1'],
    { stdio: 'inherit' }
  );

  try {
    await waitForServer(BASE_URL);
    console.log(`Preview server ready at ${BASE_URL}`);

    const browser = await chromium.launch({
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });

    const configs = [
      { name: 'desktop-light-1440x900.png', width: 1440, height: 900, theme: 'light' },
      { name: 'desktop-dark-1440x900.png', width: 1440, height: 900, theme: 'dark' },
      { name: 'tablet-768x1024.png', width: 768, height: 1024, theme: 'light' },
      { name: 'tablet-dark-768x1024.png', width: 768, height: 1024, theme: 'dark' },
      { name: 'mobile-390x844.png', width: 390, height: 844, theme: 'light' },
      { name: 'mobile-dark-390x844.png', width: 390, height: 844, theme: 'dark' },
    ];

    for (const cfg of configs) {
      console.log(`Capturing ${cfg.name} (${cfg.width}x${cfg.height}, ${cfg.theme})...`);
      const context = await browser.newContext({
        viewport: { width: cfg.width, height: cfg.height },
        colorScheme: cfg.theme,
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle' });

      // Apply theme
      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        localStorage.setItem('kb:theme', theme);
      }, cfg.theme);
      await page.waitForTimeout(200);

      // Open command palette via keyboard shortcut
      await page.keyboard.press('Control+k');

      // Locate modal and legend
      const modal = page.locator('[data-testid="command-palette-modal"]');
      await modal.waitFor({ state: 'visible', timeout: 5000 });

      const legend = page.locator('[data-testid="palette-footer-legend"]');
      await legend.waitFor({ state: 'visible', timeout: 5000 });

      await page.waitForTimeout(300);

      const outPath = path.join(OUT_DIR, cfg.name);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved ${outPath}`);

      await context.close();
    }

    await browser.close();
    console.log(`All screenshots captured successfully into ${OUT_DIR}`);
  } finally {
    previewProc.kill('SIGKILL');
  }
}

capture()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('Screenshot capture failed:', err);
    process.exit(1);
  });
