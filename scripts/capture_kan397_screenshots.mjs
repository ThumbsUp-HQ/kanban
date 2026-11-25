// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn, execSync } from 'node:child_process';
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
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      console.log(`[PAGE ERROR] ${msg.text()}`);
    }
  });
  page.on('pageerror', (err) => {
    console.log(`[UNCAUGHT PAGE ERROR] ${err.message}`);
  });

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

    if (url.includes('/api/v1/system/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', version: '0.1.0' }),
      });
    }

    if (url.includes('/ws') || url.includes('/sse')) {
      return route.fulfill({
        status: 200,
        contentType: 'text/plain',
        body: '',
      });
    }

    if (url.includes('/api/v1/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    }

    return route.continue();
  });
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  // Ensure production build exists for preview server
  if (!fs.existsSync('kanban/web/dist')) {
    console.log('Building web bundle for preview server...');
    execSync('pnpm --dir kanban/web build', { stdio: 'inherit' });
  }

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

      // Inject theme into localStorage before page loads
      await context.addInitScript((theme) => {
        try {
          localStorage.setItem('theme', theme);
        } catch {
          // ignore
        }
      }, vp.theme);

      const page = await context.newPage();
      await setupPageInterceptions(page);

      await page.goto(`${BASE_URL}/admin/imports`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(600);

      // Set data-theme on documentElement
      await page.evaluate((theme) => {
        if (document.documentElement) {
          document.documentElement.setAttribute('data-theme', theme);
          document.documentElement.dataset.theme = theme;
        }
      }, vp.theme);

      // Hide Reconnecting... WebSocket toast to prevent dropzone overlap
      await page.evaluate(() => {
        const hideChips = () => {
          document.querySelectorAll('.realtime-status-chip').forEach((el) => {
            el.style.setProperty('display', 'none', 'important');
            el.style.setProperty('visibility', 'hidden', 'important');
            el.style.setProperty('opacity', '0', 'important');
          });
        };
        hideChips();
        const observer = new MutationObserver(hideChips);
        observer.observe(document.body, { childList: true, subtree: true });
      });

      // Verify title is Migration Import Studio
      const titleEl = page.locator('[data-testid="studio-title"]');
      await titleEl.waitFor({ state: 'visible', timeout: 10000 });
      const titleText = await titleEl.textContent();
      if (!titleText || !titleText.includes('Migration Import Studio')) {
        throw new Error(`CRITICAL: Expected studio-title to include "Migration Import Studio", got: "${titleText}"`);
      }

      // Verify subnav tab is Migration and scroll it into center view
      const tabEl = page.locator('[data-testid="tab-admin-imports"]');
      await tabEl.waitFor({ state: 'visible', timeout: 5000 });
      const tabText = await tabEl.textContent();
      if (!tabText || !tabText.includes('Migration')) {
        throw new Error(`CRITICAL: Expected tab-admin-imports to include "Migration", got: "${tabText}"`);
      }
      await tabEl.scrollIntoViewIfNeeded();
      await tabEl.evaluate((el) => {
        el.scrollIntoView({ inline: 'center', block: 'nearest' });
      });
      await page.waitForTimeout(300);

      // Re-hide chip just in case re-rendered
      await page.evaluate(() => {
        document.querySelectorAll('.realtime-status-chip').forEach((el) => {
          el.style.setProperty('display', 'none', 'important');
          el.style.setProperty('visibility', 'hidden', 'important');
        });
      });

      // Capture default studio page screenshot
      const mainPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: mainPath, fullPage: false });
      console.log(`  -> Saved ${mainPath}`);

      if (vp.alias) {
        const aliasPath = path.join(OUT_DIR, `${vp.alias}.png`);
        fs.copyFileSync(mainPath, aliasPath);
        console.log(`  -> Saved alias ${aliasPath}`);
      }

      // If desktop light viewport, also capture source-switching screenshots
      if (vp.name === '01-desktop-1440x900-light') {
        const sources = [
          { id: 'jira', testId: 'source-jira-btn', filename: '05-source-jira.png' },
          { id: 'github', testId: 'source-github-btn', filename: '06-source-github.png' },
          { id: 'linear', testId: 'source-linear-btn', filename: '07-source-linear.png' },
        ];
        for (const src of sources) {
          const srcBtn = page.locator(`[data-testid="${src.testId}"]`);
          await srcBtn.waitFor({ state: 'visible', timeout: 5000 });
          await srcBtn.click();
          await page.waitForTimeout(300);

          const titleCheck = await page.locator('[data-testid="studio-title"]').textContent({ timeout: 5000 });
          if (!titleCheck || titleCheck.trim() !== 'Migration Import Studio') {
            throw new Error(`CRITICAL: Source ${src.id} title did not remain "Migration Import Studio", got: "${titleCheck}"`);
          }

          // Ensure chips are hidden before screenshot
          await page.evaluate(() => {
            document.querySelectorAll('.realtime-status-chip').forEach((el) => {
              el.style.setProperty('display', 'none', 'important');
              el.style.setProperty('visibility', 'hidden', 'important');
            });
          });

          const srcPath = path.join(OUT_DIR, src.filename);
          await page.screenshot({ path: srcPath, fullPage: false });
          console.log(`  -> Saved source-switching screenshot ${srcPath}`);
        }
        // Switch back to Plane source
        await page.locator('[data-testid="source-plane-btn"]').click();
        await page.waitForTimeout(300);
      }

      // If desktop viewport, open avatar menu to capture Migration Import Studio link in menu
      if (vp.width >= 1024) {
        const avatarBtn = page.locator('button[aria-label="User profile and settings"]');
        await avatarBtn.waitFor({ state: 'visible', timeout: 10000 });
        await avatarBtn.click();
        await page.waitForTimeout(300);

        const menuLink = page.locator('[data-testid="topbar-admin-imports-link"]');
        await menuLink.waitFor({ state: 'visible', timeout: 5000 });
        const menuLinkText = await menuLink.textContent();
        if (!menuLinkText || !menuLinkText.includes('Migration Import Studio')) {
          throw new Error(`CRITICAL: Expected topbar-admin-imports-link to include "Migration Import Studio", got: "${menuLinkText}"`);
        }

        // Ensure chips are hidden before screenshot
        await page.evaluate(() => {
          document.querySelectorAll('.realtime-status-chip').forEach((el) => {
            el.style.setProperty('display', 'none', 'important');
            el.style.setProperty('visibility', 'hidden', 'important');
          });
        });

        const menuPath = path.join(OUT_DIR, `${vp.name}-menu-open.png`);
        await page.screenshot({ path: menuPath, fullPage: false });
        console.log(`  -> Saved menu screenshot ${menuPath}`);

        // Close menu
        await page.keyboard.press('Escape');
        await page.waitForTimeout(200);
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
