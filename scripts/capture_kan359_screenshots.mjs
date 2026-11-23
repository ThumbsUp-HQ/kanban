// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18991;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-359/screenshots');

const MOCK_STICKIES = [
  {
    id: 'stk-1',
    workspace_id: 'ws-1',
    project_id: 'p-kan',
    body_markdown: '### Keyboard Traversal (KAN-359)\nFull canvas navigation via Tab / Shift+Tab and arrow keys. Spatial layout respects natural grid orientation.',
    color_token: 'amber',
    sort_rank: '0',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE', 'PROMOTE'],
  },
  {
    id: 'stk-2',
    workspace_id: 'ws-1',
    project_id: 'p-kan',
    body_markdown: '### WCAG 2.2 AA Contrast Tokens\nVerified >=4.5:1 contrast across all 6 sticky palette tokens (yellow, pink, blue, green, orange, purple).',
    color_token: 'mint',
    sort_rank: '1',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE', 'PROMOTE'],
  },
  {
    id: 'stk-3',
    workspace_id: 'ws-1',
    project_id: 'p-kan',
    body_markdown: '### Screen Reader Live Announcements\naria-live="polite" broadcasts repositioning, color updates, and promotion events dynamically.',
    color_token: 'sky',
    sort_rank: '2',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE', 'PROMOTE'],
  },
  {
    id: 'stk-4',
    workspace_id: 'ws-1',
    project_id: 'p-kan',
    body_markdown: '### Color-Independent Indicators\nExplicit textual badges and high-contrast outline cues ensure usability for colorblind and vision-impaired users.',
    color_token: 'coral',
    sort_rank: '3',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE', 'PROMOTE'],
  },
  {
    id: 'stk-5',
    workspace_id: 'ws-1',
    project_id: 'p-kan',
    body_markdown: '### Architectural Spec Promotion\nSeamless promotion from scratchpad sticky notes directly into formal canonical markdown documentation.',
    color_token: 'lavender',
    sort_rank: '4',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE', 'PROMOTE'],
  },
  {
    id: 'stk-6',
    workspace_id: 'ws-1',
    project_id: 'p-kan',
    body_markdown: '### High-Priority Triage Sticky\nRapid capture surface with instant keyboard shortcut Alt+Arrow repositioning support.',
    color_token: 'orange',
    sort_rank: '5',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE', 'PROMOTE'],
  },
];

const VIEWPORTS = [
  {
    name: '1440x900-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const cards = await page.$$('[data-testid="sticky-card"]');
      if (cards.length > 0) {
        await cards[0].focus();
      }
      await page.waitForTimeout(300);
    },
  },
  {
    name: '1440x900-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const cards = await page.$$('[data-testid="sticky-card"]');
      if (cards.length > 1) {
        await cards[1].focus();
      }
      await page.waitForTimeout(300);
    },
  },
  {
    name: '768x1024-tablet',
    width: 768,
    height: 1024,
    theme: 'light',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const cards = await page.$$('[data-testid="sticky-card"]');
      if (cards.length > 2) {
        await cards[2].focus();
      }
      await page.waitForTimeout(300);
    },
  },
  {
    name: '390x844-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'light',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const cards = await page.$$('[data-testid="sticky-card"]');
      if (cards.length > 0) {
        await cards[0].focus();
      }
      await page.waitForTimeout(300);
    },
  },
  {
    name: '844x390-mobile-landscape',
    width: 844,
    height: 390,
    theme: 'light',
    action: async (page) => {
      await page.waitForTimeout(1000);
      const cards = await page.$$('[data-testid="sticky-card"]');
      if (cards.length > 3) {
        await cards[3].focus();
      }
      await page.waitForTimeout(300);
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
    { stdio: 'inherit' }
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

      const page = await context.newPage();

      // Intercept auth
      await page.route('**/api/v1/auth/me', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'u-admin',
            handle: 'admin',
            display_name: 'Administrator',
            email: 'admin@kanban.local',
            is_server_admin: true,
            is_workspace_admin: true,
          }),
        });
      });
      await page.route('**/api/v1/user/me', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'u-admin',
            handle: 'admin',
            display_name: 'Administrator',
            email: 'admin@kanban.local',
            is_server_admin: true,
            is_workspace_admin: true,
          }),
        });
      });

      // Intercept project and workspaces
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'p-kan',
            key: 'KAN',
            name: 'Core Platform',
            description: 'Core platform stickies board',
            visibility: 'internal',
            archived: false,
          }),
        });
      });
      await page.route('**/api/v1/projects', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'p-kan', key: 'KAN', name: 'Core Platform' },
          ]),
        });
      });
      await page.route('**/api/v1/workspaces*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'ws-1', slug: 'default', name: 'Default Workspace' },
          ]),
        });
      });

      // Stickies routes
      await page.route('**/api/v1/projects/KAN/stickies*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_STICKIES),
        });
      });
      await page.route('**/api/v1/stickies*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_STICKIES),
        });
      });

      // Navigate to /stickies
      await page.goto(`${BASE_URL}/stickies`, { waitUntil: 'domcontentloaded' });

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
      console.log(`Saved screenshot to ${outPath}`);

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
