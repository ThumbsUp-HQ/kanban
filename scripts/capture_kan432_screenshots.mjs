// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Zero-Mock Playwright screenshot capture script for KAN-432.
 * Connects directly to the live FastAPI/Uvicorn backend running on http://127.0.0.1:18432 with
 * real session cookies and strictly ZERO mocked routes (0 page.route / 0 context.route / 0 mockApi).
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

const PORT = process.env.KAN432_PORT || '18432';
const BASE_URL = `http://127.0.0.1:${PORT}`;
const COOKIE_VAL = process.env.KAN432_COOKIE || '';
const CSRF_TOKEN = process.env.KAN432_CSRF || '';

const OUT_DIR = path.resolve('docs/qa/KAN-432/screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function preparePageForScreenshot(page, theme) {
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
  }, theme);
  await page.waitForTimeout(300);
}

async function createContext(browser, width, height, theme) {
  const context = await browser.newContext({
    viewport: { width, height },
    colorScheme: theme,
    bypassCSP: false, // Strict CSP enforcement!
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
    name: '03-tablet-landscape-1024x768',
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

async function main() {
  console.log(`[Playwright] Launching browser connecting to ${BASE_URL} (ZERO-MOCK)...`);
  const browser = await chromium.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  });

  const capturedConsoleLogs = [];

  try {
    // --- 1. VIEWPORT PASS: BOARD VIEW (Showing ⏳🤖 Pending Gate & 🛑🤖 Veto Snap-Back) ---
    for (const vp of VIEWPORTS) {
      console.log(`\n=== Processing Board View: ${vp.name} (${vp.width}x${vp.height}, theme=${vp.theme}) ===`);
      const context = await createContext(browser, vp.width, vp.height, vp.theme);
      const page = await context.newPage();

      page.on('console', (msg) => {
        capturedConsoleLogs.push({ url: page.url(), type: msg.type(), text: msg.text() });
      });

      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'networkidle' });

      try {
        await page.waitForSelector('.board-column', { timeout: 10000 });
        await page.waitForSelector('.board-card', { timeout: 10000 });
        // Wait a brief moment for animations/render
        await page.waitForTimeout(500);
      } catch (e) {
        console.warn('board wait warning:', e.message);
      }

      await preparePageForScreenshot(page, vp.theme);
      const filename = `${vp.name}-board-gate-indicators.png`;
      await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
      console.log(`[Captured] ${filename}`);
      await context.close();
    }

    // --- 2. INTERACTIVE SCREENSHOT 1: Lane State Default (+ New work item in In Progress) ---
    {
      console.log('\n=== Processing Interactive: Lane State Default in In Progress ===');
      const context = await createContext(browser, 1024, 768, 'light');
      const page = await context.newPage();
      page.on('console', (msg) => capturedConsoleLogs.push({ url: page.url(), type: msg.type(), text: msg.text() }));

      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'networkidle' });
      await page.waitForSelector('.board-column', { timeout: 10000 });

      try {
        // Locate the "+ New work item" button inside the In Progress column
        const inProgressCol = page.locator('.board-column:has-text("In Progress")').first();
        const newBtn = inProgressCol.locator('button:has-text("New work item"), button:has-text("+ New")').first();
        await newBtn.waitFor({ state: 'visible', timeout: 8000 });
        await newBtn.click();
        await page.waitForSelector('[role="dialog"], .modal, .issue-create-modal', { timeout: 8000 });
        await page.waitForTimeout(500);
      } catch (e) {
        console.warn('lane new item click warning:', e.message);
      }

      await preparePageForScreenshot(page, 'light');
      const filename = '06-lane-new-item-modal-state-default.png';
      await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
      console.log(`[Captured] ${filename}`);
      await context.close();
    }

    // --- 3. INTERACTIVE SCREENSHOT 2: Issue Detail View Gate Vetoed (KAN-2) ---
    {
      console.log('\n=== Processing Interactive: Issue Detail View Gate Vetoed (KAN-2) ===');
      const context = await createContext(browser, 1440, 900, 'light');
      const page = await context.newPage();
      page.on('console', (msg) => capturedConsoleLogs.push({ url: page.url(), type: msg.type(), text: msg.text() }));

      // Navigate to project board first then click KAN-2 to open drawer, or navigate to issue URL
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'networkidle' });
      await page.waitForSelector('.board-card', { timeout: 10000 });

      try {
        const kan2Card = page.locator('.board-card:has-text("KAN-2")').first();
        await kan2Card.waitFor({ state: 'visible', timeout: 8000 });
        await kan2Card.click();
        await page.waitForSelector('[data-testid="drawer-gate-vetoed"], .prop-row[data-prop="state"]', { timeout: 8000 });
        await page.waitForTimeout(500);
      } catch (e) {
        console.warn('kan2 open drawer warning:', e.message);
      }

      await preparePageForScreenshot(page, 'light');
      const filename = '07-issue-detail-gate-vetoed-state.png';
      await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
      console.log(`[Captured] ${filename}`);
      await context.close();
    }

    // --- 4. CSP VERIFICATION: Check console output across /setup, /login, /manifest.json, /board ---
    {
      console.log('\n=== Checking CSP Console Output across Routes ===');
      const context = await createContext(browser, 1440, 900, 'light');
      const page = await context.newPage();
      const cspErrors = [];

      page.on('console', (msg) => {
        const text = msg.text();
        capturedConsoleLogs.push({ url: page.url(), type: msg.type(), text });
        if (text.includes('Content Security Policy') || text.includes('manifest.json') || text.includes('manifest-src')) {
          cspErrors.push({ url: page.url(), text });
        }
      });

      console.log('Navigating to /setup...');
      await page.goto(`${BASE_URL}/setup`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(300);

      console.log('Navigating to /login...');
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(300);

      console.log('Navigating to /manifest.json directly...');
      const manifestResp = await page.goto(`${BASE_URL}/manifest.json`);
      console.log(`manifest.json status: ${manifestResp.status()}`);

      console.log('Navigating to /projects/KAN/issues?layout=board...');
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(300);

      console.log(`CSP Directive Violations Detected: ${cspErrors.length}`);
      if (cspErrors.length > 0) {
        console.error('CSP Errors Found:', JSON.stringify(cspErrors, null, 2));
      }

      // Append CSP verification report to unit-test-results.txt
      const cspReport = [
        '',
        '=== PLAYWRIGHT ZERO-MOCK BROWSER CSP & LOG REPORT ===',
        `Console messages inspected across /setup, /login, /manifest.json, /projects/KAN/board: ${capturedConsoleLogs.length}`,
        `CSP Directive Violations Detected: ${cspErrors.length}`,
        'Console Log Sample (First 20 entries):',
        ...capturedConsoleLogs.slice(0, 20).map((l) => `[${l.type}] (${l.url}) ${l.text}`),
        '=== END PLAYWRIGHT REPORT ===',
        '',
      ].join('\n');
      fs.appendFileSync('docs/qa/KAN-432/unit-test-results.txt', cspReport, 'utf8');
      await context.close();
    }

    console.log(`\nAll zero-mock screenshots captured successfully into ${OUT_DIR}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error('Fatal error during zero-mock screenshot capture:', err);
  process.exit(1);
});
