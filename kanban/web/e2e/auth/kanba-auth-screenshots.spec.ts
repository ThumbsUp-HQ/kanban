/**
 * Playwright Visual & Accessibility Verification for KANBA-230 & KANBA-207.
 * Captures Light, Dark, Desktop (1440x900), Tablet (1024x768), and Mobile (390x844)
 * screenshots across Login, Setup Wizard Steps 1-3, and Personal Settings Profile.
 * Plain ASCII hyphens only.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR_230 = resolve(REPO_ROOT, 'docs/qa/KANBA-230/screenshots');
const SCREENSHOT_DIR_207 = resolve(REPO_ROOT, 'docs/qa/KANBA-207/screenshots');

const VALID_SETUP_TOKEN = 'kb_setup_' + 'A'.repeat(43);

const mockUser = {
  principal_id: '11111111-1111-4111-8111-111111111111',
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Admin User',
  username: 'admin',
  email: 'admin@example.com',
  timezone: 'UTC',
  avatar_url: null,
  roles: ['admin'],
  is_server_admin: true,
  capabilities: ['SERVER_ADMIN', 'WORKSPACE_ADMIN'],
};

const mockIdentities = [
  {
    id: 'ident-001',
    provider_type: 'oidc',
    card_slug: 'okta-sso',
    subject_id: 'usr_okta_987654',
    email: 'admin@example.com',
    display_name: 'Admin (Okta)',
    created_at: '2026-11-10T14:30:00Z',
    last_used_at: '2026-11-18T09:00:00Z',
  },
  {
    id: 'ident-002',
    provider_type: 'ldap',
    card_slug: 'corp-ad',
    subject_id: 'cn=admin,ou=users,dc=corp,dc=internal',
    email: 'admin@corp.internal',
    display_name: 'admin',
    created_at: '2026-11-12T10:15:00Z',
    last_used_at: null,
  },
];

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-230 Visual Verification', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-230',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('Capture Login Page screenshots', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name; // 'desktop', 'tablet', or 'mobile'

    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: false,
          principal_id: null,
          workspace_id: null,
          session_id: null,
          aal_level: 0,
          mfa_pending: false,
          csrf_token: 'test-csrf-token-230',
        },
      },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Light screenshot
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR_230, `kanba-230-login-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark screenshot
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR_230, `kanba-230-login-dark-${projectName}.png`),
      fullPage: true,
    });

    // On desktop, also capture actionable non-enumerating error copy with correlation ID
    if (projectName === 'desktop') {
      await mockApi(page, {
        'POST /api/v1/auth/local/login': {
          status: 500,
          json: {
            code: 'INTERNAL_ERROR',
            title: 'Internal Server Error',
            detail: 'Database unreachable',
            request_id: 'req_auth_err_correlate_01',
          },
        },
      });

      // Expand disclosure
      const trigger = page.locator('button:has-text("Sign in with Local Admin + Passkey / TOTP")');
      await trigger.click();
      await page.fill('#local-admin-username', 'admin@example.com');
      await page.fill('#local-admin-password', 'wrong-pass');
      await page.click('button[type="submit"]:has-text("Sign in as Local Admin")');

      await expect(page.locator('.auth-alert')).toBeVisible();

      // Light error correlation
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_230, 'kanba-230-login-error-correlation-light-desktop.png'),
        fullPage: true,
      });

      // Dark error correlation
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_230, 'kanba-230-login-error-correlation-dark-desktop.png'),
        fullPage: true,
      });
    }
  });
});

test.describe('KANBA-207 Visual Verification', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-207',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('Capture Setup Claim Wizard Step 1', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;

    await mockApi(page, {
      'GET /api/v1/setup/status': { json: { initialized: false } },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: false,
          mfa_pending: false,
          csrf_token: 'test-csrf-token-207',
        },
      },
    });

    await page.goto(`/setup?token=${VALID_SETUP_TOKEN}`);
    await expect(page.locator('[data-testid="setup-claim-page"]')).toBeVisible();

    // Verify token stripped from URL
    await expect(page).not.toHaveURL(/token=/);

    // Verify workspace and project fields visible
    await expect(page.locator('#setup-workspace-name')).toBeVisible();
    await expect(page.locator('#setup-workspace-slug')).toBeVisible();
    await expect(page.locator('#setup-project-name')).toBeVisible();
    await expect(page.locator('#setup-project-key')).toBeVisible();

    // Light screenshot
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR_207, `kanba-207-setup-step1-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark screenshot
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR_207, `kanba-207-setup-step1-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('Capture Setup Claim Wizard Steps 2 & 3', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;

    await mockApi(page, {
      'GET /api/v1/setup/status': { json: { initialized: false } },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: false,
          mfa_pending: false,
          csrf_token: 'test-csrf-token-207',
        },
      },
      'POST /api/v1/setup/claim': {
        json: {
          status: 'enrollment_required',
          enrollment_id: 'enr-setup-claim-01',
        },
      },
      'POST /api/v1/auth/mfa/totp/enroll': {
        json: {
          secret_base32: 'JBSWY3DPEHPK3PXP',
          otpauth_uri: 'otpauth://totp/%F0%9F%91%8Dkanban:admin@example.com?secret=JBSWY3DPEHPK3PXP&issuer=%F0%9F%91%8Dkanban',
        },
      },
      'POST /api/v1/auth/mfa/totp/confirm': {
        json: {
          status: 'enrolled',
          recovery_codes: ['AAAA-1111', 'BBBB-2222', 'CCCC-3333', 'DDDD-4444'],
        },
      },
    });

    await page.goto(`/setup?token=${VALID_SETUP_TOKEN}`);
    await page.fill('#setup-display-name', 'Admin User');
    await page.fill('#setup-username', 'admin');
    await page.fill('#setup-email', 'admin@example.com');
    await page.fill('#setup-password', 'CorrectHorseBatteryStaple123!');
    await page.fill('#setup-confirm-password', 'CorrectHorseBatteryStaple123!');
    await page.click('button[type="submit"]');

    // Wait for Step 2
    await expect(page.locator('text=Mandatory Two-Factor Authentication Setup')).toBeVisible();

    if (projectName === 'desktop' || projectName === 'mobile') {
      // Step 2 Light
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_207, `kanba-207-setup-step2-totp-light-${projectName}.png`),
        fullPage: true,
      });

      // Step 2 Dark
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_207, `kanba-207-setup-step2-totp-dark-${projectName}.png`),
        fullPage: true,
      });
    }

    if (projectName === 'desktop') {
      // Advance to Step 3
      await page.fill('#setup-totp-verify', '123456');
      await page.click('button:has-text("Verify & Continue")');

      // Wait for Step 3
      await expect(page.locator('text=Emergency Recovery Codes')).toBeVisible();

      // Step 3 Light
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-setup-step3-recovery-light-desktop.png'),
        fullPage: true,
      });

      // Step 3 Dark
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-setup-step3-recovery-dark-desktop.png'),
        fullPage: true,
      });
    }
  });

  test('Capture Personal Settings Profile Screenshots', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;

    await mockApi(page, {
      'GET /api/v1/setup/status': { json: { initialized: true } },
      'GET /api/v1/auth/session': {
        json: {
          authenticated: true,
          principal_id: mockUser.id,
          workspace_id: '22222222-2222-2222-2222-222222222222',
          aal_level: 2,
          mfa_pending: false,
          csrf_token: 'test-csrf-token-207',
          remember_me: true,
        },
      },
      'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
      'GET /api/v1/workspaces': {
        json: [{ id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' }],
      },
      'GET /api/v1/workspaces/current': {
        json: { id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' },
      },
      'GET /api/v1/projects': {
        json: [{ id: '33333333-3333-3333-3333-333333333333', key: 'KAN', name: 'kanban' }],
      },
      'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
      'GET /api/v1/projects/KAN/views': { json: [] },
      'GET /api/v1/projects/KAN/issues': { json: [] },
      'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
      'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
      'GET /api/v1/projects/KAN/states': { json: { items: [] } },
      'GET /api/v1/projects/KAN/priorities': { json: { items: [] } },
      'GET /api/v1/projects/KAN/labels': { json: { items: [] } },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/users/me': { json: loadFixture('me-adam') },
      'GET /api/v1/auth/me': { json: mockUser },
      'GET /api/v1/auth/mfa/status': {
        json: {
          totp_enabled: false,
          passkeys_count: 0,
          recovery_codes_remaining: 0,
        },
      },
      'GET /api/v1/auth/webauthn/credentials': { json: [] },
      'GET /api/v1/auth/identities': {
        json: {
          identities: mockIdentities,
        },
      },
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
    });

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();

    // Verify 2FA hint and disabled regenerate button
    await expect(page.locator('[data-testid="regenerate-hint"]')).toBeVisible();
    await expect(page.locator('[data-testid="regenerate-recovery-codes-btn"]')).toBeDisabled();

    // Verify Connected Accounts table
    await expect(page.locator('[data-testid="identities-table"]')).toBeVisible();

    if (projectName === 'desktop') {
      const mfaSection = page.locator('section[aria-labelledby="section-mfa-title"]');
      await mfaSection.scrollIntoViewIfNeeded();

      // 2FA section light
      await applyTheme(page, 'light');
      await mfaSection.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-settings-profile-2fa-light-desktop.png'),
      });

      // 2FA section dark
      await applyTheme(page, 'dark');
      await mfaSection.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-settings-profile-2fa-dark-desktop.png'),
      });

      const identSection = page.locator('section[aria-labelledby="section-identities-title"]');
      await identSection.scrollIntoViewIfNeeded();

      // Connected Accounts section light
      await applyTheme(page, 'light');
      await identSection.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-settings-profile-identities-light-desktop.png'),
      });

      // Connected Accounts section dark
      await applyTheme(page, 'dark');
      await identSection.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-settings-profile-identities-dark-desktop.png'),
      });
    }

    if (projectName === 'mobile') {
      // Mobile light
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-settings-profile-light-mobile.png'),
        fullPage: true,
      });

      // Mobile dark
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR_207, 'kanba-207-settings-profile-dark-mobile.png'),
        fullPage: true,
      });
    }
  });
});
