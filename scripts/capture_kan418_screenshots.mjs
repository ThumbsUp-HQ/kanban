// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Zero-Mock Playwright screenshot capture script for KAN-418 (Slice 3 Phase 3).
 * Connects directly to the live backend running on http://127.0.0.1:18418 with
 * real session cookies and zero mocked routes (0 page.route / 0 mockApi).
 */

import fs from 'node:fs';
import path from 'node:path';

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

const PORT = process.env.KAN418_PORT || '18418';
const BASE_URL = `http://127.0.0.1:${PORT}`;
const COOKIE_VAL = process.env.KAN418_COOKIE || '';
const CSRF_TOKEN = process.env.KAN418_CSRF || '';

const OUT_DIRS = [
  path.resolve('docs/workouts/slice-3-mcp-oauth/screenshots'),
  path.resolve('docs/qa/KAN-418/screenshots'),
];

for (const dir of OUT_DIRS) {
  fs.mkdirSync(dir, { recursive: true });
}

async function preparePageForScreenshot(page, vp, theme) {
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
  }, theme);

  await page.addStyleTag({
    content: `
      .kb-app-shell, .kb-main-canvas {
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
      }
      .kb-snippet-modal-card {
        max-height: none !important;
      }
      .kb-topbar, header {
        position: static !important;
      }
      .realtime-status-chip {
        display: inline-flex !important;
        visibility: visible !important;
      }
    `,
  });
  await page.waitForTimeout(200);
}

async function saveScreenshot(page, filename) {
  for (const dir of OUT_DIRS) {
    const fullPath = path.join(dir, filename);
    await page.screenshot({ path: fullPath, fullPage: true });
  }
  console.log(`[Captured] ${filename}`);
}

async function createContext(browser, width, height, theme) {
  const context = await browser.newContext({
    viewport: { width, height },
    colorScheme: theme,
    bypassCSP: true,
  });

  if (COOKIE_VAL) {
    await context.addCookies([
      {
        name: 'kb_session',
        value: COOKIE_VAL,
        url: `http://127.0.0.1:${PORT}/`,
        httpOnly: true,
        sameSite: 'Lax',
      },
      {
        name: 'kb_csrf',
        value: CSRF_TOKEN,
        url: `http://127.0.0.1:${PORT}/`,
        httpOnly: false,
        sameSite: 'Lax',
      },
    ]);
  }

  return context;
}

async function main() {
  console.log(`Connecting to live Kanban application at ${BASE_URL}...`);
  const browser = await chromium.launch({ headless: true });

  try {
    // -------------------------------------------------------------------------
    // Screenshot 1: Desktop 1440x900 Light McpAccessStudio Mint Modal
    // -------------------------------------------------------------------------
    {
      const context = await createContext(browser, 1440, 900, 'light');
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/settings/mcp`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="mint-key-button"]', { timeout: 10000 });

      // Click mint key button to open mint modal
      await page.click('[data-testid="mint-key-button"]');
      await page.waitForSelector('[data-testid="mint-modal-card"]', { timeout: 5000 });

      // Fill in a descriptive label
      await page.fill('[data-testid="mint-label-input"]', 'Production CI Runner Key');

      await preparePageForScreenshot(page, { width: 1440, height: 900 }, 'light');
      await saveScreenshot(page, '01-desktop-1440x900-light-mcp-access-studio-mint-modal.png');
      await context.close();
    }

    // -------------------------------------------------------------------------
    // Screenshot 2: Desktop 1440x900 Dark ConnectOAuthAppModal
    // -------------------------------------------------------------------------
    {
      const context = await createContext(browser, 1440, 900, 'dark');
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/settings/mcp`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="connect-oauth-app-btn"], [data-testid="empty-connect-oauth-app-btn"]', { timeout: 10000 });

      const connectBtn = page.locator('[data-testid="connect-oauth-app-btn"], [data-testid="empty-connect-oauth-app-btn"]').first();
      await connectBtn.click();
      await page.waitForSelector('[data-testid="connect-oauth-app-modal"]', { timeout: 5000 });

      await preparePageForScreenshot(page, { width: 1440, height: 900 }, 'dark');
      await saveScreenshot(page, '02-desktop-1440x900-dark-connect-oauth-modal.png');
      await context.close();
    }

    // -------------------------------------------------------------------------
    // Screenshot 3: Desktop 1024x768 Light McpUnifiedStudio Workload OIDC
    // -------------------------------------------------------------------------
    {
      const context = await createContext(browser, 1024, 768, 'light');
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/mcp`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="workload-federation-section"]', { timeout: 10000 });
      await page.waitForSelector('[data-testid="workload-policies-table"]', { timeout: 10000 });

      await preparePageForScreenshot(page, { width: 1024, height: 768 }, 'light');
      await saveScreenshot(page, '03-desktop-1024x768-workload-oidc-studio.png');
      await context.close();
    }

    // -------------------------------------------------------------------------
    // Screenshot 4: Tablet Portrait 768x1024 Light OAuth Governance Bulk Purge
    // -------------------------------------------------------------------------
    {
      const context = await createContext(browser, 768, 1024, 'light');
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/oauth`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="oauth-client-governance-studio"]', { timeout: 10000 });

      // Click Purge Stale DCR button to reveal the bulk confirm bar
      const purgeBtn = page.locator('[data-testid="purge-clients-btn"]');
      if (await purgeBtn.count()) {
        await purgeBtn.click();
        await page.waitForSelector('[data-testid="purge-confirm-bar"]', { timeout: 5000 });
      }

      await preparePageForScreenshot(page, { width: 768, height: 1024 }, 'light');
      await saveScreenshot(page, '04-tablet-portrait-768x1024-oauth-client-governance-bulk-purge.png');
      await context.close();
    }

    // -------------------------------------------------------------------------
    // Screenshot 5: Mobile Portrait 390x844 Light DeviceActivatePage
    // -------------------------------------------------------------------------
    {
      const context = await createContext(browser, 390, 844, 'light');
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/activate`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="device-activate-layout"]', { timeout: 10000 });

      // Type Base20 code into input triggering vowel/confusing digit notice
      const input = page.locator('[data-testid="user-code-input"]');
      await input.fill('TWQR-A123');
      await page.waitForTimeout(300);

      await preparePageForScreenshot(page, { width: 390, height: 844 }, 'light');
      await saveScreenshot(page, '05-mobile-portrait-390x844-device-activate-page.png');
      await context.close();
    }

    // -------------------------------------------------------------------------
    // Screenshot 6: Desktop 1440x900 Light McpConfigSnippetModal
    // -------------------------------------------------------------------------
    {
      const context = await createContext(browser, 1440, 1100, 'light');
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/settings/mcp`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="mint-key-button"]', { timeout: 10000 });

      // Click mint key button, fill label and submit to reveal snippet modal
      await page.click('[data-testid="mint-key-button"]');
      await page.waitForSelector('[data-testid="mint-modal-card"]', { timeout: 5000 });
      await page.fill('[data-testid="mint-label-input"]', 'Claude Desktop Agent Key');
      await page.click('[data-testid="mint-submit-btn"]');

      // Wait for config snippet modal
      await page.waitForSelector('[data-testid="mcp-snippet-modal"]', { timeout: 8000 });

      // Redact DOM token values to ensure zero secret leakage in screenshots
      await page.evaluate(() => {
        const keyVal = document.querySelector('.kb-snippet-key-value');
        if (keyVal) {
          keyVal.textContent = 'kb_agt_***REDACTED***';
        }
        const codeBox = document.querySelector('.kb-snippet-code-box');
        if (codeBox) {
          codeBox.textContent = codeBox.textContent.replace(/kb_agt_[A-Za-z0-9_-]+/g, 'kb_agt_***REDACTED***');
        }
      });

      await preparePageForScreenshot(page, { width: 1440, height: 1100 }, 'light');
      await saveScreenshot(page, '06-desktop-1440x900-light-mcp-config-snippet-modal.png');
      await context.close();
    }

    // -------------------------------------------------------------------------
    // Screenshot 7: Desktop 1440x900 Dark OAuth Governance Paginated 500+
    // -------------------------------------------------------------------------
    {
      const context = await createContext(browser, 1440, 900, 'dark');
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/oauth`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="oauth-clients-pagination"]', { timeout: 10000 });

      await preparePageForScreenshot(page, { width: 1440, height: 900 }, 'dark');
      await saveScreenshot(page, '07-desktop-1440x900-dark-oauth-governance-paginated-500.png');
      await context.close();
    }

    console.log('All 7 zero-mock Playwright screenshots captured successfully!');
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error('Fatal error capturing screenshots:', err);
  process.exit(1);
});
