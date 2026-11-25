// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18995;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-395/screenshots');
const CONSENT_HTML_PATH = '/tmp/consent_screen_1200.html';

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
    const method = route.request().method();

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

    if (url.includes('/api/v1/auth/me') || url.includes('/api/v1/user/me')) {
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
          is_project_admin: true,
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
          {
            id: 'p_kanba',
            identifier: 'KANBA',
            name: 'Kanban Core',
            description: 'Core project',
            modules_enabled: true,
            is_project_admin: true,
          },
        ]),
      });
    }

    if (url.includes('/api/v1/auth/oauth-grants')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (url.includes('/api/v1/mcp-keys')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ keys: [], total: 0 }),
      });
    }

    if (url.includes('/api/v1/workload-identities')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
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
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });

    // 1. Consent Screen Screenshots across 5 viewports
    const consentViewports = [
      { name: 'oauth-consent-screen-1200-state-1440x900-light.png', width: 1440, height: 900, theme: 'light' },
      { name: 'oauth-consent-screen-1200-state-1440x900-dark.png', width: 1440, height: 900, theme: 'dark' },
      { name: 'oauth-consent-screen-1200-state-1024x768.png', width: 1024, height: 768, theme: 'light' },
      { name: 'oauth-consent-screen-1200-state-768x1024.png', width: 768, height: 1024, theme: 'light' },
      { name: 'oauth-consent-screen-1200-state-390x844.png', width: 390, height: 844, theme: 'light' },
    ];

    for (const cv of consentViewports) {
      console.log(`Capturing consent screen ${cv.name} (${cv.width}x${cv.height}) ${cv.theme}...`);
      const context = await browser.newContext({
        viewport: { width: cv.width, height: cv.height },
        colorScheme: cv.theme,
      });
      const page = await context.newPage();
      await page.goto(`file://${CONSENT_HTML_PATH}`, { waitUntil: 'load' });
      await page.waitForTimeout(400);

      const outPath = path.join(OUT_DIR, cv.name);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);
      await context.close();
    }

    // 2. Connect OAuth Modal Screenshots
    const modalViewports = [
      { nameSuffix: 'workspace-1440x900-light.png', width: 1440, height: 900, theme: 'light', scope: 'workspace' },
      { nameSuffix: 'workspace-1440x900-dark.png', width: 1440, height: 900, theme: 'dark', scope: 'workspace' },
      { nameSuffix: 'workspace-1024x768.png', width: 1024, height: 768, theme: 'light', scope: 'workspace' },
      { nameSuffix: 'workspace-768x1024.png', width: 768, height: 1024, theme: 'light', scope: 'workspace' },
      { nameSuffix: 'workspace-390x844.png', width: 390, height: 844, theme: 'light', scope: 'workspace' },
      { nameSuffix: 'project-1440x900-light.png', width: 1440, height: 900, theme: 'light', scope: 'project' },
      { nameSuffix: 'project-390x844.png', width: 390, height: 844, theme: 'light', scope: 'project' },
      { nameSuffix: 'server-1440x900-light.png', width: 1440, height: 900, theme: 'light', scope: 'server' },
      { nameSuffix: 'server-390x844.png', width: 390, height: 844, theme: 'light', scope: 'server' },
    ];

    for (const mv of modalViewports) {
      const fileName = `connect-oauth-modal-gemini-${mv.nameSuffix}`;
      console.log(`Capturing modal ${fileName} (${mv.width}x${mv.height}) ${mv.theme} scope=${mv.scope}...`);
      const context = await browser.newContext({
        viewport: { width: mv.width, height: mv.height },
        colorScheme: mv.theme,
      });
      const page = await context.newPage();
      await setupPageInterceptions(page);

      await page.goto(`${BASE_URL}/settings/mcp?scope=workspace`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1000);

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
        const chip = document.querySelector('.realtime-status-chip');
        if (chip) chip.remove();
      }, mv.theme);

      // Click + Connect OAuth App button
      const openBtn = page.locator('[data-testid="connect-oauth-app-btn"], [data-testid="empty-connect-oauth-app-btn"]').first();
      await openBtn.waitFor({ state: 'visible', timeout: 10000 });
      await openBtn.click();

      // Wait for modal
      const modal = page.locator('[data-testid="connect-oauth-app-modal"]');
      await modal.waitFor({ state: 'visible', timeout: 10000 });

      // Click Gemini App tab
      const geminiTab = page.locator('[data-testid="tab-gemini-app"]');
      await geminiTab.waitFor({ state: 'visible', timeout: 10000 });
      await geminiTab.click();
      await page.waitForTimeout(400);

      // Select target scope
      if (mv.scope !== 'workspace') {
        const scopeSelect = page.locator('[data-testid="scope-tier-select"]');
        await scopeSelect.selectOption(mv.scope);
        await page.waitForTimeout(400);
      }

      const outPath = path.join(OUT_DIR, fileName);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);
      await context.close();
    }

    await browser.close();
    console.log('All 14 Playwright screenshots captured successfully.');
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Fatal error during screenshot capture:', err);
  process.exit(1);
});
