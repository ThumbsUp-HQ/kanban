// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(process.cwd(), 'kanban/web/node_modules/@playwright/test'));

const PORT = 18409;
const HOST = '127.0.0.1';
const BASE_URL = `http://${HOST}:${PORT}`;
const DIST_DIR = path.resolve('kanban/web/dist');
const OUT_DIR = path.resolve('docs/qa/KAN-409/screenshots');

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
      let filePath = path.join(DIST_DIR, urlPath);

      // Check if file exists directly
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
  { name: '1440x900-light', width: 1440, height: 900, theme: 'light' },
  { name: '1440x900-dark', width: 1440, height: 900, theme: 'dark' },
  { name: '1024x768', width: 1024, height: 768, theme: 'light' },
  { name: '768x1024', width: 768, height: 1024, theme: 'light' },
  { name: '390x844', width: 390, height: 844, theme: 'light' },
];

const CHAPTERS = [
  {
    prefix: '01-multi-card-auth',
    slug: 'multi-card-authentication-studio',
    title: 'Multi-Card Authentication Studio',
    hasMermaid: true,
  },
  {
    prefix: '02-role-permission-matrix',
    slug: 'role-and-permission-matrix',
    title: 'Role and Permission Matrix',
    hasMermaid: false,
    scrollToAnchor: 'granular-rbac-policy-builder',
  },
  {
    prefix: '03-studio-config-ref',
    slug: 'studio-configuration-reference',
    title: 'Studio Configuration Reference',
    hasMermaid: false,
    scrollToAnchor: 'authentication-studio',
  },
];

async function applyTheme(page, theme) {
  await page.evaluate((t) => {
    localStorage.setItem('kb:theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(150);
}

async function main() {
  console.log('[Capture KAN-409] Starting screenshot capture run...');
  const server = await startSpaServer();
  const browser = await chromium.launch({ headless: true });

  try {
    for (const chapter of CHAPTERS) {
      console.log(`\n=== Capturing Chapter: ${chapter.title} (/docs/${chapter.slug}) ===`);

      for (const vp of VIEWPORTS) {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          deviceScaleFactor: 1,
        });
        const page = await context.newPage();

        try {
          const targetUrl = `${BASE_URL}/docs/${chapter.slug}`;
          await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });
          await applyTheme(page, vp.theme);

          // Wait for content to render
          await page.waitForSelector('.kb-docs-center-page, [data-testid="docs-center-page"], .kb-doc-viewer', {
            timeout: 10000,
          });

          // Wait for Mermaid rendering if present
          if (chapter.hasMermaid) {
            try {
              await page.waitForSelector('svg[id^="mermaid"], .kb-mermaid-block, [data-testid*="mermaid"]', { timeout: 8000 });
            } catch {
              console.log('Mermaid block wait timed out or rendered inline.');
            }
          }

          // If chapter specifies an anchor to focus on, scroll it into view with header offset
          if (chapter.scrollToAnchor) {
            try {
              await page.waitForFunction((anchor) => {
                return Boolean(document.getElementById(anchor) || document.querySelector(`[id*="${anchor}"]`));
              }, chapter.scrollToAnchor, { timeout: 8000 });

              await page.evaluate((anchor) => {
                const target = document.getElementById(anchor) || document.querySelector(`[id*="${anchor}"]`);
                if (target) {
                  const rect = target.getBoundingClientRect();
                  const absoluteTop = window.scrollY + rect.top;
                  window.scrollTo({ top: Math.max(0, absoluteTop - 40), behavior: 'instant' });
                }
              }, chapter.scrollToAnchor);
              await page.waitForTimeout(300);
            } catch (scrollErr) {
              console.log(`Scroll to anchor ${chapter.scrollToAnchor} failed or timed out: ${scrollErr.message}`);
            }
          } else {
            await page.waitForTimeout(300);
          }

          const filename = `${chapter.prefix}-${vp.name}.png`;
          const filePath = path.join(OUT_DIR, filename);

          await page.screenshot({ path: filePath, fullPage: false });
          const stats = fs.statSync(filePath);
          console.log(`[CAPTURED] ${filename} (${stats.size} bytes)`);
        } finally {
          await context.close();
        }
      }

      // If chapter has Mermaid, capture a focused scroll shot of the Mermaid diagram with generous padding
      if (chapter.hasMermaid) {
        const context = await browser.newContext({
          viewport: { width: 1440, height: 900 },
          deviceScaleFactor: 1,
        });
        const page = await context.newPage();

        try {
          await page.goto(`${BASE_URL}/docs/${chapter.slug}`, { waitUntil: 'networkidle', timeout: 30000 });
          await applyTheme(page, 'light');

          const mermaidEl = await page.waitForSelector('svg[id^="mermaid"], .kb-mermaid-block, [data-testid*="mermaid"]', {
            timeout: 8000,
          });

          if (mermaidEl) {
            await page.evaluate((el) => {
              const canvas = document.querySelector('.media-viewport__canvas');
              if (canvas) {
                canvas.style.paddingBottom = '60px';
              }
              const viewport = document.querySelector('.media-viewport');
              if (viewport) {
                viewport.style.maxHeight = '680px';
              }
              const rect = el.getBoundingClientRect();
              const absoluteTop = window.scrollY + rect.top;
              // Center diagram in viewport with padding above so floating toolbar does not overlap bottom box
              window.scrollTo({
                top: Math.max(0, absoluteTop - 40),
                behavior: 'instant',
              });
            }, mermaidEl);
            await page.waitForTimeout(400);

            const filename = `${chapter.prefix}-mermaid-flowchart.png`;
            const filePath = path.join(OUT_DIR, filename);

            await page.screenshot({ path: filePath, fullPage: false });
            const stats = fs.statSync(filePath);
            console.log(`[CAPTURED MERMAID] ${filename} (${stats.size} bytes)`);
          }
        } catch (err) {
          console.error(`Failed to capture focused mermaid: ${err.message}`);
        } finally {
          await context.close();
        }
      }
    }

    console.log('\n[Capture KAN-409] All screenshots captured successfully!');
  } finally {
    await browser.close();
    server.close(() => {
      console.log(`[SPA Server] Port ${PORT} closed cleanly.`);
    });
  }
}

main().catch((err) => {
  console.error('[Capture KAN-409 ERROR]', err);
  process.exit(1);
});
