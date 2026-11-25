// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

let chromium;
try {
  ({ chromium } = await import('/home/adamoutler/.npm/_npx/81bbc6515d992ace/node_modules/playwright/index.mjs'));
} catch {
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    ({ chromium } = await import('@playwright/test'));
  }
}

const PORT = 18407;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-407/screenshots');

const UNCLIPPED_CSS = `
  .kb-app-shell, .kb-main-canvas {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
  }
  .kb-topbar, header {
    position: static !important;
  }
`;

async function applyUnclippedStyle(page) {
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('.kb-app-shell, .kb-main-canvas')) {
      el.style.setProperty('height', 'auto', 'important');
      el.style.setProperty('max-height', 'none', 'important');
      el.style.setProperty('overflow', 'visible', 'important');
    }
    for (const el of document.querySelectorAll('.kb-topbar, header')) {
      el.style.setProperty('position', 'static', 'important');
    }
  });
}

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
    const method = route.request().method();

    if (!url.includes('/api/')) {
      return route.continue();
    }

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
          aal_level: 2,
          auth_aal: 'aal2',
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
          aal_level: 2,
          aal2_active: true,
          aal2_expires_at: new Date(Date.now() + 890_000).toISOString(),
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

    if (url.includes('/api/v1/admin/auth-cards') && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          cards: state.cards,
        }),
      });
    }

    if (url.includes('/api/v1/admin/principals')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'usr_admin_test_1',
            username: 'admin',
            email: 'admin@kanban.local',
            display_name: 'System Administrator',
            is_active: true,
            is_server_admin: true,
            created_at: new Date().toISOString(),
          },
          {
            id: 'usr_dev_1',
            username: 'alice',
            email: 'alice@example.com',
            display_name: 'Alice Developer',
            is_active: true,
            is_server_admin: false,
            created_at: new Date().toISOString(),
          },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/rbac/roles') && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'role-admin',
            slug: 'admin',
            name: 'Administrator',
            color_hex: '#e11d48',
            description: 'Full workspace and system administration',
            is_system: true,
            permissions: [
              'workspace:read', 'workspace:write', 'workspace:delete',
              'issue:read', 'issue:write', 'issue:delete',
              'field:read', 'field:write', 'field:delete',
            ],
          },
          {
            id: 'role-developer',
            slug: 'developer',
            name: 'Developer',
            color_hex: '#2563eb',
            description: 'Active project contributor',
            is_system: false,
            permissions: [
              'workspace:read',
              'issue:read', 'issue:write',
              'field:read',
            ],
          },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/rbac/roles') && url.includes('/permissions') && method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          permissions: ['workspace:read', 'issue:read', 'field:read'],
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

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
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
      executablePath: '/home/adamoutler/.cache/ms-playwright/chromium-1255/chrome-linux64/chrome',
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });

    const initialCards = [
      {
        id: 'card-local-1',
        provider_kind: 'LOCAL_ADMIN',
        slug: 'local-admin',
        display_name: 'Local Administrator',
        button_subtext: 'Built-in Superuser Password Auth',
        icon_preset: 'shield',
        is_enabled: true,
        sort_rank: '001',
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
        sort_rank: '002',
        auto_provision_users: true,
        allowed_email_domains: ['corp.example.com'],
        has_secret: true,
        dek_kid: 'dek-oidc',
        last_health_status: 'HEALTHY',
        latency_ms: 38,
        public_config: {
          client_id: 'enterprise-client-id-xyz.apps.googleusercontent.com',
          issuer: 'https://accounts.google.com',
        },
      },
    ];

    // -------------------------------------------------------------
    // Viewport 1: 01-desktop-1440x900-light
    // Shows Auth Studio Auth Cards + Drawer open with LDAP AD preset,
    // masked password input (.kb-masked-api-key), clean toggles
    // -------------------------------------------------------------
    {
      console.log('Capturing 01-desktop-1440x900-light...');
      const context = await browser.newContext({
        bypassCSP: true,
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      const state = { cards: JSON.parse(JSON.stringify(initialCards)) };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Assert 100vh layout before un-clipping
      const initialHeight = await page.evaluate(() => window.innerHeight);
      if (initialHeight !== 900) {
        throw new Error(`Viewport height mismatch: expected 900, got ${initialHeight}`);
      }

      // Open Add Auth Card drawer
      const addBtn = page.locator('.auth-studio-add-btn').first();
      await addBtn.waitFor({ state: 'visible', timeout: 5000 });
      await addBtn.click();

      const drawer = page.locator('.auth-editor-drawer');
      await drawer.waitFor({ state: 'visible', timeout: 5000 });

      // Select LDAP provider
      const providerSelect = page.locator('#card-provider-kind');
      await providerSelect.waitFor({ state: 'visible' });
      await providerSelect.selectOption('LDAP');

      // Click Active Directory preset button
      const adPresetBtn = page.locator('.auth-preset-btn', { hasText: 'Active Directory' });
      if (await adPresetBtn.count()) {
        await adPresetBtn.click();
      }

      // Fill in server URL & bind credentials
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
        await passInput.fill('HardenedAdBindPassword!2026');
      }

      await page.waitForTimeout(400);

      // Apply unclipped CSS per requirement
      await applyUnclippedStyle(page);

      await page.screenshot({
        path: path.join(OUT_DIR, '01-desktop-1440x900-light.png'),
        fullPage: true,
      });

      await context.close();
    }

    // -------------------------------------------------------------
    // Viewport 2: 02-desktop-1440x900-dark
    // Shows Break-Glass Anti-Lockout Warning Modal in Dark Theme
    // -------------------------------------------------------------
    {
      console.log('Capturing 02-desktop-1440x900-dark...');
      const context = await browser.newContext({
        bypassCSP: true,
        viewport: { width: 1440, height: 900 },
        colorScheme: 'dark',
      });
      const page = await context.newPage();
      // Only 1 card so it is the sole active admin card
      const state = {
        cards: [
          {
            id: 'card-local-sole',
            provider_kind: 'LOCAL_ADMIN',
            slug: 'local-admin',
            display_name: 'Local Administrator',
            button_subtext: 'Built-in Superuser Password Auth',
            icon_preset: 'shield',
            is_enabled: true,
            sort_rank: '001',
            auto_provision_users: false,
            allowed_email_domains: [],
            has_secret: true,
            dek_kid: null,
            last_health_status: 'HEALTHY',
            latency_ms: 1,
            public_config: {},
          },
        ],
      };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
      });

      const initialHeight = await page.evaluate(() => window.innerHeight);
      if (initialHeight !== 900) {
        throw new Error(`Viewport height mismatch: expected 900, got ${initialHeight}`);
      }

      // Find toggle switch on the card to trigger break-glass warning
      const toggleSwitch = page.locator('.auth-toggle-switch').first();
      await toggleSwitch.waitFor({ state: 'visible', timeout: 5000 });
      await toggleSwitch.click();

      // Verify break-glass warning modal appears
      const breakGlassModal = page.locator('[data-testid="break-glass-warning-dialog"]');
      await breakGlassModal.waitFor({ state: 'visible', timeout: 5000 });

      await page.waitForTimeout(400);

      // Apply unclipped CSS per requirement
      await applyUnclippedStyle(page);

      await page.screenshot({
        path: path.join(OUT_DIR, '02-desktop-1440x900-dark.png'),
        fullPage: true,
      });

      await context.close();
    }

    // -------------------------------------------------------------
    // Viewport 3: 03-desktop-1024x768
    // Shows Roles & Permissions tab (RbacPolicyBuilder) with bulk
    // quick-actions, auto-slug input, single mounted panel, no + Add User
    // -------------------------------------------------------------
    {
      console.log('Capturing 03-desktop-1024x768...');
      const context = await browser.newContext({
        bypassCSP: true,
        viewport: { width: 1024, height: 768 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      const state = { cards: JSON.parse(JSON.stringify(initialCards)) };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      const initialHeight = await page.evaluate(() => window.innerHeight);
      if (initialHeight !== 768) {
        throw new Error(`Viewport height mismatch: expected 768, got ${initialHeight}`);
      }

      // Click on "Roles & Permissions" tab
      const rolesTabBtn = page.locator('[data-testid="tab-roles"]');
      await rolesTabBtn.waitFor({ state: 'visible', timeout: 5000 });
      await rolesTabBtn.click();

      // Wait for RbacPolicyBuilder and bulk actions toolbar
      const rbacBuilder = page.locator('[data-testid="rbac-policy-builder"]');
      await rbacBuilder.waitFor({ state: 'visible', timeout: 5000 });

      const quickActions = page.locator('[data-testid="rbac-quick-actions-workspace"]');
      await quickActions.waitFor({ state: 'visible', timeout: 5000 });

      // Click "create new" role to showcase modal & auto-slug generation
      const openCreateBtn = page.locator('[data-testid="rbac-open-create-role"]');
      await openCreateBtn.waitFor({ state: 'visible', timeout: 5000 });
      await openCreateBtn.click();

      // Fill in new role name to showcase auto-slug generation
      const newRoleNameInput = page.locator('[data-testid="rbac-new-role-name"]');
      await newRoleNameInput.waitFor({ state: 'visible', timeout: 5000 });
      await newRoleNameInput.fill('Security Auditor Lead');

      await page.waitForTimeout(400);

      // Apply unclipped CSS per requirement
      await applyUnclippedStyle(page);

      await page.screenshot({
        path: path.join(OUT_DIR, '03-desktop-1024x768.png'),
        fullPage: true,
      });

      await context.close();
    }

    // -------------------------------------------------------------
    // Viewport 4: 04-tablet-portrait-768x1024
    // Shows OIDC Auth Card edit drawer with copyable callback URI
    // and localhost origin warning callout
    // -------------------------------------------------------------
    {
      console.log('Capturing 04-tablet-portrait-768x1024...');
      const context = await browser.newContext({
        bypassCSP: true,
        viewport: { width: 768, height: 1024 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      const state = { cards: JSON.parse(JSON.stringify(initialCards)) };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      const initialHeight = await page.evaluate(() => window.innerHeight);
      if (initialHeight !== 1024) {
        throw new Error(`Viewport height mismatch: expected 1024, got ${initialHeight}`);
      }

      // Click Edit on Google Workspace OIDC card
      const editOidcBtn = page.locator('[data-testid="auth-card-row-google-workspace"] button:has-text("Edit")');
      await editOidcBtn.waitFor({ state: 'visible', timeout: 5000 });
      await editOidcBtn.click();

      // Drawer is open
      const drawer = page.locator('.auth-editor-drawer');
      await drawer.waitFor({ state: 'visible', timeout: 5000 });

      // Verify localhost warning is visible
      const localhostWarn = page.locator('[data-testid="oidc-localhost-warning"]');
      await localhostWarn.waitFor({ state: 'visible', timeout: 5000 });

      await page.waitForTimeout(400);

      // Apply unclipped CSS per requirement
      await applyUnclippedStyle(page);

      await page.screenshot({
        path: path.join(OUT_DIR, '04-tablet-portrait-768x1024.png'),
        fullPage: true,
      });

      await context.close();
    }

    // -------------------------------------------------------------
    // Viewport 5: 05-mobile-portrait-390x844
    // Shows mobile responsive view of Auth Studio with realtime chip
    // -------------------------------------------------------------
    {
      console.log('Capturing 05-mobile-portrait-390x844...');
      const context = await browser.newContext({
        bypassCSP: true,
        viewport: { width: 390, height: 844 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      const state = { cards: JSON.parse(JSON.stringify(initialCards)) };
      await setupInterceptions(page, state);

      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      const initialHeight = await page.evaluate(() => window.innerHeight);
      if (initialHeight !== 844) {
        throw new Error(`Viewport height mismatch: expected 844, got ${initialHeight}`);
      }

      // Ensure cards list is visible
      const cardsList = page.locator('.auth-studio-list');
      await cardsList.waitFor({ state: 'visible', timeout: 5000 });

      await page.waitForTimeout(400);

      // Apply unclipped CSS per requirement
      await applyUnclippedStyle(page);

      await page.screenshot({
        path: path.join(OUT_DIR, '05-mobile-portrait-390x844.png'),
        fullPage: true,
      });

      await context.close();
    }

    await browser.close();
    console.log('All 5 screenshots captured successfully!');
  } finally {
    previewProc.kill();
  }
}

main().catch((err) => {
  console.error('Fatal error capturing screenshots:', err);
  process.exit(1);
});
