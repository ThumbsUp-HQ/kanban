// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8921';
const SESSION_COOKIE = process.env.SESSION_COOKIE || '8he88j3caSZNFWU2ktkmGF7L87BH32rHQJSvGw-_JwY.O0T3UR_uw5OgTWALPTJh88wdvuTd6GoOPE-zkrNenN8';
const OUT_DIR = path.resolve('docs/qa/KAN-343/screenshots');

const VIEWPORTS = [
  {
    name: '01-mobile-landscape-table-view',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=table`,
  },
  {
    name: '02-mobile-landscape-calendar-view',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=calendar`,
  },
  {
    name: '03-mobile-landscape-timeline-view',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=timeline`,
  },
  {
    name: '04-mobile-portrait-table-view',
    width: 390,
    height: 844,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=table`,
  },
  {
    name: '05-tablet-landscape-table-view',
    width: 1024,
    height: 768,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=table`,
  },
];

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Connecting to ${BASE_URL}...`);

  const browser = await chromium.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  for (const vp of VIEWPORTS) {
    console.log(`Capturing ${vp.name} (${vp.width}x${vp.height})...`);
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

    const page = await context.newPage();
    await page.goto(vp.url, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    const outPath = path.join(OUT_DIR, `${vp.name}.png`);
    await page.screenshot({ path: outPath, fullPage: false });
    console.log(`Saved screenshot: ${outPath} (${fs.statSync(outPath).size} bytes)`);
    await context.close();
  }

  await browser.close();
  console.log('All screenshots captured successfully.');
}

main().catch((err) => {
  console.error('Fatal error in screenshot capture:', err);
  process.exit(1);
});
