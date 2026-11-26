// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Zero-Mock Playwright screenshot capture script for KAN-431.
 * Connects directly to the live backend running on http://127.0.0.1:18431 with
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

const PORT = process.env.KAN431_PORT || '18431';
const BASE_URL = `http://127.0.0.1:${PORT}`;
const COOKIE_VAL = process.env.KAN431_COOKIE || '';
const CSRF_TOKEN = process.env.KAN431_CSRF || '';

const OUT_DIR = path.resolve('docs/qa/KAN-431/screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function preparePageForScreenshot(page, theme) {
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
      .kb-topbar, header {
        position: static !important;
      }
    `,
  });
  await page.waitForTimeout(300);
}

async function saveScreenshot(page, filename) {
  const fullPath = path.join(OUT_DIR, filename);
  await page.screenshot({ path: fullPath, fullPage: true });
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
  { name: 'desktop-light', width: 1440, height: 900, theme: 'light' },
  { name: 'desktop-dark', width: 1440, height: 900, theme: 'dark' },
  { name: '1024x768', width: 1024, height: 768, theme: 'light' },
  { name: '768x1024', width: 768, height: 1024, theme: 'light' },
  { name: '390x844', width: 390, height: 844, theme: 'light' },
];

async function main() {
  console.log(`[Playwright] Launching browser to connect to ${BASE_URL}...`);
  const browser = await chromium.launch({ headless: true });

  try {
    for (const vp of VIEWPORTS) {
      console.log(`\n--- Capturing viewport: ${vp.name} (${vp.width}x${vp.height}, theme=${vp.theme}) ---`);
      const context = await createContext(browser, vp.width, vp.height, vp.theme);
      const page = await context.newPage();

      // Screen 1: AttachHookDialog with Agent Transition Helper & top-level Agent Definition
      await page.goto(`${BASE_URL}/projects/PROJ/settings/workflows`, { waitUntil: 'domcontentloaded' });
      await preparePageForScreenshot(page, vp.theme);

      // Open Attach Hook dialog
      const attachBtn = page.locator('button:has-text("Add Hook")').first();
      await attachBtn.waitFor({ state: 'visible', timeout: 10000 });
      await attachBtn.click();

      // Click Agent Transition Helper radio
      const agentRadio = page.locator('label:has-text("Agent Transition Helper") input[type="radio"]');
      await agentRadio.waitFor({ state: 'visible', timeout: 10000 });
      await agentRadio.click();
      await page.waitForTimeout(500);

      await saveScreenshot(page, `01-attach-hook-agent-interceptor-${vp.name}.png`);

      // Close modal
      const closeBtn = page.locator('button[aria-label="Close dialog"], button:has-text("Cancel")').first();
      if (await closeBtn.isVisible()) {
        await closeBtn.click();
        await page.waitForTimeout(300);
      }

      // Screen 2: Hook Pipeline Row Card Metadata
      // Ensure we are viewing the transition cards with 180s timeout and clean repo badges
      await page.goto(`${BASE_URL}/projects/PROJ/settings/workflows`, { waitUntil: 'domcontentloaded' });
      await preparePageForScreenshot(page, vp.theme);
      await page.locator('.workflow-studio, .transition-rule-card').first().waitFor({ state: 'visible', timeout: 10000 });
      await saveScreenshot(page, `02-hook-pipeline-card-metadata-${vp.name}.png`);

      // Screen 3: Agent Definition Edit Drawer displaying custom system_instructions_md
      await page.goto(`${BASE_URL}/workspaces/settings/agents`, { waitUntil: 'domcontentloaded' });
      await preparePageForScreenshot(page, vp.theme);

      // Click Edit specifically on QA Gatekeeper row
      const qaRow = page.locator('tr:has-text("QA Gatekeeper")').filter({ has: page.locator('button:has-text("Edit")') }).first();
      const editBtn = (await qaRow.count()) > 0 ? qaRow.locator('button:has-text("Edit")').first() : page.locator('button:has-text("Edit")').first();
      await editBtn.waitFor({ state: 'visible', timeout: 10000 });
      await editBtn.click();

      // Expand Advanced section in drawer
      const advSummary = page.locator('[data-testid="advanced-model-harness-config"] summary');
      await advSummary.waitFor({ state: 'visible', timeout: 10000 });
      await advSummary.click();
      await page.waitForTimeout(300);

      // Wait for drawer and textarea, scroll into view to capture markdown instructions clearly
      const textarea = page.locator('textarea[data-testid="agent-instructions-textarea"]');
      await textarea.waitFor({ state: 'visible', timeout: 10000 });
      await textarea.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);

      await saveScreenshot(page, `03-agent-definition-edit-drawer-${vp.name}.png`);

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
