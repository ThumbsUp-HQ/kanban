// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Playwright screenshot capture script for KAN-438.
 * Captures responsive views of:
 * 1. DefaultWorkflowHooksStudio (/admin/workflows) showing System-Wide Default Workflow Hook Templates
 * 2. DefaultWorkflowHooksStudio dialog (/admin/workflows) showing Add/Edit Default Hook Template
 * 3. WorkflowStudioPage (/projects/PROJ/settings/workflows) showing Inherited from Default badge and Sync Default Hooks button
 * 4. WorkspaceSettingsPage (/workspaces/settings#tab-workflows) showing Workspace Default Workflow Hooks
 */

import fs from 'node:fs';
import path from 'node:path';

let chromium;
try {
  const localPlaywright = path.resolve('kanban/web/node_modules/@playwright/test/index.mjs');
  ({ chromium } = await import(localPlaywright));
} catch {
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    ({ chromium } = await import('@playwright/test'));
  }
}

const PORT = process.env.KAN438_PORT || '18438';
const BASE_URL = `http://127.0.0.1:${PORT}`;
const COOKIE_VAL = process.env.KAN438_COOKIE || '';
const CSRF_TOKEN = process.env.KAN438_CSRF || '';

const OUT_DIR = path.resolve('docs/qa/KAN-438/screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function preparePageForScreenshot(page, theme) {
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
  }, theme);
  await page.waitForTimeout(300);
}

async function saveScreenshot(page, filename) {
  const fullPath = path.join(OUT_DIR, filename);
  await page.screenshot({ path: fullPath, fullPage: false });
  console.log(`[Captured] ${filename}`);
}

async function createContext(browser, width, height, theme) {
  const context = await browser.newContext({
    viewport: { width, height },
    colorScheme: theme,
    bypassCSP: true,
  });

  if (COOKIE_VAL) {
    await context.addCookies([
      {
        name: 'kb_session',
        value: COOKIE_VAL,
        url: `http://127.0.0.1:${PORT}/`,
        httpOnly: true,
        sameSite: 'Lax',
      },
      {
        name: 'kb_csrf',
        value: CSRF_TOKEN,
        url: `http://127.0.0.1:${PORT}/`,
        httpOnly: false,
        sameSite: 'Lax',
      },
    ]);
  }

  return context;
}

const VIEWPORTS = [
  { name: 'desktop-light-1440x900', width: 1440, height: 900, theme: 'light' },
  { name: 'desktop-dark-1440x900', width: 1440, height: 900, theme: 'dark' },
  { name: 'tablet-768x1024', width: 768, height: 1024, theme: 'light' },
  { name: 'mobile-390x844', width: 390, height: 844, theme: 'light' },
];

async function main() {
  console.log(`[Playwright] Connecting to ${BASE_URL}...`);
  const browser = await chromium.launch({ headless: true });

  try {
    for (const vp of VIEWPORTS) {
      console.log(`\n--- Viewport: ${vp.name} (${vp.width}x${vp.height}, theme=${vp.theme}) ---`);
      const context = await createContext(browser, vp.width, vp.height, vp.theme);
      const page = await context.newPage();
      page.on('console', (msg) => console.log(`[Browser Console] ${msg.type()}: ${msg.text()}`));
      page.on('pageerror', (err) => console.log(`[Browser Error] ${err.message}`));

      // 1. System Default Workflow Hooks Studio (/admin/workflows)
      console.log(`Navigating to ${BASE_URL}/admin/workflows...`);
      await page.goto(`${BASE_URL}/admin/workflows`, { waitUntil: 'networkidle' });
      await preparePageForScreenshot(page, vp.theme);

      const adminStudio = page.locator('[data-testid="default-workflow-hooks-studio"]');
      await adminStudio.waitFor({ state: 'visible', timeout: 10000 });

      await saveScreenshot(page, `01-admin-default-workflow-hooks-${vp.name}.png`);
      // Also save primary desktop screenshots as canonical names
      await saveScreenshot(page, `${vp.name}.png`);

      // 2. Open Add Default Hook Template dialog
      const addBtn = page.locator('[data-testid="create-default-hook-btn"]').first();
      if (await addBtn.isVisible()) {
        await addBtn.click();
        const dialog = page.locator('[data-testid="template-dialog"]');
        await dialog.waitFor({ state: 'visible', timeout: 5000 });
        await page.waitForTimeout(200);

        await saveScreenshot(page, `02-add-default-hook-template-dialog-${vp.name}.png`);

        const cancelBtn = page.locator('[data-testid="cancel-template-btn"]').first();
        if (await cancelBtn.isVisible()) {
          await cancelBtn.click();
          await page.waitForTimeout(200);
        }
      }

      // 3. Project Workflow Studio (/projects/PROJ/settings/workflows) showing Inherited from Default badge and Sync button
      console.log(`Navigating to ${BASE_URL}/projects/PROJ/settings/workflows...`);
      await page.goto(`${BASE_URL}/projects/PROJ/settings/workflows`, { waitUntil: 'networkidle' });
      await preparePageForScreenshot(page, vp.theme);

      const studioPage = page.locator('[data-testid="workflow-studio-page"]');
      await studioPage.waitFor({ state: 'visible', timeout: 10000 });

      // Verify inherited badge is present
      const inheritedBadge = page.locator('[data-testid^="hook-inherited-badge-"]').first();
      if (await inheritedBadge.isVisible()) {
        console.log('[Verified] Inherited from Default badge is visible on project hook');
      }

      const syncBtn = page.locator('[data-testid="sync-default-hooks-btn"]');
      await syncBtn.waitFor({ state: 'visible', timeout: 5000 });

      await saveScreenshot(page, `03-project-workflow-inherited-hooks-${vp.name}.png`);

      // 4. Workspace Default Workflow Hooks tab (/workspaces/settings#tab-workflows)
      console.log(`Navigating to ${BASE_URL}/workspaces/settings#tab-workflows...`);
      await page.goto(`${BASE_URL}/workspaces/settings#tab-workflows`, { waitUntil: 'networkidle' });
      await preparePageForScreenshot(page, vp.theme);
      await page.waitForTimeout(500);

      const wsTab = page.locator('[data-testid="tab-workflows"]');
      if (await wsTab.isVisible()) {
        await wsTab.click();
        await page.waitForTimeout(300);
      }

      await saveScreenshot(page, `04-workspace-default-workflow-hooks-${vp.name}.png`);

      await context.close();
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error('[Playwright Error]', err);
  process.exit(1);
});
