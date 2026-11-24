// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18993;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-388/screenshots');

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

      await page.goto(`${BASE_URL}/docs/feature-comparison`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1000);

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, vp.theme);

      // Scroll to Section 5: Orchestration, Provenance & Day-2 Operations
      const heading = await page.getByRole('heading', {
        name: /5\. Orchestration, Provenance & Day-2 Operations/i,
      });
      if (heading) {
        await heading.scrollIntoViewIfNeeded();
        await page.waitForTimeout(600);
      }

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);

      if (vp.alias) {
        const aliasPath = path.join(OUT_DIR, `${vp.alias}.png`);
        fs.copyFileSync(outPath, aliasPath);
        console.log(`  -> Saved alias ${aliasPath}`);
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
