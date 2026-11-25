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

const PORT = 18991;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-417/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900-light-mcp-mint-modal-segmented-selectors',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    name: '02-desktop-1440x900-dark-connect-oauth-modal',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    name: '03-desktop-1024x768-workload-oidc-presets',
    width: 1024,
    height: 768,
    theme: 'light',
  },
  {
    name: '04-tablet-portrait-768x1024-oauth-governance-advanced',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: '05-mobile-portrait-390x844-device-activate',
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
          aal2_active: true,
          aal2_expires_at: new Date(Date.now() + 900_000).toISOString(),
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
          aal2_expires_at: new Date(Date.now() + 900_000).toISOString(),
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

    if (url.includes('/api/v1/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'proj_kan', identifier: 'KAN', key: 'KAN', name: 'Core Kanban' },
          { id: 'proj_ops', identifier: 'OPS', key: 'OPS', name: 'DevOps & Infra' },
        ]),
      });
    }

    if (url.includes('/api/v1/mcp-keys') || url.includes('/api/v1/admin/mcp-keys')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'key_1',
            label: 'Local Antigravity CLI',
            display_hint: 'a8f1',
            surface: 'agent',
            scope_tier: 'workspace',
            scopes: ['agent:read', 'agent:write'],
            allowed_projects: null,
            capability_mask: 31,
            allowed_cidrs: [],
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
            last_used_at: new Date().toISOString(),
            revoked_at: null,
          },
          {
            id: 'key_2',
            label: 'CI/CD Readonly Documentation Bot',
            display_hint: '9c4d',
            surface: 'docs',
            scope_tier: 'project',
            scopes: ['docs:read'],
            allowed_projects: ['KAN'],
            capability_mask: 1,
            allowed_cidrs: ['10.0.0.0/8'],
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
            last_used_at: null,
            revoked_at: null,
          },
        ]),
      });
    }

    if (url.includes('/api/v1/auth/oauth-grants')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'grant_1',
            client_id: 'client_claude_code',
            client_name: 'Claude Code Desktop',
            surface: 'agent',
            scopes: ['agent:read', 'agent:write'],
            allowed_projects: null,
            created_at: new Date().toISOString(),
            revoked_at: null,
          },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/workload-identities')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'wl_pol_1',
            workspace_id: 'ws_default',
            name: 'GitHub Actions Production Deploy',
            description: 'Automated CD pipeline for repo thumbs-up/kanban',
            issuer: 'https://token.actions.githubusercontent.com',
            client_id: 'https://kanban.hackedyour.info',
            subject_pattern: 'repo:ThumbsUp-HQ/kanban:ref:refs/heads/main',
            required_claims_json: {},
            surface: 'agent',
            scopes: ['agent:read', 'agent:write'],
            allowed_project_ids: [],
            capability_mask: 31,
            allowed_cidrs: [],
            max_ttl_seconds: 3600,
            is_enabled: true,
            created_by_id: 'usr_admin_test_1',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/oauth-clients')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            client_id: 'client_google_gemini',
            client_name: 'Google Gemini Connected Apps',
            client_type: 'confidential',
            token_endpoint_auth_method: 'client_secret_basic',
            redirect_uris: ['https://gemini.google.com/oauth/callback'],
            status: 'active',
            client_secret_prefix: 'kb_ocs_gem...',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          {
            client_id: 'client_claude_desktop',
            client_name: 'Claude Code CLI',
            client_type: 'public',
            token_endpoint_auth_method: 'none',
            redirect_uris: ['http://127.0.0.1:8920/callback'],
            status: 'active',
            client_secret_prefix: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          {
            client_id: 'client_legacy_bot',
            client_name: 'Suspended External Bot',
            client_type: 'public',
            token_endpoint_auth_method: 'none',
            redirect_uris: ['https://legacy.example.com/oauth'],
            status: 'suspended',
            client_secret_prefix: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ]),
      });
    }

    if (url.includes('/api/v1/oauth/device/info')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          client_id: 'client_remote_agent',
          client_name: 'Headless Agent Runner CLI',
          requested_scopes: ['agent:read', 'agent:write'],
          allowed_projects: ['KAN'],
          surface: 'agent',
          expires_in: 900,
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

    // 1. Desktop 1440x900 light: McpAccessStudio Question 2 segmented role/scope pills & policy TTL badge
    {
      const vp = VIEWPORTS[0];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/settings/mcp`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Assert 100vh app shell
      const appShell = page.locator('.kb-app-shell');
      await appShell.waitFor({ state: 'visible', timeout: 5000 });

      // Click + Mint MCP Key
      const mintBtn = page.locator('[data-testid="mint-key-button"]').first();
      await mintBtn.waitFor({ state: 'visible', timeout: 5000 });
      await mintBtn.click();

      // Modal open
      const mintModal = page.locator('[data-testid="mint-modal-card"]');
      await mintModal.waitFor({ state: 'visible', timeout: 5000 });

      // Type key name
      await page.locator('[data-testid="mint-label-input"]').fill('Autonomous Security Architect');

      // Click Service Bot role pill
      await page.locator('[data-testid="role-pill-service_bot"]').click();

      // Click Single Project scope pill
      await page.locator('[data-testid="scope-tier-pill-project"]').click();

      // Open Advanced restrictions
      await page.locator('[data-testid="advanced-capability-restrictions-toggle"]').click();

      // Apply unclipped styles before screenshot
      await page.evaluate(() => {
        const style = document.createElement('style');
        style.textContent = `
          .kb-app-shell, .kb-main-canvas, .kb-snippet-modal-card { height: auto !important; max-height: none !important; overflow: visible !important; }
          .kb-topbar, header { position: static !important; }
        `;
        document.head.appendChild(style);
      });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, `${vp.name}.png`),
        fullPage: true,
      });

      await context.close();
    }

    // 2. Desktop 1440x900 dark: ConnectOAuthAppModal with responsive URL wrapping and tabs
    {
      const vp = VIEWPORTS[1];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'dark',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/settings/mcp`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
      });

      // Click Connect OAuth Application
      const connectBtn = page.locator('[data-testid="connect-oauth-app-btn"]');
      await connectBtn.waitFor({ state: 'visible', timeout: 5000 });
      await connectBtn.click();

      const modal = page.locator('[data-testid="connect-oauth-app-modal"]');
      await modal.waitFor({ state: 'visible', timeout: 5000 });

      // Switch to Gemini App tab
      await page.locator('[data-testid="tab-gemini-app"]').click();

      await page.evaluate(() => {
        const style = document.createElement('style');
        style.textContent = `
          .kb-app-shell, .kb-main-canvas, .kb-snippet-modal-card { height: auto !important; max-height: none !important; overflow: visible !important; }
          .kb-topbar, header { position: static !important; }
        `;
        document.head.appendChild(style);
      });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, `${vp.name}.png`),
        fullPage: true,
      });

      await context.close();
    }

    // 3. Desktop 1024x768 light: McpUnifiedStudio Workload OIDC 1-click IdP preset buttons
    {
      const vp = VIEWPORTS[2];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/admin/mcp`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Scroll to Workload Identity Federation
      const addWlBtn = page.locator('[data-testid="add-workload-policy-btn"]');
      await addWlBtn.waitFor({ state: 'visible', timeout: 5000 });
      await addWlBtn.click();

      const modal = page.locator('[data-testid="workload-policy-modal"]');
      await modal.waitFor({ state: 'visible', timeout: 5000 });

      // Click GitHub Actions preset
      await page.locator('[data-testid="preset-github-actions"]').click();

      await page.evaluate(() => {
        const style = document.createElement('style');
        style.textContent = `
          .kb-app-shell, .kb-main-canvas, .kb-snippet-modal-card { height: auto !important; max-height: none !important; overflow: visible !important; }
          .kb-topbar, header { position: static !important; }
        `;
        document.head.appendChild(style);
      });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, `${vp.name}.png`),
        fullPage: true,
      });

      await context.close();
    }

    // 4. Tablet 768x1024 light: OAuthClientGovernanceStudio quick-filters & advanced register parameters
    {
      const vp = VIEWPORTS[3];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/admin/oauth`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Open Register OAuth Client modal
      const regBtn = page.locator('[data-testid="register-client-btn"]');
      await regBtn.waitFor({ state: 'visible', timeout: 5000 });
      await regBtn.click();

      const modal = page.locator('[data-testid="register-client-modal"]');
      await modal.waitFor({ state: 'visible', timeout: 5000 });

      await page.locator('[data-testid="input-client-name"]').fill('Enterprise DevSecOps Runner');
      await page.locator('[data-testid="input-redirect-uris"]').fill('https://ci.corp.local/oauth/callback');
      await page.locator('[data-testid="select-client-type"]').selectOption('confidential');
      await page.locator('[data-testid="select-auth-method"]').selectOption('client_secret_post');

      // Expand Advanced parameters
      await page.locator('[data-testid="advanced-oauth-parameters-toggle"]').click();

      await page.evaluate(() => {
        const style = document.createElement('style');
        style.textContent = `
          .kb-app-shell, .kb-main-canvas, .kb-snippet-modal-card { height: auto !important; max-height: none !important; overflow: visible !important; }
          .kb-topbar, header { position: static !important; }
        `;
        document.head.appendChild(style);
      });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, `${vp.name}.png`),
        fullPage: true,
      });

      await context.close();
    }

    // 5. Mobile 390x844 light: DeviceActivatePage Base20 consonants formatting & notice banner
    {
      const vp = VIEWPORTS[4];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/oauth/device`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Enter valid code
      const input = page.locator('[data-testid="user-code-input"]');
      await input.waitFor({ state: 'visible', timeout: 5000 });
      await input.fill('BCDF-GHJK');

      await page.evaluate(() => {
        const style = document.createElement('style');
        style.textContent = `
          .kb-app-shell, .kb-main-canvas, .kb-snippet-modal-card { height: auto !important; max-height: none !important; overflow: visible !important; }
          .kb-topbar, header { position: static !important; }
        `;
        document.head.appendChild(style);
      });

      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(OUT_DIR, `${vp.name}.png`),
        fullPage: true,
      });

      await context.close();
    }

    await browser.close();
    console.log('All 5 viewports captured successfully!');
  } finally {
    previewProc.kill();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
