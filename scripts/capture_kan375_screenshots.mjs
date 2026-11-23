// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '../kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18995;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-375/screenshots');

const MOCK_TEMPLATES = {
  items: [
    {
      id: 'tpl-sec',
      slug: 'security-assessment-report',
      name: 'Security Assessment Report',
      description: 'Comprehensive security audit and vulnerability report',
      tier: 'workspace',
      format: 'pdf',
      is_builtin: true,
      created_at: '2026-11-20T10:00:00Z',
      updated_at: '2026-11-20T10:00:00Z',
    },
    {
      id: 'tpl-exec',
      slug: 'executive-summary',
      name: 'Executive Summary',
      description: 'High-level status overview for leadership',
      tier: 'system',
      format: 'pdf',
      is_builtin: true,
      created_at: '2026-11-20T10:00:00Z',
      updated_at: '2026-11-20T10:00:00Z',
    },
    {
      id: 'tpl-burndown',
      slug: 'sprint-burndown',
      name: 'Sprint Burndown',
      description: 'Sprint tracking and velocity analysis',
      tier: 'project',
      format: 'xlsx',
      is_builtin: true,
      created_at: '2026-11-20T10:00:00Z',
      updated_at: '2026-11-20T10:00:00Z',
    },
  ],
  total: 3,
};

const VIEWPORTS = [
  {
    name: '1440x900-desktop-light',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    name: '1440x900-desktop-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    name: '768x1024-tablet',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: '390x844-mobile-portrait',
    width: 390,
    height: 844,
    theme: 'dark',
  },
  {
    name: '844x390-mobile-landscape',
    width: 844,
    height: 390,
    theme: 'dark',
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

    const mockMe = {
      id: '01918a22-0000-7000-8000-000000000001',
      handle: 'adam',
      display_name: 'Adam Outler',
      email: 'adam@kanban.local',
      is_server_admin: true,
      is_workspace_admin: true,
      workspace_id: 'ws-kanban',
      workspace_slug: 'kanban',
      role: 'ADMIN',
    };

    const mockProject = {
      id: 'p-kan',
      key: 'KAN',
      name: 'Platform Core',
      description: 'Primary platform repository',
      visibility: 'internal',
      archived: false,
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
      is_project_admin: true,
    };

    const mockIssues = [
      {
        id: 'iss-1',
        key: 'KAN-375',
        identifier: 'KAN-375',
        title: 'Fix Report Template Modal Workspace Not Found Error, CSRF Header and Dark-Mode Skinning',
        summary: 'Fix Report Template Modal Workspace Not Found Error, CSRF Header and Dark-Mode Skinning',
        state_id: 'st-inprog',
        state: 'In Progress',
        priority: 'urgent',
        project_id: 'p-kan',
        project_key: 'KAN',
        created_at: '2026-11-23T08:00:00Z',
        creator: mockMe,
        assignees: [mockMe],
        labels: [{ id: 'lbl-1', name: 'reports', color: '#2563eb' }],
      },
    ];

    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
        reducedMotion: 'reduce',
      });

      await context.addCookies([
        {
          name: 'kb_csrf',
          value: 'test-csrf-token-kan-375',
          domain: '127.0.0.1',
          path: '/',
        },
      ]);

      const page = await context.newPage();

      // Auth & user mocks
      await page.route('**/api/v1/auth/me', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockMe) }));
      await page.route('**/api/v1/user/me', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockMe) }));
      await page.route('**/api/v1/me', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockMe) }));
      await page.route('**/api/v1/auth/session', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            authenticated: true,
            aal_level: 2,
            csrf_token: 'test-csrf-token-kan-375',
            workspace_id: 'ws-kanban',
            workspace_slug: 'kanban',
            user: mockMe,
          }),
        });
      });
      await page.route('**/api/v1/session/csrf', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ csrf_token: 'test-csrf-token-kan-375' }) }));
      await page.route('**/api/v1/setup/status', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ initialized: true, is_initialized: true, requires_setup: false }) }));
      await page.route('**/api/v1/system/status', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ mode: 'normal' }) }));

      // Workspace mocks
      await page.route('**/api/v1/workspaces', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ id: 'ws-kanban', name: 'Primary Workspace', slug: 'kanban', is_current: true }]),
        });
      });
      await page.route('**/api/v1/workspaces/current', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'ws-kanban', name: 'Primary Workspace', slug: 'kanban' }),
        });
      });
      await page.route('**/api/v1/workspaces/kanban', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'ws-kanban', name: 'Primary Workspace', slug: 'kanban' }),
        });
      });

      // Project mocks
      await page.route('**/api/v1/projects', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([mockProject]) }));
      await page.route('**/api/v1/projects/KAN', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockProject) }));
      await page.route('**/api/v1/projects/KAN/views', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/views/default', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'view-default', layout: 'board' }) }));
      await page.route('**/api/v1/projects/KAN/cycles', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/modules', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/trash', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/workflow-hooks', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/custom-fields', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
      await page.route('**/api/v1/projects/KAN/states', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'st-backlog', name: 'Backlog', group: 'backlog', color: '#64748b', sort_order: 1 },
            { id: 'st-todo', name: 'Todo', group: 'unstarted', color: '#3b82f6', sort_order: 2 },
            { id: 'st-inprog', name: 'In Progress', group: 'started', color: '#eab308', sort_order: 3 },
            { id: 'st-done', name: 'Done', group: 'completed', color: '#22c55e', sort_order: 4 },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/priorities', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
            { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
            { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
            { slug: 'low', label: 'Low', emoji: '💤', sort_order: 4 },
          ]),
        });
      });
      await page.route('**/api/v1/projects/KAN/labels', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ id: 'lbl-1', name: 'reports', color_hex: '#2563eb' }]),
        });
      });
      await page.route('**/api/v1/projects/KAN/assignee-suggestions', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [mockMe] }),
        });
      });
      await page.route('**/api/v1/projects/KAN/issues*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: mockIssues, total: 1, page: 1, size: 50 }),
        });
      });
      await page.route('**/api/v1/notifications*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], count: 0, unread_count: 0 }) }));

      // Reports API mocks
      await page.route('**/api/v1/workspaces/*/report-templates*', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_TEMPLATES),
        });
      });
      await page.route('**/api/v1/workspaces/*/reports/preview', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            preview_html: '<h2>Security Assessment Report</h2><p>Workspace: <strong>kanban</strong> | Scope: <strong>Project KAN</strong></p><table style="width:100%; border-collapse:collapse; margin-top:12px;"><thead><tr style="background:#1e293b; color:#fff;"><th>Key</th><th>Summary</th><th>State</th><th>Priority</th></tr></thead><tbody><tr><td>KAN-375</td><td>Fix Report Template Modal Workspace Not Found Error</td><td>In Progress</td><td>Urgent</td></tr></tbody></table>',
            issue_count: 1,
          }),
        });
      });

      page.on('console', (msg) => {
        if (msg.type() === 'error') console.log(`[PAGE ERROR ${vp.name}]:`, msg.text());
      });

      try {
        await page.goto(`${BASE_URL}/projects/KAN/issues?layout=list`, { waitUntil: 'load', timeout: 15000 });
      } catch (err) {
        console.warn(`Warning navigating to list:`, err.message);
      }

      await page.evaluate((theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('kb:theme', theme);
        localStorage.setItem('theme', theme);
      }, vp.theme);

      await page.waitForTimeout(600);

      // Open reports export modal
      try {
        const filterToggle = page.locator('[data-testid="navigator-filters-toggle"]');
        if (await filterToggle.isVisible({ timeout: 800 })) {
          await filterToggle.click();
          await page.waitForTimeout(300);
        }

        const listBtn = page.locator('[data-testid="navigator-reports-export-btn"]');
        if (await listBtn.isVisible({ timeout: 2000 })) {
          await listBtn.click();
        } else {
          const displayBtn = page.locator('button.filter-btn-trigger:has-text("Display")');
          if (await displayBtn.isVisible({ timeout: 1000 })) {
            await displayBtn.click();
            await page.waitForTimeout(300);
            const reportsOption = page.locator('[data-testid="filter-display-reports-btn"]');
            if (await reportsOption.isVisible({ timeout: 1000 })) {
              await reportsOption.click();
            }
          }
        }
      } catch (e) {
        console.warn('Click export button error:', e.message);
      }

      // Wait for report export modal
      try {
        await page.waitForSelector('[data-testid="report-export-backdrop"]', { timeout: 5000 });
        await page.waitForSelector('[data-testid="report-template-select"]', { timeout: 3000 });
        await page.waitForTimeout(600);
      } catch (e) {
        console.warn('Report export modal selector wait error:', e.message);
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
