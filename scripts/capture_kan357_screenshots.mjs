// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium } from '/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs';

const PORT = 18957;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-357/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-light-quick-create-modal',
    width: 1440,
    height: 900,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      // Trigger Quick Create modal if hotkey or button exists
      const newIssueBtn = await page.$('[data-testid="quick-create-btn"], [data-testid="new-issue-btn"], button:has-text("+ New Issue"), button:has-text("Create Issue")');
      if (newIssueBtn) {
        await newIssueBtn.click();
        await page.waitForTimeout(500);
      } else {
        await page.keyboard.press('c');
        await page.waitForTimeout(500);
      }
      // Populate and trigger submit error
      const summary = await page.$('#quick-create-summary');
      if (summary) {
        await summary.fill('A11y Test Issue with Form Labels');
        const submit = await page.$('[data-testid="quick-create-submit-btn"]');
        if (submit) {
          await submit.click();
          await page.waitForTimeout(500);
        }
      }
    },
  },
  {
    name: '02-desktop-dark-project-settings-wip',
    width: 1440,
    height: 900,
    theme: 'dark',
    url: `${BASE_URL}/projects/KAN/settings`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      // Switch to States tab
      const statesTab = await page.$('[data-testid="tab-states"]');
      if (statesTab) {
        await statesTab.click();
        await page.waitForTimeout(500);
      }
      // Toggle advanced section
      const advToggle = await page.$('[data-testid="state-advanced-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
      // Trigger soft > hard WIP validation error
      const softInput = await page.$('#state-wip-soft-input');
      const hardInput = await page.$('#state-wip-hard-input');
      const nameInput = await page.$('#state-name-input');
      if (nameInput) await nameInput.fill('Review Phase');
      if (softInput) await softInput.fill('12');
      if (hardInput) await hardInput.fill('4');
      const addBtn = await page.$('[data-testid="create-state-btn"]');
      if (addBtn) {
        await addBtn.click();
        await page.waitForTimeout(500);
      }
    },
  },
  {
    name: '03-tablet-auth-card-editor-drawer',
    width: 768,
    height: 1024,
    theme: 'light',
    url: `${BASE_URL}/admin/auth`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const addCardBtn = await page.$('[data-testid="add-auth-card-btn"], button:has-text("+ Add Provider Card"), button:has-text("Add Provider")');
      if (addCardBtn) {
        await addCardBtn.click();
        await page.waitForTimeout(600);
      }
      // Submit empty card to trigger accessible field error announcements
      const saveBtn = await page.$('[data-testid="auth-card-submit-btn"], button:has-text("Create Card")');
      if (saveBtn) {
        await saveBtn.click();
        await page.waitForTimeout(500);
      }
    },
  },
  {
    name: '04-mobile-portrait-mcp-mint-modal',
    width: 390,
    height: 844,
    theme: 'light',
    url: `${BASE_URL}/settings/mcp`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const mintBtn = await page.$('[data-testid="mint-key-button"]');
      if (mintBtn) {
        await mintBtn.click();
        await page.waitForTimeout(600);
      }
      // Open advanced restrictions
      const advToggle = await page.$('[data-testid="advanced-capability-restrictions-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
      // Type invalid CIDR to trigger error announcement
      const cidrInput = await page.$('#mint-allowed-cidrs-input');
      if (cidrInput) {
        await cidrInput.fill('999.999.999.999/99');
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: '05-mobile-landscape-custom-field-editor',
    width: 844,
    height: 390,
    theme: 'light',
    url: `${BASE_URL}/projects/KAN/settings/custom-fields`,
    action: async (page) => {
      await page.waitForTimeout(1000);
      const newBtn = await page.$('[data-testid="create-new-field-btn"]');
      if (newBtn) {
        await newBtn.click();
        await page.waitForTimeout(500);
      }
      const advToggle = await page.$('[data-testid="custom-field-advanced-section-toggle"]');
      if (advToggle) {
        await advToggle.click();
        await page.waitForTimeout(400);
      }
      const nameInput = await page.$('#field-name');
      if (nameInput) await nameInput.fill('Risk Factor');
      const slugInput = await page.$('#field-slug');
      if (slugInput) await slugInput.fill('risk-factor');

      const meta = await page.$('#format-metadata');
      if (meta) {
        await meta.fill('{ malformed json }');
        const saveBtn = await page.$('[data-testid="save-definition-btn"]');
        if (saveBtn) {
          await saveBtn.click();
          await page.waitForTimeout(500);
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

      // Intercept project detail
      await page.route('**/api/v1/projects/KAN', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'p-1',
            identifier: 'KAN',
            name: 'Kanban Platform',
            description: 'Core project',
            modules_enabled: true,
            is_project_admin: true,
          }),
        });
      });

      // Intercept project states
      await page.route('**/api/v1/projects/KAN/states**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'st-1',
              name: 'Todo',
              group: 'unstarted',
              sort_order: 1,
              color_hex: '#64748b',
              is_default: true,
              wip_soft_limit: 3,
              wip_hard_limit: 6,
            },
            {
              id: 'st-2',
              name: 'In Progress',
              group: 'started',
              sort_order: 2,
              color_hex: '#3b82f6',
              is_default: false,
              wip_soft_limit: null,
              wip_hard_limit: null,
            },
          ]),
        });
      });

      // Intercept custom fields
      await page.route('**/api/v1/projects/KAN/custom-fields**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'f-1',
              slug: 'cvss-score',
              name: 'CVSS Score',
              tier: 'wasm',
              output_format: 'severity_pill',
              output_format_metadata: {},
              target_scope: 'PROJECT',
              credential_mode: 'INVOKING_USER',
              egress_allowlist: [],
              is_enabled: true,
            },
          ]),
        });
      });

      // Intercept MCP keys
      await page.route('**/api/v1/mcp/keys**', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });

      // Intercept quick create submission with simulated error
      await page.route('**/api/v1/projects/KAN/issues', (route) => {
        if (route.request().method() === 'POST') {
          route.fulfill({
            status: 400,
            contentType: 'application/json',
            body: JSON.stringify({
              detail: 'Validation error: Issue summary requires unique index verification',
            }),
          });
        } else {
          route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
        }
      });

      await page.goto(vp.url, { waitUntil: 'domcontentloaded' });

      // Apply theme
      if (vp.theme === 'dark') {
        await page.evaluate(() => {
          document.documentElement.classList.add('dark');
          document.documentElement.setAttribute('data-theme', 'dark');
        });
      }

      if (vp.action) {
        try {
          await vp.action(page);
        } catch (err) {
          console.warn(`Action failed for ${vp.name}:`, err.message);
        }
      }

      await page.screenshot({
        path: path.join(OUT_DIR, `${vp.name}.png`),
        fullPage: false,
      });
      console.log(`Saved ${vp.name}.png`);
      await context.close();
    }

    await browser.close();
    console.log('All 5 responsive screenshots successfully captured!');
  } finally {
    previewProc.kill();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
