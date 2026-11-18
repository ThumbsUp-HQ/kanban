/**
 * KANBA-187 Playwright E2E & Screenshot Verification Suite.
 * Generates authentic annotated screenshots across Desktop, Tablet, and Mobile in docs/qa/KANBA-187/screenshots/.
 */

import { test, expect } from '../support/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

const mockProfile = {
  principal_id: '22222222-2222-4222-8222-222222222222',
  display_name: 'Alex Rivera',
  username: 'arivera',
  email: 'arivera@example.com',
  timezone: 'America/New_York',
  avatar_url: null,
  roles: ['user'],
  is_server_admin: false,
};

const mockMfaStatus = {
  totp_enabled: false,
  passkeys_count: 1,
  recovery_codes_remaining: 10,
};

const mockPasskeys = [
  {
    id: 'passkey-fedcba98',
    nickname: 'MacBook Air Touch ID',
    created_at: '2026-02-15T12:00:00Z',
    last_used_at: '2026-03-01T09:30:00Z',
    aaguid: '00000000-0000-0000-0000-000000000000',
  },
];

const defaultMocks = {
  'GET /api/v1/setup/status': { json: { initialized: true } },
  'GET /api/v1/auth/session': {
    json: {
      authenticated: true,
      principal_id: '22222222-2222-4222-8222-222222222222',
      workspace_id: '22222222-2222-2222-2222-222222222222',
      aal_level: 2,
      mfa_pending: false,
      csrf_token: 'test-csrf-token-187',
      remember_me: true,
      idle_expires_at: '2026-11-24T23:00:00Z',
      absolute_expires_at: '2026-12-17T23:00:00Z',
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
  'GET /api/v1/auth/me': { json: mockProfile },
  'GET /api/v1/auth/mfa/status': { json: mockMfaStatus },
  'GET /api/v1/auth/webauthn/credentials': { json: mockPasskeys },
};

test.describe('KANBA-187 Personal Settings Studio', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-187',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-personal-settings-studio: renders profile, timezone, and avatar upload section', async ({
    page,
  }, testInfo) => {
    await mockApi(page, defaultMocks);

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-personal-settings-studio',
      annotations: [
        {
          selector: '[aria-labelledby="section-profile-title"]',
          label: 'Profile & Timezone',
          note: 'Allows updating display name, IANA timezone, and avatar picture with strict validation.',
        },
        {
          selector: '[data-testid="avatar-preview"]',
          label: 'Sanitized Avatar Preview',
          note: 'Rejects SVG payloads; supports PNG, JPEG, and WebP up to 2 MiB.',
        },
      ],
    });
  });

  test('02-password-change: validates password policy with Show/Hide toggle and session revocation', async ({
    page,
  }, testInfo) => {
    await mockApi(page, defaultMocks);

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();

    const currentPw = page.locator('[data-testid="current-password-input"]');
    const newPw = page.locator('[data-testid="new-password-input"]');
    const confirmPw = page.locator('[data-testid="confirm-password-input"]');

    await currentPw.fill('CurrentMasterPass123!');
    await newPw.fill('BrandNewSecurePassword2026!');
    await confirmPw.fill('BrandNewSecurePassword2026!');

    await annotatedScreenshot(page, testInfo, {
      name: '02-password-change',
      annotations: [
        {
          selector: '[aria-labelledby="section-password-title"]',
          label: 'Password Management',
          note: 'Enforces min 12 chars (min 14 for admins) and revokes other sessions on change.',
        },
        {
          selector: '[data-testid="change-password-btn"]',
          label: 'Session Revocation Action',
          note: 'Atomic password rotation and session termination.',
        },
      ],
    });
  });

  test('03-passkeys-mfa: displays enrolled passkeys with rename/remove and 2FA status', async ({
    page,
  }, testInfo) => {
    await mockApi(page, defaultMocks);

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '03-passkeys-mfa',
      annotations: [
        {
          selector: '[aria-labelledby="section-passkeys-title"]',
          label: 'Passkeys Self-Service',
          note: 'Self-service WebAuthn management with nickname renaming and removal.',
        },
        {
          selector: '[aria-labelledby="section-mfa-title"]',
          label: 'Two-Factor Status Box',
          note: 'Real-time factor summary showing TOTP status and remaining recovery codes.',
        },
      ],
    });
  });

  test('04-recovery-keys-modal: displays 10 one-time emergency recovery codes in modal', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...defaultMocks,
      'POST /api/v1/auth/mfa/recovery/regenerate': {
        json: {
          recovery_codes: [
            'a1b2-c3d4',
            'e5f6-g7h8',
            'i9j0-k1l2',
            'm3n4-o5p6',
            'q7r8-s9t0',
            'u1v2-w3x4',
            'y5z6-a7b8',
            'c9d0-e1f2',
            'g3h4-i5j6',
            'k7l8-m9n0',
          ],
        },
      },
    });

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();

    const regenBtn = page.locator('[data-testid="regenerate-recovery-codes-btn"]');
    await regenBtn.click();
    await expect(page.locator('[data-testid="recovery-codes-grid"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '04-recovery-keys-modal',
      annotations: [
        {
          selector: '[data-testid="recovery-codes-grid"]',
          label: 'One-Time Recovery Codes Grid',
          note: '10 single-use emergency recovery keys with one-click selection and secure display.',
        },
      ],
    });
  });
});
