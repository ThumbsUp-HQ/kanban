// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Playwright screenshot capture script for KAN-446.
 * Captures responsive views of standardized StudioDocLink placement across:
 * 1. desktop-light-1440x900.png
 * 2. desktop-dark-1440x900.png
 * 3. tablet-768x1024.png
 * 4. tablet-dark-768x1024.png
 * 5. mobile-390x844.png
 * 6. mobile-dark-390x844.png
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

let chromium;
try {
  const localPlaywright = path.resolve('kanban/web/node_modules/@playwright/test/index.mjs');
  ({ chromium } = await import(localPlaywright));
} catch {
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    ({ chromium } = await import('@playwright/test'));
  }
}

const PORT = process.env.KAN446_PORT || '18446';
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-446/screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return;
    } catch {
      // Retry
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`Server did not respond at ${url} within ${timeoutMs}ms`);
}

const VIEWPORTS = [
  { filename: 'desktop-light-1440x900.png', width: 1440, height: 900, theme: 'light' },
  { filename: 'desktop-dark-1440x900.png', width: 1440, height: 900, theme: 'dark' },
  { filename: 'tablet-768x1024.png', width: 768, height: 1024, theme: 'light' },
  { filename: 'tablet-dark-768x1024.png', width: 768, height: 1024, theme: 'dark' },
  { filename: 'mobile-390x844.png', width: 390, height: 844, theme: 'light' },
  { filename: 'mobile-dark-390x844.png', width: 390, height: 844, theme: 'dark' },
];

async function main() {
  console.log(`[KAN-446] Starting preview server on port ${PORT}...`);
  const server = spawn('pnpm', ['--dir', 'kanban/web', 'preview', '--host', '127.0.0.1', '--port', PORT, '--strictPort'], {
    stdio: 'inherit',
  });

  try {
    await waitForServer(BASE_URL);
    console.log(`[KAN-446] Server is ready at ${BASE_URL}. Launching Chromium...`);

    const browser = await chromium.launch({
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    });

    try {
      for (const vp of VIEWPORTS) {
        console.log(`\nCapturing ${vp.filename} (${vp.width}x${vp.height}, theme=${vp.theme})...`);
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          colorScheme: vp.theme,
          deviceScaleFactor: 1,
        });

        const page = await context.newPage();
        page.on('console', (msg) => console.log('[Browser Console]', msg.type(), msg.text()));
        page.on('pageerror', (err) => console.log('[Browser Error]', err.message));
        page.on('response', (res) => { if (!res.ok()) console.log('[HTTP Error]', res.status(), res.url()); });

        // Intercept API routes
        await page.route('**/api/v1/setup/status', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ initialized: true, is_initialized: true }),
          });
        });

        await page.route('**/api/v1/auth/session', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              is_authenticated: true,
              user: {
                id: 'u-admin',
                handle: 'admin',
                display_name: 'Security Admin',
                is_server_admin: true,
                is_workspace_admin: true,
              },
            }),
          });
        });

        await page.route('**/api/v1/auth/me', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: 'u-admin',
              handle: 'admin',
              display_name: 'Security Admin',
              is_server_admin: true,
              is_workspace_admin: true,
            }),
          });
        });

        await page.route('**/api/v1/admin/auth-cards', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              cards: [
                {
                  id: 'c-okta',
                  provider_kind: 'OIDC',
                  slug: 'okta',
                  display_name: 'Okta Enterprise SSO',
                  button_subtext: 'Workforce IDP',
                  icon_preset: 'shield',
                  is_enabled: true,
                  sort_rank: '1',
                  auto_provision_users: true,
                  allowed_email_domains: ['example.com'],
                  has_secret: true,
                  dek_kid: 'dek-1',
                  last_health_status: 'HEALTHY',
                  last_handshake_at: '2026-11-26T15:00:00Z',
                  check_summary: 'Handshake healthy (42ms)',
                  latency_ms: 42,
                  public_config: { issuer_url: 'https://idp.example.com', client_id: 'client-okta' },
                },
                {
                  id: 'c-local',
                  provider_kind: 'LOCAL',
                  slug: 'local',
                  display_name: 'Local Admin Credentials',
                  button_subtext: 'Emergency Break-Glass',
                  icon_preset: 'key',
                  is_enabled: true,
                  sort_rank: '2',
                  auto_provision_users: false,
                  allowed_email_domains: [],
                  has_secret: false,
                  dek_kid: null,
                  last_health_status: 'HEALTHY',
                  last_handshake_at: null,
                  check_summary: 'Native Local Storage',
                  latency_ms: 1,
                  public_config: {},
                },
              ],
            }),
          });
        });

        await page.route('**/api/v1/admin/principals*', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([]),
          });
        });

        await page.route('**/api/v1/admin/rbac/roles*', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([]),
          });
        });

        await page.route('**/api/v1/system/status', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ deployment_mode: 'multi_container', version: '0.1.0' }),
          });
        });

        // Navigate to Authentication Studio
        await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });

        // Apply theme data attribute
        await page.evaluate((theme) => {
          document.documentElement.setAttribute('data-theme', theme);
          localStorage.setItem('theme', theme);
        }, vp.theme);

        // Wait for doc link to be visible
        await page.waitForSelector('[data-testid="auth-studio-doc-link"]', { state: 'visible', timeout: 10000 });
        await page.waitForTimeout(500);

        const outPath = path.join(OUT_DIR, vp.filename);
        await page.screenshot({ path: outPath, fullPage: false });
        console.log(`Saved screenshot: ${outPath}`);

        await context.close();
      }
      console.log('\nAll 6 screenshots captured successfully!');
    } finally {
      await browser.close();
    }
  } finally {
    server.kill();
  }
}

main().catch((err) => {
  console.error('Fatal error during screenshot capture:', err);
  process.exit(1);
});
