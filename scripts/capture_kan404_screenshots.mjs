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

const PORT = 18998;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-404/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900-light',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    name: '02-desktop-1440x900-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    name: '03-desktop-1024x768',
    width: 1024,
    height: 768,
    theme: 'light',
  },
  {
    name: '04-tablet-portrait-768x1024',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: '05-mobile-portrait-390x844',
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

async function setupInterceptions(page, state) {
  await page.route('**/*', async (route) => {
    const url = route.request().url();
    const method = route.request().method();

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

    if (url.includes('/api/v1/users/me')) {
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
          aal_level: state.isElevated ? 2 : 1,
          auth_aal: state.isElevated ? 'aal2' : 'aal1',
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
          aal_level: state.isElevated ? 2 : 1,
          aal2_active: state.isElevated,
          aal2_expires_at: state.isElevated
            ? new Date(Date.now() + 890_000).toISOString()
            : null,
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
          aal_level: state.isElevated ? 2 : 1,
          auth_aal: state.isElevated ? 'aal2' : 'aal1',
          aal2_active: state.isElevated,
          aal2_expires_at: state.isElevated
            ? new Date(Date.now() + 890_000).toISOString()
            : null,
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

    if (url.includes('/api/v1/admin/auth-cards') && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          cards: state.cards,
        }),
      });
    }

    if (url.includes('/api/v1/admin/auth-cards') && method === 'POST') {
      state.postAttempts++;
      if (!state.isElevated && state.postAttempts === 1) {
        return route.fulfill({
          status: 403,
          contentType: 'application/problem+json',
          body: JSON.stringify({
            status: 403,
            code: 'AAL2_REQUIRED',
            challenge_id: 'ch-stepup-ldap-1',
            methods: ['totp', 'webauthn'],
          }),
        });
      }

      // Elevation verified -> request replayed and saved!
      state.isElevated = true;
      const postData = JSON.parse(route.request().postData() || '{}');
      const newCard = {
        id: 'card-ldap-new',
        provider_kind: 'LDAP',
        slug: 'corporate-ldap',
        display_name: postData.display_name || postData.name || 'Corporate LDAP Directory',
        button_subtext: 'Active Directory / OpenLDAP',
        icon_preset: 'directory',
        is_enabled: true,
        sort_rank: '002',
        auto_provision_users: true,
        allowed_email_domains: ['corp.example.com'],
        has_secret: true,
        dek_kid: 'dek-ldap',
        last_health_status: 'HEALTHY',
        latency_ms: 18,
        public_config: postData.public_config || postData.details || {},
      };
      state.cards.push(newCard);

      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'x-kb-aal2-expires-at': new Date(Date.now() + 900_000).toISOString(),
        },
        body: JSON.stringify(newCard),
      });
    }

    if (url.includes('/api/v1/admin/principals')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (
      url.includes('/totp/verify') ||
      url.includes('/webauthn/verify') ||
      url.includes('/recovery/verify')
    ) {
      state.isElevated = true;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'x-kb-aal2-expires-at': new Date(Date.now() + 900_000).toISOString(),
        },
        body: JSON.stringify({
          ok: true,
          authenticated: true,
          aal_level: 2,
          csrf_token: 'mock-new-elevated-csrf',
        }),
      });
    }

    if (url.includes('/api/v1/auth/aal2/touch')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'x-kb-aal2-expires-at': new Date(Date.now() + 900_000).toISOString(),
        },
        body: JSON.stringify({
          aal2_active: true,
          aal2_expires_at: new Date(Date.now() + 900_000).toISOString(),
        }),
      });
    }

    if (url.includes('/api/v1/auth/aal2/drop')) {
      state.isElevated = false;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          aal2_active: false,
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

    const initialCards = [
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
      {
        id: 'card-google-1',
        provider_kind: 'OIDC',
        slug: 'google-workspace',
        display_name: 'Google Workspace OIDC',
        button_subtext: 'Enterprise SSO',
        icon_preset: 'google',
        is_enabled: true,
        sort_rank: '001',
        auto_provision_users: true,
        allowed_email_domains: ['example.com'],
        has_secret: true,
        dek_kid: 'dek-1',
        last_health_status: 'HEALTHY',
        latency_ms: 42,
        public_config: { client_id: 'mock-client-id' },
      },
    ];

    // 1. Viewport 1440x900 light: WebSudoModalHost overlaid cleanly above AuthCardEditorDrawer with typed LDAP DN intact
    {
      const vp = VIEWPORTS[0];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
      page.on('pageerror', (err) => console.log('PAGE ERROR:', err));
      page.on('requestfailed', (req) => console.log('REQ FAILED:', req.url(), req.failure()?.errorText));
      const state = {
        isElevated: false,
        postAttempts: 0,
        cards: JSON.parse(JSON.stringify(initialCards)),
      };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Open Add Auth Card drawer
      try {
        const addBtn = page.locator('.auth-studio-add-btn').first();
        await addBtn.waitFor({ state: 'visible', timeout: 5000 });
        await addBtn.click();
      } catch (err) {
        console.log('Current URL:', page.url());
        console.log('Body HTML:', (await page.locator('body').innerHTML()).slice(0, 1000));
        throw err;
      }

      // Drawer is open
      const drawer = page.locator('.auth-editor-drawer');
      await drawer.waitFor({ state: 'visible', timeout: 5000 });

      // Select LDAP provider
      const providerSelect = page.locator('#card-provider-kind');
      await providerSelect.waitFor({ state: 'visible' });
      await providerSelect.selectOption('LDAP');

      // Type LDAP details into drawer
      const nameInput = page.locator('#card-display-name');
      await nameInput.fill('Corporate Active Directory');

      const urlInput = page.locator('#card-server-url');
      if (await urlInput.count()) {
        await urlInput.fill('ldaps://ad.corp.example.com:636');
      }

      const bindDnInput = page.locator('#card-bind-dn');
      if (await bindDnInput.count()) {
        await bindDnInput.fill('cn=admin,ou=services,dc=corp,dc=example,dc=com');
      }

      const passInput = page.locator('#card-secret');
      if (await passInput.count()) {
        await passInput.fill('SecretBindPass123!');
      }

      const baseDnInput = page.locator('#card-base-dn');
      if (await baseDnInput.count()) {
        await baseDnInput.fill('ou=employees,dc=corp,dc=example,dc=com');
      }

      // Submit form -> triggers 403 AAL2_REQUIRED -> triggers WebSudoModalHost
      const saveBtn = page.locator('button[type="submit"].auth-studio-add-btn');
      await saveBtn.click();

      // WebSudo modal appears cleanly at z-index: 10050 above drawer
      const websudoModal = page.locator('[data-testid="websudo-stepup-modal"]');
      await websudoModal.waitFor({ state: 'visible', timeout: 10000 });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, '01-desktop-1440x900-light-websudo-modal-over-drawer.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 2. Viewport 1440x900 dark: active sudo pill state in AdminStudioSubnav
    {
      const vp = VIEWPORTS[1];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'dark',
      });
      const page = await context.newPage();
      page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
      page.on('pageerror', (err) => console.log('PAGE ERROR:', err));
      page.on('requestfailed', (req) => console.log('REQ FAILED:', req.url(), req.failure()?.errorText));
      const state = {
        isElevated: true,
        postAttempts: 0,
        cards: JSON.parse(JSON.stringify(initialCards)),
      };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
      });

      const sudoPill = page.locator('[data-testid="admin-sudo-pill"]');
      await sudoPill.waitFor({ state: 'visible', timeout: 5000 });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, '02-desktop-1440x900-dark-admin-sudo-pill-active.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 3. Viewport 1024x768 light: Post-replay success with replayed request creating new card
    {
      const vp = VIEWPORTS[2];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
      page.on('pageerror', (err) => console.log('PAGE ERROR:', err));
      page.on('requestfailed', (req) => console.log('REQ FAILED:', req.url(), req.failure()?.errorText));
      const state = {
        isElevated: false,
        postAttempts: 0,
        cards: JSON.parse(JSON.stringify(initialCards)),
      };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Open Add Auth Card drawer
      const addBtn = page.locator('.auth-studio-add-btn').first();
      await addBtn.waitFor({ state: 'visible', timeout: 5000 });
      await addBtn.click();

      const drawer = page.locator('.auth-editor-drawer');
      await drawer.waitFor({ state: 'visible', timeout: 5000 });

      const providerSelect = page.locator('#card-provider-kind');
      await providerSelect.waitFor({ state: 'visible' });
      await providerSelect.selectOption('LDAP');

      const nameInput = page.locator('#card-display-name');
      await nameInput.fill('Corporate Active Directory');

      const urlInput = page.locator('#card-server-url');
      if (await urlInput.count()) {
        await urlInput.fill('ldaps://ad.corp.example.com:636');
      }

      const bindDnInput = page.locator('#card-bind-dn');
      if (await bindDnInput.count()) {
        await bindDnInput.fill('cn=admin,ou=services,dc=corp,dc=example,dc=com');
      }

      const passInput = page.locator('#card-secret');
      if (await passInput.count()) {
        await passInput.fill('SecretBindPass123!');
      }

      const baseDnInput = page.locator('#card-base-dn');
      if (await baseDnInput.count()) {
        await baseDnInput.fill('ou=employees,dc=corp,dc=example,dc=com');
      }

      const saveBtn = page.locator('button[type="submit"].auth-studio-add-btn');
      await saveBtn.click();

      const websudoModal = page.locator('[data-testid="websudo-stepup-modal"]');
      await websudoModal.waitFor({ state: 'visible', timeout: 10000 });

      // Switch to TOTP tab / button if available
      const totpBtn = page.locator('[data-testid="use-totp-fallback-btn"]');
      if (await totpBtn.count() && await totpBtn.isVisible()) {
        await totpBtn.click();
      } else {
        const totpTab = page.locator('button[role="tab"]').filter({ hasText: /Authenticator/i });
        if (await totpTab.count()) {
          await totpTab.click();
        }
      }

      const codeInput = page.locator('#totp-code-input');
      await codeInput.waitFor({ state: 'visible', timeout: 5000 });
      await codeInput.fill('123456');

      const verifyBtn = page.locator('.auth-submit-btn');
      if (await verifyBtn.count() && await verifyBtn.isEnabled()) {
        await verifyBtn.click();
      }

      // Wait for modal to disappear and drawer to close upon successful replayed save
      await websudoModal.waitFor({ state: 'hidden', timeout: 10000 });
      await page.waitForTimeout(600);

      await page.screenshot({
        path: path.join(OUT_DIR, '03-desktop-1024x768-light-websudo-replay-success.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 4. Viewport 768x1024 tablet: WebSudo modal responsive layout
    {
      const vp = VIEWPORTS[3];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
      page.on('pageerror', (err) => console.log('PAGE ERROR:', err));
      page.on('requestfailed', (req) => console.log('REQ FAILED:', req.url(), req.failure()?.errorText));
      const state = {
        isElevated: false,
        postAttempts: 0,
        cards: JSON.parse(JSON.stringify(initialCards)),
      };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      const addBtn = page.locator('.auth-studio-add-btn').first();
      await addBtn.waitFor({ state: 'visible', timeout: 10000 });
      await addBtn.click();

      const drawer = page.locator('.auth-editor-drawer');
      await drawer.waitFor({ state: 'visible', timeout: 5000 });

      const providerSelect = page.locator('#card-provider-kind');
      await providerSelect.waitFor({ state: 'visible' });
      await providerSelect.selectOption('LDAP');

      const nameInput = page.locator('#card-display-name');
      await nameInput.fill('Tablet Test LDAP');

      const urlInput = page.locator('#card-server-url');
      if (await urlInput.count()) {
        await urlInput.fill('ldaps://ad.corp.example.com:636');
      }

      const bindDnInput = page.locator('#card-bind-dn');
      if (await bindDnInput.count()) {
        await bindDnInput.fill('cn=admin,ou=services,dc=corp,dc=example,dc=com');
      }

      const passInput = page.locator('#card-secret');
      if (await passInput.count()) {
        await passInput.fill('SecretBindPass123!');
      }

      const baseDnInput = page.locator('#card-base-dn');
      if (await baseDnInput.count()) {
        await baseDnInput.fill('ou=employees,dc=corp,dc=example,dc=com');
      }

      const saveBtn = page.locator('button[type="submit"].auth-studio-add-btn');
      await saveBtn.click();

      const websudoModal = page.locator('[data-testid="websudo-stepup-modal"]');
      await websudoModal.waitFor({ state: 'visible', timeout: 10000 });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, '04-tablet-portrait-768x1024-light-websudo-modal.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 5. Viewport 390x844 mobile: locked sudo pill in AdminStudioSubnav
    {
      const vp = VIEWPORTS[4];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
      page.on('pageerror', (err) => console.log('PAGE ERROR:', err));
      page.on('requestfailed', (req) => console.log('REQ FAILED:', req.url(), req.failure()?.errorText));
      const state = {
        isElevated: false,
        postAttempts: 0,
        cards: JSON.parse(JSON.stringify(initialCards)),
      };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      const sudoPill = page.locator('[data-testid="admin-sudo-pill"]');
      await sudoPill.waitFor({ state: 'visible', timeout: 5000 });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, '05-mobile-portrait-390x844-light-admin-sudo-pill-locked.png'),
        fullPage: false,
      });

      await context.close();
    }

    await browser.close();
    console.log('All 5 viewport screenshots captured successfully in docs/qa/KAN-404/screenshots/');
  } finally {
    previewProc.kill();
  }
}

main().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
