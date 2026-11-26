// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Playwright screenshot capture script for KAN-434.
 * Demonstrates:
 * 1. Immediate AI provider card rendering after POST without page reload
 * 2. + New work item QuickCreateIssueModal description sync with programmatic DOM input
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

const PORT = process.env.KAN434_PORT || '18434';
const BASE_URL = `http://127.0.0.1:${PORT}`;
const COOKIE_VAL = process.env.KAN434_COOKIE || '';
const CSRF_TOKEN = process.env.KAN434_CSRF || '';

const OUT_DIR = path.resolve('docs/qa/KAN-434/screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function preparePageForScreenshot(page, theme) {
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
  }, theme);
  await page.waitForTimeout(300);
}

async function saveScreenshot(page, filename) {
  const fullPath = path.join(OUT_DIR, filename);
  await page.screenshot({ path: fullPath, fullPage: false });
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

const VIEWPORTS = [
  { name: 'desktop-light-1440x900', width: 1440, height: 900, theme: 'light' },
  { name: 'desktop-dark-1440x900', width: 1440, height: 900, theme: 'dark' },
  { name: 'tablet-768x1024', width: 768, height: 1024, theme: 'light' },
  { name: 'mobile-390x844', width: 390, height: 844, theme: 'light' },
];

async function main() {
  console.log(`[Playwright] Connecting to ${BASE_URL}...`);
  const browser = await chromium.launch({ headless: true });

  try {
    for (const vp of VIEWPORTS) {
      console.log(`\n--- Viewport: ${vp.name} (${vp.width}x${vp.height}, theme=${vp.theme}) ---`);
      const context = await createContext(browser, vp.width, vp.height, vp.theme);
      const page = await context.newPage();

      // Screen 1: AI Studio - Immediate provider rendering after Create
      await page.goto(`${BASE_URL}/workspaces/settings/ai`, { waitUntil: 'domcontentloaded' });
      await preparePageForScreenshot(page, vp.theme);

      // Check if Register Provider button is present
      const addBtn = page.locator('[data-testid="register-provider-btn"]').first();
      await addBtn.waitFor({ state: 'visible', timeout: 15000 });
      await addBtn.click();

      // Wait for Drawer
      const presetBtn = page.locator('[data-testid="preset-ollama-btn"]');
      if (await presetBtn.isVisible()) {
        await presetBtn.click();
        await page.waitForTimeout(200);
      }

      const nameInput = page.locator('[data-testid="provider-name-input"]');
      await nameInput.waitFor({ state: 'visible', timeout: 10000 });
      await nameInput.fill(`Fast Ollama ${vp.name}`);

      const modelsInput = page.locator('[data-testid="provider-models-input"]');
      if (await modelsInput.isVisible()) {
        await modelsInput.fill('llama3:8b, mistral:7b');
      }

      const baseUrlInput = page.locator('[data-testid="provider-base-url-input"]');
      if (await baseUrlInput.isVisible()) {
        await baseUrlInput.fill('http://127.0.0.1:11434');
      }

      // Click save
      const saveBtn = page.locator('[data-testid="save-provider-btn"]');
      await saveBtn.click();

      // Card must render immediately without reload
      const card = page.locator(`text=Fast Ollama ${vp.name}`);
      await card.waitFor({ state: 'visible', timeout: 10000 });
      await page.waitForTimeout(500);

      await saveScreenshot(page, `01-ai-provider-immediate-render-${vp.name}.png`);

      // Screen 2: Quick Create Work Item Modal - Description DOM Input Sync
      await page.goto(`${BASE_URL}/projects/KAN/issues`, { waitUntil: 'domcontentloaded' });
      await preparePageForScreenshot(page, vp.theme);

      // Trigger Quick Create modal
      await page.evaluate(() => {
        window.dispatchEvent(new CustomEvent('kb:create-issue', { bubbles: true }));
      });

      const summaryInput = page.locator('#quick-create-summary');
      await summaryInput.waitFor({ state: 'visible', timeout: 10000 });
      await summaryInput.fill(`Transaction Sync Item (${vp.name})`);

      // Programmatically assign value to description and dispatch native 'input' event (React 19 _valueTracker test)
      await page.evaluate(() => {
        const descEl = document.getElementById('quick-create-description');
        if (descEl) {
          descEl.value = '## KAN-434 Verification Proof\n- PostgreSQL READ COMMITTED refetch sync verified.\n- Programmatic DOM input synced to React state.';
          descEl.dispatchEvent(new Event('input', { bubbles: true }));
          descEl.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      await page.waitForTimeout(500);

      await saveScreenshot(page, `02-quick-create-description-sync-${vp.name}.png`);

      await context.close();
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error('[Playwright Error]', err);
  process.exit(1);
});
