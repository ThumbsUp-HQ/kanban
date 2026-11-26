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

const PORT = 18472;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-472/screenshots');

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
  page.on('console', (msg) => {
    const text = msg.text();
    if (!text.includes('Download the React DevTools') && !text.includes('[vite]')) {
      console.log('PAGE LOG:', text);
    }
  });
  page.on('pageerror', (err) => console.log('PAGE ERR:', err));

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

  const mockAdminUser = {
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

  const mockViews = [
    {
      id: 'view-sprint-board',
      name: 'Sprint Active Board',
      description_markdown: 'Primary active sprint items grouped by workflow state with priority sub-grouping.',
      layout: 'board',
      group_by: 'state',
      sub_group_by: 'priority',
      is_shared: true,
      filters: { search_query: 'auth' },
    },
    {
      id: 'view-triage-table',
      name: 'Triage & Backlog Table',
      description_markdown: 'Full column table view for triage and unassigned backlog items.',
      layout: 'table',
      group_by: null,
      sub_group_by: null,
      is_shared: false,
      filters: null,
    },
    {
      id: 'view-release-timeline',
      name: 'Release Milestone Timeline',
      description_markdown: 'Gantt timeline view with dependency blocks across active cycles.',
      layout: 'timeline',
      group_by: null,
      sub_group_by: null,
      is_shared: true,
      filters: null,
    },
  ];

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
          user: mockAdminUser,
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

    if (url.includes('/api/v1/projects/KAN/views')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockViews),
      });
    }

    if (url.includes('/api/v1/projects/KAN/states')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/api/v1/projects/KAN/priorities')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/api/v1/projects/KAN/labels')) {
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

    if (url.includes('/api/v1/projects/KAN/members')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (
      url.includes('/api/v1/projects/KAN') &&
      !url.includes('/views') &&
      !url.includes('/states') &&
      !url.includes('/priorities') &&
      !url.includes('/labels') &&
      !url.includes('/modules') &&
      !url.includes('/members')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'proj_kan',
          key: 'KAN',
          identifier: 'KAN',
          name: 'Platform Engineering',
          description_markdown: 'Core project views.',
          capabilities: ['ADMIN', 'PROJECT_ADMIN'],
          is_project_admin: true,
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
            id: 'proj_kan',
            key: 'KAN',
            name: 'Platform Engineering',
            capabilities: ['ADMIN', 'PROJECT_ADMIN'],
            is_project_admin: true,
          },
        ]),
      });
    }

    return route.continue();
  });
}

async function captureViewports() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log('Building web bundle...');
  const buildProc = spawn('pnpm', ['--dir', 'kanban/web', 'build'], { stdio: 'inherit' });
  await new Promise((resolve, reject) => {
    buildProc.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Build exited with code ${code}`));
    });
  });

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
      console.log(`Capturing ${cfg.name}...`);
      const context = await browser.newContext({
        viewport: { width: cfg.width, height: cfg.height },
        colorScheme: cfg.theme,
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/projects/KAN/views`, { waitUntil: 'networkidle' });

      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        localStorage.setItem('kb:theme', theme);
      }, cfg.theme);

      // Wait for ProjectSavedViewsView to render
      const viewRoot = page.locator('[data-testid="project-views-view"]');
      await viewRoot.waitFor({ state: 'visible', timeout: 8000 });

      // Wait for doc link
      const docLink = page.locator('[data-testid="saved-views-doc-link"]');
      await docLink.waitFor({ state: 'visible', timeout: 8000 });

      // Wait for saved view card
      const card = page.locator('[data-testid="saved-view-card-view-sprint-board"]');
      await card.waitFor({ state: 'visible', timeout: 8000 });

      await page.waitForTimeout(400);

      const outPath = path.join(OUT_DIR, cfg.name);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved ${outPath}`);
      await context.close();
    }

    // Now capture doc-link-interaction-after.png
    console.log('Capturing doc-link-interaction-after.png...');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/projects/KAN/views`, { waitUntil: 'networkidle' });

      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('theme', 'light');
        localStorage.setItem('kb:theme', 'light');
      });

      const docLink = page.locator('[data-testid="saved-views-doc-link"]');
      await docLink.waitFor({ state: 'visible', timeout: 8000 });

      // Click the doc link to open the in-app help drawer
      await docLink.click();
      await page.waitForTimeout(1000);

      // Wait for help drawer content to render
      await page.waitForFunction(() => {
        const bodyText = document.body.innerText || '';
        return (
          bodyText.includes('Enterprise Whitespace') ||
          bodyText.includes('Kanban Board') ||
          !!document.querySelector('.kb-help-drawer') ||
          !!document.querySelector('[data-testid="help-drawer"]')
        );
      }, { timeout: 10000 }).catch(() => {});

      await page.waitForTimeout(800);

      const interactionPath = path.join(OUT_DIR, 'doc-link-interaction-after.png');
      await page.screenshot({ path: interactionPath, fullPage: false });
      console.log(`Saved ${interactionPath}`);
      await context.close();
    }

    await browser.close();
    console.log(`All screenshots successfully captured in ${OUT_DIR}`);
  } finally {
    previewProc.kill('SIGKILL');
  }
}

captureViewports()
  .then(() => {
    process.exit(0);
  })
  .catch((err) => {
    console.error('Screenshot capture failed:', err);
    process.exit(1);
  });
