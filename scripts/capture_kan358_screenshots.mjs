// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8921';
const SESSION_COOKIE =
  process.env.SESSION_COOKIE ||
  '8he88j3caSZNFWU2ktkmGF7L87BH32rHQJSvGw-_JwY.O0T3UR_uw5OgTWALPTJh88wdvuTd6GoOPE-zkrNenN8';
const OUT_DIR = path.resolve('docs/qa/KAN-358/screenshots');

const VIEWPORTS = [
  {
    name: '01-swimlane-2d-grid-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=board&sub_group_by=priority`,
    focusSelector: '.swimlane-card',
  },
  {
    name: '02-swimlane-2d-roving-focus-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=board&sub_group_by=priority`,
    focusSelector: '.swimlane-card',
    keyPress: 'ArrowDown',
  },
  {
    name: '03-list-view-row-grid-tablet',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=list`,
    focusSelector: '.issue-list-card',
  },
  {
    name: '04-table-view-grid-mobile-landscape',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/issues?layout=table`,
    focusSelector: 'tbody tr[role="row"]',
  },
  {
    name: '05-calendar-timeline-grid-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/issues?layout=calendar`,
    focusSelector: '[role="gridcell"]',
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
    console.log(`Capturing ${vp.name} (${vp.width}x${vp.height}, theme=${vp.theme})...`);
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
      colorScheme: vp.theme,
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
    try {
      await page.goto(vp.url, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(1000);

      if (vp.theme === 'dark') {
        await page.evaluate(() => {
          document.documentElement.setAttribute('data-theme', 'dark');
          document.documentElement.classList.add('dark');
        });
      }

      if (vp.focusSelector) {
        try {
          const el = await page.$(vp.focusSelector);
          if (el) {
            await el.focus();
            if (vp.keyPress) {
              await page.keyboard.press(vp.keyPress);
            }
          }
        } catch {
          // ignore focus error if not found
        }
      }

      await page.waitForTimeout(500);

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved screenshot: ${outPath} (${fs.statSync(outPath).size} bytes)`);
    } catch (err) {
      console.warn(`Warning capturing ${vp.name}: ${err.message}`);
    } finally {
      await context.close();
    }
  }

  await browser.close();
  console.log('All screenshots captured successfully.');
}

main().catch((err) => {
  console.error('Fatal error in screenshot capture:', err);
  process.exit(1);
});
