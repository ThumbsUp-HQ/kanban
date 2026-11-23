// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18991;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-361/screenshots');

const VIEWPORTS = [
  {
    name: '1440x900-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/analytics`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const advToggle = await page.$('[data-testid="flow-advanced-stats-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '1440x900-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/analytics`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const advToggle = await page.$('[data-testid="flow-advanced-stats-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '768x1024-tablet',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/analytics`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const advToggle = await page.$('[data-testid="flow-advanced-stats-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '390x844-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/analytics`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const advToggle = await page.$('[data-testid="flow-advanced-stats-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '844x390-mobile-landscape',
    width: 844,
    height: 390,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/analytics`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const advToggle = await page.$('[data-testid="flow-advanced-stats-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
];

const mockFlowData = {
  project_key: 'KAN',
  project_id: 'a0000000-0000-0000-0000-000000000001',
  window_days: 90,
  cfd: {
    states: [
      { id: 's1', name: 'Backlog', state_group: 'backlog', color_hex: '#94a3b8', sort_order: 1 },
      { id: 's2', name: 'In Progress', state_group: 'started', color_hex: '#3b82f6', sort_order: 2 },
      { id: 's3', name: 'Done', state_group: 'completed', color_hex: '#10b981', sort_order: 3 },
    ],
    state_groups: ['backlog', 'unstarted', 'started', 'completed', 'cancelled'],
    points: [
      { date: '2026-11-01', backlog: 12, unstarted: 5, started: 4, completed: 2, cancelled: 0, total: 23 },
      { date: '2026-11-05', backlog: 10, unstarted: 6, started: 5, completed: 5, cancelled: 0, total: 26 },
      { date: '2026-11-10', backlog: 8, unstarted: 4, started: 6, completed: 10, cancelled: 0, total: 28 },
      { date: '2026-11-15', backlog: 6, unstarted: 3, started: 4, completed: 16, cancelled: 0, total: 29 },
    ],
  },
  cycle_lead_time: {
    points: [
      {
        issue_id: 'i1',
        issue_key: 'KAN-101',
        title: 'Contrast audit for analytics SVG charts',
        cycle_time_days: 2.5,
        lead_time_days: 5.0,
        completed_at: '2026-11-02T10:00:00Z',
      },
      {
        issue_id: 'i2',
        issue_key: 'KAN-102',
        title: 'Eliminate hardcoded non-token hex colors',
        cycle_time_days: 4.0,
        lead_time_days: 7.0,
        completed_at: '2026-11-05T12:00:00Z',
      },
      {
        issue_id: 'i3',
        issue_key: 'KAN-103',
        title: 'Burndown ideal vs actual trajectory non-color cues',
        cycle_time_days: 6.5,
        lead_time_days: 9.0,
        completed_at: '2026-11-12T14:00:00Z',
      },
    ],
    cycle_time_percentiles: { p50: 2.5, p85: 4.5, p95: 6.5 },
    lead_time_percentiles: { p50: 5.0, p85: 7.5, p95: 9.0 },
    total_completed_in_window: 3,
  },
  aging_wip: {
    active_issues: [
      {
        issue_id: 'i4',
        issue_key: 'KAN-104',
        title: 'Aging WIP token compliance',
        state_id: 's2',
        state_name: 'In Progress',
        state_color_hex: '#3b82f6',
        state_entered_at: '2026-11-20T10:00:00Z',
        first_started_at: '2026-11-20T10:00:00Z',
        age_in_current_state_hours: 32.0,
        total_wip_hours: 32.0,
      },
      {
        issue_id: 'i5',
        issue_key: 'KAN-105',
        title: 'High latency security gate audit',
        state_id: 's2',
        state_name: 'In Progress',
        state_color_hex: '#3b82f6',
        state_entered_at: '2026-11-14T10:00:00Z',
        first_started_at: '2026-11-14T10:00:00Z',
        age_in_current_state_hours: 88.0,
        total_wip_hours: 88.0,
      },
    ],
    column_thresholds: {
      s2: {
        state_id: 's2',
        state_name: 'In Progress',
        state_group: 'started',
        color_hex: '#3b82f6',
        p50_hours: 24.0,
        p85_hours: 48.0,
        p95_hours: 72.0,
        sample_size: 14,
      },
    },
    total_active_wip: 2,
  },
  monte_carlo: {
    trials: 10000,
    historical_daily_throughput: [2, 1, 3, 0, 2, 4, 1],
    average_daily_throughput: 1.86,
    how_many: {
      horizon_days: 14,
      p50: 26,
      p85: 20,
      p95: 16,
    },
    when: {
      target_items: 20,
      p50_days: 11,
      p85_days: 15,
      p95_days: 18,
      p50_date: '2026-11-28',
      p85_date: '2026-12-02',
      p95_date: '2026-12-05',
    },
  },
};

const mockCycles = [
  {
    id: 'cyc-1',
    name: 'Sprint 42 (Active)',
    status: 'active',
    start_date: '2026-11-01',
    end_date: '2026-11-14',
    project_id: 'a0000000-0000-0000-0000-000000000001',
  },
];

const mockBurndown = {
  cycle_id: 'cyc-1',
  cycle_name: 'Sprint 42 (Active)',
  start_date: '2026-11-01',
  end_date: '2026-11-14',
  series: [
    { date: '2026-11-01', scope: 24, remaining: 24 },
    { date: '2026-11-03', scope: 24, remaining: 20 },
    { date: '2026-11-05', scope: 25, remaining: 16 },
    { date: '2026-11-07', scope: 25, remaining: 11 },
    { date: '2026-11-09', scope: 25, remaining: 7 },
  ],
  ideal: [
    { date: '2026-11-01', remaining: 24.0 },
    { date: '2026-11-03', remaining: 20.0 },
    { date: '2026-11-05', remaining: 16.0 },
    { date: '2026-11-07', remaining: 12.0 },
    { date: '2026-11-09', remaining: 8.0 },
  ],
};

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
            email: 'admin@kanban.local',
            display_name: 'Administrator',
            handle: 'admin',
            is_active: true,
            is_superuser: true,
            created_at: '2026-01-01T00:00:00Z',
          }),
        });
      });

      // Intercept workspaces
      await page.route('**/api/v1/workspaces', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'ws-1', name: 'Default Workspace', slug: 'default' },
          ]),
        });
      });

      // Intercept projects
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'a0000000-0000-0000-0000-000000000001',
            key: 'KAN',
            name: 'Kanban Platform Core',
            description_markdown: 'Core project',
          }),
        });
      });

      // Intercept flow metrics
      await page.route('**/api/v1/projects/KAN/analytics/flow*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockFlowData),
        });
      });

      // Intercept cycles
      await page.route('**/api/v1/projects/KAN/cycles', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockCycles),
        });
      });

      // Intercept burndown
      await page.route('**/api/v1/cycles/cyc-1/burndown', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockBurndown),
        });
      });

      // Catch-all fallbacks
      await page.route('**/api/v1/projects/KAN/views', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/states', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/labels', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/members', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/priorities', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));

      try {
        await page.goto(vp.url, { waitUntil: 'load', timeout: 15000 });
      } catch (err) {
        console.warn(`Warning navigating to ${vp.url}:`, err.message);
      }

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, vp.theme);

      if (vp.action) {
        try {
          await vp.action(page);
        } catch (e) {
          console.warn(`Action failed for ${vp.name}:`, e.message);
        }
      }

      const outPath = path.join(OUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);
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
