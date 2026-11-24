// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '../kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18985;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-385/screenshots');

const VIEWPORTS = [
  { width: 1440, height: 900, name: '1440x900-desktop' },
  { width: 1100, height: 800, name: '1100x800-intermediate-desktop' },
  { width: 1024, height: 768, name: '1024x768-tablet-landscape' },
  { width: 900, height: 700, name: '900x700-compact-tablet' },
  { width: 768, height: 1024, name: '768x1024-tablet-portrait' },
  { width: 390, height: 844, name: '390x844-mobile-portrait' },
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
  const configs = [
    { stateId: 'st-backlog', count: 3, prefix: 'Backlog Item' },
    { stateId: 'st-todo', count: 8, prefix: 'Todo Item' },
    { stateId: 'st-prog', count: 5, prefix: 'In Progress Item' },
    { stateId: 'st-done', count: 4, prefix: 'Completed Item' },
  ];

  let seq = 1;
  for (const cfg of configs) {
    for (let i = 1; i <= cfg.count; i++) {
      items.push({
        id: `iss-${seq}`,
        key: `KAN-${seq}`,
        project_key: 'KAN',
        project_name: 'Platform Core',
        summary: `${cfg.prefix} #${i} - Flex overlap test issue`,
        description_markdown: 'Verification item for query toggle and states filter non-overlap.',
        state_id: cfg.stateId,
        board_rank: `000000000000${String(seq).padStart(4, '0')}`,
        priority: {
          id: 'p-high',
          label: 'High',
          slug: 'high',
          emoji: '⚡',
        },
        state: {
          id: cfg.stateId,
          name: cfg.stateId === 'st-backlog' ? 'Backlog' : cfg.stateId === 'st-todo' ? 'Todo' : cfg.stateId === 'st-prog' ? 'In Progress' : 'Done',
          group: cfg.stateId === 'st-done' ? 'completed' : cfg.stateId === 'st-prog' ? 'started' : 'unstarted',
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

async function setupPageRoutes(page, mockStates, mockIssuesData) {
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
      body: JSON.stringify({ csrf_token: 'csrf-proof-token-385' }),
    });
  });
  await page.route('**/api/v1/setup/status', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ initialized: true, is_initialized: true }),
    });
  });

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
        id: 'obj-385',
        scope: 'project',
        sharing: { users: [], groups: [], agents: [] },
      }),
    });
  });
}

function checkIntersection(rectA, rectB) {
  const overlapX = Math.max(0, Math.min(rectA.right, rectB.right) - Math.max(rectA.left, rectB.left));
  const overlapY = Math.max(0, Math.min(rectA.bottom, rectB.bottom) - Math.max(rectA.top, rectB.top));
  return overlapX * overlapY;
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
      { id: 'st-done', name: 'Done', group: 'completed', color_hex: '#22c55e', sort_order: 4 },
    ];

    for (const vp of VIEWPORTS) {
      logProof(`\n================================================================`);
      logProof(`[Viewport Test]: ${vp.name} (${vp.width}x${vp.height})`);
      logProof(`================================================================`);

      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });

      const page = await context.newPage();
      await setupPageRoutes(page, mockStates, mockIssuesData);

      // -------------------------------------------------------------
      // Surface 1: FilterDisplayBar on Board Layout (?layout=board)
      // -------------------------------------------------------------
      logProof(`\n  --- Surface 1: FilterDisplayBar on Board Layout (?layout=board) ---`);
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="filter-display-bar"]', { timeout: 12000 });
      await page.waitForSelector('[data-testid="mode-query-btn"]', { timeout: 12000 });
      await page.waitForSelector('.navigator-state-trigger', { timeout: 12000 });
      await page.waitForTimeout(300);

      const boardMetrics = await page.evaluate(() => {
        const queryBtn = document.querySelector('[data-testid="mode-query-btn"]');
        const statesTrigger = document.querySelector('.navigator-state-trigger');
        const searchForm = document.querySelector('.filter-search-form');
        const controlsGroup = document.querySelector('.filter-controls-group');
        if (!queryBtn || !statesTrigger) {
          throw new Error('Required buttons missing on Board layout');
        }
        const rQuery = queryBtn.getBoundingClientRect();
        const rStates = statesTrigger.getBoundingClientRect();
        const rForm = searchForm?.getBoundingClientRect();
        const rControls = controlsGroup?.getBoundingClientRect();
        return {
          query: { left: rQuery.left, top: rQuery.top, right: rQuery.right, bottom: rQuery.bottom, width: rQuery.width, height: rQuery.height },
          states: { left: rStates.left, top: rStates.top, right: rStates.right, bottom: rStates.bottom, width: rStates.width, height: rStates.height },
          searchFormWidth: rForm?.width ?? 0,
          controlsGroupLeft: rControls?.left ?? 0,
        };
      });

      const boardOverlap = checkIntersection(boardMetrics.query, boardMetrics.states);
      logProof(`    Query Button Box : left=${boardMetrics.query.left.toFixed(1)}, right=${boardMetrics.query.right.toFixed(1)}, top=${boardMetrics.query.top.toFixed(1)}, bottom=${boardMetrics.query.bottom.toFixed(1)}`);
      logProof(`    States Button Box: left=${boardMetrics.states.left.toFixed(1)}, right=${boardMetrics.states.right.toFixed(1)}, top=${boardMetrics.states.top.toFixed(1)}, bottom=${boardMetrics.states.bottom.toFixed(1)}`);
      logProof(`    Overlap Area     : ${boardOverlap.toFixed(2)} px^2 (expected 0)`);
      if (boardOverlap > 0) {
        throw new Error(`FAILURE: Collision detected in FilterDisplayBar at ${vp.width}x${vp.height}! Overlap area: ${boardOverlap}px^2`);
      }
      logProof(`    PASS: Zero collision in FilterDisplayBar (overlapArea === 0).`);

      const boardScreenshotPath = path.join(OUT_DIR, `board-${vp.name}.png`);
      await page.screenshot({ path: boardScreenshotPath, fullPage: false });
      logProof(`    -> Saved board screenshot: ${boardScreenshotPath}`);

      // -------------------------------------------------------------
      // Surface 2: IssueNavigatorBar on List Layout (?layout=list)
      // -------------------------------------------------------------
      logProof(`\n  --- Surface 2: IssueNavigatorBar on List Layout (?layout=list) ---`);
      await page.goto(`${BASE_URL}/projects/KAN/issues?layout=list`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('[data-testid="issue-navigator-bar"]', { timeout: 12000 });
      await page.waitForSelector('[data-testid="mode-query-btn"]', { timeout: 12000 });
      await page.waitForSelector('.navigator-state-trigger', { timeout: 12000 });

      const headerModes = [
        { mode: '1col', selector: '[data-testid="header-mode-1col-btn"]' },
        { mode: 'basic-2col', selector: '[data-testid="header-mode-basic-2col-btn"]' },
        { mode: 'advanced-1line', selector: '[data-testid="header-mode-advanced-1line-btn"]' },
      ];

      for (const hm of headerModes) {
        logProof(`    Mode: ${hm.mode}`);
        const modeBtn = await page.$(hm.selector);
        if (modeBtn) {
          await modeBtn.click();
          await page.waitForTimeout(200);
        }

        const navMetrics = await page.evaluate(() => {
          const queryBtn = document.querySelector('[data-testid="mode-query-btn"]');
          const statesTrigger = document.querySelector('.navigator-state-trigger');
          if (!queryBtn || !statesTrigger) {
            throw new Error('Required buttons missing in IssueNavigatorBar');
          }
          const rQuery = queryBtn.getBoundingClientRect();
          const rStates = statesTrigger.getBoundingClientRect();
          return {
            query: { left: rQuery.left, top: rQuery.top, right: rQuery.right, bottom: rQuery.bottom, width: rQuery.width, height: rQuery.height },
            states: { left: rStates.left, top: rStates.top, right: rStates.right, bottom: rStates.bottom, width: rStates.width, height: rStates.height },
          };
        });

        const navOverlap = checkIntersection(navMetrics.query, navMetrics.states);
        logProof(`      Query Box : left=${navMetrics.query.left.toFixed(1)}, right=${navMetrics.query.right.toFixed(1)}, top=${navMetrics.query.top.toFixed(1)}, bottom=${navMetrics.query.bottom.toFixed(1)}`);
        logProof(`      States Box: left=${navMetrics.states.left.toFixed(1)}, right=${navMetrics.states.right.toFixed(1)}, top=${navMetrics.states.top.toFixed(1)}, bottom=${navMetrics.states.bottom.toFixed(1)}`);
        logProof(`      Overlap   : ${navOverlap.toFixed(2)} px^2 (expected 0)`);
        if (navOverlap > 0) {
          throw new Error(`FAILURE: Collision detected in IssueNavigatorBar (${hm.mode}) at ${vp.width}x${vp.height}! Overlap: ${navOverlap}px^2`);
        }
        logProof(`      PASS: Zero collision in ${hm.mode} (overlapArea === 0).`);

        const navScreenshotPath = path.join(OUT_DIR, `list-${hm.mode}-${vp.name}.png`);
        await page.screenshot({ path: navScreenshotPath, fullPage: false });
        logProof(`      -> Saved screenshot: ${navScreenshotPath}`);
      }

      // Also save primary viewport proof alias
      const primaryAliasPath = path.join(OUT_DIR, `${vp.name}.png`);
      fs.copyFileSync(path.join(OUT_DIR, `board-${vp.name}.png`), primaryAliasPath);

      await context.close();
    }

    await browser.close();
    logProof(`\nALL 6 VIEWPORTS VALIDATED WITH ZERO OVERLAP ACROSS ALL SURFACES.`);
  } finally {
    previewProc.kill('SIGTERM');
  }

  fs.writeFileSync('docs/qa/KAN-385/playwright-search-overlap.txt', testOutputs.join('\n'));
}

main().catch((err) => {
  console.error('Fatal error running capture_kan385_screenshots:', err);
  process.exit(1);
});
