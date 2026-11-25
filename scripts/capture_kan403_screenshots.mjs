// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

let chromium;
try {
  ({ chromium } = await import(path.resolve('node_modules/.pnpm/playwright@1.65.0/node_modules/playwright/index.mjs')));
} catch {
  try {
    ({ chromium } = await import('/home/adamoutler/.npm/_npx/81bbc6515d992ace/node_modules/playwright/index.mjs'));
  } catch {
    ({ chromium } = await import('playwright-core'));
  }
}

const PORT = 18403;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-403/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900',
    width: 1440,
    height: 900,
  },
  {
    name: '02-desktop-1440x900-dark',
    width: 1440,
    height: 900,
  },
  {
    name: '03-tablet-landscape-1024x768',
    width: 1024,
    height: 768,
  },
  {
    name: '04-tablet-portrait-768x1024',
    width: 768,
    height: 1024,
  },
  {
    name: '05-mobile-portrait-390x844',
    width: 390,
    height: 844,
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

    if (url.includes('/api/v1/auth/session')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          mfa_pending: false,
          csrf_token: 'mock-csrf-token-12345',
          principal_id: 'usr_ws_admin_1',
          workspace_id: 'ws_default',
          aal_level: 2,
          aal2_active: true,
          aal2_expires_at: new Date(Date.now() + 890_000).toISOString(),
        }),
      });
    }

    if (url.includes('/api/v1/users/me/preferences')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          principal_id: 'usr_ws_admin_1',
          workspace_id: 'ws_default',
          agent_onboarding_prefs: {
            scope: 'local_only',
            execution_mode: 'swarm',
            model_strategy: 'quota_sipping_flash',
            qa_rigor: 'strict_forensic',
            custom_notes: '',
          },
        }),
      });
    }

    if (url.includes('/api/v1/users/me') || url.includes('/api/v1/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr_ws_admin_1',
          email: 'admin@kanban.local',
          username: 'admin',
          display_name: 'System Administrator',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'WORKSPACE_ADMIN',
          aal_level: 2,
          auth_aal: 'aal2',
          aal2_active: true,
          passkeys: [],
          totp_enabled: true,
          recovery_codes_remaining: 8,
          identities: [],
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

    if (url.includes('/api/v1/projects/KAN') || url.includes('/api/v1/projects/proj-kan-uuid')) {
      if (url.includes('/members')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      if (url.includes('/states')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      if (url.includes('/priorities')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      if (url.includes('/labels')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      if (url.includes('/custom-fields')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      if (url.includes('/integrations')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      if (url.includes('/modules')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'proj-kan-uuid',
          key: 'KAN',
          identifier: 'KAN',
          name: 'Platform Core',
          description: 'Platform Core Project',
          description_markdown: 'Platform Core Project with Dedicated Autonomous AI Agents',
          workspace_id: 'ws_default',
          modules_enabled: true,
          skip_loaded_sequence_numbers: false,
          default_module_ids: [],
          auto_archive_days: 30,
          capabilities: ['ADMIN', 'EDIT', 'READ'],
          is_project_admin: true,
        }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log(`Building web app before preview...`);
  const buildProc = spawn('pnpm', ['--dir', 'kanban/web', 'build'], { stdio: 'inherit' });
  await new Promise((resolve, reject) => {
    buildProc.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`pnpm build failed with code ${code}`));
    });
  });

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

    async function captureItem({ vp, colorScheme, url, selector, filename }) {
      console.log(`Capturing ${filename} (${vp.width}x${vp.height} ${colorScheme})...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme,
      });
      const page = await context.newPage();
      await setupInterceptions(page);
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, colorScheme);
      await page.waitForSelector(selector, { timeout: 15000 });
      await page.waitForSelector('[data-testid="copy-agent-onboarding-prompt-btn"]', { timeout: 10000 });
      await page.waitForSelector('[data-testid="save-agent-onboarding-prefs-btn"]', { timeout: 10000 });

      // Clean viewport assertions, dismiss transient fallback toast and realtime chips, and unconstrain 100vh containers for fullPage screenshot via CSP-safe class
      await page.evaluate(() => {
        document.body.classList.add('kb-screenshot-unconstrained');

        // Check horizontal bounding box
        const card = document.querySelector('[data-testid="agent-onboarding-prompt-card"]');
        if (card && card.scrollWidth > card.clientWidth + 5) {
          console.warn(`Card horizontal overflow detected: scrollWidth=${card.scrollWidth}, clientWidth=${card.clientWidth}`);
        }
      });

      const copyBtn = page.locator('[data-testid="copy-agent-onboarding-prompt-btn"]');
      const saveBtn = page.locator('[data-testid="save-agent-onboarding-prefs-btn"]');
      await copyBtn.scrollIntoViewIfNeeded();
      await saveBtn.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);

      await page.screenshot({
        path: path.join(OUT_DIR, filename),
        fullPage: true,
      });
      await context.close();
    }

    // Capture for each viewport:
    // 1. Viewport 1440x900 light
    await captureItem({
      vp: VIEWPORTS[0],
      colorScheme: 'light',
      url: `${BASE_URL}/settings/profile`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '01-personal-settings-desktop-1440x900-light.png',
    });
    await captureItem({
      vp: VIEWPORTS[0],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '01-project-settings-desktop-1440x900-light.png',
    });

    // 2. Viewport 1440x900 dark
    await captureItem({
      vp: VIEWPORTS[1],
      colorScheme: 'dark',
      url: `${BASE_URL}/settings/profile`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '02-personal-settings-desktop-1440x900-dark.png',
    });
    await captureItem({
      vp: VIEWPORTS[1],
      colorScheme: 'dark',
      url: `${BASE_URL}/projects/KAN/settings`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '02-project-settings-desktop-1440x900-dark.png',
    });

    // 3. Viewport 1024x768 Tablet Landscape
    await captureItem({
      vp: VIEWPORTS[2],
      colorScheme: 'light',
      url: `${BASE_URL}/settings/profile`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '03-personal-settings-tablet-landscape-1024x768.png',
    });
    await captureItem({
      vp: VIEWPORTS[2],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '03-project-settings-tablet-landscape-1024x768.png',
    });

    // 4. Viewport 768x1024 Tablet Portrait
    await captureItem({
      vp: VIEWPORTS[3],
      colorScheme: 'light',
      url: `${BASE_URL}/settings/profile`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '04-personal-settings-tablet-portrait-768x1024.png',
    });
    await captureItem({
      vp: VIEWPORTS[3],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '04-project-settings-tablet-portrait-768x1024.png',
    });

    // 5. Viewport 390x844 Mobile Portrait
    await captureItem({
      vp: VIEWPORTS[4],
      colorScheme: 'light',
      url: `${BASE_URL}/settings/profile`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '05-personal-settings-mobile-portrait-390x844.png',
    });
    await captureItem({
      vp: VIEWPORTS[4],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings`,
      selector: '[data-testid="agent-onboarding-prompt-card"]',
      filename: '05-project-settings-mobile-portrait-390x844.png',
    });

    await browser.close();
    console.log(`All screenshots captured successfully into ${OUT_DIR}`);
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Fatal error capturing screenshots:', err);
  process.exit(1);
});
