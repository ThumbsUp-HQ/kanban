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

const PORT = 18474;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-474/screenshots');

const VIEWPORTS = [
  {
    name: 'desktop-light-1440x900.png',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    name: 'desktop-dark-1440x900.png',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    name: 'tablet-768x1024.png',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: 'tablet-dark-768x1024.png',
    width: 768,
    height: 1024,
    theme: 'dark',
  },
  {
    name: 'mobile-390x844.png',
    width: 390,
    height: 844,
    theme: 'light',
  },
  {
    name: 'mobile-dark-390x844.png',
    width: 390,
    height: 844,
    theme: 'dark',
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

async function setupInterceptions(page) {
  await page.addInitScript(() => {
    class MockWS extends EventTarget {
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

  await page.route('**/*', async (route) => {
    const url = route.request().url();

    if (url.includes('/api/v1/setup/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ initialized: true, is_initialized: true, requires_setup: false }),
      });
    }

    if (url.includes('/api/v1/notifications')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, unread_count: 0 }),
      });
    }

    if (url.includes('/api/v1/users/me') || url.includes('/api/v1/auth/me')) {
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
          aal_level: 1,
          auth_aal: 'aal1',
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
          aal_level: 1,
          aal2_active: false,
          aal2_expires_at: null,
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

    if (url.includes('/api/v1/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'proj_kan', key: 'KAN', name: 'Kanban Project' },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/auth-cards')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          cards: [
            {
              id: 'card-local-1',
              provider_kind: 'LOCAL_ADMIN',
              slug: 'local-admin',
              display_name: 'Local Administrator',
              button_subtext: 'Built-in Superuser',
              icon_preset: 'shield',
              is_enabled: true,
              sort_rank: '999',
              auto_provision_users: false,
              allowed_email_domains: [],
              has_secret: true,
              dek_kid: null,
              last_health_status: 'HEALTHY',
              latency_ms: 1,
              public_config: {},
            },
          ],
        }),
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
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: vp.theme,
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, vp.theme);

      // Trigger WebSudo step-up challenge modal
      await page.evaluate(() => {
        window.dispatchEvent(
          new CustomEvent('kb:open-aal2-stepup', {
            detail: { challengeId: 'ch-stepup-qa', methods: ['totp', 'webauthn'] },
          })
        );
      });

      const modal = page.locator('[data-testid="websudo-stepup-modal"]');
      await modal.waitFor({ state: 'visible', timeout: 10000 });

      const docLink = page.locator('[data-testid="websudo-doc-link"]');
      await docLink.waitFor({ state: 'visible', timeout: 5000 });

      await page.waitForTimeout(400);

      const targetPath = path.join(OUT_DIR, vp.name);
      await page.screenshot({ path: targetPath, fullPage: false });
      console.log(`Wrote ${targetPath}`);

      await context.close();
    }

    // 7. Interaction test screenshot: doc-link-interaction-after.png
    // Desktop 1440x900 light: Click StudioDocLink and verify HelpDrawer opens beside/over WebSudo modal without breaking modal state
    {
      console.log('Capturing doc-link-interaction-after.png...');
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Trigger WebSudo step-up challenge modal
      await page.evaluate(() => {
        window.dispatchEvent(
          new CustomEvent('kb:open-aal2-stepup', {
            detail: { challengeId: 'ch-stepup-qa', methods: ['totp', 'webauthn'] },
          })
        );
      });

      const modal = page.locator('[data-testid="websudo-stepup-modal"]');
      await modal.waitFor({ state: 'visible', timeout: 10000 });

      const docLink = page.locator('[data-testid="websudo-doc-link"]');
      await docLink.waitFor({ state: 'visible', timeout: 5000 });

      // Click StudioDocLink
      await docLink.click();

      // HelpDrawer opens
      const helpDrawer = page.locator('.kb-help-drawer, [data-testid="help-drawer"]');
      await helpDrawer.waitFor({ state: 'visible', timeout: 10000 });

      // Wait a moment for transitions
      await page.waitForTimeout(500);

      const interactionPath = path.join(OUT_DIR, 'doc-link-interaction-after.png');
      await page.screenshot({ path: interactionPath, fullPage: false });
      console.log(`Wrote ${interactionPath}`);

      await context.close();
    }

    await browser.close();
    console.log('All 7 screenshots captured successfully!');
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
