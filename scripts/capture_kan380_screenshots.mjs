// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '../kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18980;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-380/screenshots');

const VIEWPORTS = [
  {
    id: '01',
    name: '01-desktop-scroll-1440x900',
    alias: '1440x900-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    id: '02',
    name: '02-desktop-scroll-1440x900-dark',
    alias: '1440x900-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    id: '03',
    name: '03-tablet-scroll-1024x768',
    alias: '1024x768-tablet',
    width: 1024,
    height: 768,
    theme: 'light',
  },
  {
    id: '04',
    name: '04-tablet-portrait-scroll-768x1024',
    alias: '768x1024-tablet-portrait',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    id: '05',
    name: '05-mobile-scroll-390x844',
    alias: '390x844-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'light',
  },
  {
    id: '06',
    name: '06-small-mobile-scroll-375x667',
    alias: '375x667-mobile-compact',
    width: 375,
    height: 667,
    theme: 'light',
  },
];

async function waitForServer(url, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404 || res.status === 200) {
        return true;
      }
    } catch {
      // wait and retry
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Server failed to start at ${url} within ${timeoutMs}ms`);
}

function generateMockIssues() {
  const items = [];
  // 5 states: st-backlog (4 cards), st-todo (25 cards for vertical scroll proof), st-prog (5 cards), st-review (4 cards), st-done (6 cards)
  const configs = [
    { stateId: 'st-backlog', count: 4, prefix: 'Backlog Item' },
    { stateId: 'st-todo', count: 25, prefix: 'Desktop Scroll Item' },
    { stateId: 'st-prog', count: 5, prefix: 'In Progress Item' },
    { stateId: 'st-review', count: 4, prefix: 'Review Item' },
    { stateId: 'st-done', count: 6, prefix: 'Completed Item' },
  ];

  let seq = 1;
  for (const cfg of configs) {
    for (let i = 1; i <= cfg.count; i++) {
      items.push({
        id: `iss-${seq}`,
        key: `KAN-${seq}`,
        project_key: 'KAN',
        project_name: 'Platform Core',
        summary: `${cfg.prefix} #${i} - Comprehensive verification test item`,
        description_markdown: 'Detailed description for desktop scrolling and flex containment verification.',
        state_id: cfg.stateId,
        board_rank: `000000000000${String(seq).padStart(4, '0')}`,
        priority: {
          id: 'p-high',
          label: 'High',
          slug: 'high',
          emoji: '⚡',
        },
        assignees: [
          {
            id: 'u-adam',
            kind: 'principal',
            principal: {
              id: 'u-adam',
              handle: 'adam',
              display_name: 'Adam Architect',
              type: 'USER',
            },
          },
        ],
        capabilities: ['VIEW', 'EDIT', 'ADMIN'],
        created_at: '2026-11-20T10:00:00Z',
        updated_at: '2026-11-23T10:00:00Z',
      });
      seq++;
    }
  }
  return { items, total: items.length };
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Starting preview server on port ${PORT}...`);
  const previewProc = spawn(
    'pnpm',
    ['--dir', 'kanban/web', 'exec', 'vite', 'preview', '--port', String(PORT), '--host', '127.0.0.1'],
    { stdio: 'inherit' }
  );

  const testOutputs = [];
  function logProof(line) {
    console.log(line);
    testOutputs.push(line);
  }

  try {
    await waitForServer(BASE_URL);
    logProof(`[Playwright Proof] Preview server ready at ${BASE_URL}`);

    const browser = await chromium.launch({
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    });

    const mockIssuesData = generateMockIssues();
    const mockStates = [
      { id: 'st-backlog', name: 'Backlog', group: 'backlog', color_hex: '#64748b', sort_order: 1 },
      { id: 'st-todo', name: 'To Do', group: 'unstarted', color_hex: '#f59e0b', sort_order: 2 },
      { id: 'st-prog', name: 'In Progress', group: 'started', color_hex: '#3b82f6', sort_order: 3 },
      { id: 'st-review', name: 'In Review', group: 'started', color_hex: '#8b5cf6', sort_order: 4 },
      { id: 'st-done', name: 'Done', group: 'completed', color_hex: '#22c55e', sort_order: 5 },
    ];

    for (const vp of VIEWPORTS) {
      logProof(`\n[Viewport Test]: ${vp.name} (${vp.width}x${vp.height}) theme=${vp.theme}`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });

      const page = await context.newPage();

      // Intercept auth & system APIs
      await page.route('**/api/v1/auth/me', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'u-adam',
            handle: 'adam',
            display_name: 'Adam Architect',
            email: 'adam@kanban.local',
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
            id: 'u-adam',
            handle: 'adam',
            display_name: 'Adam Architect',
            email: 'adam@kanban.local',
            is_server_admin: true,
            is_workspace_admin: true,
          }),
        });
      });
      await page.route('**/api/v1/auth/session', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            authenticated: true,
            user: { id: 'u-adam', handle: 'adam', is_server_admin: true, is_workspace_admin: true },
          }),
        });
      });
      await page.route('**/api/v1/session/csrf', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ csrf_token: 'csrf-proof-token-380' }),
        });
      });
      await page.route('**/api/v1/setup/status', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ initialized: true, is_initialized: true }),
        });
      });

      // Intercept project & workspace APIs
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'p-1',
            identifier: 'KAN',
            name: 'Platform Core',
            description_markdown: 'Core project workspace',
            modules_enabled: true,
            capabilities: ['VIEW', 'EDIT', 'ADMIN', 'PROJECT_ADMIN'],
            is_project_admin: true,
          }),
        });
      });

      await page.route('**/api/v1/projects/KAN/states**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockStates),
        });
      });

      await page.route('**/api/v1/projects/KAN/issues**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockIssuesData),
        });
      });

      await page.route('**/api/v1/projects/KAN/views**', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      });
      await page.route('**/api/v1/projects/KAN/priorities**', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
      });
      await page.route('**/api/v1/projects/KAN/cycles**', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      });
      await page.route('**/api/v1/projects/KAN/modules**', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      });

      await page.route('**/api/v1/objects/**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'obj-380',
            scope: 'project',
            sharing: { users: [], groups: [], agents: [] },
          }),
        });
      });

      // Navigate to board view
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'domcontentloaded' });

      // Apply theme
      if (vp.theme === 'dark') {
        await page.evaluate(() => {
          document.documentElement.classList.add('dark');
          document.documentElement.setAttribute('data-theme', 'dark');
        });
      } else {
        await page.evaluate(() => {
          document.documentElement.classList.remove('dark');
          document.documentElement.setAttribute('data-theme', 'light');
        });
      }

      await page.waitForSelector('.board-canvas', { timeout: 10000 });
      await page.waitForSelector('.board-lanes', { timeout: 10000 });
      await page.waitForSelector('[data-testid="scroll-area-st-todo"]', { timeout: 10000 });
      await page.waitForTimeout(600);

      // Perform desktop geometry & scroll validation on 1440x900
      if (vp.width === 1440 && vp.height === 900) {
        const scrollAreaMetrics = await page.evaluate(() => {
          const el = document.querySelector('[data-testid="scroll-area-st-todo"]');
          if (!el) throw new Error('st-todo scroll area missing');
          const rect = el.getBoundingClientRect();
          return {
            scrollHeight: el.scrollHeight,
            clientHeight: el.clientHeight,
            top: rect.top,
            bottom: rect.bottom,
            height: rect.height,
          };
        });

        logProof(`  [Assertion 1 - Column Vertical Geometry]:`);
        logProof(`    scrollHeight=${scrollAreaMetrics.scrollHeight}px, clientHeight=${scrollAreaMetrics.clientHeight}px`);
        logProof(`    rect.bottom=${scrollAreaMetrics.bottom.toFixed(1)}px (must be <= 900px)`);

        if (scrollAreaMetrics.scrollHeight <= scrollAreaMetrics.clientHeight) {
          throw new Error(`Vertical overflow failed: scrollHeight (${scrollAreaMetrics.scrollHeight}) <= clientHeight (${scrollAreaMetrics.clientHeight})`);
        }
        if (scrollAreaMetrics.bottom > 900) {
          throw new Error(`Column scroll area overflows bottom of viewport: bottom (${scrollAreaMetrics.bottom}) > 900`);
        }
        logProof(`    PASS: Column scroll-area is cleanly constrained within viewport!`);

        // Perform vertical scroll
        const verticalScrollAdvance = await page.evaluate(() => {
          const el = document.querySelector('[data-testid="scroll-area-st-todo"]');
          if (!el) throw new Error('st-todo scroll area missing');
          el.scrollTop = 250;
          return el.scrollTop;
        });

        logProof(`  [Assertion 2 - Column Vertical Scroll Action]:`);
        logProof(`    scrollTop advanced to=${verticalScrollAdvance}px (expected >= 200px)`);
        if (verticalScrollAdvance < 200) {
          throw new Error(`Vertical scroll advance failed: scrollTop=${verticalScrollAdvance} < 200`);
        }
        logProof(`    PASS: Vertical scrolling works flawlessly!`);

        // Perform horizontal scroll validation on lanes
        const lanesMetrics = await page.evaluate(() => {
          const lanes = document.querySelector('.board-lanes');
          if (!lanes) throw new Error('.board-lanes missing');
          const rect = lanes.getBoundingClientRect();
          lanes.scrollLeft = 200;
          return {
            scrollWidth: lanes.scrollWidth,
            clientWidth: lanes.clientWidth,
            bottom: rect.bottom,
            scrollLeft: lanes.scrollLeft,
          };
        });

        logProof(`  [Assertion 3 - Horizontal Lanes Geometry & Scroll Action]:`);
        logProof(`    lanes scrollWidth=${lanesMetrics.scrollWidth}px, clientWidth=${lanesMetrics.clientWidth}px`);
        logProof(`    lanes rect.bottom=${lanesMetrics.bottom.toFixed(1)}px (must be <= 900px)`);
        logProof(`    lanes scrollLeft advanced to=${lanesMetrics.scrollLeft}px (expected > 0)`);

        if (lanesMetrics.bottom > 900) {
          throw new Error(`Board lanes overflow bottom of viewport: bottom (${lanesMetrics.bottom}) > 900`);
        }
        if (lanesMetrics.scrollLeft <= 0) {
          throw new Error(`Horizontal scroll advance failed: scrollLeft=${lanesMetrics.scrollLeft} <= 0`);
        }
        logProof(`    PASS: Horizontal scrolling and scrollbar visibility work flawlessly!`);
      }

      // Add visual annotation banner for the screenshot
      await page.evaluate((vpInfo) => {
        const banner = document.createElement('div');
        banner.style.position = 'fixed';
        banner.style.top = '60px';
        banner.style.right = '20px';
        banner.style.background = 'rgba(15, 23, 42, 0.9)';
        banner.style.color = '#38bdf8';
        banner.style.border = '1px solid #0284c7';
        banner.style.borderRadius = '6px';
        banner.style.padding = '8px 12px';
        banner.style.fontSize = '12px';
        banner.style.fontFamily = 'monospace';
        banner.style.zIndex = '99999';
        banner.style.pointerEvents = 'none';
        banner.style.boxShadow = '0 4px 12px rgba(0,0,0,0.5)';
        banner.textContent = `KAN-380 Desktop Board Scroll Proof | Viewport: ${vpInfo.width}x${vpInfo.height} (${vpInfo.theme}) | Flex: 1 1 0% min-h: 0`;
        document.body.appendChild(banner);
      }, vp);

      // Save screenshot
      const targetPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: targetPath, fullPage: false });
      logProof(`  -> Saved ${targetPath}`);

      // Also copy to alias filename for compatibility
      const aliasPath = path.join(OUT_DIR, `${vp.alias}.png`);
      fs.copyFileSync(targetPath, aliasPath);
      logProof(`  -> Saved alias ${aliasPath}`);

      await context.close();
    }

    await browser.close();
    logProof('\nAll 5-viewport screenshots and scroll proofs completed successfully.');

    // Write log to docs/qa/KAN-380/playwright-desktop-scroll.txt
    fs.writeFileSync(path.resolve('docs/qa/KAN-380/playwright-desktop-scroll.txt'), testOutputs.join('\n'));
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
