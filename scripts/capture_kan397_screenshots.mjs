// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
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

const PORT = 18997;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-397/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900-light',
    alias: '1440x900-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    name: '02-desktop-1440x900-dark',
    alias: '1440x900-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    name: '03-tablet-portrait-768x1024',
    alias: '768x1024-tablet-portrait',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: '04-mobile-390x844',
    alias: '390x844-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'light',
  },
];

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

async function setupPageInterceptions(page) {
  await page.route('**/*', async (route) => {
    const url = route.request().url();

    if (url.includes('/api/v1/setup/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ initialized: true }),
      });
    }

    if (url.includes('/api/v1/auth/session')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          mfa_pending: false,
          csrf_token: 'mock-csrf-token-12345',
          principal_id: 'usr_admin_test_1',
          workspace_id: 'ws_default',
          aal_level: 2,
        }),
      });
    }

    if (url.includes('/api/v1/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr_admin_test_1',
          email: 'admin@kanban.local',
          username: 'admin',
          display_name: 'System Administrator',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'WORKSPACE_ADMIN',
          aal_level: 2,
          auth_aal: 'aal2',
        }),
      });
    }

    if (url.includes('/api/v1/workspaces')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'ws_default', slug: 'kanban', name: 'Kanban Workspace' },
        ]),
      });
    }

    if (url.includes('/api/v1/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'proj_kan', key: 'KAN', name: 'Kanban Project' },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/workspace-settings')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ air_gap_mode: false }),
      });
    }

    return route.continue();
  });
}

async function main() {
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
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name} (${vp.width}x${vp.height}) theme=${vp.theme}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: vp.theme === 'dark' ? 'dark' : 'light',
      });
      const page = await context.newPage();
      await setupPageInterceptions(page);

      await page.goto(`${BASE_URL}/admin/imports`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(500);

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, vp.theme);

      // Verify title is Migration Import Studio
      const titleEl = page.locator('[data-testid="studio-title"]');
      await titleEl.waitFor({ state: 'visible', timeout: 10000 });
      const titleText = await titleEl.textContent();
      if (!titleText || !titleText.includes('Migration Import Studio')) {
        throw new Error(`CRITICAL: Expected studio-title to include "Migration Import Studio", got: "${titleText}"`);
      }

      // Verify subnav tab is Migration
      const tabEl = page.locator('[data-testid="tab-admin-imports"]');
      await tabEl.waitFor({ state: 'visible', timeout: 5000 });
      const tabText = await tabEl.textContent();
      if (!tabText || !tabText.includes('Migration')) {
        throw new Error(`CRITICAL: Expected tab-admin-imports to include "Migration", got: "${tabText}"`);
      }

      // Capture default studio page screenshot
      const mainPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: mainPath, fullPage: false });
      console.log(`  -> Saved ${mainPath}`);

      if (vp.alias) {
        const aliasPath = path.join(OUT_DIR, `${vp.alias}.png`);
        fs.copyFileSync(mainPath, aliasPath);
        console.log(`  -> Saved alias ${aliasPath}`);
      }

      // If desktop viewport, open avatar menu to capture Migration Import Studio link in menu
      if (vp.width >= 1024) {
        const avatarBtn = page.locator('button[aria-label="User profile and settings"]');
        if (await avatarBtn.isVisible()) {
          await avatarBtn.click();
          await page.waitForTimeout(300);

          const menuLink = page.locator('[data-testid="topbar-admin-imports-link"]');
          await menuLink.waitFor({ state: 'visible', timeout: 5000 });
          const menuLinkText = await menuLink.textContent();
          if (!menuLinkText || !menuLinkText.includes('Migration Import Studio')) {
            throw new Error(`CRITICAL: Expected topbar-admin-imports-link to include "Migration Import Studio", got: "${menuLinkText}"`);
          }

          const menuPath = path.join(OUT_DIR, `${vp.name}-menu-open.png`);
          await page.screenshot({ path: menuPath, fullPage: false });
          console.log(`  -> Saved menu screenshot ${menuPath}`);

          // Close menu
          await avatarBtn.click();
          await page.waitForTimeout(200);
        }
      }

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
