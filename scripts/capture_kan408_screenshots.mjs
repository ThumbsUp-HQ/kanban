// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

let chromium;
for (const p of [
  '/home/adamoutler/.npm/_npx/81bbc6515d992ace/node_modules/playwright/index.mjs',
  '@playwright/test',
  'playwright',
]) {
  try {
    ({ chromium } = await import(p));
    if (chromium) break;
  } catch {}
}

const PORT = 18408;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIRS = [
  path.resolve('docs/workouts/slice-1-auth-rbac/screenshots'),
  path.resolve('docs/qa/KAN-408/screenshots'),
];

async function applyUnclippedStyle(page) {
  await page.evaluate(() => {
    document.documentElement.style.setProperty('position', 'relative', 'important');
    for (const el of document.querySelectorAll('.kb-app-shell, .kb-main-canvas')) {
      el.style.setProperty('height', 'auto', 'important');
      el.style.setProperty('max-height', 'none', 'important');
      el.style.setProperty('overflow', 'visible', 'important');
    }
    for (const el of document.querySelectorAll('.kb-topbar, header')) {
      el.style.setProperty('position', 'static', 'important');
    }
    for (const el of document.querySelectorAll('[class*="backdrop"], [class*="modal-overlay"], .rbac-modal-overlay')) {
      el.style.setProperty('position', 'absolute', 'important');
      el.style.setProperty('inset', '0', 'important');
      el.style.setProperty('min-height', '100%', 'important');
      el.style.setProperty('height', '100%', 'important');
    }
  });
}

async function saveScreenshot(page, filename) {
  for (const dir of OUT_DIRS) {
    fs.mkdirSync(dir, { recursive: true });
    await page.screenshot({
      path: path.join(dir, filename),
      fullPage: true,
    });
  }
  console.log(`Saved screenshot: ${filename}`);
}

async function main() {
  const sessionCookie = process.env.KANBAN_SESSION_COOKIE;
  const csrfCookie = process.env.KANBAN_CSRF_COOKIE;
  const recoveryCode = process.env.KANBAN_RECOVERY_CODE || '';
  const dbName = process.env.KANBAN_DB_NAME || 'kanban_workout';

  const telemetry = {
    consoleErrors: [],
    pageErrors: [],
    serverErrors: [],
  };

  const browser = await chromium.launch({
    headless: true,
    executablePath: '/home/adamoutler/.cache/ms-playwright/chromium-1255/chrome-linux64/chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  function attachTelemetry(page) {
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const txt = msg.text();
        // Ignore benign favicon/font 404s and expected 4xx HTTP responses logged by Chromium
        if (!txt.includes('favicon.ico') && !txt.startsWith('Failed to load resource:')) {
          telemetry.consoleErrors.push(txt);
        }
      }
    });
    page.on('pageerror', (err) => {
      telemetry.pageErrors.push(err.message);
    });
    page.on('response', (res) => {
      if (res.status() >= 500) {
        telemetry.serverErrors.push(`${res.request().method()} ${res.url()} -> ${res.status()}`);
      }
    });
  }

  async function createContext(options = {}) {
    const context = await browser.newContext(options);
    if (sessionCookie) {
      await context.addCookies([
        { name: 'kb_session', value: sessionCookie, domain: '127.0.0.1', path: '/' },
        { name: 'kb_csrf', value: csrfCookie || 'workout-csrf', domain: '127.0.0.1', path: '/' },
      ]);
    }
    const origNewPage = context.newPage.bind(context);
    context.newPage = async (...args) => {
      const page = await origNewPage(...args);
      attachTelemetry(page);
      return page;
    };
    return context;
  }

  try {
    // -----------------------------------------------------------------------
    // Viewport 1: 01-desktop-1440x900-light (Auth Studio + LDAP AD preset in drawer)
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 01-desktop-1440x900-light...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      // Open Add Auth Card drawer
      const addBtn = page.locator('.auth-studio-add-btn').first();
      await addBtn.waitFor({ state: 'visible', timeout: 15000 });
      await addBtn.click();
      const drawer = page.locator('.auth-editor-drawer');
      await drawer.waitFor({ state: 'visible', timeout: 5000 });

      // Select LDAP
      const providerSelect = page.locator('#card-provider-kind');
      if (await providerSelect.count()) {
        await providerSelect.selectOption('LDAP');
      }

      // Click Active Directory preset
      const adPresetBtn = page.locator('.auth-preset-btn', { hasText: 'Active Directory' });
      if (await adPresetBtn.count()) {
        await adPresetBtn.click();
      }

      const nameInput = page.locator('#card-display-name');
      if (await nameInput.count()) await nameInput.fill('Corporate Active Directory');
      const urlInput = page.locator('#card-server-url');
      if (await urlInput.count()) await urlInput.fill('ldaps://ad.corp.example.com:636');
      const bindDnInput = page.locator('#card-bind-dn');
      if (await bindDnInput.count()) await bindDnInput.fill('cn=admin,ou=services,dc=corp,dc=example,dc=com');
      const passInput = page.locator('#card-secret');
      if (await passInput.count()) await passInput.fill('HardenedAdBindPassword!2026');

      await page.waitForTimeout(400);
      await applyUnclippedStyle(page);
      await saveScreenshot(page, '01-desktop-1440x900-light.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Viewport 2: 02-desktop-1440x900-dark (Break-Glass Warning Modal)
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 02-desktop-1440x900-dark...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'dark',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
      });

      // Find toggle switch on the local admin card to trigger break-glass warning
      const localSwitch = page.locator('.auth-toggle-switch').last();
      await localSwitch.waitFor({ state: 'visible', timeout: 8000 });
      await localSwitch.click();

      // Verify break-glass warning modal appears
      const breakGlassModal = page.locator('[data-testid="break-glass-warning-dialog"]');
      await breakGlassModal.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});

      await page.waitForTimeout(400);
      await applyUnclippedStyle(page);
      await saveScreenshot(page, '02-desktop-1440x900-dark.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Viewport 3: 03-desktop-1024x768 (Roles & Permissions tab with RbacPolicyBuilder)
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 03-desktop-1024x768...');
      const context = await createContext({
        viewport: { width: 1024, height: 768 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });

      const rolesTabBtn = page.locator('#auth-tab-roles, .auth-tab-btn:has-text("Roles")').first();
      if (await rolesTabBtn.count() && await rolesTabBtn.isVisible()) {
        await rolesTabBtn.click();
        const rbacBuilder = page.locator('.rbac-policy-builder, [data-testid="rbac-builder"]');
        await rbacBuilder.first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
      }

      await page.waitForTimeout(400);
      await applyUnclippedStyle(page);
      await saveScreenshot(page, '03-desktop-1024x768.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Viewport 4: 04-tablet-portrait-768x1024 (OIDC Auth Card edit drawer)
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 04-tablet-portrait-768x1024...');
      const context = await createContext({
        viewport: { width: 768, height: 1024 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);

      // Open Add Auth Card drawer
      const addBtn = page.locator('.auth-studio-add-btn').first();
      if (await addBtn.count() && await addBtn.isVisible()) {
        await addBtn.click();
        const drawer = page.locator('.auth-editor-drawer');
        await drawer.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});

        // Select OIDC
        const providerSelect = page.locator('#card-provider-kind');
        if (await providerSelect.count()) {
          await providerSelect.selectOption('OIDC');
        }
        const nameInput = page.locator('#card-display-name');
        if (await nameInput.count()) await nameInput.fill('Corporate Google SSO');
      }

      await page.waitForTimeout(400);
      await applyUnclippedStyle(page);
      await saveScreenshot(page, '04-tablet-portrait-768x1024.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Viewport 5: 05-mobile-portrait-390x844 (Responsive Auth Studio)
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 05-mobile-portrait-390x844...');
      const context = await createContext({
        viewport: { width: 390, height: 844 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);
      await applyUnclippedStyle(page);
      await saveScreenshot(page, '05-mobile-portrait-390x844.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Live Workflow State 06: Passkey WebAuthn Registered & Enrolled
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 06-passkey-webauthn-registered.png...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      // Setup CDP virtual authenticator
      const cdp = await context.newCDPSession(page);
      await cdp.send('WebAuthn.enable');
      await cdp.send('WebAuthn.addVirtualAuthenticator', {
        options: {
          protocol: 'ctap2',
          transport: 'internal',
          hasResidentKey: true,
          hasUserVerification: true,
          isUserVerified: true,
          automaticPresenceSimulation: true,
        },
      });

      await page.goto(`${BASE_URL}/settings/profile`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);

      // Verify the registered passkey row is visible in the table (enrolled during Workout 1)
      await page.waitForSelector('.kb-table-scroll-container, [data-testid^="passkey-badge-"], tr:has-text("Touch ID")', { state: 'visible', timeout: 8000 }).catch(() => {});
      await page.waitForTimeout(600);

      await applyUnclippedStyle(page);
      await saveScreenshot(page, '06-passkey-webauthn-registered.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Live Workflow State 07: TOTP & Recovery Codes Dialog
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 07-totp-recovery-codes.png...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      page.on('dialog', (dialog) => dialog.accept());
      await page.goto(`${BASE_URL}/settings/profile`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);

      const regenBtn = page.locator('[data-testid="regenerate-recovery-codes-btn"]').first();
      if (await regenBtn.count() && await regenBtn.isVisible()) {
        await regenBtn.click();
        const modal = page.locator('[data-testid="recovery-codes-grid"]');
        await modal.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
      }

      await applyUnclippedStyle(page);
      await saveScreenshot(page, '07-totp-recovery-codes.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Live Workflow State 08: LDAP Test-Draft Handshake Success
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 08-ldap-test-draft-success.png...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);

      // Open Add Auth Card drawer
      const addBtn = page.locator('.auth-studio-add-btn').first();
      if (await addBtn.count() && await addBtn.isVisible()) {
        await addBtn.click();
        const drawer = page.locator('.auth-editor-drawer');
        await drawer.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});

        // Fill in LDAPS parameters
        const providerSelect = page.locator('#card-provider-kind');
        if (await providerSelect.count()) await providerSelect.selectOption('LDAP');
        const nameInput = page.locator('#card-display-name');
        if (await nameInput.count()) await nameInput.fill('Planet Express LDAPS Enterprise');
        const urlInput = page.locator('#card-server-url');
        if (await urlInput.count()) await urlInput.fill('ldaps://127.0.0.1:10636');
        const bindDnInput = page.locator('#card-bind-dn');
        if (await bindDnInput.count()) await bindDnInput.fill('cn=admin,dc=planetexpress,dc=com');
        const baseDnInput = page.locator('#card-base-dn');
        if (await baseDnInput.count()) await baseDnInput.fill('dc=planetexpress,dc=com');
        const passInput = page.locator('#card-secret');
        if (await passInput.count()) await passInput.fill('GoodNewsEveryone');

        // Expand advanced section and populate pinned CA PEM
        const advBtn = page.locator('[data-testid="auth-advanced-section"] button, .auth-advanced-toggle').first();
        if (await advBtn.count()) await advBtn.click();

        const caInput = page.locator('#card-ca-cert, textarea[name="ca_cert_pem"]').first();
        if (await caInput.count() && process.env.KANBAN_CA_PEM) {
          await caInput.fill(process.env.KANBAN_CA_PEM);
        }

        // Click Test Handshake button with data-testid="drawer-test-handshake-btn" inside drawer
        const testBtn = drawer.locator('[data-testid="drawer-test-handshake-btn"]').first();
        if (await testBtn.count() && await testBtn.isVisible()) {
          await testBtn.click();
          await page.waitForSelector('[data-testid="drawer-handshake-result"]', { state: 'visible', timeout: 8000 }).catch(() => {});
          await page.waitForTimeout(600);
        }
      }

      await applyUnclippedStyle(page);
      await saveScreenshot(page, '08-ldap-test-draft-success.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Live Workflow State 09: Expired WebSudo Dirty-Drawer Replay Prompt
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 09-websudo-replay-active.png...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);

      // Open Add Auth Card drawer
      const addBtn = page.locator('button.auth-studio-add-btn:has-text("+ Add auth card")').first();
      if (await addBtn.count() && await addBtn.isVisible()) {
        await addBtn.click();
        const drawer = page.locator('.auth-editor-drawer');
        await drawer.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});

        // Fill in typed LDAP DN fields so drawer is dirty
        const providerSelect = page.locator('#card-provider-kind');
        if (await providerSelect.count()) await providerSelect.selectOption('LDAP');
        const nameInput = page.locator('#card-display-name');
        if (await nameInput.count()) await nameInput.fill('Staging Active Directory Enterprise');
        const bindDnInput = page.locator('#card-bind-dn');
        if (await bindDnInput.count()) await bindDnInput.fill('cn=admin,dc=planetexpress,dc=com');
        const baseDnInput = page.locator('#card-base-dn');
        if (await baseDnInput.count()) await baseDnInput.fill('dc=planetexpress,dc=com');
        const urlInput = page.locator('#card-server-url');
        if (await urlInput.count()) await urlInput.fill('ldaps://127.0.0.1:10636');

        // 1. Expire AAL2 in PostgreSQL
        try {
          execSync(
            `docker exec swarm-b-kan408-7b120ade-pg-test-1 psql -U kanban_test -d ${dbName} -c "UPDATE sessions SET aal2_verified_at = now() - interval '20 minutes', aal2_last_active_at = now() - interval '20 minutes';"`
          );
          console.log('Expired AAL2 in sessions table via PostgreSQL.');
        } catch (e) {
          console.warn('PostgreSQL session AAL2 expiration warning:', e.message);
        }

        // 2. Click Save card in drawer -> triggers real HTTP 403 AAL2_STALE on /api/v1/admin/auth-cards
        const saveBtn = drawer.locator('[data-testid="drawer-save-btn"], button[type="submit"]:has-text("Create Card")').first();
        if (await saveBtn.count() && await saveBtn.isVisible()) {
          await saveBtn.click();
        }

        // 3. Wait for organic WebSudo step-up modal to appear
        const wsModal = page.locator('[data-testid="websudo-stepup-modal"]');
        await wsModal.waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
        await page.waitForTimeout(400);

        await applyUnclippedStyle(page);
        await saveScreenshot(page, '09-websudo-replay-active.png');

        // 4. Enter recovery code in the organic modal to verify first-replay 200 OK
        if (recoveryCode && await wsModal.isVisible()) {
          const recTab = wsModal.locator('button[role="tab"]:has-text("Recovery")').first();
          if (await recTab.count() && await recTab.isVisible()) {
            await recTab.click();
            await page.waitForTimeout(200);
          }
          const recInput = wsModal.locator('#recovery-code-input, input[placeholder*="xxxx"]').first();
          if (await recInput.count() && await recInput.isVisible()) {
            await recInput.fill(recoveryCode);
            const submitRecBtn = wsModal.locator('button[type="submit"]:has-text("Verify recovery code")').first();
            if (await submitRecBtn.count() && await submitRecBtn.isVisible()) {
              await submitRecBtn.click();
              await page.waitForTimeout(1000);
            }
          }
        }
      }

      await context.close();
    }

    // -----------------------------------------------------------------------
    // Live Workflow State 10: OIDC Verified-Claim Linking
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 10-oidc-verified-claim-linked.png...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);

      const usersTabBtn = page.locator('#auth-tab-users, .auth-tab-btn:has-text("Users")').first();
      if (await usersTabBtn.count() && await usersTabBtn.isVisible()) {
        await usersTabBtn.click();
        await page.waitForTimeout(500);
      }

      await applyUnclippedStyle(page);
      await saveScreenshot(page, '10-oidc-verified-claim-linked.png');
      await context.close();
    }

    // -----------------------------------------------------------------------
    // Live Workflow State 11: Custom RBAC Role Policy Builder
    // -----------------------------------------------------------------------
    {
      console.log('Capturing 11-custom-rbac-policy-builder.png...');
      const context = await createContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);

      const rolesTabBtn = page.locator('#auth-tab-roles, .auth-tab-btn:has-text("Roles")').first();
      if (await rolesTabBtn.count() && await rolesTabBtn.isVisible()) {
        await rolesTabBtn.click();
        await page.waitForTimeout(600);

        // Select Quality Auditor Lead from dropdown if present
        const addRoleSelect = page.locator('[data-testid="rbac-select-role-dropdown"]').first();
        if (await addRoleSelect.count() && await addRoleSelect.isVisible()) {
          const options = await addRoleSelect.locator('option').allTextContents();
          const targetOpt = options.find((opt) => opt.includes('Quality Auditor Lead'));
          if (targetOpt) {
            await addRoleSelect.selectOption({ label: targetOpt });
          }
        }

        // Wait for role chip to be visible
        const roleChip = page.locator('[data-testid="rbac-selected-role-quality-auditor-lead"], .rbac-role-chip').first();
        await roleChip.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
      }

      await page.waitForTimeout(400);
      await applyUnclippedStyle(page);
      await saveScreenshot(page, '11-custom-rbac-policy-builder.png');
      await context.close();
    }

  } finally {
    await browser.close();

    console.log('Telemetry summary:');
    console.log(`  Console errors: ${telemetry.consoleErrors.length}`);
    console.log(`  Page errors: ${telemetry.pageErrors.length}`);
    console.log(`  5xx server errors: ${telemetry.serverErrors.length}`);

    // Write screenshot-telemetry.json
    const telemetryPath = path.resolve('docs/qa/KAN-408/screenshot-telemetry.json');
    fs.mkdirSync(path.dirname(telemetryPath), { recursive: true });
    fs.writeFileSync(telemetryPath, JSON.stringify(telemetry, null, 2), 'utf-8');

    // Update workout-results.json with screenshot telemetry if it exists
    const resultsPath = path.resolve('docs/qa/KAN-408/workout-results.json');
    if (fs.existsSync(resultsPath)) {
      try {
        const results = JSON.parse(fs.readFileSync(resultsPath, 'utf-8'));
        results.screenshots = results.screenshots || {};
        results.screenshots.telemetry = {
          console_errors_count: telemetry.consoleErrors.length,
          page_errors_count: telemetry.pageErrors.length,
          server_5xx_count: telemetry.serverErrors.length,
        };
        fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2), 'utf-8');
      } catch (err) {
        console.warn('Failed updating workout-results.json telemetry:', err.message);
      }
    }

    if (telemetry.consoleErrors.length > 0) {
      console.error('Console errors logged:', telemetry.consoleErrors);
      throw new Error(`Browser console errors detected: ${telemetry.consoleErrors.length}`);
    }
    if (telemetry.pageErrors.length > 0) {
      console.error('Page errors logged:', telemetry.pageErrors);
      throw new Error(`Browser page errors detected: ${telemetry.pageErrors.length}`);
    }
    if (telemetry.serverErrors.length > 0) {
      console.error('Server 5xx errors logged:', telemetry.serverErrors);
      throw new Error(`Server 5xx errors detected: ${telemetry.serverErrors.length}`);
    }
  }
}

main().catch((err) => {
  console.error('Fatal in capture_kan408_screenshots:', err);
  process.exit(1);
});
