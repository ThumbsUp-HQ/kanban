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

const PORT = 18996;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-400/screenshots');

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
    name: '03-tablet-1024x768',
    alias: '1024x768-tablet',
    width: 1024,
    height: 768,
    theme: 'light',
  },
  {
    name: '04-tablet-portrait-768x1024',
    alias: '768x1024-tablet-portrait',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: '05-mobile-390x844',
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

    if (url.includes('/api/v1/admin/workspace-settings')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ air_gap_mode: false }),
      });
    }

    if (
      url.includes('/api/v1/admin/ai/providers/probe-models') ||
      url.includes('/api/v1/admin/ai/providers/test-connection')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          latency_ms: 38,
          models: ['gpt-4o', 'gpt-4o-mini', 'o1-preview'],
          model_count: 3,
        }),
      });
    }

    if (url.includes('/api/v1/admin/ai/providers')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'prov_openai_primary',
            provider_kind: 'openai',
            display_name: 'OpenAI Production Tier',
            base_url: 'https://api.openai.com/v1',
            model_allowlist: ['gpt-4o', 'gpt-4o-mini'],
            residency_tier: 'cloud_standard',
            priority: 1,
            settings: {},
            api_key_set: true,
            is_enabled: true,
          },
          {
            id: 'prov_ollama_local',
            provider_kind: 'ollama',
            display_name: 'Local Ollama Llama 3',
            base_url: 'http://127.0.0.1:11434',
            model_allowlist: ['llama3:latest'],
            residency_tier: 'local_only',
            priority: 2,
            settings: {},
            api_key_set: false,
            is_enabled: true,
          },
        ]),
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

      await page.goto(`${BASE_URL}/admin/ai`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(500);

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, vp.theme);

      // Open drawer via Register Provider button
      const registerBtn = page.locator('[data-testid="register-provider-btn"]');
      await registerBtn.waitFor({ state: 'visible', timeout: 10000 });
      await registerBtn.click();

      // Wait for drawer and inputs
      const nameInput = page.locator('[data-testid="provider-name-input"]');
      const keyInput = page.locator('[data-testid="provider-key-input"]');
      await nameInput.waitFor({ state: 'visible', timeout: 5000 });
      await keyInput.waitFor({ state: 'visible', timeout: 5000 });

      // Fill in details
      await nameInput.fill('OpenAI GPT-4o Production');
      await keyInput.fill('sk-proj-testSecretApiKey123456789Production');
      await page.waitForTimeout(300);

      // Verify zero password inputs exist
      const passwordInputs = await page.locator('input[type="password"]').count();
      if (passwordInputs !== 0) {
        throw new Error(`CRITICAL: Found ${passwordInputs} input[type="password"] elements! KAN-400 requires 0.`);
      }

      // Capture masked screenshot
      const outPathMasked = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPathMasked, fullPage: false });
      console.log(`  -> Saved masked ${outPathMasked}`);

      if (vp.alias) {
        const aliasPath = path.join(OUT_DIR, `${vp.alias}.png`);
        fs.copyFileSync(outPathMasked, aliasPath);
        console.log(`  -> Saved alias ${aliasPath}`);
      }

      // Also save explicit masked name
      const explicitMaskedPath = path.join(OUT_DIR, `${vp.name}-masked.png`);
      fs.copyFileSync(outPathMasked, explicitMaskedPath);

      // Toggle to revealed state
      const toggleBtn = page.locator('button[aria-label="Show secret key"]');
      if (await toggleBtn.isVisible()) {
        await toggleBtn.click();
        await page.waitForTimeout(300);

        const outPathRevealed = path.join(OUT_DIR, `${vp.name}-revealed.png`);
        await page.screenshot({ path: outPathRevealed, fullPage: false });
        console.log(`  -> Saved revealed ${outPathRevealed}`);
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
