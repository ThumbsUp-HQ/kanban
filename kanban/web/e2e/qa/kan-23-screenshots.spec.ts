/**
 * Playwright Visual & QA Proof Verification for KAN-23.
 * Captures Desktop (1440x900) and Mobile (390x844) in Light and Dark themes.
 * Plain ASCII hyphens only. Zero em-dashes or en-dashes.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KAN-23/screenshots');

const samplePngBase64 =
  'iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAMElEQVR4nO3BMQEAAADCoPVPbQo/oAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOA1wS0AAWzW3uEAAAAASUVORK5CYII=';
const samplePngBuffer = Buffer.from(samplePngBase64, 'base64');

const mockUser = {
  principal_id: '11111111-1111-4111-8111-111111111111',
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Security Architect',
  username: 'architect',
  email: 'architect@thumbsup.org',
  timezone: 'UTC',
  avatar_url: null as string | null,
  roles: ['admin'],
  is_server_admin: true,
  capabilities: ['SERVER_ADMIN', 'WORKSPACE_ADMIN'],
};

const baseMocks = {
  'GET /api/v1/setup/status': { json: { initialized: true } },
  'GET /api/v1/auth/session': {
    json: {
      authenticated: true,
      principal_id: mockUser.id,
      workspace_id: '22222222-2222-2222-2222-222222222222',
      aal_level: 2,
      mfa_pending: false,
      csrf_token: 'test-csrf-token-kan23',
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
  'GET /api/v1/auth/mfa/status': {
    json: {
      totp_enabled: false,
      passkeys_count: 0,
      recovery_codes_remaining: 0,
    },
  },
  'GET /api/v1/auth/webauthn/credentials': { json: [] },
  'GET /api/v1/auth/identities': { json: { identities: [] } },
};

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KAN-23 Visual Verification & Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan23',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('Capture avatar crop modal at 1.0x and 2.5x zoom, preserved display name, and full-size lightbox', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    let userState = { ...mockUser };

    await mockApi(page, {
      ...baseMocks,
      'GET /api/v1/auth/me': () => ({ json: userState }),
      'PUT /api/v1/auth/me/avatar': () => {
        userState = {
          ...userState,
          avatar_url: `/api/v1/users/${userState.id}/avatar?v=abc123def456`,
        };
        return { json: userState };
      },
      'GET /api/v1/users/:id/avatar': {
        body: samplePngBuffer,
        headers: {
          'content-type': 'image/png',
          'content-security-policy': "default-src 'none'; sandbox",
          'x-content-type-options': 'nosniff',
          'cross-origin-resource-policy': 'same-origin',
          etag: '"abc123def456"',
        },
      },
    });

    await page.goto('/settings/profile');
    await expect(page.locator('[data-testid="personal-settings-page"]')).toBeVisible();

    // 1. Enter an unsaved display name draft
    const displayNameInput = page.locator('[data-testid="display-name-input"]');
    await displayNameInput.fill('Security Architect (Draft Edits)');
    expect(await displayNameInput.inputValue()).toBe('Security Architect (Draft Edits)');

    // 2. Select image file to open AvatarCropModal
    await page.locator('[data-testid="avatar-file-input"]').setInputFiles({
      name: 'avatar-test.png',
      mimeType: 'image/png',
      buffer: samplePngBuffer,
    });

    const cropModal = page.locator('[data-testid="avatar-crop-modal"]');
    await expect(cropModal).toBeVisible();

    // Verify 1.0x zoom
    await expect(page.locator('[data-testid="avatar-crop-zoom-value"]')).toHaveText('1.0x');

    // Screenshot 1: Avatar Crop Modal at 1.0x (Light & Dark)
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-avatar-crop-1.0x-light-${projectName}.png`),
      fullPage: true,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-avatar-crop-1.0x-dark-${projectName}.png`),
      fullPage: true,
    });

    // 3. Adjust Zoom Slider to 2.5x
    const zoomSlider = page.locator('[data-testid="avatar-crop-zoom-slider"]');
    await zoomSlider.fill('2.5');
    await expect(page.locator('[data-testid="avatar-crop-zoom-value"]')).toHaveText('2.5x');

    // Screenshot 2: Avatar Crop Modal at 2.5x (Light & Dark)
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-avatar-crop-2.5x-light-${projectName}.png`),
      fullPage: true,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-avatar-crop-2.5x-dark-${projectName}.png`),
      fullPage: true,
    });

    // 4. Save Picture
    const saveBtn = page.locator('[data-testid="avatar-crop-save-btn"]');
    await saveBtn.click();
    await expect(cropModal).toBeHidden();

    // Verify Display Name draft was preserved without reload
    expect(await displayNameInput.inputValue()).toBe('Security Architect (Draft Edits)');

    // Screenshot 3: Post-save Display Name preserved without reload (Light & Dark)
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-display-name-preserved-light-${projectName}.png`),
      fullPage: true,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-display-name-preserved-dark-${projectName}.png`),
      fullPage: true,
    });

    // 5. Click Avatar Preview to open Full-Size Lightbox Modal
    const avatarPreviewBtn = page.locator('[data-testid="avatar-preview"]');
    await expect(avatarPreviewBtn).toBeVisible();
    await avatarPreviewBtn.click();

    const lightboxModal = page.locator('[data-testid="avatar-lightbox-modal"]');
    await expect(lightboxModal).toBeVisible();

    // Screenshot 4: Full-Size Avatar Lightbox (Light & Dark)
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-avatar-lightbox-light-${projectName}.png`),
      fullPage: true,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `kan-23-avatar-lightbox-dark-${projectName}.png`),
      fullPage: true,
    });
  });
});
