// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18972;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const BACKEND_URL = 'http://127.0.0.1:8921';
const SESSION_COOKIE =
  '8he88j3caSZNFWU2ktkmGF7L87BH32rHQJSvGw-_JwY.O0T3UR_uw5OgTWALPTJh88wdvuTd6GoOPE-zkrNenN8';
const OUT_DIR = path.resolve('docs/qa/KAN-372/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-split-share-menu-open-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const shareBtn = await page.waitForSelector('[data-testid="split-share-btn"]');
      await shareBtn.click();
      await page.waitForSelector('[data-testid="share-export-menu"]');
      await page.waitForTimeout(300);
    },
  },
  {
    name: '02-desktop-csv-export-modal-open-light',
    width: 1440,
    height: 900,
    theme: 'light',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const shareBtn = await page.waitForSelector('[data-testid="split-share-btn"]');
      await shareBtn.click();
      const csvItem = await page.waitForSelector('[data-testid="share-export-csv"]');
      await csvItem.click();
      await page.waitForSelector('[data-testid="csv-import-export-modal"]');
      await page.waitForTimeout(300);
    },
  },
  {
    name: '03-tablet-zip-export-modal-with-password',
    width: 768,
    height: 1024,
    theme: 'dark',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const shareBtn = await page.waitForSelector('[data-testid="split-share-btn"]');
      await shareBtn.click();
      const zipItem = await page.waitForSelector('[data-testid="share-export-zip"]');
      await zipItem.click();
      await page.waitForSelector('[data-testid="csv-import-export-modal"]');
      const passInput = await page.waitForSelector('[data-testid="export-zip-password-input"]');
      await passInput.fill('super-secure-aes256-password');
      await page.waitForTimeout(300);
    },
  },
  {
    name: '04-compact-report-export-modal',
    width: 1024,
    height: 768,
    theme: 'light',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const shareBtn = await page.waitForSelector('[data-testid="split-share-btn"]');
      await shareBtn.click();
      const reportItem = await page.waitForSelector('[data-testid="share-export-report"]');
      await reportItem.click();
      await page.waitForSelector('[data-testid="report-export-backdrop"]');
      await page.waitForTimeout(300);
    },
  },
  {
    name: '05-tablet-copied-link-feedback',
    width: 768,
    height: 1024,
    theme: 'dark',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const shareBtn = await page.waitForSelector('[data-testid="split-share-btn"]');
      await shareBtn.click();
      const copyItem = await page.waitForSelector('[data-testid="share-export-copy-link"]');
      await copyItem.click();
      await page.waitForTimeout(500);
    },
  },
];

async function waitForServer(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404 || res.status === 200) {
        return true;
      }
    } catch {
      // retry
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Server failed to start at ${url} within ${timeoutMs}ms`);
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Starting preview server on port ${PORT}...`);
  const previewProc = spawn(
    'pnpm',
    ['--dir', 'kanban/web', 'exec', 'vite', 'preview', '--port', String(PORT), '--host', '127.0.0.1'],
    { stdio: 'inherit' },
  );

  try {
    await waitForServer(BASE_URL);
    console.log(`Preview server ready at ${BASE_URL}`);

    const browser = await chromium.launch({
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    });

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });

      await context.addCookies([
        {
          name: 'kb_session',
          value: SESSION_COOKIE,
          domain: '127.0.0.1',
          path: '/',
          httpOnly: true,
          sameSite: 'Lax',
        },
      ]);
      await context.grantPermissions(['clipboard-read', 'clipboard-write']);

      const page = await context.newPage();

      // Forward /api/** requests to live backend
      await page.route('**/api/**', async (route) => {
        const reqUrl = route.request().url().replace(`http://127.0.0.1:${PORT}`, BACKEND_URL);
        try {
          const headers = { ...route.request().headers() };
          headers.cookie = `kb_session=${SESSION_COOKIE}`;
          const response = await fetch(reqUrl, {
            method: route.request().method(),
            headers,
            body: route.request().postDataBuffer(),
          });
          const body = await response.arrayBuffer();
          await route.fulfill({
            status: response.status,
            headers: Object.fromEntries(response.headers.entries()),
            body: Buffer.from(body),
          });
        } catch {
          await route.abort();
        }
      });

      // Navigate to project KAN issues in split list layout with KAN-101 peeked
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=list&peek=KAN-101`, { waitUntil: 'networkidle' });

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        if (theme === 'dark') {
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
        }
        localStorage.setItem('theme', theme);
      }, vp.theme);

      if (vp.action) {
        await vp.action(page);
      }

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved screenshot to ${outPath} (${fs.statSync(outPath).size} bytes)`);

      await context.close();
    }

    await browser.close();
    console.log('All screenshots captured successfully.');
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Failed to capture screenshots:', err);
  process.exit(1);
});
