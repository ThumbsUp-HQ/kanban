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

const PORT = 18995;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-389/screenshots');

const MOCK_CLIENTS = [
  {
    client_id: 'client_active_app',
    client_name: 'Cursor IDE Assistant',
    client_type: 'confidential',
    token_endpoint_auth_method: 'client_secret_basic',
    client_secret_prefix: 'kb_ocs_cur...',
    redirect_uris: [
      'https://cursor.com/callback',
      'http://127.0.0.1:4567/callback',
      'http://127.0.0.1:4568/callback',
    ],
    status: 'active',
    created_at: new Date('2026-01-01T00:00:00Z').toISOString(),
  },
  {
    client_id: 'client_pending_app',
    client_name: 'Claude Code Agent',
    client_type: 'public',
    token_endpoint_auth_method: 'none',
    redirect_uris: ['http://127.0.0.1:8920/oauth/callback'],
    status: 'suspended',
    created_at: new Date('2026-02-01T00:00:00Z').toISOString(),
  },
  {
    client_id: 'client_disabled_app',
    client_name: 'Legacy Sync Tool',
    client_type: 'public',
    token_endpoint_auth_method: 'none',
    redirect_uris: ['http://127.0.0.1:9999/callback'],
    status: 'disabled',
    created_at: new Date('2026-03-01T00:00:00Z').toISOString(),
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

    if (url.includes('/api/v1/admin/oauth-clients')) {
      if (method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_CLIENTS),
        });
      }
      if (method === 'POST') {
        const postData = route.request().postDataJSON() || {};
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            client_id: 'kb_client_gemini_dcr_9823',
            client_name: postData.client_name || 'Gemini App MCP OAuth Client',
            client_type: postData.client_type || 'confidential',
            token_endpoint_auth_method:
              postData.token_endpoint_auth_method || 'client_secret_basic',
            redirect_uris: postData.redirect_uris || [
              'https://gemini.google.com/oauth/callback',
            ],
            status: 'active',
            client_secret:
              'kb_ocs_9b7d8e2f1a3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c',
            client_secret_prefix: 'kb_ocs_9b7...',
            created_at: new Date().toISOString(),
          }),
        });
      }
      if (method === 'PATCH') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'ok' }),
        });
      }
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

    // 1. Desktop - 1440x900 - Governance Studio Table
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'dark',
      });
      const page = await context.newPage();
      await setupPageInterceptions(page);
      await page.goto(`${BASE_URL}/admin/oauth`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(600);
      console.log('Current URL:', page.url());
      console.log('Body HTML preview:', (await page.locator('body').innerHTML()).slice(0, 500));

      await page.screenshot({
        path: path.join(OUT_DIR, '01-desktop-oauth-governance-studio.png'),
        fullPage: false,
      });
      console.log('Saved 01-desktop-oauth-governance-studio.png');

      // 2. Open Register Modal - select Confidential client
      await page.click('[data-testid="register-client-btn"]');
      await page.waitForTimeout(400);

      await page.fill('[data-testid="input-client-name"]', 'Gemini App MCP OAuth Client');
      await page.selectOption('[data-testid="select-client-type"]', 'confidential');
      await page.selectOption('[data-testid="select-auth-method"]', 'client_secret_basic');
      await page.fill(
        '[data-testid="input-redirect-uris"]',
        'https://gemini.google.com/oauth/callback\nhttp://127.0.0.1:8920/oauth/callback'
      );
      await page.waitForTimeout(400);

      await page.screenshot({
        path: path.join(OUT_DIR, '02-desktop-register-confidential-client-modal.png'),
        fullPage: false,
      });
      console.log('Saved 02-desktop-register-confidential-client-modal.png');

      // 3. Submit registration to view one-time client_secret panel
      await page.click('[data-testid="submit-register-btn"]');
      await page.waitForSelector('[data-testid="client-secret-panel"]');
      await page.waitForTimeout(400);

      await page.screenshot({
        path: path.join(OUT_DIR, '03-desktop-one-time-client-secret-panel.png'),
        fullPage: false,
      });
      console.log('Saved 03-desktop-one-time-client-secret-panel.png');

      // Close modal
      await page.click('[data-testid="done-register-btn"]');
      await page.waitForTimeout(400);

      // 4. Open Edit Redirect URIs modal on Cursor IDE Assistant
      await page.click('[data-testid="edit-uris-btn-client_active_app"]');
      await page.waitForSelector('[data-testid="edit-uris-modal"]');
      await page.waitForTimeout(400);

      await page.screenshot({
        path: path.join(OUT_DIR, '04-desktop-edit-redirect-uris-modal.png'),
        fullPage: false,
      });
      console.log('Saved 04-desktop-edit-redirect-uris-modal.png');

      await context.close();
    }

    // 5 & 6. Tablet - 768x1024
    {
      const context = await browser.newContext({
        viewport: { width: 768, height: 1024 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupPageInterceptions(page);
      await page.goto(`${BASE_URL}/admin/oauth`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(600);
      console.log('Current URL:', page.url());
      console.log('Body HTML preview:', (await page.locator('body').innerHTML()).slice(0, 500));

      await page.screenshot({
        path: path.join(OUT_DIR, '05-tablet-oauth-governance-studio.png'),
        fullPage: false,
      });
      console.log('Saved 05-tablet-oauth-governance-studio.png');

      await page.click('[data-testid="register-client-btn"]');
      await page.waitForTimeout(400);
      await page.selectOption('[data-testid="select-client-type"]', 'confidential');
      await page.fill('[data-testid="input-client-name"]', 'Tablet MCP Assistant');
      await page.fill(
        '[data-testid="input-redirect-uris"]',
        'https://tablet-assistant.local/callback'
      );
      await page.waitForTimeout(400);

      await page.screenshot({
        path: path.join(OUT_DIR, '06-tablet-register-confidential-client.png'),
        fullPage: false,
      });
      console.log('Saved 06-tablet-register-confidential-client.png');

      await context.close();
    }

    // 7 & 8. Mobile - 390x844
    {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
        colorScheme: 'dark',
      });
      const page = await context.newPage();
      await setupPageInterceptions(page);
      await page.goto(`${BASE_URL}/admin/oauth`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(600);
      console.log('Current URL:', page.url());
      console.log('Body HTML preview:', (await page.locator('body').innerHTML()).slice(0, 500));

      await page.screenshot({
        path: path.join(OUT_DIR, '07-mobile-oauth-governance-studio.png'),
        fullPage: false,
      });
      console.log('Saved 07-mobile-oauth-governance-studio.png');

      await page.click('[data-testid="register-client-btn"]');
      await page.waitForTimeout(400);
      await page.fill('[data-testid="input-client-name"]', 'Mobile Gemini Agent');
      await page.selectOption('[data-testid="select-client-type"]', 'confidential');
      await page.fill(
        '[data-testid="input-redirect-uris"]',
        'https://gemini.google.com/oauth/callback'
      );
      await page.click('[data-testid="submit-register-btn"]');
      await page.waitForSelector('[data-testid="client-secret-panel"]');
      await page.waitForTimeout(400);

      await page.screenshot({
        path: path.join(OUT_DIR, '08-mobile-one-time-client-secret-panel.png'),
        fullPage: false,
      });
      console.log('Saved 08-mobile-one-time-client-secret-panel.png');

      await context.close();
    }

    await browser.close();
    console.log('All Playwright screenshots captured successfully for KAN-389.');
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
