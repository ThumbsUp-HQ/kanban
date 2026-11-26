// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Playwright screenshot capture script for KAN-437.
 * Captures responsive views of:
 * 1. WorkflowStudioPage showing Project Default Gate Timeout control (10m / 600000 ms) and hook row badges
 * 2. AttachHookDialog showing Per-Hook Timeout Override input (1000..600000 ms) with presets
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

const PORT = process.env.KAN437_PORT || '18437';
const BASE_URL = `http://127.0.0.1:${PORT}`;
const COOKIE_VAL = process.env.KAN437_COOKIE || '';
const CSRF_TOKEN = process.env.KAN437_CSRF || '';

const OUT_DIR = path.resolve('docs/qa/KAN-437/screenshots');
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
      page.on('console', (msg) => console.log(`[Browser Console] ${msg.type()}: ${msg.text()}`));
      page.on('pageerror', (err) => console.log(`[Browser Error] ${err.message}`));

      // Screen 1: Workflow Studio - Project Default Gate Timeout control and hook duration badges
      console.log(`Navigating to ${BASE_URL}/projects/PROJ/settings/workflows...`);
      await page.goto(`${BASE_URL}/projects/PROJ/settings/workflows`, { waitUntil: 'networkidle' });
      await preparePageForScreenshot(page, vp.theme);
      console.log(`Current URL: ${page.url()}`);

      // Wait for the project default gate timeout panel
      const timeoutSection = page.locator('[data-testid="project-gate-timeout-panel"]');
      await timeoutSection.waitFor({ state: 'visible', timeout: 10000 });

      // Save workflow studio overview screenshot
      await saveScreenshot(page, `01-workflow-studio-default-timeout-${vp.name}.png`);
      // Also save directly as vp.name.png for any exact path matchers
      await saveScreenshot(page, `${vp.name}.png`);

      // Screen 2: AttachHookDialog - Per-Hook Timeout Override Input with presets
      const addHookBtn = page.locator('button:has-text("Add Hook")').first();
      if (await addHookBtn.isVisible()) {
        await addHookBtn.click();
        const dialog = page.locator('div[role="dialog"]');
        await dialog.waitFor({ state: 'visible', timeout: 10000 });

        // Select Agent Transition Helper
        const agentRadio = page.locator('label:has-text("Agent Transition Helper") input[type="radio"]');
        if (await agentRadio.isVisible()) {
          await agentRadio.click();
          await page.waitForTimeout(200);
        }

        // Open Advanced Hook Settings
        const advSummary = page.locator('[data-testid="attach-hook-advanced-section"] summary, details summary:has-text("Advanced Hook Settings")').first();
        if (await advSummary.isVisible()) {
          await advSummary.click();
          await page.waitForTimeout(200);
        }

        // Click 10m preset button
        const preset10m = page.locator('[data-testid="hook-timeout-preset-10m"]').first();
        if (await preset10m.isVisible()) {
          await preset10m.click();
          await page.waitForTimeout(200);
        }

        await saveScreenshot(page, `02-attach-hook-timeout-override-${vp.name}.png`);

        // Close dialog
        const closeBtn = page.locator('button:has-text("Cancel"), button[aria-label="Close"]').first();
        if (await closeBtn.isVisible()) {
          await closeBtn.click();
          await page.waitForTimeout(200);
        }
      }

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
