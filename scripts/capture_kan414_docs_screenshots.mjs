// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(process.cwd(), 'kanban/web/node_modules/@playwright/test'));

const PORT = 18414;
const HOST = '127.0.0.1';
const BASE_URL = `http://${HOST}:${PORT}`;
const DIST_DIR = path.resolve('kanban/web/dist');
const OUT_DIR = path.resolve('docs/qa/KAN-414/screenshots');

fs.mkdirSync(OUT_DIR, { recursive: true });

function getMimeType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  switch (ext) {
    case '.html': return 'text/html; charset=utf-8';
    case '.js':
    case '.mjs': return 'application/javascript; charset=utf-8';
    case '.css': return 'text/css; charset=utf-8';
    case '.json': return 'application/json; charset=utf-8';
    case '.png': return 'image/png';
    case '.jpg':
    case '.jpeg': return 'image/jpeg';
    case '.svg': return 'image/svg+xml';
    case '.ico': return 'image/x-icon';
    case '.woff': return 'font/woff';
    case '.woff2': return 'font/woff2';
    default: return 'application/octet-stream';
  }
}

function startSpaServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const urlPath = req.url ? req.url.split('?')[0] : '/';
      const filePath = path.join(DIST_DIR, urlPath);

      // Check if file exists directly in dist
      if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
        const mime = getMimeType(filePath);
        res.writeHead(200, { 'Content-Type': mime });
        fs.createReadStream(filePath).pipe(res);
        return;
      }

      // Check public/docs-images fallback if path starts with /docs-images/
      if (urlPath.startsWith('/docs-images/')) {
        const publicImgPath = path.join(process.cwd(), 'kanban/web/public', urlPath);
        if (fs.existsSync(publicImgPath) && fs.statSync(publicImgPath).isFile()) {
          res.writeHead(200, { 'Content-Type': getMimeType(publicImgPath) });
          fs.createReadStream(publicImgPath).pipe(res);
          return;
        }
      }

      // SPA fallback to index.html
      const indexPath = path.join(DIST_DIR, 'index.html');
      if (fs.existsSync(indexPath)) {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        fs.createReadStream(indexPath).pipe(res);
      } else {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('Not Found');
      }
    });

    server.listen(PORT, HOST, () => {
      console.log(`[SPA Server] Listening on ${BASE_URL} (serving ${DIST_DIR})`);
      resolve(server);
    });

    server.on('error', (err) => {
      reject(err);
    });
  });
}

const VIEWPORTS = [
  { suffix: '1440x900-desktop-light', width: 1440, height: 900, theme: 'light' },
  { suffix: '1440x900-desktop-dark', width: 1440, height: 900, theme: 'dark' },
  { suffix: '1024x768-tablet-landscape', width: 1024, height: 768, theme: 'light' },
  { suffix: '768x1024-tablet-portrait', width: 768, height: 1024, theme: 'light' },
  { suffix: '390x844-mobile-portrait', width: 390, height: 844, theme: 'light' },
];

async function applyTheme(page, theme) {
  await page.evaluate((t) => {
    localStorage.setItem('kb:theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(200);
}

async function main() {
  console.log('[Capture KAN-414] Starting screenshot capture run...');
  const server = await startSpaServer();
  const browser = await chromium.launch({ headless: true });

  try {
    // 1. Chapter 17: Multi-Provider AI Engine across 5 viewports
    console.log('\n=== Capturing Chapter: Multi-Provider AI Engine across 5 viewports ===');
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      try {
        await page.goto(`${BASE_URL}/docs/multi-provider-ai-engine-and-runners`, {
          waitUntil: 'networkidle',
          timeout: 30000,
        });
        await applyTheme(page, vp.theme);
        await page.waitForSelector('.kb-doc-viewer, .kb-docs-content, h1', { timeout: 10000 });
        await page.waitForTimeout(400);

        const filename = `01-multi-provider-ai-engine-${vp.suffix}.png`;
        const filePath = path.join(OUT_DIR, filename);
        await page.screenshot({ path: filePath, fullPage: false });
        console.log(`[CAPTURED] ${filename} (${fs.statSync(filePath).size} bytes)`);
      } finally {
        await context.close();
      }
    }

    // 2. Chapter 32: Studio Configuration Reference Section 8 across 5 viewports
    console.log('\n=== Capturing Chapter: Studio Config Reference Section 8 across 5 viewports ===');
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      try {
        await page.goto(`${BASE_URL}/docs/studio-configuration-reference#8-ai-providers-studio`, {
          waitUntil: 'networkidle',
          timeout: 30000,
        });
        await applyTheme(page, vp.theme);
        await page.waitForSelector('.kb-doc-viewer, .kb-docs-content, h1', { timeout: 10000 });

        // Scroll cleanly to section 8 configuration table
        await page.evaluate(() => {
          const headings = Array.from(document.querySelectorAll('h3'));
          const tableHeading = headings.find(h => h.textContent.includes('AI Providers Studio Configuration Table'));
          const target = tableHeading || document.getElementById('ai-providers-studio');
          if (target) {
            const rect = target.getBoundingClientRect();
            window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - 20), behavior: 'instant' });
          }
        });
        await page.waitForTimeout(400);

        const filename = `02-studio-config-ref-slice2-${vp.suffix}.png`;
        const filePath = path.join(OUT_DIR, filename);
        await page.screenshot({ path: filePath, fullPage: false });
        console.log(`[CAPTURED] ${filename} (${fs.statSync(filePath).size} bytes)`);
      } finally {
        await context.close();
      }
    }

    // 3. Focused shot of Mermaid diagram in Multi-Provider AI Engine (1440x900)
    console.log('\n=== Capturing Focused Mermaid Diagram (1440x900) ===');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      try {
        await page.goto(`${BASE_URL}/docs/multi-provider-ai-engine-and-runners`, {
          waitUntil: 'networkidle',
          timeout: 30000,
        });
        await applyTheme(page, 'light');

        const mermaidEl = await page.waitForSelector('svg[id^="mermaid"], .kb-mermaid-block, [data-testid*="mermaid"]', {
          timeout: 10000,
        });

        if (mermaidEl) {
          await page.evaluate((el) => {
            const canvas = document.querySelector('.media-viewport__canvas');
            if (canvas) canvas.style.paddingBottom = '140px';
            const viewport = document.querySelector('.media-viewport');
            if (viewport) viewport.style.maxHeight = '720px';
            const controls = document.querySelector('.media-viewport__controls');
            if (controls) controls.style.display = 'none'; // Avoid obscuring bottom boxes
            const rect = el.getBoundingClientRect();
            window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - 40), behavior: 'instant' });
          }, mermaidEl);
          await page.waitForTimeout(500);

          const filename = '03-slice2-mermaid-diagram-rendered-1440x900.png';
          const filePath = path.join(OUT_DIR, filename);
          await page.screenshot({ path: filePath, fullPage: false });
          console.log(`[CAPTURED] ${filename} (${fs.statSync(filePath).size} bytes)`);
        }
      } finally {
        await context.close();
      }
    }

    // 4. Scrolled shot visibly showing embedded slice2-*.png images rendered in /docs/multi-provider-ai-engine-and-runners
    console.log('\n=== Capturing Embedded slice2-*.png rendered images (1440x900) ===');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      try {
        await page.goto(`${BASE_URL}/docs/multi-provider-ai-engine-and-runners`, {
          waitUntil: 'networkidle',
          timeout: 30000,
        });
        await applyTheme(page, 'light');
        await page.waitForSelector('img[src*="slice2"], img[src*="images/"]', { timeout: 10000 });

        // Scroll to the Budget Caps section with embedded slice2 budget modal screenshots
        await page.evaluate(() => {
          const heading = document.getElementById('budget-caps') ||
                          document.querySelector('[id*="budget-caps"]');
          if (heading) {
            const rect = heading.getBoundingClientRect();
            window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - 20), behavior: 'instant' });
          } else {
            const img = document.querySelector('img[src*="slice2-ai-budget-modal"]');
            if (img) {
              const rect = img.getBoundingClientRect();
              window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - 40), behavior: 'instant' });
            }
          }
        });
        await page.waitForTimeout(500);

        const filename = '04-slice2-embedded-images-rendered-1440x900.png';
        const filePath = path.join(OUT_DIR, filename);
        await page.screenshot({ path: filePath, fullPage: false });
        console.log(`[CAPTURED] ${filename} (${fs.statSync(filePath).size} bytes)`);
      } finally {
        await context.close();
      }
    }

    // 5. Scrolled shot of Section 9: Agent Definitions Studio Table
    console.log('\n=== Capturing Section 9 Table (1440x900) ===');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      try {
        await page.goto(`${BASE_URL}/docs/studio-configuration-reference#9-agent-definitions-studio`, {
          waitUntil: 'networkidle',
          timeout: 30000,
        });
        await applyTheme(page, 'light');
        await page.waitForSelector('.kb-doc-viewer, .kb-docs-content, h1', { timeout: 10000 });

        await page.evaluate(() => {
          const headings = Array.from(document.querySelectorAll('h3'));
          const tableHeading = headings.find(h => h.textContent.includes('Agent Definitions Studio Configuration Table'));
          const target = tableHeading || document.getElementById('agent-definitions-studio');
          if (target) {
            const rect = target.getBoundingClientRect();
            window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - 20), behavior: 'instant' });
          }
        });
        await page.waitForTimeout(500);

        const filename = '05-studio-config-ref-section9-1440x900.png';
        const filePath = path.join(OUT_DIR, filename);
        await page.screenshot({ path: filePath, fullPage: false });
        console.log(`[CAPTURED] ${filename} (${fs.statSync(filePath).size} bytes)`);
      } finally {
        await context.close();
      }
    }

    // 6. Scrolled shot of Section 10: Remote Runners Studio Table
    console.log('\n=== Capturing Section 10 Table (1440x900) ===');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      try {
        await page.goto(`${BASE_URL}/docs/studio-configuration-reference#10-remote-runners-studio`, {
          waitUntil: 'networkidle',
          timeout: 30000,
        });
        await applyTheme(page, 'light');
        await page.waitForSelector('.kb-doc-viewer, .kb-docs-content, h1', { timeout: 10000 });

        await page.evaluate(() => {
          const headings = Array.from(document.querySelectorAll('h3'));
          const tableHeading = headings.find(h => h.textContent.includes('Remote Runners Studio Configuration Table'));
          const target = tableHeading || document.getElementById('remote-runners-studio');
          if (target) {
            const rect = target.getBoundingClientRect();
            window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - 20), behavior: 'instant' });
          }
        });
        await page.waitForTimeout(500);

        const filename = '06-studio-config-ref-section10-1440x900.png';
        const filePath = path.join(OUT_DIR, filename);
        await page.screenshot({ path: filePath, fullPage: false });
        console.log(`[CAPTURED] ${filename} (${fs.statSync(filePath).size} bytes)`);
      } finally {
        await context.close();
      }
    }

    // 7. Scrolled shot of Repository Access table in Multi-Provider AI Engine
    console.log('\n=== Capturing Repository Access Table (1440x900) ===');
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      try {
        await page.goto(`${BASE_URL}/docs/multi-provider-ai-engine-and-runners#repository-access`, {
          waitUntil: 'networkidle',
          timeout: 30000,
        });
        await applyTheme(page, 'light');
        await page.waitForSelector('.kb-doc-viewer, .kb-docs-content, h1', { timeout: 10000 });

        await page.evaluate(() => {
          const target = document.getElementById('repository-access') ||
                         document.querySelector('[id*="repository-access"]');
          if (target) {
            const rect = target.getBoundingClientRect();
            window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - 20), behavior: 'instant' });
          }
        });
        await page.waitForTimeout(500);

        const filename = '07-multi-provider-ai-repo-access-table-1440x900.png';
        const filePath = path.join(OUT_DIR, filename);
        await page.screenshot({ path: filePath, fullPage: false });
        console.log(`[CAPTURED] ${filename} (${fs.statSync(filePath).size} bytes)`);
      } finally {
        await context.close();
      }
    }

    console.log('\n[Capture KAN-414] All 15 screenshots captured successfully!');
  } finally {
    await browser.close();
    server.close(() => {
      console.log(`[SPA Server] Port ${PORT} closed cleanly.`);
    });
  }
}

main().catch((err) => {
  console.error('[Capture KAN-414 ERROR]', err);
  process.exit(1);
});
