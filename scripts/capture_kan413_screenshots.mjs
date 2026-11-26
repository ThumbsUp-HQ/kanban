// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
/**
 * Zero-mock Playwright multi-viewport screenshot capture harness for KAN-413.
 * Captures unclipped PNG screenshots of real running SPA on 127.0.0.1:18413 with 0 page.route / 0 mockApi.
 */

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(path.join(process.cwd(), 'kanban/web/node_modules/@playwright/test'));

const [,, serverUrl, adminCookie, adminCsrf, outDir1, outDir2] = process.argv;

if (!serverUrl || !adminCookie || !adminCsrf || !outDir1 || !outDir2) {
  console.error('Usage: node capture_kan413_screenshots.mjs <SERVER_URL> <COOKIE> <CSRF> <OUT_DIR1> <OUT_DIR2>');
  process.exit(1);
}

fs.mkdirSync(outDir1, { recursive: true });
fs.mkdirSync(outDir2, { recursive: true });

async function saveScreenshot(page, filename) {
  const file1 = path.join(outDir1, filename);
  const file2 = path.join(outDir2, filename);
  await page.screenshot({ path: file1, fullPage: true });
  fs.copyFileSync(file1, file2);
  console.log(`[CAPTURED] ${filename} (${fs.statSync(file1).size} bytes)`);
}

async function run() {
  console.log(`Launching Chromium against live server: ${serverUrl}`);
  const browser = await chromium.launch({ headless: true });

  const urlObj = new URL(serverUrl);
  const domain = urlObj.hostname;

  // Viewport definitions
  const viewports = [
    { name: '1440x900-light', width: 1440, height: 900, colorScheme: 'light' },
    { name: '1440x900-dark', width: 1440, height: 900, colorScheme: 'dark' },
    { name: '1024x768-tablet-landscape', width: 1024, height: 768, colorScheme: 'light' },
    { name: '768x1024-tablet-portrait', width: 768, height: 1024, colorScheme: 'light' },
    { name: '390x844-mobile-portrait', width: 390, height: 844, colorScheme: 'light' },
  ];

  // Helper to create authed context
  async function createContext(vp) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      colorScheme: vp.colorScheme,
    });
    await ctx.addCookies([
      {
        name: 'kb_session',
        value: adminCookie,
        domain,
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
      },
      {
        name: 'kb_csrf',
        value: adminCsrf,
        domain,
        path: '/',
        httpOnly: false,
        sameSite: 'Lax',
      },
    ]);
    return ctx;
  }

  // 1. Capture Multi-Viewport Screens for AiStudioPage
  for (const vp of viewports) {
    const ctx = await createContext(vp);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/workspaces/settings/ai`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="ai-studio-page"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="ai-provider-card"]', { timeout: 10000 }).catch(() => {});
    await saveScreenshot(page, `slice2-ai-studio-${vp.name}.png`);
    await ctx.close();
  }

  // 2. Capture Multi-Viewport Screens for AgentStudioPage
  for (const vp of viewports) {
    const ctx = await createContext(vp);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/workspaces/settings/agents`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="agent-studio-page"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="agent-definition-card"]', { timeout: 10000 }).catch(() => {});
    await saveScreenshot(page, `slice2-agent-studio-${vp.name}.png`);
    await ctx.close();
  }

  // 3. Capture Multi-Viewport Screens for RunnerStudioPage
  for (const vp of viewports) {
    const ctx = await createContext(vp);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/admin/agent-runners`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="runner-studio-page"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="runner-card"]', { timeout: 10000 }).catch(() => {});
    await saveScreenshot(page, `slice2-runner-studio-${vp.name}.png`);
    await ctx.close();
  }

  // 4. Capture PersonalSettingsPage with AgentOnboardingPromptCard (1440x900 light/dark)
  for (const vp of viewports.slice(0, 2)) {
    const ctx = await createContext(vp);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/settings/profile`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="agent-onboarding-prompt-card"]', { timeout: 10000 });
    await page.locator('[data-testid="agent-onboarding-prompt-card"]').scrollIntoViewIfNeeded();
    await saveScreenshot(page, `slice2-onboarding-${vp.name}.png`);
    await ctx.close();
  }

  // 5. Interactive States: AiProviderEditorDrawer (verify 0 password inputs)
  {
    const ctx = await createContext(viewports[0]);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/workspaces/settings/ai`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="register-provider-btn"]');
    await page.click('[data-testid="register-provider-btn"]');
    await page.waitForSelector('[data-testid="ai-provider-editor-drawer"]');

    // Invariant check: 0 password input fields in DOM
    const passwordInputs = await page.$$('input[type="password"]');
    if (passwordInputs.length !== 0) {
      throw new Error(`Forbidden password input found in AiProviderEditorDrawer: count=${passwordInputs.length}`);
    }
    console.log('[SECURITY VERIFIED] AiProviderEditorDrawer contains 0 password inputs');
    await saveScreenshot(page, 'slice2-ai-provider-drawer-create.png');
    await ctx.close();
  }

  // 6. Interactive States: AiBudgetModal (Freeze & Unlimited states)
  {
    const ctx = await createContext(viewports[0]);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/workspaces/settings/ai`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="ai-studio-page"]');
    const manageBtn = page.locator('[data-testid^="manage-budget-btn-"]').first();
    await manageBtn.waitFor();
    await manageBtn.click();
    await page.waitForSelector('[data-testid="ai-budget-modal"]');

    // Capture Unlimited state
    const unlimitedBtn = page.locator('[data-testid="cap-mode-unlimited-btn"]');
    await unlimitedBtn.waitFor();
    await unlimitedBtn.click();
    await page.waitForTimeout(300);
    await saveScreenshot(page, 'slice2-ai-budget-modal-unlimited.png');

    // Switch to Enforce mode
    const enforceBtn = page.locator('[data-testid="cap-mode-enforce-btn"]');
    await enforceBtn.waitFor();
    await enforceBtn.click();
    await page.waitForTimeout(300);

    // Click 0 (Freeze) preset and capture Freeze state
    const freezeBtn = page.locator('[data-testid="preset-budget-0-freeze-btn"]');
    await freezeBtn.waitFor();
    await freezeBtn.click();
    await page.waitForTimeout(300);
    await saveScreenshot(page, 'slice2-ai-budget-modal-freeze.png');

    await ctx.close();
  }

  // 7. Interactive States: AgentStudioPage -> AgentValidationModal
  {
    const ctx = await createContext(viewports[0]);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/workspaces/settings/agents`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="agent-studio-page"]');
    const validateBtn = page.locator('[data-testid^="validate-agent-btn-"]').first();
    await validateBtn.waitFor();
    await validateBtn.click();
    await page.waitForSelector('[data-testid="agent-validation-modal"]');
    await page.waitForTimeout(500);
    await saveScreenshot(page, 'slice2-agent-validation-modal-trace.png');
    await ctx.close();
  }

  // 8. Interactive States: RunnerStudioPage -> MintEnrollmentTokenModal
  {
    const ctx = await createContext(viewports[0]);
    const page = await ctx.newPage();
    await page.goto(`${serverUrl}/admin/agent-runners`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="open-mint-modal-btn"]');
    await page.click('[data-testid="open-mint-modal-btn"]');
    await page.waitForSelector('[data-testid="mint-enrollment-token-modal"]');

    // Generate token by clicking submit button
    const submitBtn = page.locator('[data-testid="submit-mint-token-btn"]');
    if (await submitBtn.count() > 0) {
      await submitBtn.click();
      await page.waitForSelector('[data-testid="runner-cli-command"]', { timeout: 5000 });
    }
    // Mask token in DOM before screenshot
    await page.evaluate(() => {
      const el = document.querySelector('.kb-token-display-box span');
      if (el) el.textContent = 'kb_rnr_enroll_***REDACTED***';
      const cmd = document.querySelector('[data-testid="runner-cli-command"]');
      if (cmd) cmd.textContent = cmd.textContent.replace(/kb_rnr_enroll_[A-Za-z0-9_-]+/g, 'kb_rnr_enroll_***REDACTED***');
    });
    await page.waitForTimeout(300);
    await saveScreenshot(page, 'slice2-runner-mint-token-modal.png');
    await ctx.close();
  }

  await browser.close();
  console.log('All zero-mock screenshots captured successfully!');
}

run().catch((err) => {
  console.error('Fatal error capturing screenshots:', err);
  process.exit(1);
});
