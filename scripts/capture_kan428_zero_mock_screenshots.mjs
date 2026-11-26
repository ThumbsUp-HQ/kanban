// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';

let chromium;
try {
  const localPlaywright = path.resolve('kanban/web/node_modules/@playwright/test/index.mjs');
  ({ chromium } = await import(localPlaywright));
} catch {
  ({ chromium } = await import('@playwright/test'));
}

const PORT = 18428;
const BASE_URL = `http://127.0.0.1:${PORT}`;

const OUT_DIRS = [
  path.resolve('docs/workouts/slice-5-workspace-project-workflows/screenshots'),
  path.resolve('docs/qa/KAN-428/screenshots'),
];

for (const dir of OUT_DIRS) {
  fs.mkdirSync(dir, { recursive: true });
}

// Read session credentials
let sessionData = { cookie: '', cookieRaw: '', csrfToken: '' };
try {
  const raw = fs.readFileSync('/tmp/slice5_session.json', 'utf-8');
  sessionData = JSON.parse(raw);
} catch (e) {
  console.warn('Could not read /tmp/slice5_session.json, proceeding with default session:', e.message);
}

const VIEWPORTS = [
  { name: 'desktop-1440x900-light', width: 1440, height: 900, colorScheme: 'light' },
  { name: 'desktop-1440x900-dark', width: 1440, height: 900, colorScheme: 'dark' },
  { name: 'tablet-landscape-1024x768', width: 1024, height: 768, colorScheme: 'light' },
  { name: 'tablet-portrait-768x1024', width: 768, height: 1024, colorScheme: 'light' },
  { name: 'mobile-portrait-390x844', width: 390, height: 844, colorScheme: 'light' },
];

async function saveScreenshot(page, filename) {
  for (const dir of OUT_DIRS) {
    const targetPath = path.join(dir, filename);
    await page.screenshot({ path: targetPath });
    console.log(`Saved screenshot: ${targetPath}`);
  }
}

async function main() {
  console.log(`Launching Playwright Chromium in ZERO-MOCK mode against ${BASE_URL}...`);
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    for (const vp of VIEWPORTS) {
      console.log(`\n=== Viewport: ${vp.name} (${vp.width}x${vp.height}, ${vp.colorScheme}) ===`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: vp.colorScheme,
      });

      if (sessionData.cookieRaw) {
        await context.addCookies([
          {
            name: 'kb_session',
            value: sessionData.cookieRaw,
            url: BASE_URL,
            httpOnly: true,
            sameSite: 'Lax',
          },
          {
            name: 'kb_csrf',
            value: sessionData.csrfToken,
            url: BASE_URL,
            httpOnly: false,
            sameSite: 'Lax',
          },
        ]);
      }

      const page = await context.newPage();
      page.setDefaultTimeout(5000);
      page.setDefaultNavigationTimeout(10000);

      async function safeNavigate(targetUrl, expectedSelector) {
        try {
          await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 8000 });
          if (expectedSelector) {
            await page.locator(expectedSelector).first().waitFor({ state: 'visible', timeout: 6000 }).catch(() => {});
          }
        } catch (e) {
          console.warn(`safeNavigate to ${targetUrl} fallback:`, e.message);
        }
        await page.waitForTimeout(150);
      }

      // ==========================================
      // 1. WorkspaceSettingsPage
      // ==========================================
      console.log('Navigating to /workspaces/settings...');
      await safeNavigate(`${BASE_URL}/workspaces/settings`, '[data-testid="idle-preset-30m"]');

      await page.evaluate((theme) => {
        try {
          localStorage.setItem('kb-theme', theme);
          document.documentElement.setAttribute('data-theme', theme);
          if (theme === 'dark') {
            document.documentElement.classList.add('dark');
          } else {
            document.documentElement.classList.remove('dark');
          }
        } catch (_) {}
      }, vp.colorScheme);

      const idlePill = page.locator('[data-testid="idle-preset-30m"]');
      if (await idlePill.isVisible()) {
        await idlePill.click();
        await page.waitForTimeout(100);
      }

      await saveScreenshot(page, `01-workspace-settings-general-${vp.name}.png`);

      if (vp.name === 'desktop-1440x900-light') {
        const tabGroups = page.locator('[data-testid="tab-groups"]');
        if (await tabGroups.isVisible()) {
          await tabGroups.click();
          await page.waitForTimeout(200);
          await saveScreenshot(page, `02-workspace-settings-groups-nested-${vp.name}.png`);
        }

        const tabTrash = page.locator('[data-testid="tab-trash"]');
        if (await tabTrash.isVisible()) {
          await tabTrash.click();
          await page.waitForTimeout(200);
          await saveScreenshot(page, `03-workspace-settings-trash-retention-${vp.name}.png`);
        }
      }

      // ==========================================
      // 2. ProjectSettingsPage
      // ==========================================
      console.log('Navigating to /projects/KAN/settings...');
      await safeNavigate(`${BASE_URL}/projects/KAN/settings`, '[data-testid="tab-priorities"]');

      const tabPriorities = page.locator('[data-testid="tab-priorities"]');
      if (await tabPriorities.isVisible()) {
        await tabPriorities.click();
        await page.waitForTimeout(150);
      }
      const fireEmojiBtn = page.locator('[data-testid="priority-emoji-btn-🔥"]');
      if (await fireEmojiBtn.isVisible()) {
        await fireEmojiBtn.click();
        await page.waitForTimeout(100);
      }
      await saveScreenshot(page, `04-project-settings-priorities-${vp.name}.png`);

      const tabStates = page.locator('[data-testid="tab-states"]');
      if (await tabStates.isVisible()) {
        await tabStates.click();
        await page.waitForTimeout(150);
      }
      await saveScreenshot(page, `05-project-settings-wip-limits-${vp.name}.png`);

      const tabDanger = page.locator('[data-testid="tab-danger"]');
      if (await tabDanger.isVisible()) {
        await tabDanger.click();
        await page.waitForTimeout(150);
      }
      await saveScreenshot(page, `06-project-settings-danger-zone-${vp.name}.png`);

      // ==========================================
      // 3. PersonalSettingsPage
      // ==========================================
      console.log('Navigating to /settings/profile...');
      await safeNavigate(`${BASE_URL}/settings/profile`, '[data-testid="personal-settings-page"]');

      const tzInput = page.locator('[data-testid="timezone-filter-input"]');
      if (await tzInput.isVisible()) {
        await tzInput.fill('New York');
        await page.waitForTimeout(150);
      }
      await saveScreenshot(page, `08-personal-settings-${vp.name}.png`);

      // ==========================================
      // 4. CustomFieldsStudio
      // ==========================================
      console.log('Navigating to /projects/KAN/settings/custom-fields...');
      await safeNavigate(`${BASE_URL}/projects/KAN/settings/custom-fields`, '[data-testid="custom-fields-studio"]');
      await saveScreenshot(page, `10-custom-fields-studio-${vp.name}.png`);

      if (vp.name === 'desktop-1440x900-light') {
        const invoiceRow = page.locator('[data-testid="field-item-invoice-total"], li:has-text("invoice-total"), li:has-text("Invoice Total")');
        if (await invoiceRow.first().isVisible()) {
          await invoiceRow.first().click();
          await page.waitForTimeout(200);
          await saveScreenshot(page, `13-custom-fields-escalation-dual-control-${vp.name}.png`);
        }

        const newCfBtn = page.locator('[data-testid="new-custom-field-btn"], button:has-text("+ New Field"), button:has-text("New Custom Field"), button:has-text("Create")');
        if (await newCfBtn.first().isVisible()) {
          await newCfBtn.first().click();
          await page.waitForTimeout(200);
          await saveScreenshot(page, `11-custom-fields-editor-tier-a-${vp.name}.png`);

          const formatSelect = page.locator('select[name="output_format"], [data-testid="output-format-select"]');
          if (await formatSelect.isVisible()) {
            await formatSelect.selectOption('number');
            await page.waitForTimeout(150);
            await saveScreenshot(page, `12-custom-fields-structured-format-${vp.name}.png`);
          }
        }
      }

      // ==========================================
      // 5. WorkflowStudioPage
      // ==========================================
      console.log('Navigating to /projects/KAN/settings/workflows...');
      await safeNavigate(`${BASE_URL}/projects/KAN/settings/workflows`, '[data-testid="workflow-studio-page"]');
      await saveScreenshot(page, `15-workflow-studio-${vp.name}.png`);

      if (vp.name === 'desktop-1440x900-light') {
        const attachBtn = page.locator('[data-testid="add-transition-rule-btn"], button:has-text("Add Transition Rule"), button:has-text("Attach Hook")');
        if (await attachBtn.first().isVisible()) {
          await attachBtn.first().click();
          await page.waitForTimeout(200);
          await saveScreenshot(page, `16-workflow-attach-hook-dialog-${vp.name}.png`);

          const backdrop = page.locator('.workflow-modal-backdrop');
          if (await backdrop.isVisible()) {
            await backdrop.click({ position: { x: 5, y: 5 }, force: true });
            await page.waitForTimeout(150);
          }
        }

        const dryRunBtn = page.locator('button:has-text("Dry-Run Against Sample Ticket"), button[aria-label*="Dry-run against sample ticket"], [data-testid="launch-dry-run-btn"]');
        if (await dryRunBtn.first().isVisible()) {
          await dryRunBtn.first().click();
          await page.waitForTimeout(200);
          await saveScreenshot(page, `17-workflow-dry-run-drawer-${vp.name}.png`);

          const closeDrawerBtn = page.locator('button[aria-label="Close Dry-Run Drawer"], button:has-text("✕ Close"), [data-testid="close-drawer-btn"]');
          if (await closeDrawerBtn.first().isVisible()) {
            await closeDrawerBtn.first().click();
            await page.waitForTimeout(150);
          } else {
            const backdrop = page.locator('.workflow-modal-backdrop');
            if (await backdrop.isVisible()) {
              await backdrop.click({ position: { x: 5, y: 5 }, force: true });
              await page.waitForTimeout(150);
            }
          }
        }

        const bindRepoBtn = page.locator('button[aria-label="Bind Git Repository"], button:has-text("+ Bind Git Repository")');
        if (await bindRepoBtn.first().isVisible()) {
          await bindRepoBtn.first().click();
          await page.waitForTimeout(200);
          await saveScreenshot(page, `18-workflow-git-repo-bindings-${vp.name}.png`);

          const cancelRepoBtn = page.locator('.workflow-dialog-actions button.workflow-btn-secondary:has-text("Cancel")');
          if (await cancelRepoBtn.first().isVisible()) {
            await cancelRepoBtn.first().click();
            await page.waitForTimeout(150);
          } else {
            const backdrop = page.locator('.workflow-modal-backdrop');
            if (await backdrop.isVisible()) {
              await backdrop.click({ position: { x: 5, y: 5 }, force: true });
              await page.waitForTimeout(150);
            }
          }
        }
      }

      await context.close();
      console.log(`Finished viewport ${vp.name}.`);
    }
  } finally {
    await browser.close();
    console.log('Playwright Chromium browser closed.');
  }
}

main().catch((err) => {
  console.error('Playwright capture failed:', err);
  process.exit(1);
});
