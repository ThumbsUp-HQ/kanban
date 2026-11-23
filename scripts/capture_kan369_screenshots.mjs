// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18989;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-369/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-light-project-settings',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/settings`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const advToggle = await page.$('[data-testid="project-general-advanced-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '02-desktop-dark-workflow-studio',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/settings/workflows`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const attachBtn = await page.$('[data-testid="attach-hook-button"], button:has-text("Add Hook"), button:has-text("Attach Hook")');
      if (attachBtn) {
        await attachBtn.click();
        await page.waitForTimeout(500);
        const hookAdvToggle = await page.$('[data-testid="attach-hook-advanced-section-toggle"]');
        if (hookAdvToggle) {
          await hookAdvToggle.click();
          await page.waitForTimeout(400);
        }
      }
    },
  },
  {
    name: '03-tablet-custom-fields',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/settings/custom-fields`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const cfAdvToggle = await page.$('[data-testid="custom-field-advanced-section-toggle"]');
      if (cfAdvToggle) {
        await cfAdvToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '04-mobile-portrait-project-settings',
    width: 390,
    height: 844,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/settings`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const advToggle = await page.$('[data-testid="project-general-advanced-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '05-mobile-landscape-workflow-hooks',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/settings/workflows`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const attachBtn = await page.$('[data-testid="attach-hook-button"], button:has-text("Add Hook"), button:has-text("Attach Hook")');
      if (attachBtn) {
        await attachBtn.click();
        await page.waitForTimeout(500);
        const hookAdvToggle = await page.$('[data-testid="attach-hook-advanced-section-toggle"]');
        if (hookAdvToggle) {
          await hookAdvToggle.click();
          await page.waitForTimeout(400);
        }
      }
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
      // wait and retry
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

      // Intercept user profile & auth
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

      // Project mock endpoints
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'p-kan',
            key: 'KAN',
            name: 'Core Platform',
            description: 'Primary platform repository with progressive disclosure settings',
            visibility: 'internal',
            archived: false,
            auto_archive_days: 90,
            skip_loaded_seq: true,
          }),
        });
      });
      await page.route('**/api/v1/projects/KAN/states', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'st-backlog', name: 'Backlog', category: 'backlog', color: '#64748b', sort_rank: '0', soft_wip_limit: null, hard_wip_limit: null },
            { id: 'st-todo', name: 'Todo', category: 'unstarted', color: '#3b82f6', sort_rank: '1', soft_wip_limit: null, hard_wip_limit: null },
            { id: 'st-inprog', name: 'In Progress', category: 'started', color: '#eab308', sort_rank: '2', soft_wip_limit: 5, hard_wip_limit: 10 },
            { id: 'st-done', name: 'Done', category: 'completed', color: '#22c55e', sort_rank: '3', soft_wip_limit: null, hard_wip_limit: null },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/priorities', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'pr-low', level: 1, name: 'Low', color: '#94a3b8', sort_order: 1 },
            { id: 'pr-med', level: 2, name: 'Medium', color: '#3b82f6', sort_order: 2 },
            { id: 'pr-high', level: 3, name: 'High', color: '#f97316', sort_order: 3 },
            { id: 'pr-crit', level: 4, name: 'Urgent', color: '#ef4444', sort_order: 4 },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/labels', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'lb-bug', name: 'bug', color: '#ef4444', exclusive_group: 'kind' },
            { id: 'lb-feat', name: 'feature', color: '#3b82f6', exclusive_group: 'kind' },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/members', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'pm-1', user_id: 'u-admin', user: { id: 'u-admin', display_name: 'Administrator', handle: 'admin' }, role: 'admin' },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/modules', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/trash', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/admin/principals*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));

      // Workflow studio mocks
      await page.route('**/api/v1/projects/KAN/workflow-hooks', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'hk-1',
              name: 'Security Clearance Validator',
              from_state: 'st-backlog',
              to_state: 'st-inprog',
              hook_kind: 'sync_validator',
              sort_rank: '0',
              failure_policy: 'fail_closed',
              manifest_sha256: 'abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd',
              is_enabled: true,
              wasm_module_sha256: '3fa85f64-5717-4562-b3fc-2c963f66afa6',
              allowed_mutable_fields: ['labels', 'priority'],
            },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/workflow-wasm-modules', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { sha256: '3fa85f64-5717-4562-b3fc-2c963f66afa6', name: 'security_guard.wasm', size_bytes: 10240 },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/workflow-agents', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));

      // Custom fields mocks
      await page.route('**/api/v1/projects/KAN/custom-fields', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'cf-1',
              name: 'Risk Rating',
              slug: 'risk_rating',
              field_flavor: 'calculated',
              output_format: 'text',
              is_enabled: true,
              script_source: "return issue.priority === 'urgent' ? 'HIGH' : 'LOW';",
              format_metadata: { precision: 2 },
            },
          ]),
        });
      });

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
