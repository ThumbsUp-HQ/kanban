/**
 * Playwright Visual & QA Proof Verification for KAN-26.
 * Captures Desktop (1440x900) and Mobile (390x844) in Light and Dark themes.
 * Plain ASCII hyphens only. Zero em-dashes or en-dashes.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KAN-26/screenshots');

const mockUser = {
  principal_id: '11111111-1111-4111-8111-111111111111',
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Security Architect',
  username: 'architect',
  email: 'architect@thumbsup.org',
  timezone: 'UTC',
  avatar_url: null,
  roles: ['admin'],
  is_server_admin: true,
  capabilities: ['SERVER_ADMIN', 'WORKSPACE_ADMIN'],
};

const mockIdentities = [
  {
    id: 'ident-oidc-001',
    provider_kind: 'oidc',
    card_slug: 'google-workspace',
    card_display_name: 'Google Workspace OIDC',
    subject_email_at_link: 'security@thumbsup.org',
    immutable_subject_id: 'sub_oidc_1029384756',
    created_at: '2026-11-19T08:00:00Z',
    last_login_at: '2026-11-19T11:30:00Z',
  },
  {
    id: 'ident-github-002',
    provider_kind: 'oauth2',
    card_slug: 'github-corp',
    card_display_name: 'GitHub Enterprise',
    subject_email_at_link: 'architect@github.corp',
    immutable_subject_id: 'gh_usr_998877',
    created_at: '2026-11-18T14:15:00Z',
    last_login_at: null,
  },
];

const baseMocks = {
  'GET /api/v1/setup/status': { json: { initialized: true } },
  'GET /api/v1/auth/session': {
    json: {
      authenticated: true,
      principal_id: mockUser.id,
      workspace_id: '22222222-2222-2222-2222-222222222222',
      aal_level: 2,
      mfa_pending: false,
      csrf_token: 'test-csrf-token-kan26',
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
  'GET /api/v1/notifications': { json: { items: [] } },
  'GET /api/v1/users/me': { json: mockUser },
  'GET /api/v1/auth/me': { json: mockUser },
  'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
};

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KAN-26 Visual Verification & Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan26',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('Capture /settings/profile rendering provider_kind oidc without error', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, {
      ...baseMocks,
      'GET /api/v1/auth/mfa/status': {
        json: {
          totp_enabled: true,
          passkeys_count: 1,
          recovery_codes_remaining: 8,
        },
      },
      'GET /api/v1/auth/webauthn/credentials': {
        json: [
          {
            id: 'pk-yubikey-01',
            nickname: 'YubiKey 5C NFC',
            created_at: '2026-11-15T10:00:00Z',
            last_used_at: '2026-11-19T09:00:00Z',
            aaguid: 'cb69481e-8ff7-4039-93ec-0a2729a1e67d',
          },
        ],
      },
      'GET /api/v1/auth/identities': {
        json: {
          identities: mockIdentities,
        },
      },
    });

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();
    await expect(page.locator('[data-testid="identities-table"]')).toBeVisible();

    // Verify provider_kind rendered in uppercase without crash
    await expect(page.locator('text=(OIDC)')).toBeVisible();
    await expect(page.locator('text=(OAUTH2)')).toBeVisible();

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-26-settings-profile-identities-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-26-settings-profile-identities-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('Capture AppErrorModal contrast and ThumbsUp-HQ/kanban report link', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, {
      ...baseMocks,
      'GET /api/v1/auth/mfa/status': { json: { totp_enabled: false, passkeys_count: 0, recovery_codes_remaining: 0 } },
      'GET /api/v1/auth/webauthn/credentials': { json: [] },
      'GET /api/v1/auth/identities': { json: { identities: [] } },
    });

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();

    // Trigger simulated error to open AppErrorModal
    await page.evaluate(() => {
      window.dispatchEvent(
        new ErrorEvent('error', {
          error: new Error('Simulated Fatal Application Error: External Service Unreachable at runtime'),
          message: 'Simulated Fatal Application Error: External Service Unreachable at runtime',
        }),
      );
    });

    const errorModal = page.locator('[data-testid="app-error-modal"]');
    await expect(errorModal).toBeVisible();

    // Verify GitHub report link points to ThumbsUp-HQ/kanban
    const reportLink = page.locator('[data-testid="error-report-link"]');
    await expect(reportLink).toBeVisible();
    const href = await reportLink.getAttribute('href');
    expect(href).toContain('https://github.com/ThumbsUp-HQ/kanban/issues/new');

    // Verify Copy Traceback button is present
    const copyBtn = page.locator('[data-testid="error-copy-btn"]');
    await expect(copyBtn).toBeVisible();

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-26-app-error-modal-light-${projectName}.png`),
      fullPage: true,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-26-app-error-modal-dark-${projectName}.png`),
      fullPage: true,
    });
  });

  test('Capture Topbar circular avatar and bell under Ctrl+A selection proving zero square bleed', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, {
      ...baseMocks,
      'GET /api/v1/auth/mfa/status': { json: { totp_enabled: false, passkeys_count: 0, recovery_codes_remaining: 0 } },
      'GET /api/v1/auth/webauthn/credentials': { json: [] },
      'GET /api/v1/auth/identities': { json: { identities: [] } },
    });

    await page.goto('/settings/profile');
    await expect(page.locator('.kb-topbar')).toBeVisible();

    // Select entire page body to simulate Ctrl+A range selection
    await page.evaluate(() => {
      window.getSelection()?.selectAllChildren(document.body);
    });
    await page.waitForTimeout(100);

    // Light Theme
    await applyTheme(page, 'light');
    await page.evaluate(() => {
      window.getSelection()?.selectAllChildren(document.body);
    });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-26-topbar-selection-light-${projectName}.png`),
      fullPage: false,
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.evaluate(() => {
      window.getSelection()?.selectAllChildren(document.body);
    });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-26-topbar-selection-dark-${projectName}.png`),
      fullPage: false,
    });
  });
});
